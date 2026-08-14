"""통합 러너 — load → signal → validity → OOS → QD → backtest → outputs+manifest.

CLI(cli.py)의 evaluate/oos/qd/backtest/validity 서브커맨드가 여기로 연결된다.

결정론: 같은 config+input+seed로 재실행하면 metric parquet 내용이 동일하다.
timestamp는 manifest에만 기록한다.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import Config
from .data.signal_context import SignalContext
from .data.qlib_provider import FormulaEvalError
from .inputs.loaders import load_result, load_weights
from .inputs.trajectory import load_trajectory
from .validity.evaluator import ValidityGate, ValidityReport
from .oos.evaluator import OOSEvaluator
from .qd.descriptors import QDDescriptorEvaluator, CORE_COLUMNS
from .qd.projection import QDProjection, descriptor_diagnostics
from .qd.grid import QDGrid, nn_distances, hq_filter, rarefaction_coverage
from .qd.diversity import de_legacy, de_common_valid
from .qd.trajectory import unique_candidates, search_budget, generation_metrics
from .qd.pfs import PFSEvaluator
from .backtest.simple import SimpleBacktestEvaluator
from .outputs.writer import OutputWriter
from .manifest import build_manifest, save_manifest

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class EvaluationRun:
    """단일 miner result에 대한 전체 평가."""

    def __init__(self, cfg: Config, input_path: str,
                 method: Optional[str] = None, seed_id: Optional[str] = None,
                 weights_path: Optional[str] = None,
                 trajectory_path: Optional[str] = None,
                 out_root: Optional[str] = None):
        self.cfg = cfg
        self.result = load_result(input_path, method, seed_id)
        self.method = str(self.result["method"].iloc[0])
        self.seed_id = str(self.result["seed"].iloc[0])
        self.formulas: List[str] = self.result["formula"].tolist()
        self.unique_formulas: List[str] = list(dict.fromkeys(self.formulas))
        self.weights = (load_weights(weights_path, len(self.formulas))
                        if weights_path else [1.0 / len(self.formulas)] * len(self.formulas))
        self.weights_source = "input" if weights_path else "equal_default"
        self.trajectory = load_trajectory(trajectory_path) if trajectory_path else None
        root = out_root or cfg.get("output.root") or os.path.join(_ASB_ROOT, "out")
        self.writer = OutputWriter(root)
        self.ctx = SignalContext(cfg)
        self.gate = ValidityGate(cfg)
        self._sign_cache: Dict[str, Tuple[float, int, bool]] = {}

    # ------------------------------------------------------------ train sign
    def train_sign(self, formula: str) -> Tuple[float, int, bool]:
        """(signed_train_IC, train_sign, restored?) — 입력에 있으면 사용,
        없으면 train split 재평가로 복원 (B5)."""
        if formula in self._sign_cache:
            return self._sign_cache[formula]
        row = self.result[self.result["formula"] == formula].iloc[0]
        if "signed_train_IC" in row and pd.notna(row.get("signed_train_IC")):
            sic = float(row["signed_train_IC"])
            out = (sic, 1 if sic >= 0 else -1, False)
        else:
            sic = self.ctx.signed_ic_on_train(formula)   # zero_ic → FormulaEvalError
            out = (sic, 1 if sic >= 0 else -1, True)
        self._sign_cache[formula] = out
        return out

    # ------------------------------------------------------------ validity
    def run_validity(self, split: str = "test") -> Tuple[pd.DataFrame, Dict[str, ValidityReport]]:
        reports: Dict[str, ValidityReport] = {}
        rows = []
        for f in self.unique_formulas:
            try:
                values, _ = self.ctx.evaluate(f, split)
                rep = self.gate.assess(f, values, self.ctx.split[split].universe_mask)
                if rep.hard_valid:
                    try:
                        self.train_sign(f)                 # zero_ic_observations 검사 겸용
                    except FormulaEvalError as e:
                        if e.reason == "hard_invalid:zero_ic_observations":
                            rep = ValidityGate.mark_zero_ic(rep)
                        else:
                            rep = self.gate.report_eval_failure(f, e.reason)
            except FormulaEvalError as e:
                rep = self.gate.report_eval_failure(f, e.reason)
            reports[f] = rep
            row = rep.to_row()
            row.update({"method": self.method, "seed": self.seed_id, "split": split,
                        "signal_engine": self.ctx.engine_used(f)})
            rows.append(row)
        return pd.DataFrame(rows), reports

    # ------------------------------------------------------------ OOS
    def run_oos(self, reports: Dict[str, ValidityReport], split: str = "test"):
        ev = OOSEvaluator(self.ctx, self.cfg)
        rows, dailies = [], []
        for f in self.unique_formulas:
            rep = reports[f]
            if not rep.passes_gate:
                rows.append({"formula": f, "method": self.method, "seed": self.seed_id,
                             "split": split, "valid": False,
                             "invalid_reason": rep.invalid_reason, "kind": "individual"})
                continue
            sic, sign, restored = self.train_sign(f)
            res = ev.evaluate_factor(f, sign, split)
            res.row.update({"method": self.method, "seed": self.seed_id,
                            "signed_train_IC": sic, "train_sign_restored": restored,
                            "valid": True, "invalid_reason": None,
                            "signal_engine": self.ctx.engine_used(f)})
            rows.append(res.row)
            dailies.append(res.daily)
        factor_df = pd.DataFrame(rows)

        pool_rows = []
        gated = [f for f in self.formulas if reports[f].passes_gate]
        gated_w = [w for f, w in zip(self.formulas, self.weights)
                   if reports[f].passes_gate]
        if len(gated) >= 1:
            res = ev.evaluate_pool(gated, gated_w, split,
                                   pool_id=f"{self.method}:{self.seed_id}")
            res.row.update({"method": self.method, "seed": self.seed_id,
                            "weights_source": self.weights_source,
                            "n_factors_dropped_by_gate": len(self.formulas) - len(gated)})
            pool_rows.append(res.row)
            dailies.append(res.daily)
        pool_df = pd.DataFrame(pool_rows)
        daily_df = pd.concat(dailies, ignore_index=True) if dailies else pd.DataFrame()
        return factor_df, pool_df, daily_df

    # ------------------------------------------------------------ QD
    def run_qd(self, reports: Dict[str, ValidityReport]):
        qd_ev = QDDescriptorEvaluator(self.ctx, self.cfg)
        dedup = self.cfg.get("qd.dedup", "exact")
        formulas = self.unique_formulas if dedup == "exact" else self.formulas
        gated = [f for f in formulas if reports[f].passes_gate]

        # BD_valid / BD_test (+drift)
        rows = []
        for f in gated:
            sic, sign, _ = self.train_sign(f)
            rec: Dict = {"formula": f, "method": self.method, "seed": self.seed_id,
                         "kind": "individual", "scope": "final_pool",
                         "signed_train_IC": sic, "train_sign": sign}
            for split in ("valid", "test"):
                d = qd_ev.compute(f, sign, split)
                prefix = "valid_" if split == "valid" else ""
                for k, v in d.items():
                    if k in ("formula", "split", "train_sign"):
                        continue
                    rec[f"{prefix}{k}"] = v
            rows.append(rec)
        desc = pd.DataFrame(rows)

        cols = list(self.cfg.get("qd.descriptor_set.columns", CORE_COLUMNS))
        proj_dir = self.cfg.get("qd.projection.load_from")
        if desc.empty:
            return desc, pd.DataFrame(), None

        # descriptor drift (raw)
        for c in cols:
            vc = f"valid_{c}"
            if vc in desc.columns and c in desc.columns:
                desc[f"drift_{c}"] = desc[c] - desc[vc]

        # projection: 기본 = 이 run의 **valid** descriptor로 fit (G3),
        # load_from 지정 시 기존 좌표계 재사용
        valid_cols = [f"valid_{c}" for c in cols]
        if proj_dir:
            proj = QDProjection.load(proj_dir)
        else:
            fit_df = desc[valid_cols].rename(columns=dict(zip(valid_cols, cols)))
            proj = QDProjection(cols, int(self.cfg.get("qd.projection.n_components", 2)))
            proj.fit_reference(fit_df, {
                "reference_split": self.cfg.get("qd.projection.reference_split", "valid"),
                "reference_runs": [f"{self.method}:{self.seed_id}"]})
            proj.save(self.writer.manifest_path("qd_projection"))

        pcs_valid, _ = proj.transform(
            desc[valid_cols].rename(columns=dict(zip(valid_cols, cols))))
        pcs_test, ok_test = proj.transform(desc[cols])
        desc["valid_PCA1"], desc["valid_PCA2"] = pcs_valid[:, 0], pcs_valid[:, 1]
        desc["PCA1"], desc["PCA2"] = pcs_test[:, 0], pcs_test[:, 1]
        desc["projected"] = ok_test
        desc["descriptor_drift_raw"] = np.sqrt(
            sum((desc.get(f"drift_{c}", pd.Series(np.nan, index=desc.index)) ** 2
                 for c in cols)))
        desc["descriptor_drift_pca"] = np.sqrt(
            (desc["PCA1"] - desc["valid_PCA1"]) ** 2 +
            (desc["PCA2"] - desc["valid_PCA2"]) ** 2)

        # diagnostics 저장
        diag = descriptor_diagnostics(desc, [c for c in cols if c in desc.columns])
        for name, df in diag.items():
            self.writer.write_table(df.reset_index(),
                                    f"descriptor_diagnostics_{name}", "manifests")

        # ---- pool metrics (final_pool scope) ----
        grid_cfg = self.cfg.get("qd.grid", {})
        bounds = grid_cfg.get("bounds")
        pcs = desc[["PCA1", "PCA2"]].to_numpy(dtype=float)
        if bounds:
            grid = QDGrid(bounds, grid_cfg.get("resolution", [20, 20]))
        else:
            ref_pcs = desc[["valid_PCA1", "valid_PCA2"]].to_numpy(dtype=float)
            grid = QDGrid.from_reference(ref_pcs, grid_cfg.get("resolution", [20, 20]))
        pool: Dict = {"method": self.method, "seed": self.seed_id,
                      "scope": "final_pool",
                      "n_factors": len(self.formulas),
                      "n_unique_factors": len(self.unique_formulas),
                      "n_gated_factors": len(gated),
                      "grid_bounds": str(grid.bounds)}
        pool.update(grid.pool_metrics(pcs))
        pool.update({f"pca2d_{k}": v for k, v in nn_distances(pcs).items()})
        std_pts, _ = proj.standardized(desc[cols])
        pool.update({f"rawstd_{k}": v for k, v in nn_distances(std_pts).items()})

        q_metric = self.cfg.get("qd.quality.metric", "IC")
        q_col = {"IC": "IC_1d"}.get(q_metric, q_metric)
        q_th = self.cfg.get("qd.quality.threshold")
        if q_col in desc.columns:
            hq = hq_filter(desc[q_col].to_numpy(dtype=float), q_th)
            pool["hq_threshold"] = q_th
            pool["hq_coverage"] = (grid.pool_metrics(pcs[hq])["coverage"]
                                   if hq.any() else 0.0)
        rare_n = self.cfg.get("qd.rarefaction.n")
        if rare_n:
            pool.update(rarefaction_coverage(
                grid, pcs, int(rare_n),
                int(self.cfg.get("qd.rarefaction.repeats", 100)),
                int(self.cfg.get("qd.rarefaction.seed", 0))))

        # ---- DE (test split, gate 통과 factor) ----
        from .data.signal_context import daily_zscore
        vals_list, valid_list, zf_list = [], [], []
        for f in gated:
            v, m = self.ctx.evaluate(f, "test")
            vals_list.append(v)
            valid_list.append(m)
            zf_list.append(daily_zscore(v, m))
        if len(zf_list) >= 2:
            pool["AlphaEval_DE_legacy"] = de_legacy(zf_list)
            pool.update(de_common_valid(
                vals_list, valid_list, self.ctx.split["test"].universe_mask,
                n_factors_dropped=len(self.unique_formulas) - len(gated)))
        pool_df = pd.DataFrame([pool])

        # ---- trajectory (Search-QD) ----
        if self.trajectory is not None:
            uniq = unique_candidates(self.trajectory)
            info_rows = []
            for _, r in uniq.iterrows():
                f = r["formula"]
                known = f in desc["formula"].values
                if known:
                    d0 = desc[desc["formula"] == f].iloc[0]
                    info_rows.append({"formula": f, "pc1": d0["PCA1"], "pc2": d0["PCA2"],
                                      "valid": True, "quality": d0.get("IC_1d", np.nan)})
                else:
                    info_rows.append({"formula": f, "pc1": np.nan, "pc2": np.nan,
                                      "valid": False, "quality": np.nan})
            info = pd.DataFrame(info_rows)
            gm = generation_metrics(self.trajectory, info, grid,
                                    quality_col="quality", hq_threshold=q_th)
            gm["method"], gm["seed"], gm["scope"] = self.method, self.seed_id, "generation"
            budget = search_budget(self.trajectory)
            for k, v in budget.items():
                pool_df[f"budget_{k}"] = v
            self.writer.write_table(gm, "qd_generation_metrics")

        return desc, pool_df, proj

    # ------------------------------------------------------------ backtest
    def run_backtest(self, reports: Dict[str, ValidityReport], split: str = "test"):
        bt = SimpleBacktestEvaluator(self.ctx, self.cfg)
        rows, dailies = [], []
        for f in self.unique_formulas:
            rep = reports[f]
            if not rep.passes_gate:
                rows.append({"formula": f, "method": self.method, "seed": self.seed_id,
                             "split": split, "valid": False,
                             "invalid_reason": rep.invalid_reason, "kind": "individual"})
                continue
            _, sign, _ = self.train_sign(f)
            m, d = bt.evaluate_factor(f, sign, split)
            m.update({"method": self.method, "seed": self.seed_id,
                      "valid": True, "invalid_reason": None})
            rows.append(m)
            dailies.append(d)
        factor_df = pd.DataFrame(rows)

        gated = [f for f in self.formulas if reports[f].passes_gate]
        gated_w = [w for f, w in zip(self.formulas, self.weights)
                   if reports[f].passes_gate]
        pool_rows = []
        if gated:
            m, d = bt.evaluate_pool(gated, gated_w, split,
                                    pool_id=f"{self.method}:{self.seed_id}")
            m.update({"method": self.method, "seed": self.seed_id,
                      "weights_source": self.weights_source})
            pool_rows.append(m)
            dailies.append(d)
        pool_df = pd.DataFrame(pool_rows)
        daily_df = pd.concat(dailies, ignore_index=True) if dailies else pd.DataFrame()
        return factor_df, pool_df, daily_df

    # ------------------------------------------------------------ 전체
    def run(self, commands=("validity", "oos", "qd", "backtest")) -> Dict[str, str]:
        outputs: Dict[str, str] = {}
        validity_df, reports = self.run_validity()
        outputs["validity"] = self.writer.write_table(
            validity_df, "validity_factor_metrics")

        if "oos" in commands:
            f_df, p_df, daily = self.run_oos(reports)
            outputs["oos_factor"] = self.writer.write_table(f_df, "oos_factor_metrics")
            if not p_df.empty:
                outputs["oos_pool"] = self.writer.write_table(p_df, "oos_pool_metrics")
            if self.cfg.get("oos.save_daily_series", True) and not daily.empty:
                self.writer.write_table(daily, "oos_daily", "daily")

        if "qd" in commands:
            desc, qd_pool, _proj = self.run_qd(reports)
            if not desc.empty:
                if self.cfg.get("pfs.enabled", False):
                    pfs_ev = PFSEvaluator(self.ctx, self.cfg)
                    pfs_rows = []
                    for f in desc["formula"]:
                        pfs_rows.append(pfs_ev.evaluate_factor(f, "test"))
                    desc = desc.merge(
                        pd.DataFrame(pfs_rows).drop(columns=["split"]),
                        on="formula", how="left")
                outputs["qd_desc"] = self.writer.write_table(
                    desc, "qd_factor_descriptors")
            if not qd_pool.empty:
                outputs["qd_pool"] = self.writer.write_table(qd_pool, "qd_pool_metrics")

        if "backtest" in commands:
            f_df, p_df, daily = self.run_backtest(reports)
            outputs["bt_factor"] = self.writer.write_table(
                f_df, "backtest_factor_metrics")
            if not p_df.empty:
                outputs["bt_pool"] = self.writer.write_table(p_df, "backtest_pool_metrics")
            if not daily.empty:
                self.writer.write_table(daily, "backtest_daily", "daily")

        manifest = build_manifest(self.cfg, self.ctx, {
            "method": self.method, "seed": self.seed_id,
            "formula_count": len(self.formulas),
            "unique_formula_count": len(self.unique_formulas),
            "weights_source": self.weights_source,
            "has_trajectory": self.trajectory is not None,
            "outputs": outputs,
            "parquet_fallbacks": self.writer.fallbacks,
        })
        outputs["manifest"] = save_manifest(
            manifest, self.writer.manifest_path(
                f"run_{self.method}_{self.seed_id}.json"))
        return outputs


def run_command(args) -> int:
    cfg = Config.load(args.config)
    run = EvaluationRun(cfg, args.input, method=args.method, seed_id=args.seed_id,
                        weights_path=args.weights, trajectory_path=args.trajectory,
                        out_root=args.out)
    cmd_map = {"evaluate": ("validity", "oos", "qd", "backtest"),
               "oos": ("validity", "oos"),
               "qd": ("validity", "qd"),
               "backtest": ("validity", "backtest"),
               "validity": ("validity",)}
    outputs = run.run(cmd_map[args.command])
    for k, v in outputs.items():
        print(f"[alphasearchbench] {k}: {v}")
    return 0

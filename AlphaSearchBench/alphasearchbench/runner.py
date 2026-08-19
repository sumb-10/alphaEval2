"""통합 러너 — load → signal → validity → OOS → QD → backtest → outputs+manifest.

CLI(cli.py)의 evaluate/oos/qd/backtest/validity 서브커맨드가 여기로 연결된다.

결정론: 같은 config+input+seed로 재실행하면 metric parquet 내용이 동일하다.
timestamp는 manifest에만 기록한다.
"""
from __future__ import annotations

import math
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
                 out_root: Optional[str] = None,
                 ctx=None):
        self.cfg = cfg
        self.result = load_result(input_path, method, seed_id)
        if len(self.result):
            self.method = str(self.result["method"].iloc[0])
            self.seed_id = str(self.result["seed"].iloc[0])
            self.formulas: List[str] = self.result["formula"].tolist()
        else:
            # 빈 pool(예: 후보 전량 미수락 run) — CLI 인자로 정체성을 유지하고
            # trajectory(search-QD/allcand)만 평가한다. 조용한 유실 금지 원칙과
            # 일관: pool 지표는 생략되되 run 자체는 평가 대상으로 남는다.
            self.method = str(method or "unknown")
            self.seed_id = str(seed_id or "0")
            self.formulas = []
        self.unique_formulas: List[str] = list(dict.fromkeys(self.formulas))
        self.weights = (load_weights(weights_path, len(self.formulas))
                        if weights_path else
                        ([1.0 / len(self.formulas)] * len(self.formulas)
                         if self.formulas else []))
        self.weights_source = "input" if weights_path else "equal_default"
        # [ASB-P1.0 §3] combiner 정책: raw_equal(기본, label-free) |
        # train_signed_equal(1-bit 지도 보정 — w_i = sign(train IC_i)/n).
        # 방향은 train 창 IC 부호에서만 유도(§3.2), |IC| <= τ_sign 이거나 판정
        # 불가면 '방향 없음'으로 결합에서 제외하고 사유·개수를 기록한다.
        self.combiner = str(cfg.get("backtest.combiner", "raw_equal"))
        if self.combiner not in ("raw_equal", "train_signed_equal"):
            raise ValueError(f"backtest.combiner must be raw_equal|train_signed_equal,"
                             f" got {self.combiner!r}")
        self.sign_threshold = float(cfg.get("backtest.sign_threshold", 0.0))
        self._no_direction: List[str] = []
        self.trajectory = load_trajectory(trajectory_path) if trajectory_path else None
        root = out_root or cfg.get("output.root") or os.path.join(_ASB_ROOT, "out")
        self.writer = OutputWriter(root)
        # ctx 주입: 같은 cfg(=같은 split·universe)로 여러 pool을 평가할 때 패널·신호
        # 캐시를 공유해 재적재를 피한다 (scripts/protocol_sweep.py). 기본은 자체 생성.
        self.ctx = ctx if ctx is not None else SignalContext(cfg)
        self.gate = ValidityGate(cfg)
        self._sign_cache: Dict[str, Tuple[float, int, bool]] = {}

    # ------------------------------------------------------------ pool 가중
    def pool_weights(self, gated: List[str]) -> Tuple[List[str], List[float], str]:
        """combiner 정책에 따른 (결합 대상, 가중, weights_source 라벨).

        raw_equal: 입력 가중(기본 1/n) 그대로 — label-free.
        train_signed_equal: w_i = sign(train IC_i)/n' (방향 있는 factor만,
          n' = 방향 있는 factor 수). 제외분은 no_direction으로 기록.
        """
        base = {f: w for f, w in zip(self.formulas, self.weights)}
        if self.combiner == "raw_equal":
            return gated, [base[f] for f in gated], self.weights_source
        kept: List[str] = []
        signs: List[float] = []
        self._no_direction = []
        for f in gated:
            sic, sign, _ = self.train_sign(f)
            ok = (sic is not None and not (isinstance(sic, float) and math.isnan(sic))
                  and abs(float(sic)) > self.sign_threshold)
            if ok:
                kept.append(f)
                signs.append(float(sign))
            else:
                self._no_direction.append(f)
        if not kept:
            return [], [], "train_signed_equal"
        w = [sg / len(kept) for sg in signs]
        return kept, w, "train_signed_equal"

    # ------------------------------------------------------------ train sign
    def train_sign(self, formula: str) -> Tuple[float, int, bool]:
        """(signed_train_IC, train_sign, restored?) — 입력에 있으면 사용,
        없으면 train split 재평가로 복원 (B5)."""
        if formula in self._sign_cache:
            return self._sign_cache[formula]
        match = self.result[self.result["formula"] == formula]
        # trajectory 전용 후보(all_candidates 덤프)는 입력 pool에 없음 → 복원 경로
        row = match.iloc[0] if len(match) else None
        if row is not None and "signed_train_IC" in row and pd.notna(row.get("signed_train_IC")):
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
        pool_f, pool_w, wsrc = self.pool_weights(gated)
        if len(pool_f) >= 1:
            res = ev.evaluate_pool(pool_f, pool_w, split,
                                   pool_id=f"{self.method}:{self.seed_id}")
            res.row.update({"method": self.method, "seed": self.seed_id,
                            "weights_source": wsrc,
                            "combiner": self.combiner,
                            "n_no_direction": len(self._no_direction),
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
        allc_enabled = (self.cfg.get("qd.descriptor_scope", "final_pool")
                        == "all_candidates" and self.trajectory is not None)
        # 전원 gate 탈락 pool이어도 all_candidates 덤프·projection·search-QD는
        # 수행한다 (예: off seed의 루프홀 pool — 탐색 동학 분석에 필수).
        if desc.empty and not allc_enabled:
            return desc, pd.DataFrame(), None

        # descriptor drift (raw)
        for c in cols:
            vc = f"valid_{c}"
            if vc in desc.columns and c in desc.columns:
                desc[f"drift_{c}"] = desc[c] - desc[vc]

        # ---- all_candidates descriptor 행 생성 (opt-in; PCA는 아래에서) ----
        # 시도된 unique 후보 전부의 descriptor 행(scope="all_candidates").
        # 평가 불가 후보는 skip_reason stub (조용한 유실 금지).
        allc = pd.DataFrame()
        if (self.cfg.get("qd.descriptor_scope", "final_pool") == "all_candidates"
                and self.trajectory is not None):
            pool_set = set(desc["formula"]) if not desc.empty else set()
            arows = []
            for f in unique_candidates(self.trajectory)["formula"]:
                if f in pool_set:
                    continue
                rec2: Dict = {"formula": f, "method": self.method,
                              "seed": self.seed_id, "kind": "individual",
                              "scope": "all_candidates"}
                try:
                    sic2, sign2, _ = self.train_sign(f)
                    rec2.update({"signed_train_IC": sic2, "train_sign": sign2})
                    for split in ("valid", "test"):
                        d2 = qd_ev.compute(f, sign2, split)
                        prefix = "valid_" if split == "valid" else ""
                        for k, v in d2.items():
                            if k in ("formula", "split", "train_sign"):
                                continue
                            rec2[f"{prefix}{k}"] = v
                except FormulaEvalError as e:
                    rec2["skip_reason"] = e.reason
                arows.append(rec2)
            allc = pd.DataFrame(arows)
            if not allc.empty:
                for c in cols:
                    vc = f"valid_{c}"
                    if vc in allc.columns and c in allc.columns:
                        allc[f"drift_{c}"] = allc[c] - allc[vc]

        # projection: 기본 = 이 run의 final-pool **valid** descriptor로 fit (G3).
        # 표본 부족(finite<3) 시 all_candidates의 valid descriptor를 fit 기반에
        # 합류(여전히 valid-only — test 봉인 유지, projection_reference에 기록).
        # 그래도 부족하면 projection·grid를 생략하고 사유를 남긴다.
        valid_cols = [f"valid_{c}" for c in cols]
        proj = None
        proj_note = "final_pool"
        if proj_dir:
            proj = QDProjection.load(proj_dir)
            proj_note = f"loaded:{proj_dir}"
        else:
            fit_df = (desc[valid_cols].rename(columns=dict(zip(valid_cols, cols)))
                      if not desc.empty else pd.DataFrame(columns=cols))
            if (fit_df.dropna().shape[0] < 3 and not allc.empty
                    and all(vc in allc.columns for vc in valid_cols)):
                fit_df = pd.concat(
                    [fit_df,
                     allc[valid_cols].rename(columns=dict(zip(valid_cols, cols)))],
                    ignore_index=True)
                proj_note = "final_pool+all_candidates_fallback"
            try:
                proj = QDProjection(cols, int(self.cfg.get("qd.projection.n_components", 2)))
                proj.fit_reference(fit_df, {
                    "reference_split": self.cfg.get("qd.projection.reference_split", "valid"),
                    "reference_runs": [f"{self.method}:{self.seed_id}"],
                    "reference_basis": proj_note})
                proj.save(self.writer.manifest_path("qd_projection"))
            except ValueError as e:
                proj = None
                proj_note = f"skipped:{e}"

        desc["descriptor_drift_raw"] = np.sqrt(
            sum((desc.get(f"drift_{c}", pd.Series(np.nan, index=desc.index)) ** 2
                 for c in cols)))
        if proj is not None and not desc.empty:
            pcs_valid, _ = proj.transform(
                desc[valid_cols].rename(columns=dict(zip(valid_cols, cols))))
            pcs_test, ok_test = proj.transform(desc[cols])
            desc["valid_PCA1"], desc["valid_PCA2"] = pcs_valid[:, 0], pcs_valid[:, 1]
            desc["PCA1"], desc["PCA2"] = pcs_test[:, 0], pcs_test[:, 1]
            desc["projected"] = ok_test
            desc["descriptor_drift_pca"] = np.sqrt(
                (desc["PCA1"] - desc["valid_PCA1"]) ** 2 +
                (desc["PCA2"] - desc["valid_PCA2"]) ** 2)
        if proj is not None:
            if not allc.empty:
                if all(vc in allc.columns for vc in valid_cols):
                    a_pv, _ = proj.transform(
                        allc[valid_cols].rename(columns=dict(zip(valid_cols, cols))))
                    allc["valid_PCA1"], allc["valid_PCA2"] = a_pv[:, 0], a_pv[:, 1]
                if all(c in allc.columns for c in cols):
                    a_pt, a_ok = proj.transform(allc[cols])
                    allc["PCA1"], allc["PCA2"] = a_pt[:, 0], a_pt[:, 1]
                    allc["projected"] = a_ok

        # diagnostics 저장
        diag = (descriptor_diagnostics(desc, [c for c in cols if c in desc.columns])
                if not desc.empty else {})
        for name, df in diag.items():
            self.writer.write_table(df.reset_index(),
                                    f"descriptor_diagnostics_{name}", "manifests")

        # ---- pool metrics (final_pool scope) ----
        pool: Dict = {"method": self.method, "seed": self.seed_id,
                      "scope": "final_pool",
                      "n_factors": len(self.formulas),
                      "n_unique_factors": len(self.unique_formulas),
                      "n_gated_factors": len(gated),
                      "projection_reference": proj_note}
        grid = None
        q_th = self.cfg.get("qd.quality.threshold")
        if proj is not None:
            grid_cfg = self.cfg.get("qd.grid", {})
            bounds = grid_cfg.get("bounds")
            if not desc.empty:
                pcs = desc[["PCA1", "PCA2"]].to_numpy(dtype=float)
                ref_pcs = desc[["valid_PCA1", "valid_PCA2"]].to_numpy(dtype=float)
            else:
                pcs = np.empty((0, 2), dtype=float)
                ref_pcs = (allc[["valid_PCA1", "valid_PCA2"]].to_numpy(dtype=float)
                           if "valid_PCA1" in allc.columns else np.empty((0, 2)))
                pool["grid_reference"] = "all_candidates_valid_pca"
            if bounds:
                grid = QDGrid(bounds, grid_cfg.get("resolution", [20, 20]))
            elif np.isfinite(ref_pcs).all(axis=1).sum() >= 2:
                grid = QDGrid.from_reference(ref_pcs, grid_cfg.get("resolution", [20, 20]))
            if grid is not None:
                pool["grid_bounds"] = str(grid.bounds)
                pool.update(grid.pool_metrics(pcs))
                pool.update({f"pca2d_{k}": v for k, v in nn_distances(pcs).items()})
            if not desc.empty:
                std_pts, _ = proj.standardized(desc[cols])
                pool.update({f"rawstd_{k}": v
                             for k, v in nn_distances(std_pts).items()})

            q_metric = self.cfg.get("qd.quality.metric", "IC")
            q_col = {"IC": "IC_1d"}.get(q_metric, q_metric)
            if q_col in desc.columns and grid is not None:
                hq = hq_filter(desc[q_col].to_numpy(dtype=float), q_th)
                pool["hq_threshold"] = q_th
                pool["hq_coverage"] = (grid.pool_metrics(pcs[hq])["coverage"]
                                       if hq.any() else 0.0)
            rare_n = self.cfg.get("qd.rarefaction.n")
            if rare_n and grid is not None:
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

        if not allc.empty:
            pool_df["n_all_candidates_rows"] = len(allc)
            pool_df["n_all_candidates_skipped"] = int(
                allc["skip_reason"].notna().sum()) if "skip_reason" in allc else 0

        # ---- trajectory (Search-QD) — grid 필요 (projection 생략 시 budget만) ----
        if self.trajectory is not None and grid is None:
            budget = search_budget(self.trajectory)
            for k, v in budget.items():
                pool_df[f"budget_{k}"] = v
        if self.trajectory is not None and grid is not None:
            uniq = unique_candidates(self.trajectory)
            lookup = pd.concat([desc, allc], ignore_index=True) if not allc.empty else desc
            info_rows = []
            for _, r in uniq.iterrows():
                f = r["formula"]
                known = f in lookup["formula"].values
                if known:
                    d0 = lookup[lookup["formula"] == f].iloc[0]
                    # search-QD 좌표·quality는 valid split 기준 (test 봉인 —
                    # 탐색 동학 분석에 test 행동을 쓰지 않는다)
                    pc1 = d0.get("valid_PCA1", np.nan)
                    pc2 = d0.get("valid_PCA2", np.nan)
                    info_rows.append({"formula": f,
                                      "pc1": pc1 if pd.notna(pc1) else d0.get("PCA1", np.nan),
                                      "pc2": pc2 if pd.notna(pc2) else d0.get("PCA2", np.nan),
                                      "valid": bool(pd.isna(d0.get("skip_reason", np.nan))),
                                      "quality": d0.get("valid_IC_1d", d0.get("IC_1d", np.nan))})
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

        if not allc.empty:
            desc = pd.concat([desc, allc], ignore_index=True)
        return desc, pool_df, proj

    # ------------------------------------------------------------ backtest
    def _make_backtest_evaluator(self):
        """backtest.mode 배선. 이전에는 mode가 manifest에만 기록되고 실행은 항상
        simple이어서 `mode: qlib` config가 조용한 no-op였다 (WS-A에서 수정).
        qlib 모드는 long-only top-k(TopkDropout) — naked short 미체결이라
        long-short 연구 포트폴리오는 simple 전용 (qlib_native.py Phase 8 audit).
        """
        mode = str(self.cfg.get("backtest.mode", "simple"))
        if mode == "simple":
            return SimpleBacktestEvaluator(self.ctx, self.cfg)
        if mode == "qlib":
            from .backtest.qlib_native import QlibBacktestEvaluator
            return QlibBacktestEvaluator(self.ctx, self.cfg)
        raise ValueError(f"backtest.mode must be simple|qlib, got {mode!r}")

    def run_backtest(self, reports: Dict[str, ValidityReport], split: str = "test"):
        bt = self._make_backtest_evaluator()
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
        pool_f, pool_w, wsrc = self.pool_weights(gated)
        pool_rows = []
        if pool_f:
            m, d = bt.evaluate_pool(pool_f, pool_w, split,
                                    pool_id=f"{self.method}:{self.seed_id}")
            m.update({"method": self.method, "seed": self.seed_id,
                      "weights_source": wsrc, "combiner": self.combiner,
                      "n_no_direction": len(self._no_direction)})
            pool_rows.append(m)
            dailies.append(d)
        pool_df = pd.DataFrame(pool_rows)
        daily_df = pd.concat(dailies, ignore_index=True) if dailies else pd.DataFrame()
        return factor_df, pool_df, daily_df

    # ------------------------------------------------------------ 전체
    def run(self, commands=("validity", "oos", "qd", "backtest")) -> Dict[str, str]:
        outputs: Dict[str, str] = {}
        validity_df, reports = self.run_validity()
        if not validity_df.empty:
            outputs["validity"] = self.writer.write_table(
                validity_df, "validity_factor_metrics")

        if "oos" in commands:
            f_df, p_df, daily = self.run_oos(reports)
            if not f_df.empty:
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
            if not f_df.empty:
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

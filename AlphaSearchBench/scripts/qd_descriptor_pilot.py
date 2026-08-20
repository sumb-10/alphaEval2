"""[QD 설계] Primary Behavioral Core v3 — tilt 후보 3종 대조 + permutation null.

개정 3차 (GPT 피드백 2026-08-20 반영): 목적은 정한 정의의 "확인"이 아니라
descriptor 정의 자체의 freeze 근거 생산 —
  * B  = activation_breadth (기존 구현 재사용)
  * T  = common-universe turnover: re-z-score(primary) + L1-only(민감도)
         + T_union(진단)
  * characteristic tilt 후보 3종 동시 산출 (liq: Amihud ILLIQ20,
    vol: VOL_W, W ∈ {20,60,120}):
      A^W  = E_t|Σ w̃·c|        (weighted tilt — intersection re-z-score,
                                  L1-only 변형 민감도 병기)
      A^Q  = E_t|q̄_top20 − q̄_bot20|  (quantile characteristic spread —
                                  backtest quantile 0.2와 정합)
      A^ρ  = E_t|Spearman(S, q)| (rank alignment benchmark)
  * B–tilt 기계적 결합 검증: characteristic을 일별 permutation한 null
    (K=3, 고정 seed, liq20·vol20)에서 세 후보의 A^null을 산출 —
    Corr(B, A^null)이 큰 후보는 primary 탈락 근거.
  * ILLIQ min_periods ∈ {10, 20} 이중 산출 (사용자 게이트 재료).
  * 일별 최소 공통 종목 수 exclusion rate를 {2,10,30}에서 기록.

전부 label-free·sign-invariant — raw signal만 사용(train_sign 불요).
컨텍스트: expB ASB eval manifest (csi800, valid 2017-2019). test split은
2020으로 축소(동결 test 2024-01-21+ 비적재). 모든 계산은 valid split만.
기존 모듈 무수정(분석 전용 스크립트).
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr

_HERE = os.path.dirname(os.path.abspath(__file__))
_ASB_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ASB_ROOT)

MANIFEST = os.path.join(
    _ASB_ROOT, "AlphaAgent_asb/out/alphaagent_asb_expB_csi800/asb_eval/"
    "manifests/run_alphaagent_asb_42.json")
OUT_DIR = os.path.join(_ASB_ROOT, "out/qd_design_pilot")
OUT_PARQUET = os.path.join(OUT_DIR, "qd_descriptor_pilot_v3_valid.parquet")
SPLIT = "valid"
MIN_CROSS_N = 30            # 일별 최소 공통 종목 수 (primary filter)
EXCL_THRESHOLDS = (2, 10, 30)
VOL_WINDOWS = (20, 60, 120)
ILLIQ_W = 20
QUANTILE = 0.2              # backtest long_short_quantile과 동일
N_NULL = 3
NULL_SEED = 20260820
NULL_CHARS = ("L20", "V20")  # null 검증 대상 (결합 채널은 char-불변)
SAVE_EVERY = 25


def build_ctx():
    from alphasearchbench.config import Config
    with open(os.path.join(_ASB_ROOT, "configs/default.yaml")) as fh:
        base = yaml.safe_load(fh) or {}
    m = json.load(open(MANIFEST))
    # benchmark 제외: manifest는 resolved ticker 문자열이라 default의 map을 파괴함
    for k in ("dataset", "market", "splits", "label", "qd"):
        if k not in m:
            continue
        if isinstance(m[k], dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **m[k]}
        else:
            base[k] = m[k]
    base["splits"]["test"] = ["2020-01-01", "2020-12-31"]   # 동결 test 비적재
    cfg = Config(base)
    from alphasearchbench.data.signal_context import SignalContext
    return SignalContext(cfg)


def collect_formulas():
    """final_pool unique만 — LLM 먼저(부분 결과에도 포함되도록)."""
    llm, gp = [], []
    p = os.path.join(_ASB_ROOT, "AlphaAgent_asb/out/alphaagent_asb_expB_csi800/"
                     "asb_eval/metrics/qd_factor_descriptors.parquet")
    exp = pd.read_parquet(p)
    stored = exp.drop_duplicates("formula").set_index("formula")[
        ["valid_activation_breadth"]]
    for f in exp["formula"].dropna().unique():          # expB는 all_candidates 51
        llm.append((f, "LLM"))
    for p in sorted(glob.glob(os.path.join(
            _ASB_ROOT, "gplearn_asb/out/pilot_csi800_*/asb_eval/metrics/"
            "qd_factor_descriptors.parquet"))):
        d = pd.read_parquet(p)
        if "scope" in d.columns:
            d = d[d["scope"] == "final_pool"]
        for f in d["formula"].dropna().unique():
            gp.append((f, "GP"))
    df = pd.DataFrame(llm + gp, columns=["formula", "grp"]) \
           .drop_duplicates("formula").reset_index(drop=True)
    return df, stored


def pct_in_universe(char: np.ndarray, universe: np.ndarray) -> np.ndarray:
    """일별 PIT-universe cross-sectional percentile (0~1]. 비유니버스/결측 NaN."""
    a = np.where(universe & np.isfinite(char), char, np.nan)
    return pd.DataFrame(a).rank(axis=1, pct=True).to_numpy()


def permute_daily(q: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """일별로 finite 셀 값들만 종목 간 permutation (분포 보존, S와 독립)."""
    out = np.full_like(q, np.nan)
    for t in range(q.shape[0]):
        idx = np.flatnonzero(np.isfinite(q[t]))
        if len(idx):
            out[t, idx] = q[t, idx][rng.permutation(len(idx))]
    return out


def tilt_candidates(S, z_valid, valid, q_panel, min_n=MIN_CROSS_N,
                    with_diag=True):
    """한 characteristic q panel에 대한 후보 3종 (+진단).

    A^W(re-z-score primary / L1-only 민감도), A^Q(top/bot 20% q̄ 차),
    A^ρ(|Spearman|). 반환 dict: W, W_signed, W_l1, Q, Q_signed, rho,
    days_used, mass_covered, excl_lt{2,10,30}.
    """
    T = S.shape[0]
    cells = valid & np.isfinite(q_panel)
    n = cells.sum(axis=1)
    excl = {th: int((n < th).sum()) for th in EXCL_THRESHOLDS}
    Xw, Xw_l1, Xq, rho = [], [], [], []
    mass = []
    for t in range(T):
        if n[t] < min_n:
            continue
        J = cells[t]
        sj = S[t][J].astype(np.float64)
        qj = q_panel[t][J]
        mu, sd = sj.mean(), sj.std()
        if not np.isfinite(mu) or sd < 1e-8:
            continue
        cj = 2.0 * qj - 1.0
        # A^W — intersection re-z-score (Σz=0 보장)
        zj = (sj - mu) / sd
        w = zj / np.abs(zj).sum()
        Xw.append(float((w * cj).sum()))
        # A^W L1-only 민감도 — valid-기준 z를 J에서 재정규화만
        zo = z_valid[t][J]
        so = np.abs(zo).sum()
        if so > 0:
            Xw_l1.append(float((zo / so * cj).sum()))
        # A^Q — top/bottom 20% by signal, equal-weight q̄ 차
        k = max(1, int(QUANTILE * len(sj)))
        order = np.argsort(sj)
        Xq.append(float(qj[order[-k:]].mean() - qj[order[:k]].mean()))
        # A^ρ — |Spearman|
        r_ = spearmanr(sj, qj).correlation
        if np.isfinite(r_):
            rho.append(abs(float(r_)))
        if with_diag:
            s_all = np.abs(z_valid[t][valid[t]]).sum()
            if s_all > 0:
                mass.append(float(np.abs(z_valid[t][J]).sum() / s_all))
    def _agg(v, absolute=True):
        if not v:
            return float("nan")
        a = np.abs(v) if absolute else np.asarray(v, dtype=np.float64)
        return float(np.mean(a))
    out = {
        "W": _agg(Xw), "W_signed": _agg(Xw, absolute=False),
        "W_l1": _agg(Xw_l1), "Q": _agg(Xq),
        "Q_signed": _agg(Xq, absolute=False), "rho": _agg(rho),
        "days_used": len(Xw),
    }
    if with_diag:
        out["mass_covered"] = float(np.mean(mass)) if mass else float("nan")
        for th, cnt in excl.items():
            out[f"excl_lt{th}"] = cnt
    return out


def t_common(S, z_valid, valid, min_n=MIN_CROSS_N):
    """공통 유효셀 turnover — re-z-score(primary) + L1-only(민감도)."""
    v_rz, v_l1, used, skipped = [], [], 0, 0
    for t in range(1, S.shape[0]):
        c = valid[t] & valid[t - 1]
        if int(c.sum()) < min_n:
            skipped += 1
            continue
        a_raw, b_raw = S[t][c].astype(np.float64), S[t - 1][c].astype(np.float64)
        sa_, sb_ = a_raw.std(), b_raw.std()
        if sa_ < 1e-8 or sb_ < 1e-8:
            skipped += 1
            continue
        za = (a_raw - a_raw.mean()) / sa_
        zb = (b_raw - b_raw.mean()) / sb_
        wa, wb = za / np.abs(za).sum(), zb / np.abs(zb).sum()
        v_rz.append(0.5 * float(np.abs(wa - wb).sum()))
        # L1-only 변형 (valid-기준 z 재정규화)
        oa, ob = z_valid[t][c], z_valid[t - 1][c]
        sa2, sb2 = np.abs(oa).sum(), np.abs(ob).sum()
        if sa2 > 0 and sb2 > 0:
            v_l1.append(0.5 * float(np.abs(oa / sa2 - ob / sb2).sum()))
        used += 1
    return ((float(np.mean(v_rz)) if v_rz else float("nan")),
            (float(np.mean(v_l1)) if v_l1 else float("nan")), used, skipped)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    from alphasearchbench.data.signal_context import daily_zscore
    from alphasearchbench.qd.descriptors import (activation_breadth,
                                                 daily_liquidity_percentile,
                                                 liquidity_footprint,
                                                 signal_weight_turnover)
    ctx = build_ctx()
    sc = ctx.split[SPLIT]
    uni = sc.universe_mask
    s0, s1 = ctx.engine.row_range(*ctx.splits_cfg[SPLIT])

    # ---- characteristic q panels (full panel rolling → split slice) ----
    close = pd.DataFrame(ctx.engine.panels["$close"])
    amount = pd.DataFrame(ctx.engine.panels["$amount"])
    r = close / close.shift(1) - 1.0                     # 무채움 — 정지일 NaN
    illiq_raw = r.abs() / amount.where(amount > 0)       # amount<=0/결측 → NaN
    q_panels = {}
    for mp in (10, 20):
        ill = illiq_raw.rolling(ILLIQ_W, min_periods=mp).mean().to_numpy()[s0:s1]
        q_panels[f"L{mp}"] = 1.0 - pct_in_universe(ill, uni)   # 1=최고 유동성
    for W in VOL_WINDOWS:
        vw = r.rolling(W, min_periods=W).std().to_numpy()[s0:s1]
        q_panels[f"V{W}"] = pct_in_universe(vw, uni)           # 1=최고 변동성
    # permutation nulls (전 수식 공유 — S와 독립이면 충분)
    rng = np.random.default_rng(NULL_SEED)
    null_panels = {ch: [permute_daily(q_panels[ch], rng) for _ in range(N_NULL)]
                   for ch in NULL_CHARS}
    liq_pct_adv = daily_liquidity_percentile(ctx.adv(SPLIT), uni)  # FOOT 참고용
    cov_line = " ".join(f"{k}:{np.isfinite(v).mean():.3f}"
                        for k, v in q_panels.items())
    print(f"[ctx] valid rows {uni.shape[0]}, universe 평균 "
          f"{uni.sum(axis=1).mean():.0f}종목; q finite ratio {cov_line}",
          flush=True)

    forms, stored_b = collect_formulas()
    print(f"[formulas] {len(forms)} unique "
          f"({dict(forms['grp'].value_counts())})", flush=True)

    def descrs(S, valid, with_null=True):
        z = daily_zscore(S, valid)
        tc_rz, tc_l1, tp_used, tp_skip = t_common(S, z, valid)
        row = {
            "B": activation_breadth(z, valid),
            "T_common": tc_rz, "T_common_l1": tc_l1,
            "t_pairs_used": tp_used, "t_pairs_skipped": tp_skip,
            "T_union": signal_weight_turnover(z),
            "FOOT": liquidity_footprint(z, liq_pct_adv, valid),
            "coverage": float((valid.sum(axis=1)
                               / np.maximum(uni.sum(axis=1), 1)).mean()),
        }
        for ch, q in q_panels.items():
            res = tilt_candidates(S, z, valid, q)
            row.update({f"{ch}_{k}": v for k, v in res.items()})
        if with_null:
            for ch in NULL_CHARS:
                acc = {"W": [], "Q": [], "rho": []}
                for qn in null_panels[ch]:
                    rn = tilt_candidates(S, z, valid, qn, with_diag=False)
                    for k in acc:
                        acc[k].append(rn[k])
                for k, v in acc.items():
                    row[f"null_{ch}_{k}"] = float(np.nanmean(v))
        return row

    rows, n_signcheck = [], 0
    for i, (f, grp) in enumerate(forms.itertuples(index=False)):
        try:
            S, valid = ctx.evaluate(f, SPLIT)
        except Exception as e:            # noqa: BLE001 — 실패도 기록 대상
            rows.append({"formula": f, "grp": grp, "eval_error": str(e)[:120]})
            continue
        row = {"formula": f, "grp": grp}
        row.update(descrs(S, valid))
        if n_signcheck < 3 and np.isfinite(row["B"]):
            neg = descrs(-S, valid, with_null=False)
            inv = ["B", "T_common", "T_common_l1", "T_union", "FOOT"] + \
                  [f"{ch}_{k}" for ch in q_panels for k in ("W", "rho")]
            for k in inv:
                if not (np.isnan(row[k]) and np.isnan(neg[k])):
                    assert abs(row[k] - neg[k]) < 1e-10, \
                        f"sign-invariance 위반: {k} {f}"
            # Q는 signal tie의 top/bot 경계 배정이 ±S에서 다를 수 있음
            # (tie-breaking 아티팩트) — 위반이 아니라 경고로 기록
            for ch in q_panels:
                k = f"{ch}_Q"
                if not (np.isnan(row[k]) and np.isnan(neg[k])) \
                        and abs(row[k] - neg[k]) > 1e-8:
                    print(f"[warn] Q tie-asymmetry {k} {f}: "
                          f"Δ={abs(row[k] - neg[k]):.2e}", flush=True)
            for k in ("L20_W_signed", "V20_W_signed"):
                if not (np.isnan(row[k]) and np.isnan(neg[k])):
                    assert abs(row[k] + neg[k]) < 1e-10, \
                        f"signed 반전 위반: {k} {f}"
            # Q_signed 역시 tie-breaking 아티팩트 대상 — 경고로만
            k = "L20_Q_signed"
            if not (np.isnan(row[k]) and np.isnan(neg[k])) \
                    and abs(row[k] + neg[k]) > 1e-8:
                print(f"[warn] Q_signed tie-asymmetry {f}: "
                      f"Δ={abs(row[k] + neg[k]):.2e}", flush=True)
            row["sign_invariance_checked"] = True
            n_signcheck += 1
        rows.append(row)
        if (i + 1) % SAVE_EVERY == 0:
            pd.DataFrame(rows).to_parquet(OUT_PARQUET, index=False)
            print(f"  ... {i + 1}/{len(forms)} (부분 저장)", flush=True)

    df = pd.DataFrame(rows)
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"[saved] {OUT_PARQUET}")

    chk = df[df["grp"] == "LLM"].set_index("formula").join(stored_b, how="inner")
    both = chk[np.isfinite(chk["B"]) & np.isfinite(chk["valid_activation_breadth"])]
    if len(both):
        print(f"[integrity] expB B 재계산 vs 저장값: n={len(both)}, "
              f"max|Δ|={(both['B'] - both['valid_activation_breadth']).abs().max():.2e}")

    ok = df[np.isfinite(df["B"])] if "B" in df.columns else df.iloc[0:0]
    print(f"\n[n] usable {len(ok)} ({dict(ok['grp'].value_counts())})")

    print("\n===== [핵심] B–tilt null coupling (Spearman) =====")
    for ch in NULL_CHARS:
        line = {}
        for k in ("W", "Q", "rho"):
            line[f"Corr(B, null_{k})"] = round(
                ok["B"].corr(ok[f"null_{ch}_{k}"], method="spearman"), 2)
            line[f"Corr(B, real_{k})"] = round(
                ok["B"].corr(ok[f"{ch}_{k}"], method="spearman"), 2)
            line[f"null_mean_{k}"] = round(float(ok[f"null_{ch}_{k}"].mean()), 4)
            line[f"real_mean_{k}"] = round(float(ok[f"{ch}_{k}"].mean()), 4)
        print(ch, json.dumps(line, ensure_ascii=False))

    print("\n== per-group stats (후보별, L20/V20) ==")
    cand_cols = [f"{ch}_{k}" for ch in ("L20", "V20") for k in ("W", "Q", "rho")]
    print(ok.groupby("grp")[cand_cols].agg(["mean", "std", "min", "max"])
            .round(3).to_string())

    print("\n== A_L ↔ A_V 중복성 (후보별 Spearman) ==")
    for k in ("W", "Q", "rho"):
        v = ok[f"L20_{k}"].corr(ok[f"V20_{k}"], method="spearman")
        print(f"  {k}: {v:.2f}")

    print("\n== A_V window stability (Spearman) ==")
    for k in ("W", "Q"):
        sub = ok[[f"V{W}_{k}" for W in VOL_WINDOWS]]
        print(f"  후보 {k}:")
        print(sub.corr(method="spearman").round(3).to_string())

    print("\n== ILLIQ min_periods 10 vs 20 ==")
    for k in ("W", "Q", "rho"):
        v = ok[f"L10_{k}"].corr(ok[f"L20_{k}"], method="spearman")
        print(f"  {k}: Spearman {v:.3f}")

    print("\n== 4x4 core 시나리오 (Spearman) ==")
    for k in ("Q", "W"):
        cols = ["B", "T_common", f"L20_{k}", f"V20_{k}"]
        print(f"-- tilt 후보 = {k} --")
        print(ok[cols].corr(method="spearman").round(2).to_string())

    print("\n== turnover 변형 대조 (Spearman) ==")
    tcols = ["T_common", "T_common_l1", "T_union", "coverage", "B"]
    print(ok[tcols].corr(method="spearman").round(2).to_string())

    print("\n== exclusion 진단 (L20 기준, 총 731일) ==")
    for th in EXCL_THRESHOLDS:
        print(f"  n<{th}: 평균 {ok[f'L20_excl_lt{th}'].mean():.1f}일")
    print(f"  days_used 평균 {ok['L20_days_used'].mean():.0f}, "
          f"mass_covered 평균 {ok['L20_mass_covered'].mean():.3f}")
    n_err = df["eval_error"].notna().sum() if "eval_error" in df.columns else 0
    print(f"\n[failures] eval_error {n_err}건")


if __name__ == "__main__":
    main()

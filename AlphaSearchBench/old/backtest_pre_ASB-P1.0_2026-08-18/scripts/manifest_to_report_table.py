"""[보고서 자동화] manifest → 실험 보고서 3-A/3-B 세팅 표 생성.

보고 계획 규칙 ⑤: 3-A(마이닝 프레임워크 세팅)·3-B(AlphaSearchBench 평가 세팅)는
손으로 옮기지 않고 manifest에서 추출한다 — 보고서 수치와 실제 실행 설정이
어긋나는 사고를 구조적으로 막는다.

입력 manifest 두 종류:
  * 마이닝:  gplearn_asb/out/<run>/manifests/run_*.json         (gplearn_asb)
             AlphaAgent_asb/out/<run>/manifests/run_*.json      (AlphaAgent_asb)
  * 평가:    <run>/asb_eval/manifests/run_*.json                (AlphaSearchBench)
             out/protocol_sweep/<tag>/manifests/sweep_*.json    (프로토콜 스윕)

사용:
  python scripts/manifest_to_report_table.py --run gplearn_asb/out/pilot_csi800_fbfit_42
  python scripts/manifest_to_report_table.py --sweep out/protocol_sweep/ws_a_e3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from glob import glob
from typing import Any, Dict, Optional

_ASB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _abs(p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(_ASB_ROOT, p)


def _load_one(pattern: str) -> Optional[Dict[str, Any]]:
    files = sorted(glob(pattern))
    if not files:
        return None
    with open(files[-1]) as fh:
        return json.load(fh)


def _row(k: str, v: Any) -> str:
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False, default=str)
    return f"| {k} | `{v}` |"


def mining_table(man: Dict[str, Any]) -> str:
    """3-A. Alpha Mining Framework 세팅 (gplearn_asb / AlphaAgent_asb 자동 판별)."""
    is_gp = "gp_params" in man or "gplearn_asb_version" in man
    fw = "gplearn_asb" if is_gp else "alphaagent_asb"
    out = [f"### 3-A. Alpha Mining Framework 세팅 — `{fw}`", "",
           "| 항목 | 값 |", "|---|---|"]
    if is_gp:
        keys = ["gplearn_asb_version", "semantics_version", "run_id", "seed",
                "constraint_mode", "fitness_metric", "fitness_opts", "hof_mode",
                "static_gate", "worst_fitness", "thresholds", "market",
                "search_window", "label_horizon", "universe_hash",
                "close_fallback_signed_ic"]
        for k in keys:
            if k in man:
                out.append(_row(k, man[k]))
        for k, v in (man.get("gp_params") or {}).items():
            out.append(_row(f"gp.{k}", v))
        b = man.get("budget") or {}
        for k in ("total_evaluations", "unique_evaluations", "memo_hits",
                  "wall_clock_seconds"):
            if k in b:
                out.append(_row(f"budget.{k}", b[k]))
    else:
        keys = ["alphaagent_asb_version", "run_id", "seed", "compatibility_mode",
                "market", "search_window", "max_rounds", "seed_range",
                "constraint_mode", "thresholds", "universe_hash"]
        for k in keys:
            if k in man:
                out.append(_row(k, man[k]))
        for k, v in (man.get("llm") or {}).items():
            if "key" in str(k).lower():          # API 키류는 절대 출력하지 않음
                continue
            out.append(_row(f"llm.{k}", v))
        for k, v in (man.get("budget") or {}).items():
            out.append(_row(f"budget.{k}", v))
        if man.get("deviations"):
            out.append(_row("deviations", man["deviations"]))
    return "\n".join(out)


def eval_table(man: Dict[str, Any]) -> str:
    """3-B. AlphaSearchBench 평가 세팅."""
    out = ["### 3-B. AlphaSearchBench 평가 세팅", "", "| 항목 | 값 |", "|---|---|"]
    keys = ["alphasearchbench_version", "git_commit", "market", "benchmark",
            "splits", "label", "train_sign_rule", "execution", "validity",
            "qd", "pfs", "seed", "run", "created_at"]
    for k in keys:
        if k in man:
            out.append(_row(k, man[k]))
    return "\n".join(out)


def sweep_table(man: Dict[str, Any]) -> str:
    """프로토콜 스윕 manifest → arm별 평가 세팅 표."""
    out = ["### 3-B. AlphaSearchBench 평가 세팅 (프로토콜 arm별)", "",
           f"tag=`{man.get('tag')}` split=`{man.get('split')}` "
           f"pools={len(man.get('pools') or [])} "
           f"wall={man.get('wall_seconds', 0):.0f}s", "",
           "| arm | config | splits | backtest |", "|---|---|---|---|"]
    for a in man.get("arms", []):
        out.append(f"| {a.get('arm')} | `{os.path.basename(str(a.get('config')))}` | "
                   f"`{json.dumps(a.get('splits'), ensure_ascii=False)}` | "
                   f"`{json.dumps(a.get('backtest'), ensure_ascii=False)}` |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="마이닝 run 디렉토리 (asb_eval 있으면 3-B도 함께)")
    ap.add_argument("--sweep", help="프로토콜 스윕 디렉토리")
    args = ap.parse_args()
    if not (args.run or args.sweep):
        ap.error("--run 또는 --sweep 중 하나가 필요합니다")

    blocks = []
    if args.run:
        d = _abs(args.run)
        m = _load_one(os.path.join(d, "manifests", "run_*.json"))
        if m is None:
            print(f"[warn] 마이닝 manifest 없음: {d}", file=sys.stderr)
        else:
            blocks.append(mining_table(m))
        e = _load_one(os.path.join(d, "asb_eval", "manifests", "run_*.json"))
        if e is not None:
            blocks.append(eval_table(e))
    if args.sweep:
        s = _load_one(os.path.join(_abs(args.sweep), "manifests", "sweep_*.json"))
        if s is None:
            print(f"[warn] 스윕 manifest 없음: {args.sweep}", file=sys.stderr)
        else:
            blocks.append(sweep_table(s))
    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())

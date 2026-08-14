"""AlphaSearchBench CLI.

    python -m alphasearchbench evaluate --config configs/smoke.yaml --input result.csv
    python -m alphasearchbench oos      --config ... --input ...
    python -m alphasearchbench qd       --config ... --input ...
    python -m alphasearchbench backtest --config ... --input ...

Phase 0에서는 서브커맨드 뼈대와 --help만 제공하고, 각 파이프라인은
해당 Phase에서 연결된다.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alphasearchbench",
        description="AlphaSearchBench — OOS / QD / Backtest evaluation for alpha mining results",
    )
    p.add_argument("--version", action="version", version=f"alphasearchbench {__version__}")
    sub = p.add_subparsers(dest="command")

    def common(sp):
        sp.add_argument("--config", required=True, help="experiment yaml (default.yaml 위에 merge)")
        sp.add_argument("--input", required=True, help="miner result file (csv/pkl; DATA_CONTRACT.md 참조)")
        sp.add_argument("--method", default=None, help="method name override (기본: input 파일에서 추론)")
        sp.add_argument("--seed-id", default=None, help="run seed identifier (메타데이터)")
        sp.add_argument("--weights", default=None, help="pool weights file (json/csv, optional)")
        sp.add_argument("--trajectory", default=None, help="trajectory jsonl (optional)")
        sp.add_argument("--out", default=None, help="output root (기본: AlphaSearchBench/out)")

    common(sub.add_parser("evaluate", help="validity → OOS → QD → backtest 전체 실행"))
    common(sub.add_parser("oos", help="OOS evaluation만"))
    common(sub.add_parser("qd", help="QD evaluation만"))
    common(sub.add_parser("backtest", help="backtest evaluation만"))
    common(sub.add_parser("validity", help="validity gate만"))
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    # 파이프라인 연결은 Phase 9(통합)에서 완성된다. 각 Phase 개발 중에는
    # 해당 모듈의 API를 직접 사용한다.
    from .runner import run_command   # Phase 9에서 구현
    return run_command(args)


if __name__ == "__main__":
    sys.exit(main())

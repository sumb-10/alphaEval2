#!/usr/bin/env python3
"""production 패키지(alphasearchbench/)가 AlphaEval 내부 모듈을 import하지
않는지 검사한다.

규칙 (사용자 확정):
  * 검사 대상 = alphasearchbench/ (production package)
  * instrumentation/ 은 **optional integration adapter**로 명시적 예외
    (miner 코드와 통합하는 것이 존재 이유 — core의 필수 dependency 아님)
  * tests/의 reference import는 허용 (regression 비교용)
  * qlib.* 은 외부 dependency로 허용
"""
from __future__ import annotations

import os
import re
import sys

ASB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ASB, "alphasearchbench")

FORBIDDEN = re.compile(
    r"^\s*(from|import)\s+(backtest|scripts|Alphaagent|AlphaEvolve|AutoAlpha"
    r"|AlphaForge|AlphaQCM|alphagen|gplearn|my_qlib|tensor_eval|fast_eval"
    r"|ictester|modeltester)\b")


def main() -> int:
    violations = []
    for root, _dirs, files in os.walk(PKG):
        if os.path.basename(root) == "instrumentation":
            continue                       # 명시적 예외 (optional adapter)
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            with open(path) as f:
                for ln, line in enumerate(f, 1):
                    if FORBIDDEN.match(line):
                        violations.append(f"{os.path.relpath(path, ASB)}:{ln}: {line.strip()}")
    if violations:
        print("FAIL — AlphaEval 내부 import 발견:")
        for v in violations:
            print("  ", v)
        return 1
    print("OK — production 패키지에 AlphaEval 내부 import 없음 (instrumentation/ 제외)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

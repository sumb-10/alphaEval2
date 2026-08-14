#!/usr/bin/env python3
"""AlphaSearchBench 작업이 기존 AlphaEval tracked 파일을 수정하지 않았는지 검사.

방식 (사용자 확정): repo가 clean한지가 아니라, **Phase 0에 저장한 tracked-file
diff 목록(out/manifests/phase0_baseline_files.txt)과 비교**하여
AlphaSearchBench/ 밖에 **추가** 변경이 발생하지 않았음을 확인한다.
"""
from __future__ import annotations

import os
import subprocess
import sys

ASB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALPHAEVAL = os.path.dirname(ASB)
BASELINE = os.path.join(ASB, "out", "manifests", "phase0_baseline_files.txt")


def main() -> int:
    with open(BASELINE) as f:
        baseline = {ln.strip() for ln in f if ln.strip()}
    r = subprocess.run(["git", "diff", "--name-only"], cwd=ALPHAEVAL,
                       capture_output=True, text=True, timeout=30)
    current = {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}
    new_changes = {p for p in (current - baseline)
                   if not p.startswith("AlphaSearchBench/")}
    if new_changes:
        print("FAIL — Phase 0 기준선 이후 AlphaSearchBench/ 밖 tracked 파일 변경:")
        for p in sorted(new_changes):
            print("  ", p)
        return 1
    print(f"OK — 기준선({len(baseline)}건) 대비 AlphaSearchBench/ 밖 추가 변경 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())

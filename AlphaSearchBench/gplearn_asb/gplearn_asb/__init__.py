"""gplearn_asb — Validity-aware GP variant (worst-fitness penalty).

원본 gplearn(AlphaEval fork)의 search mechanics를 보존하면서, invalid
candidate가 높은 IC fitness로 선택되는 루프홀만 worst-fitness penalty로
통제하는 실험 variant. 원본 소스는 수정하지 않는다 (vendored 사본 사용).

constraint modes: "off" | "hard_penalty" | "strict_penalty"
"""
__version__ = "0.1.0"

METHOD_NAME = "gplearn_asb"
CONSTRAINT_MODES = ("off", "hard_penalty", "strict_penalty")
SEMANTICS_VERSION = "1"   # cache key 구성요소 — 평가 의미론 변경 시 올릴 것

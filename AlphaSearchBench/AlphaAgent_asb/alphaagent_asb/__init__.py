"""AlphaAgent_asb — 논문 기반 LLM 알파 마이닝(AlphaAgent)의 ASB 호환 이식.

원형: AlphaEval/Alphaagent (vendored_alphaagent/ 사본 참조).
feedback 지표(LLM이 보는 AnnRet/IC)는 vendored FactorBacktester 원형 그대로,
ASB 진단(signed IC/validity)은 gplearn_asb MiningEvaluator — 두 경로 분리.
"""
__version__ = "0.1.0"

METHOD_NAME = "alphaagent_asb"
COMPAT_MODES = ("parity", "safe")
CONSTRAINT_MODES = ("off", "hard_penalty", "strict_penalty")

TRAJECTORY_SEMANTICS = (
    "generation=round_id is an ASB compatibility field. AlphaAgent candidates "
    "belonging to different seed_idx values are independent refinement "
    "trajectories and do not form a reproducing population.")

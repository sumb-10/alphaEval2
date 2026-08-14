"""AlphaSearchBench — alpha search/mining 산출물의 공통 평가 프레임워크.

파이프라인: Formula Loader → SignalContext → Validity Gate → {OOS, QD, Backtest}
→ Standardized Results + Manifest.

원칙: AlphaEval 원본 무수정 · production 런타임의 AlphaEval 내부 import 금지 ·
silent fallback 금지 · train-only calibration · legacy/paper/research 네임스페이스 분리.
"""
__version__ = "0.1.0"

# vendored_gplearn — 출처와 수정 이력

- 출처: `AlphaEval/gplearn/` (fork of gplearn 0.4.2) — 2026-08-14 시점 사본.
- 7개 .py 파일은 **byte-identical verbatim 사본**이다 (md5 대조로 확인).
  원본 파일에 provenance 주석을 넣지 않은 이유: 동등성 회귀 테스트에서
  바이트 단위 비교를 가능하게 유지하기 위함.
- 수정 이력: **없음** (수정이 필요해지면 이 파일에 항목별로 기록할 것).
- import 의존성 주의: `_program.py`/`genetic.py`가 module-level로
  `import qlib`, `from backtest.ictester import ICBacktester`를 수행한다.
  → cli가 (1) 실제 qlib bootstrap, (2) `qlib.init` no-op 치환,
  (3) `backtest.backtester` sys.modules 사전 등록(원본 러너 패턴)을
  마친 뒤에만 이 패키지를 import해야 한다.

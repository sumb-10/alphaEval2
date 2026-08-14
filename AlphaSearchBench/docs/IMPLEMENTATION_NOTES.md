# IMPLEMENTATION_NOTES — 구현 중 결정·발견 사항

스펙(`../../docs/alphasearchbench.md`)과 충돌하지 않는 engineering decision과
구현 중 발견된 제약을 기록한다.

## 발견된 구조적 제약

1. **qlib native backtest는 long-only** — Phase 8 audit 실측:
   Exchange가 보유 없는 SELL을 조용히 미체결 처리(trade_val=0, 포지션
   미생성). 따라서 long-short 연구 백테스트는 simple 모드 전용이고 qlib
   모드는 `mode="qlib_long_only"`로 제한 지원한다. timestamp는 실증됨:
   신호 t → t+1 시가 체결 (deal_price="open"에서 체결가 = 그날 $open).
2. **AutoAlpha instrumentation의 한계** — AutoAlpha 탐색이 전역 `random`을
   사용해 시드 고정으로도 비재현(+n_jobs/depth 버그, AboutAutoAlpha.md).
   어댑터는 "평가된 후보 관찰 로깅"(LoggingEvaluator)만 보장하며 genome
   의미론은 best-effort.
3. **overflow 병리 formula에서 qlib native와의 비트일치가 깨진다**
   (pilot 검증 V2에서 특성화, `docs/experiment/asb_pilot_verification.md`).
   - 정상 formula에서는 셀 단위 비트일치가 유지된다 (pilot 21개 중 17개:
     max|diff|=0, **inf 위치까지 일치** — 예: `Power(Resi($high,30),…)`의
     +inf 2,261셀 동일). 마이닝 fitness도 6자리 재현.
   - **중간 노드에서 float 오버플로가 발생해 rolling 연산(Rsquare/WMA)으로
     흘러 들어가는 경우**에만 어긋난다: qlib native는 노드별 float32 캐스팅
     으로 조기에 inf→(rolling 통과 중) NaN 전파, ASB engine은 내부 float64
     유지 후 후기 캐스팅이라 +inf로 남거나 인접 셀 값이 달라진다
     (winner: qlib NaN 셀 266,805개가 ASB에선 +inf; 경계 Rsquare formula:
     공통 finite 셀 max|diff|=0.435, ASB가 42,473셀 추가 마스킹).
   - **집계 의미론 차이 1건**: 신호에 ±inf 셀이 있을 때 fast runner의
     `_ic_pair`(join.dropna)는 해당 **일 전체**의 corr가 NaN이 되어 그 날이
     탈락하는 반면, ASB `masked_daily_corr`는 inf **셀만** 제외하고 그 날을
     살린다 (예: smoke Power 계열 |IC| 0.0498(마이닝) vs 0.0647(ASB) —
     부호 동일, 판정 불변).
   - 영향 범위: 이런 신호는 정의상 validity gate가 걸러내는 병리 케이스
     뿐이며(4/21, 전부 아티팩트 판정), 정상 신호 평가에는 영향 없음.
     v0.1에서는 **알려진 경계조건으로 문서화**하고 수정하지 않는다 —
     수정하려면 노드별 float32 캐스팅 시점을 qlib과 완전 일치시켜야 하며,
     그 대상 신호가 전부 hard/research invalid이므로 실익이 없다.

4. **signal engine 2단계 (qlib native fallback)** — FormulaEngine은 GP
   함수형 문법 전용 고속 엔진이라 qlib 전체 문법(infix 산술, 비교 연산,
   Corr/Cov/Rank, 숫자 리터럴 — AlphaAgent가 생성)을 파싱하지 못한다.
   `SignalContext.evaluate`는 parse_error/unknown_operator/unknown_field에
   한해 **qlib native `D.features`로 같은 수식을 계산**해 동일 격자에
   정렬한다 (2026-08-14, AlphaAgent_asb 통합에서 발견). qlib이 reference
   의미론이므로 금지된 'silent fallback'($close 대체 — 다른 신호)과 무관한
   엔진 선택이며, 사용 엔진은 validity/oos factor 테이블의 `signal_engine`
   컬럼에 기록된다. 비용: 해당 formula × split당 qlib 쿼리 1회(캐시됨).
   진짜 평가 실패(eval_error 등)는 종전대로 hard invalid로 전파된다.

## Engineering decisions (문서화된 선택)

3. **weights 미제공 시 equal weights(1/n)** — pool 평가를 생략하는 대신
   기본값으로 진행하되 `weights_source: "equal_default"`를 manifest·pool
   metrics에 기록. train-학습 weights 제공을 권장.
4. **단일-run 모드의 PCA reference** — `qd.projection.load_from` 미지정 시
   해당 run의 **valid split** descriptor로 fit하고 좌표계를
   `manifests/qd_projection/`에 저장한다. 여러 method를 한 지도에서 비교할
   때는 기준 run에서 fit한 좌표계를 `load_from`으로 재사용해야 한다 (G3/G4
   준수 — fit 입력은 언제나 validation descriptor).
5. **OOS IC의 inf 처리** — legacy(ictester)는 ±inf 셀을 corr에 포함시켜
   그날 IC를 NaN으로 만들고 NaN>50%면 0.0을 반환. ASB research protocol은
   inf를 invalid cell로 제외하고 validity로 보고한다(METRICS.md). inf 없는
   formula에서는 legacy와 1e-9 이내 일치(regression 테스트).
6. **backtest 첫날 건립 비용** — legacy의 첫날 NaN cost(truthy 버그) 대신
   무포지션→건립 turnover(l1=1)에 비용을 명시적으로 부과.
7. **정지 종목의 손익 기여 0** — simple 모드에서 execution return NaN인
   보유 종목은 그날 무손익 가정(`n_missing_returns` 기록). 현실적 처리는
   qlib native(long-only)가 담당.
8. **engine의 warmup 부족 시 명시적 실패** — 표현식의 좌측 절단점이
   `warmup_start` 이전이면 조용한 편차 대신
   `eval_error:insufficient_warmup`으로 실패시킨다 (smoke config처럼 warmup을
   좁힌 경우의 안전장치).
9. **parquet 폴백** — pyarrow 실패 시 `.pkl`로 저장하고 manifest의
   `parquet_fallbacks`에 기록한다 (현재 env에는 pyarrow 17.0.0 설치됨).
10. **`qd.horizons`의 최솟값(=1d)이 regime 조건 IC의 기준 horizon** —
    V/M/L은 1d IC 시계열의 조건부 평균으로 정의.
11. **instrumentation/은 import 금지 검사의 명시적 예외** — optional
    adapter의 존재 이유가 miner 통합이므로. core(그 외 전부)는
    `check_no_alphaeval_imports.py`로 강제.
12. **pip 설치 2건** — AlphaEval38 env에 pyarrow 17.0.0, pytest 8.3.5 추가
    (Phase 0; parquet 산출과 테스트 실행의 전제).

## 테스트 실행 기록 (완료 시점)

| suite | 결과 |
|---|---|
| Phase 0 scaffold | 4/4 PASSED |
| Phase 1 signal/validity (+TensorEvaluator 비트 동등성) | 10/10 PASSED |
| Phase 2 OOS synthetic | 8/8 PASSED |
| Phase 3 QD core | 11/11 PASSED |
| Phase 4 QD pool | 9/9 PASSED |
| Phase 5 trajectory | 5/5 PASSED |
| Phase 6 PFS | 5/5 PASSED |
| Phase 7 simple backtest | 5/5 PASSED |
| Phase 8 qlib timestamp audit [optional] | 2/2 PASSED |
| Phase 9 E2E 통합(+결정론) | 7/7 PASSED |
| regression (legacy 대조) | 4/4 PASSED |
| synthetic suite | 6/6 PASSED |
| check_no_alphaeval_imports | OK |
| check_original_untouched | OK (기준선 1건 대비 추가 변경 없음) |

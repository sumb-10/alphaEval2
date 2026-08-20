# Search Space Record — `alphaagent_native` v1

상태: 기록·버전링용 (Controlled Benchmark 단계의 중립 공통 명세
`alpha_space_v1` 사전 문서 — `gp_native_v1.md`와 동일 양식).
이 문서는 **AlphaAgent(LLM 마이너)가 실제로 생성 가능한 수식 공간**을
정의한다. 코드 근거: `AlphaAgent_asb/alphaagent_asb/prompts.py`
(`FACTOR_FUNCTION_DEFINITION` — parity mode, 원본 `factor_agent.py` 미러).
LLM 마이너의 문법은 파서가 아니라 **프롬프트 선언 + 사후 검증**으로
정의된다는 점이 심볼릭 마이너와의 근본 차이다.

버전 규칙: terminal/operator/제약 선언이 바뀌면 v2로 증가.

## Terminals (5)

```
$open  $high  $low  $close  $volume
```

GP(`gp_native_v1`)의 10개 대비 절반 — `$vwap, $amount, $change, $factor,
$adjclose`가 없다. **숫자 상수는 자유롭게 허용**(명시 금지 없음): expB
실측에서 51/51 수식이 숫자 리터럴 포함.

## Operators (프롬프트 선언 22)

| 종류 | 연산자 | 비고 |
|---|---|---|
| unary (3) | `Abs, Log, Sign` | |
| infix (5) | `+ - * / **` | GP에는 prefix `Add/Sub/Mul/Div/Power`로 존재 |
| rolling (12) | `Ref, Corr, Cov, Delta, WMA, Min, Max, IdxMax, IdxMin, Rank, Sum, Std` | window `d`는 **자유 정수** (GP: {5,12,30,64} 고정) |
| comparison (2) | `Greater(x,y), Less(x,y)` | 프롬프트 정의: "1 if x > y, else 0" — ⚠ 아래 의미론 불일치 |

GP와의 차집합: AlphaAgent에는 `Mean, EMA, Var, Skew, Kurt, Med, Mad,
Slope, Rsquare, Resi`가 **없고**(특히 `Mean` 부재는 원본 프롬프트 그대로),
GP에는 `Corr, Cov, Rank`가 없다(Corr/Cov는 vendored에서 비활성).

## 실사용 분포 (expB, 실 LLM gpt-5.6-luna, unique 51)

```
Delta 79  Ref 69  WMA 47  Sum 35  Abs 28  Std 25  Greater 14  Log 10
Rank 9  Less 6  Max 4  Corr 4  IdxMin 3  Min 3  IdxMax 1  Sign 1  (Cov 0)
```

infix 포함 ≈48/51, 숫자 리터럴 51/51.

## 알려진 의미론·평가 경로 이슈 (교차 방법 대조 시 필수 확인)

1. **Greater/Less — native implementation semantic defect** (단순 문법
   차이가 아님): 프롬프트는 LLM에게 비교 지시자("1 if x > y, else 0")로
   가르치지만, 평가 엔진(canonical FormulaEngine·qlib-native 모두 qlib
   의미론)은 **element-wise max/min**을 계산한다 — LLM이 의도한 조건부
   로직과 실제 신호가 체계적으로 다르다. **처리 정책 (2026-08-19 확정)**:
   ① 원본 재현용 legacy AlphaAgent 경로는 결함 그대로 보존,
   ② clean/native 실험 경로에서는 프롬프트↔evaluator 의미를 일치시키도록
   수정한다(수정 구현은 AlphaAgent clean 경로 작업 시),
   ③ 수정 전/후는 profile/version을 분리한다(GP v2가 point mutation·HOF
   결함을 legacy 보존 + clean 수정으로 처리한 것과 동일 구도).
   Controlled 단계에서 GP와 엄밀 비교 시 반드시 별도 처리 대상.
2. **canonical parser 비호환** — infix 연산자·자유 상수·`Rank/Corr/Cov`는
   ASB canonical parser(`parse_expression`) 문법 밖이다. expB 실측
   51개 중 49개가 canonical 파스 불가 → **qlib-native 엔진 fallback**으로
   평가되며, 사용 엔진은 validity 테이블의 `signal_engine` 필드에
   provenance로 남는다. 교차 방법 신호 동등성 주장은 이 fallback 경로의
   parity 검증에 의존한다.
3. **window 자유 정수** — GP의 고정 window 집합과 달리 임의 d가 가능
   (실측 예: 3, 5, 10, 20, 60 등). 복잡도 대조 시 window 값은 잎 노드
   1개로 계량한다(`2026-08-19_C2_LD_evidence.md`).

## 복잡도 실측 (ast 기반 공통 계량, expB unique 50)

```
L(size):  med 19  p90 37  p95 56  max 76
D(depth): med  6  p90  8  p95 10  max 11
```

GP v1 대비 자연 스케일이 훨씬 크다(GP unique 7,671: L med 7 max 43,
D med 4 max 10). 단 n=50 소표본 — 실 LLM 대규모 run 후 갱신 필요.
**용도 제한**: 이 분포는 **GP complexity bound(L/D) 결정 근거로 사용하지
않는다** — native 단계에서 AlphaAgent에 동일 bound를 적용하지 않으므로,
Controlled Benchmark 설계를 위한 참고자료로만 유지한다.

## Provenance

* 문법 선언: `alphaagent_asb/prompts.py` (원본 factor_agent.py parity 미러)
* 실측 코퍼스: `AlphaAgent_asb/out/alphaagent_asb_expB_csi800`
  (실 LLM gpt-5.6-luna, unique 51)
* 복잡도 계량·대조: `docs/experiments/2026-08-19_C2_LD_evidence.md`

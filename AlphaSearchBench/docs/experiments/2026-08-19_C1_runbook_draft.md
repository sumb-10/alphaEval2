# C-1 Runbook — budget 배분 검증 (사전등록, 개정 2차)

상태: **사전 동결본 — 효력 발생 조건**: C-2b(L/D 값) 확정 후 mining
config에 주입. 사용자 승인은 **조건부 사전 부여됨**(2026-08-19):
C-2a가 사전 정의된 non-binding 조건 5개(C2_LD_evidence.md §C-2a)를 전부
만족하면 L=40/D=10 자동 확정 + 본 runbook에 따라 C-1 9 runs 자동 시작,
하나라도 위반 시 중단·보고. 판독 규칙·실패 규약은 실행 *전에* 동결한다.
개정 2차(2026-08-19): **ASB evaluate 전면 삭제 → GP-side validation
scorer**, seeds {0,1,2}, paired 2/3 vs BOTH 판정, 실패 규약 이분.

## 목적과 경계

5,000 후보 예산에서 population×generations 배분
{1000×5, 500×10, 250×20} 중 하나를 **1회** 결정한다.
결정은 validation(2022-01-01~2023-12-31)에서만 — 동결 test(2024-01-21~)
접촉 금지.

**Phase C 경계**: GP 내부 mining/validation semantics만 사용한다. shared
data/utility 계층(FormulaEngine, `daily_zscore`)의 재사용은 허용하되
**ASB evaluation policy(evaluator·backtest·OOS/QD metric)는 사용하지
않는다**. Phase D에서 freeze된 GP 산출물을 ASB가 독립 평가한다.

## 실행 매트릭스

* **3 arms × seeds {0, 1, 2} = mining 9 runs + GP-side scorer 9회.**
  (42 제외 — v1 development evidence 중복 회피. 세 arm이 동일 seed set을
  공유해 paired 비교 가능.)
* mining config: `configs/v2/vanilla_baseline.yaml` 파생 — population만
  {1000, 500, 250}, L/D는 C-2b 확정값 주입. 나머지 키 변경 금지(스키마 강제).
* run_id: `v2_csi800_fbfit_c1_<pop>x<gens>_s<seed>`.

## GP-side validation scorer (`gplearn_asb/gplearn_asb/validation_scorer.py`)

GP hyperparameter selection 전용 내부 도구(범용 평가 프레임워크 아님).
계약(동결 — 결과 확인 후 변경 금지):

1. **Orientation** — mining production path가 pool CSV에 저장한 train-side
   orientation(raw `signed_train_IC`의 부호)을 고정 사용. validation
   재추정 금지. 이 컬럼이 orientation 적용 전 raw 값임은 회귀 테스트로
   고정(음수 IC fixture + production `diagnose` 재계산 대조).
2. **Pool combiner (canonical train_signed_equal)** —
   `combined = Σᵢ (signᵢ/n)·daily_zscore(sigᵢ)` (shared 유틸 재사용;
   일별 cross-sectional, ddof=0, std<1e-8→1, 결측 셀→0).
   **combined valid mask = ∨ᵢ validᵢ** — 결측→0 치환 셀의 누수 차단.
3. **포트폴리오·성과** — validation 창으로 인스턴스화한 `MiningEvaluator`의
   `_net_sharpe(combined, sign=+1)` 직접 호출(quantile 0.2, cost 0.0015,
   건립비용, oneway turnover — candidate fitness와 동일 코드 경로).
4. **pool_fb** = `fb_fitness_value(net_sharpe, net_ann_ret_arith,
   mean_daily_turnover_oneway, min_annual_turnover=0.01)` 재사용.
   non-finite/degenerate → NaN → cell failure(임의 저점수 부여 금지).
5. **n=1 equivalence regression contract**: 단일 factor pool의 scorer
   결과 = 동일 validation 창의 canonical candidate 평가(production path)
   — membership·daily net return·turnover(일평균/연환산)·AnnRet·Sharpe·fb
   전 항목 일치.

## Pool integrity gate (scorer 실행 전)

`n_factors == 10` ∧ `unique formulas == 10` ∧ 전 factor train orientation
존재 ∧ 전 factor validation 신호 계산 성공.

**"신호 계산 성공" 정의(고정)**: engine exception → model failure;
all-nonfinite signal → model failure; **일부 NaN/결측은 failure 아님**
(valid mask 처리); **validation에서 candidate-level coverage threshold를
재적용해 factor를 탈락시키지 않는다** — C-1은 factor 추가 선별이 아니라
pool 전체의 OOS utility 평가다.

gate 위반 → 해당 arm-seed **cell failure**(부분 pool 점수화 금지), 원인은
mining diagnostics 참조로 기록.

## 실패 규약 (동결)

* **Operational failure** (Slurm/filesystem/crash): 동일 config·동일 seed
  재실행 **허용** — retry 사유와 이전 실패 job ID를 manifest/실험 로그에
  기록. 결과 확인 후 adaptive한 seed/arm/config 추가·판독 규칙 변경 금지.
* **Model/output failure** (10 unique 생성 실패, orientation 결측,
  validation 신호 평가 실패, 진성 퇴화 pool): retry로 없애서는 안 되는
  실험 결과 — raw metric NaN + `failure_reason` 보존, ranking에서 임의
  제외 금지.

## 판독 규칙 (동결)

1. 각 arm의 validation pool-level fb 3-seed **median** 계산.
   model failure 셀은 **−∞ 취급**(median of {−∞, a, b} = min(a, b) —
   survivorship bias 차단).
2. median 최대 arm = provisional winner.
3. provisional winner가 **다른 각 arm에 대해** paired seeds 3개 중 **≥2
   우세**여야 채택. paired 비교에서 model failure = 패배, 양측 failure =
   무승부(어느 쪽 승리도 아님).
4. 어느 한 상대에 대해서라도 2/3 dominance 실패 → allocation effect
   **inconclusive**.
5. median 동률 또는 전 arm −∞ → provisional winner 없음 → inconclusive.
6. inconclusive → **pre-specified reference allocation 1000×5** 유지
   (5,000-candidate budget 하의 사전 지정 기준값 — "canonical vanilla
   default" 아님: upstream gplearn의 canonical generations가 5인 것은 아님).
7. net Sharpe는 secondary 병기 전용 — primary 판정 번복에 사용 금지.
8. 탐색 진단(unique 수, best fitness 도달 세대, duplicate rate)은 selection
   criterion이 아니라 보고서의 참고 자료.

## 산출·보고

E-보고서 1본(승인 양식): arm×seed 9칸 표(pool fb·net Sharpe·integrity·
failure_reason), 성공-only median 참고 병기(판정에는 미사용), 규칙 적용
과정 명시, manifest 링크. validation 수치는 설정 결정 전용 — 일반화 증거
인용 금지.

## 비용 추정

mining 1 run ≈ 수 시간(cpu1, 7y 창) × 9 + scorer 9회(각 수 분) — 동시
제출 시 반나절 내(제출 한도 20 이내).

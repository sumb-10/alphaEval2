# AlphaAgent_asb — LLM 알파 마이닝(AlphaAgent)의 ASB 호환 이식

원형: `AlphaEval/Alphaagent/` (논문 "AlphaAgent: LLM-Driven Alpha Mining with
Regularized Exploration to Counteract Alpha Decay" 구현). 원본 무수정 —
verbatim 사본은 `alphaagent_asb/vendored_alphaagent/`, 원형 대비 편차는
`PROVENANCE.md`(D-1~D-8)에 전량 기록.

## 핵심 설계 — feedback과 diagnostics의 분리

LLM에게 되돌아가는 숫자(AnnRet/IC)는 다음 후보 생성에 직접 영향을 주므로
**원형 FactorBacktester를 그대로 실행**해 산출한다(첫날 NaN cost 버그·IC
3자리 반올림 포함). ASB 진단(signed IC + validity 15키)은 gplearn_asb의
MiningEvaluator로 **기록 전용** 병행 — search에는 개입하지 않는다
(constraint overlay는 config 옵션, 기본 `"off"`).

```
FactorAgent 수식
 ├─ feedback: vendored FactorBacktester → AnnRet·IC(프롬프트 값) → EvalAgent LLM 판정
 └─ diagnostics: MiningEvaluator → signed_train_IC·validity (기록 전용)
→ trajectory (합격/불합격 전 후보 + 자연어 궤적)
```

trajectory 시간축: `generation = round_id`, `idx_in_population = seed_idx`
(ASB 호환 필드 — **seed 간에는 재생산 관계가 없다**, manifest의
trajectory_semantics 참조). 분석 명칭: refinement-round dynamics.

값 기록 규약: `raw_fitness = abs(feedback_IC_raw)`(반올림 전),
`feedback_IC_prompt`(LLM이 실제로 본 3자리 반올림 값)와 분리 저장.

## 실행

```bash
cd AlphaSearchBench/AlphaAgent_asb
# 개발/테스트 (LLM 불필요, 결정적)
python -m alphaagent_asb.cli mine --config configs/smoke.yaml --fake
# 기록 재생 (결정적 재실행)
python -m alphaagent_asb.cli mine --config C --replay out/<run>/trajectory/llm_calls.jsonl
# live (사용자 승인 + OPENAI_API_KEY 필요)
python -m alphaagent_asb.cli mine --config configs/experiments/<exp>.yaml
# Slurm
sbatch -p cpu1 scripts/slurm_alphaagent_asb.sbatch <config> fake|live <run_id>
```

산출물(`out/{run_id}/`): `metrics/final_pool_*.csv`(ASB 표준 입력,
signed_train_IC 포함), `metrics/candidate_diagnostics_*`,
`metrics/round_stats_*`, `trajectory/{run_id}.jsonl`(Search-QD 호환) +
`trajectory/llm_calls.jsonl`(전 호출 로그 — replay 입력),
`manifests/run_*.json`(LLM budget: 후보 수와 콜 수 분리).

## 재현성 계층

FakeLLM(결정적) < Replay(기록 재생, 결정적) < Live(비결정 — request seed·
온도 config·전량 로그로 사후 감사). live run은 비용이 발생하므로 사용자
승인 게이트.

## 문서

`IMPLEMENTATION_PLAN.md`(설계·지도 원칙 4문장), `TODO.md`(진행 실측),
`PROVENANCE.md`(편차), `REPORT.md`(live pilot 후).

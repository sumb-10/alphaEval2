# gplearn_asb — Validity-aware GP (worst-fitness penalty)

원본 gplearn(AlphaEval fork)의 search mechanics를 보존하면서, **invalid
candidate가 높은 IC fitness로 선택되는 루프홀만** worst-fitness penalty로
통제하는 실험 variant. 원본 `gplearn/`·`scripts/`는 수정하지 않는다
(byte-identical vendored 사본 사용 — `gplearn_asb/vendored_gplearn/PROVENANCE.md`).

## 핵심 원리

```
candidate 생성(원본 유전연산·RNG 순서 그대로)
  → 신호 평가(ASB FormulaEngine) + validity 진단(항상 계산)
  → constraint mode에 따라 effective fitness 결정
      valid            → |train IC|
      invalid          → worst sentinel(유한, 기본 −1.0)
  → population에는 둘 다 유지 (삭제/재샘플 없음, population size 불변)
  → tournament/HOF가 effective fitness를 소비 → invalid는 자연 도태
```

- **off**: penalty 없음 + 원본의 `$close` fallback 루프홀까지 재현 —
  동등성 검증용. 실증: 883881 조건에서 최종 pool **완전 재현**
  (formula 목록 동일, IC 차이 ≤1e-16).
- **hard_penalty**: 수학적으로 정의 불가능한 4종(formula_eval_failed /
  all_nonfinite / no_correlatable_day / zero_ic_observations)만 worst.
- **strict_penalty**: hard + research threshold(coverage/유효종목수/유효일
  비율, `>= pass` 규약, config 주입 — hard-code 없음) 실패도 worst.

raw_fitness(=|IC|, penalty 전)와 effective_fitness는 항상 **둘 다** 저장된다
— "raw 0.565 / effective −1.0" 같은 루프홀 후보의 흔적이 분석 가능해야 하므로.

## 실행

```bash
cd AlphaSearchBench/gplearn_asb
# 로컬
python -m gplearn_asb.cli mine --config configs/smoke.yaml --mode strict_penalty
# Slurm
sbatch -p cpu1 scripts/slurm_gplearn_asb.sbatch \
    configs/experiments/pilot_csi800_base.yaml hard_penalty 42
```

산출물(`out/{run_id}/`): `metrics/final_pool_*.csv`(ASB 표준 입력 호환,
signed_train_IC 포함 — sign 사후 복원 불필요), `metrics/candidate_diagnostics_*`,
`metrics/generation_stats_*`(세대별 invalid rate·parent diversity),
`trajectory/*.jsonl`(ASB Search-QD 호환), `manifests/run_*.json`(budget 포함).

ASB 연계:
```bash
cd AlphaSearchBench
python -m alphasearchbench evaluate \
    --config configs/examples/csi800_example.yaml \
    --input gplearn_asb/out/<run>/metrics/final_pool_<run>.csv \
    --trajectory gplearn_asb/out/<run>/trajectory/<run>.jsonl \
    --method gplearn_asb_<mode> --seed-id 42 --out out/<dest>
```

## 테스트

```bash
python -m pytest tests/            # unit + smoke(3모드 미니 run) + regression
```
regression에는 gen-0 원본 동일성, 합성 population 안정성(invalid 90%에서도
크기 불변·invalid 잔존), 실제 pathological winner fixture가 포함된다.

## 구조·설계 근거

`IMPLEMENTATION_PLAN.md`(감사 사실·설계 결정), `TODO.md`(진행 실측),
`REPORT.md`(3-arm pilot 결과 — Phase H 후). 스펙 원문:
`AlphaEval/docs/gplearn_asb.md`.

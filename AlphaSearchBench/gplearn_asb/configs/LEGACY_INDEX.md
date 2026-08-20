# Legacy Config Index — 동결 선언

**이 디렉토리의 기존 config들(아래 표)은 GP v1(legacy/development) 산출물의
재현 전용으로 동결한다.** 신규 실험에 사용 금지. 경로·내용을 이동/수정하지
않는다(과거 report·manifest가 경로를 참조 — 재현성 우선). 신규 실험은
`configs/v2/`만 사용한다. 근거: `docs/research_docs/Vanilla_GP_v2.md` §0·§5.

기존 기간(test 2021–24 포함)의 모든 결과는 development evidence이며 공식
주장에 사용하지 않는다.

| config | 용도 | 재현 대상 |
|---|---|---|
| `default.yaml` | legacy 기본값 (v1 cli 경로) | 전 v1 run의 base |
| `smoke.yaml` | legacy 3-mode smoke | `tests/smoke/test_smoke_modes.py` |
| `smoke_fixedhof.yaml`, `smoke_ictstat.yaml`, `smoke_fbfit.yaml` | A+B+P 검증 smoke | job 884709 |
| `experiments/replicate_883881.yaml` | 원본 run 883881 비트 재현 | `tests/regression/` |
| `experiments/pilot_csi800_base.yaml` | 3-arm pilot + seed sweep | `out/pilot_csi800_{off,strict,hard}_*`, REPORT §1–5·8 |
| `experiments/pilot_csi800_netsharpe.yaml` | 실험2 (net_sharpe) | `out/pilot_csi800_netsharpe_*` |
| `experiments/ablation_ictstat.yaml` | B ablation ① | `out/pilot_csi800_ictstat_42`, E-보고서 |
| `experiments/ablation_ns_guarded.yaml` | B ablation ② | `out/pilot_csi800_nsguard_42` |
| `experiments/ablation_fbfit.yaml` | B ablation ③ + E1 seed sweep | `out/pilot_csi800_fbfit_*`, docs/experiments/E1 |
| `experiments/ablation_fbfit_guard.yaml` | E2 (fb+IC-floor) | `out/pilot_csi800_fbfitguard_42`, docs/experiments/E2 |

legacy 경로의 알려진 특성(의도적 보존): buggy point mutation(정수 유입),
original HOF anti-selection, off 모드 $close fallback, metric 의존 early
stopping 가드. v2에는 존재하지 않는다.

**공유 모듈 주의**: v2는 `fitness.apply_constraint`·`evaluator`·`genetic`
등을 legacy와 **살아있는 코드로 공유**한다(내부 mode=strict_penalty 탑승).
legacy 실험을 위해 이 모듈들을 수정하면 v2도 함께 바뀌므로, **수정 시
v2 결정성 fixture(`tests/regression/test_v2_correctness.py`) 재실행이
필수**다.

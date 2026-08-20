# C-2 evidence — complexity bound (L/D) 교차 방법 실측 대조

목적: GP v2 freeze 조건 ①(`gp.max_program_length`(L)·`gp.max_program_depth`(D)
값 확정)의 결정 재료. **값 확정은 사용자 결정 사항** — 본 문서는 실측
분포·후보 bound별 영향·권고안만 기록한다.

## 계량 정의 (교차 방법 공통)

Python ast 기반: `Call`/`BinOp`/`UnaryOp` = 내부 노드 1, 이름·상수(window
포함) = 잎 1. **L = 총 노드 수, D = 트리 깊이(잎=1).**
GP prefix 문법에서 v2 static 계량(`static_check._tree_size/_tree_depth`)과
**동치임을 검증**(GP 표본 500 수식, 불일치 0건) — 즉 이 대조의 L/D는 v2
bound가 실제로 판정하는 값과 같은 자다. infix·자유 상수를 쓰는
AlphaAgent 문법도 동일 자로 계량된다.

## 실측 분포

| 코퍼스 | n | L med | L p90 | L p95 | L p99 | L max | D med | D p90 | D p95 | D p99 | D max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| GP v1 fbfit 5-seed unique 후보 | 7,671 | 7 | 14 | 17 | 23 | 43 | 4 | 5 | 6 | 7 | 10 |
| GP v1 pool 승자 (전 run) | 217 | 9 | 19 | 21 | 25 | 27 | 5 | 6 | 7 | 8 | 10 |
| AlphaAgent expB unique (실 LLM) | 50 | 19 | 37 | 56 | 72 | 76 | 6 | 8 | 10 | 11 | 11 |

판독:
* GP는 bound 없이도(v1) 자연 분포가 L≤43·D≤10에 갇힌다 — fitness 압력이
  bloat를 사실상 제어. pool 승자는 max L 27로 더 작다.
* AlphaAgent의 자연 스케일은 GP의 ~2.5배(중앙값 기준). LLM은 상수·infix를
  써서 장식이 많은 수식을 낸다. 단 **n=50 소표본**.

## 후보 bound가 자르는 비율 (해당 방법의 자연 분포 기준)

| bound | GP 초과율 | AlphaAgent 초과율 |
|---|---|---|
| L≤20, D≤6 | 3.35% | 54.0% |
| L≤25, D≤7 | 0.64% | 24.0% |
| L≤30, D≤8 | 0.21% | 16.0% |
| **L≤40, D≤10** | **0.03%** | **8.0%** |

## 권고안 (사용자 확정 대기)

**1순위 후보: L=40, D=10 — 단 freeze 보류, C-2a 파일럿으로 비구속성 확인
후 C-2b(사용자)에서 확정.**
* GP v1 관측 기준 사실상 비구속(초과 0.03% — fb 가드들과 같은 "사전등록
  안전핀" 성격)이라 vanilla 철학(탐색을 bound로 조형하지 않음, parsimony
  0)과 정합. 관측 자연 envelope(L 43·D 10)를 살짝 안쪽에서 자른다.
* **미해결 위험(→ C-2a)**: 위 분포는 v1의 5세대 구조 관측이다. C-1의
  250×20처럼 세대수가 늘면 crossover/mutation 반복으로 bloat tail이
  길어질 수 있고, 그 경우 40/10은 안전핀이 아니라 특정 arm의 실질 탐색
  제약이 되어 C-1이 "배분 × complexity-bound 상호작용" 비교로 오염된다.
  D=10은 관측 최대값과 맞닿아 있어 특히 재확인 대상.
* AlphaAgent 분포는 **GP bound 결정 근거로 사용하지 않는다**(native
  단계에서 동일 bound 미적용 — Controlled 설계 참고자료로만).

2순위(적극적 복잡도 제어를 원할 때): L=25, D=7 — GP pool 승자의 p95/p99
경계라 해석가능성 지향이지만, 탐색 조형이 시작된다(GP 0.64% 절단).

## C-2a — train-only 구조 파일럿 (freeze 선행 게이트, 5 runs)

성능 비교가 아니라 v2의 자연 complexity dynamics를 확인하는
**specification experiment** (validation/test 미사용 — leakage 없음).

* **C-2a.1 screening**: {1000×5, 500×10, 250×20} × seed 0 (3 runs).
* **C-2a.2 tail confirmation**: 250×20 × seeds {1,2} (2 runs — bloat 위험
  최대 arm의 seed 강건성).
* 설정: train 2015–2021, canonical fb_fitness, typed mutation, parsimony
  0, **L/D bound null**.
* **통계 모집단(고정)**: 분모 = 전체 generated candidate attempts(중복·
  invalid 무관 전부). admissible-only는 보조 병기.
* **trajectory 완전성 assertion(분석 선행 gate)**: rows==5,000,
  세대별 rows==population, L/D 계량 실패 0 — 위반 시 분석 중단·원인 보고.
* **고정 산출**: overall `P(L>40 ∨ D>10)`, 세대별 p95/p99/max/exceedance
  궤적, 전체 attempts p95/p99/p99.9/max, 최종 population 분포, pool winner
  L/D, 250×20 seed 간 반복성.
* **판정 취급**: C-2a는 evidence generation — Non-binding/Marginal/Binding
  은 descriptive label로만 병기하고 **자동 freeze 규칙으로 쓰지 않는다**.
  L/D 최종 확정은 C-2b에서 사용자가 이 수치를 근거로 결정.
* **C-2b 조건부 사전 승인 (2026-08-19 사용자 지시)**: 아래 5개 조건이
  **전부** 만족되면 C-2b를 자동 통과시켜 L=40/D=10을 확정하고 configs에
  주입한 뒤 C-1 9 runs를 자동 시작한다. **하나라도 위반하면 C-2b에서
  중단하고 보고한다** —
  ① 모든 run에서 P(L>40 ∨ D>10) = 0
  ② 250×20의 seeds {0,1,2} 전부 exceedance = 0
  ③ generation별 exceedance 증가 추세 없음
  ④ trajectory completeness assertion 전부 통과
  ⑤ 검증 스위트 green.

## C-2a 실측 결과 (2026-08-20) — **auto-gate 위반, C-2b 중단**

| run | 상태 | exceed P(L>40∨D>10) | L p99/p99.9/max | D p99/p99.9/max |
|---|---|---|---|---|
| 1000×5 s0 | 완료 (2:00h) | **0%** | −/−/≤40 | −/9/10 |
| 500×10 s0 | 완료 (3:55h) | **4.10%** | 43/59/**77** | 12/15/**17** |
| 250×20 s0 | 완료 (2:50h) | **1.68%** | 38/51/**62** | 11/13/**15** |
| 250×20 s1 | 완료 (0:33h) | 0% | 11/17/21 | 5/6/7 |
| 250×20 s2 | **TIMEOUT 12h** (3,915/5,000 rows, 세대 15/20) | **부분 41.5%** (1,624/3,915) | max **48**(부분) | max **30**(부분) |

**판정**: 조건 ① 위반(500×10 s0 4.1%, 250×20 s0 1.7%), ② 위반(250×20
seed 간 0%/1.7%/41.5% — 극단적 seed 변동), ③ 위반(s2 세대별 Dmax
단조 증가: gen0 5 → gen12 **30**), ④ 위반(s2 미완주 — 단 원인이
operational이 아니라 **bloat 자체**: 깊은 트리의 평가 비용 폭증으로
run 시간이 33분/2:50/12h+로 발산), ⑤ 충족(검증 스위트 83 passed).

**핵심 발견**:
1. **"L=40/D=10 = 비구속 안전핀" 가설은 기각됐다.** v2의 자연 bloat
   dynamics는 세대수·seed에 따라 envelope를 크게 벗어난다(v1 관측
   max L43/D10은 5세대 구조의 산물이었음이 판명).
2. **bloat는 통계 문제이자 운영 문제다** — D 20~30의 중첩 rolling
   트리는 평가 비용을 폭증시켜 12h TIMEOUT을 직접 유발했다. bound
   없는 운영은 불가능하다.
3. 세대수가 적은 1000×5만 안정적으로 envelope 내부(0%).

**C-2b 재료 (사용자 결정 대기)**: bound는 이제 "안전핀"이 아니라
**실측된 병리에 대한 필수 제어**로 정당화가 바뀐다. 채택 시 C-1은
"동일 L/D bound 하의 배분 비교"로 해석을 사전 등록해야 한다(bound가
binding이므로 상호작용은 존재하나 전 arm 동일 적용).

## Caveats (정직 기재)

1. AlphaAgent 코퍼스 n=50 (expB 단일 run) — 실 LLM 대규모 run 후 갱신 필요.
2. GP 분포는 v1(2010–19 창, buggy mutation 포함) 관측 — v2(typed mutation,
   2015–21 창)의 분포는 미세하게 다를 수 있음. 단 bound가 비구속 영역이면
   영향 없음.
3. bound는 GP v2 mining에 적용되는 값이며, AlphaAgent 생성에는 현재 bound가
   없다 — 교차 방법 공통 명세(`alpha_space_v1`)는 Controlled 단계 소관.

재현: 본 문서의 수치는 candidate_diagnostics parquet(fbfit 5-seed,
alphaagent expB)과 final_pool CSV 전수에서 ast 계량으로 산출.

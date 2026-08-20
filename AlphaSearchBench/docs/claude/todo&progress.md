s2 취소와 C-2a.3 재개가 완료됐습니다. 요청하신 세 가지에 답합니다.

1. 기존 ε/cap 기록 — 있습니다
out/c2a3/prereg_SMOKE_4runs.json — s2 대기 중 4개 완주 control로 미리 돌려둔 기록입니다 (ε_p10 = 2.878e-4, cap 후보 80/18·100/20 모두 exceedance 0%·pool winner 초과 0). s2가 빠져 SMOKE로 표기했던 것이고, 방금 이를 정본으로 승격했습니다.

2. s2 취소 실행 + 사전등록 FINAL 확정
890129 scancel 완료, 감시자 자연 종료. manifest deviations에 개정 기록(treatment 실행 전 개정이므로 사전등록 integrity 유지).
s2 partial gens 0–14 (완전 세대 3,750 rows) 을 편입해 최종 사전등록 실행 → prereg_FINAL_4c_plus_s2partial.json:
ε = 4.764e-4 (pooled gaps n=63,123; 4-run 민감도값 2.878e-4 병기). s2 편입으로 ε가 약 1.7배 커졌는데, 이는 s2의 bloat 국면 gap이 상대적으로 커서입니다 — 여전히 gap 중앙값(5.8e-3)의 1/12 수준이라 "near-tie만 개입" 성격은 유지됩니다.
cap = 100/20 확정: 정상 4 runs는 두 후보 모두 초과 0%지만, 관측 envelope max가 77/17이라 80/18은 마진이 L+3/D+1로 극박합니다. 100/20은 정상 탐색과 분리 여유를 확보하면서 s2류 병리는 여전히 차단(80/18: 7.41%, 100/20: 4.59% 차단 — cap의 의도된 역할).
cli.py:376의 BLOAT_LEXI_EPSILON에 최종 ε 주입(사전등록 파일 provenance 주석 포함), import 검증 통과.
Screening 5 jobs 제출 완료 (890161–890165, 전부 스키마 검증 통과): cap-only regression(500×10 s0 — control 889686과 bit-identical 기대, 불일치 시 wiring defect로 중단), Lexi-only {500×10, 250×20}, Lexi+cap {500×10, 250×20}. control 기준 3~4시간 예상이며 감시자가 완료 시 판독(bit-identical 검증 → Quality/Complexity/Diversity → bloat 원인 진단 → 보고서·권고)으로 이어갑니다. 보고서 후 C-2b는 중단하고 사용자 게이트 대기합니다.

3. 전체 ABCD Phase
Phase	내용	상태
A. 설계·명세	ASB 축 설계(validity/OOS/QD/backtest), 검색공간 명세(gp_native_v1, alphaagent_native_v1), 설계 문서 시리즈	✅ 골격 완료 — validity_gate_design·oos_test_design freeze, qd_test_design만 잔여(GPT 진단 토스 대기)
B. Clean Vanilla GP v2 구현·검증	4-point fix, fb 가드(0.01/252), label tail exclusion, typed mutation, fixed HOF, 전체 스위트 green(889597)	✅ 마감 (2026-08-19)
C. 실험 설계 확정	C-0 split	✅ 확정 — train 2015–21 / val 2022–23 / test 2024-01-21~2026-06-30 동결
C-2a L/D 자연분포 실측	✅ 완료 — "40/10 비구속" 가설 기각, auto-gate 위반으로 C-2b 중단
C-2a.3 bloat-control (ε-lexi)	⏳ 지금 실행 중 — 사전등록 확정, screening 5 jobs 제출
C-2b L/D·complexity-control 방식 확정	🔒 사용자 게이트 (C-2a.3 보고 후 결정)
C-1 budget 배분 (3 arms × 3 seeds)	🔒 사용자 게이트 — runbook 동결·GP-side scorer 구현·regression green, C-2b 확정값 주입만 남음
C-3 freeze	🔒 사용자 게이트 — vanilla_v2 승격 + 2015–2023 refit 공식 mining (규모: 시드/market/ablation 미정)
D. ASB 통합·최종 평가	D-1 qlib 번들 소스 확정·갱신	🔒 사용자 게이트
D-2 ASB Track 선언 (GP native)	대기 (D-1 후)
D-3 동결 test 1회 평가	대기 — Primary Full OOS + Strict Untouched Subset(2025-01-21~) 병기 판독
(묶음) validity/OOS 문서의 Proposed 계약 구현	연기 — Phase D와 함께
경로는 C-2a.3 보고 → C-2b(사용자) → C-1 9 runs → C-3 freeze(사용자) → D-1~D-3 순입니다. 현재 병목은 C-2a.3 screening 완료(오늘 오후 내)와 qd_test_design 트랙(GPT 진단 대기) 두 갈래입니다.

참고: claude.ai의 Notion/Slack MCP 커넥터가 미인증 상태라는 시스템 알림이 있었습니다 — 현재 작업엔 불필요하지만, 쓰실 일이 있으면 claude.ai 커넥터 설정에서 인증이 필요합니다.
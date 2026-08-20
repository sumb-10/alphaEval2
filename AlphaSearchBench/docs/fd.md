네. 다시 normative spec 관점에서 수식·경계조건·split semantics까지 검토해보니, 앞서 말씀드린 수정사항 외에도 확실히 닫아야 할 필수 항목이 5건 더 있습니다. Core 자체를 다시 바꿀 문제는 아닙니다. 현재 문서는 E
t
	​

, T의 pair, A^Q의 overlap 처리 등을 정의하고 있지만 아래 edge contract가 아직 완전히 닫혀 있지 않습니다.

추가 필수 수정	문제	권장 확정
1. E
t
	​

의 집계 domain 명시	모든 descriptor가 E
t
	​

[⋅]라고만 되어 있어 어떤 날짜를 평균하는지 불완전	해당 evaluation split 내부의 eligible trading dates만 단순 산술평균, 제외일을 0으로 채우지 않음
2. T
common
	​

 split-boundary 규약	full panel을 적재하므로 valid 첫날과 train 마지막 날을 pair로 만들 여지가 있음	T pair는 양쪽 날짜 모두 동일 evaluation split에 속하는 연속 거래일일 때만 사용. split 경계 pair 금지
3. A^Q overlap 후 leg 크기 진단	J
t
	​

≥30이어도 tie overlap 제거 후 top/bottom이 1~2종목까지 작아질 수 있음	n_top, n_bottom, n_overlap_removed 필수 저장. production 규약이 backtest parity라면 non-empty만 요구한다는 사실도 명시
4. §8의 A^Q null-variance 설명 수정	파일럿은 fixed-k였지만 production은 inclusive quantile-threshold. “null variance는 0.2N leg size에만 의존”은 production 정의에 일반적으로 성립하지 않음	fixed-k pilot에 대한 관찰이라고 한정하고, production threshold 정의는 §11의 null-coupling acceptance test로 재검증한다고 명시
5. ILLIQ의 obs 집합을 수식으로 정의	현재 amount≤0/결측만 적혀 있고 numerator return의 nonfinite 처리와 min_obs count가 완전히 정의되지 않음	D
i,t
	​

={d:t−19≤d≤t, r
i,d
	​

 finite,Amount
i,d
	​

 finite,Amount
i,d
	​

>0}, (
1. 특히 E
t
	​

와 split boundary는 반드시 추가해야 합니다

현재 B, T, A
L
Q
	​

,A
V
Q
	​

 모두 기간 평균을 E
t
	​

로 표기하지만, eligible day를 제외한 날을 NaN으로 버리는지 0으로 포함하는지가 명문화되어 있지 않습니다.

공통 계약으로 다음 한 줄을 넣는 것이 좋습니다.

E
t
	​

[g
t
	​

]:=
∣T
g
	​

∣
1
	​

t∈T
g
	​

∑
	​

g
t
	​


여기서 T
g
	​

는 해당 evaluation split 안에서 descriptor 정의를 만족하는 eligible trading dates입니다. 제외일은 0이 아니라 집계 대상에서 제외합니다.

특히 T는:

(t−1,t)∈P
split
	​


이고 두 날짜 모두 같은 split 안에 있어야 한다고 못박아야 합니다. ILLIQ/VOL은 과거 데이터를 warm-up으로 사용하는 것이 의도된 반면, T는 split 밖의 signal behavior를 첫 pair에 섞을 이유가 없습니다.

2. min_cross_section_n=30만으로 A^Q leg 안정성이 보장되지 않습니다

현재 규약은 J
t
	​

≥30을 요구한 뒤 20/80 quantile threshold를 만들고 overlap을 제거합니다.

예를 들어 30개 종목 중:

28개 signal = 0
1개 = −1
1개 = +1

이면 Q
0.2
	​

=Q
0.8
	​

=0이 될 수 있습니다. inclusive threshold 후 28개 zero가 overlap으로 제거되면:

n
top
	​

=1,n
bottom
	​

=1

이 됩니다.

즉 min_cross_section_n=30은 spread의 실제 leg가 6개 이상이라는 뜻이 아닙니다.

여기서 지금 새로운 min_leg_n을 도입하면 frozen definition이 바뀌므로 저는 권하지 않습니다. 대신 production 계약을 그대로 유지하면서 반드시:

n_top
n_bottom
n_overlap_removed
min_leg_n_observed

를 저장하십시오.

그리고 문서에:

min_cross_section_n=30은 threshold 계산 전 단면 크기 조건이며, overlap 제거 후 leg 크기의 하한을 보장하지 않는다. Frozen v2는 backtest-parity를 위해 non-empty leg만 요구하며 leg-size diagnostics를 필수 저장한다.

라고 적는 것이 정확합니다.

3. §8의 “A^Q null variance가 0.2N에만 의존”은 반드시 수정해야 합니다

이건 새로 발견한 가장 명확한 수학적 문구 오류입니다.

현재 §8은:

A^Q의 null 분산이 leg 크기(0.2N)에만 의존하고 B와 무관

이라고 설명합니다. 그런데 이 결과는 파일럿에서 사용한 fixed-k argsort 정의에 대한 것입니다. Production 정의는 inclusive 20/80 percentile threshold라 ties에 따라 leg 크기가 변합니다.

따라서 다음처럼 바꾸는 것이 정확합니다.

파일럿 v3의 fixed-k 근사에서는 A^Q null coupling이 관측되지 않았다. Frozen production 정의는 inclusive percentile-threshold membership이므로 tie-heavy signal에서 leg size가 가변적일 수 있다. 따라서 production implementation acceptance에서 permutation-null B-coupling을 별도로 재검증한다.

Core 선택을 다시 열 필요는 없습니다. 다만 pilot estimator와 frozen estimator가 완전히 같은 수식인 것처럼 쓰면 안 됩니다.

4. ILLIQ의 observation set도 수학적으로 닫아야 합니다

현재:

ILLIQ20=mean
obs
	​

DollarVolume
∣r∣
	​


인데 obs가 정확히 무엇인지 완전히 정의되지 않았습니다.

다음이 가장 정확합니다.

D
i,t
	​

={d∈[t−19,t]:r
i,d
	​

∈R,Amount
i,d
	​

∈R,Amount
i,d
	​

>0}
ILLIQ20
i,t
	​

=
⎩
⎨
⎧
	​

∣D
i,t
	​

∣
1
	​

d∈D
i,t
	​

∑
	​

Amount
i,d
	​

∣r
i,d
	​

∣
	​

,
NaN,
	​

∣D
i,t
	​

∣≥10
otherwise
	​


그러면 min_obs=10이 정확히 무엇을 세는지가 명백해집니다.

5. T의 상한은 “근사적”이 아니라 정확합니다

현재 문서에는:

0≤T≤1 (근사적으로 상한 1)

이라고 되어 있습니다.

하지만 두 날짜 모두:

∥
w
~
t
	​

∥
1
	​

=∥
w
~
t−1
	​

∥
1
	​

=1

이므로 삼각부등식으로

∥
w
~
t
	​

−
w
~
t−1
	​

∥
1
	​

≤∥
w
~
t
	​

∥
1
	​

+∥
w
~
t−1
	​

∥
1
	​

=2

따라서

0≤T
t
	​

≤1
	​


은 정확한 bound입니다.

“근사적으로”를 삭제하세요. 작은 표현 차이지만 frozen 수학 명세에서는 수정해야 합니다.

추가로 한 건은 repo에서 반드시 확인해야 합니다

이것은 아직 제가 문서만으로 확정 오류라고 단정하지는 않지만, 구현 전에 반드시 확인해야 합니다.

현재 descriptor의 J
t
	​

는 finite(S)인 zero-valued signal도 포함합니다. 반면 최신 ASB 설계 문서는 simple backtest 쪽에서 isfinite(combo) & |combo|>0으로 signal cell을 더 좁힌다고 기록합니다.

따라서 §6의

“ASB backtest quantile 계약과 동일”

이라는 주장이 실제 simple.py에서 zero signal을 quantile population에서 제외하는지 직접 확인되어야 합니다.

만약 backtest가 zero를 제외한다면 둘 중 하나를 명확히 결정해야 합니다.

Spread도 zero를 제외해 완전한 backtest parity를 유지하거나,
Spread는 finite-zero를 포함하되 selection rule만 동일하다고 표현을 낮추기.

binary/sparse formula가 실제 존재하므로 이 차이는 숫자에 영향을 줄 수 있습니다. 이 부분은 read-only repo 확인이 필요합니다.

최종 판정

앞서 제시한 수정사항에 추가로 확실히 필요한 것은 위 5건입니다.

그중 중요도는:

필수 A급

E
t
	​

 eligible-day aggregation + T split boundary
A^Q post-overlap leg diagnostics
fixed-k pilot과 production threshold의 null-variance 서술 분리
ILLIQ obs 정확한 정의

수학 정밀화지만 반드시 수정

T의 [0,1] exact bound

그리고 backtest의 zero-signal eligibility 한 건만 repo 원문과 마지막으로 대조하십시오.

이것까지 닫히면 저는 더 이상 descriptor 정의 자체에서 freeze를 막을 만한 실질적인 specification hole은 없다고 판단하겠습니다.
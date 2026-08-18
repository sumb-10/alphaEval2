# Alpha101 - Canonical Formulas and Implementation Notes
> Source: Zura Kakushadze, **101 Formulaic Alphas** (2015), Appendix A (formulas on PDF pp. 8-15; operator/input definitions on pp. 15-16).  
> This document preserves the paper formulas as the canonical representation and adds only implementation notes needed for reproducible coding.
## 1. Canonical implementation rules
1. **Keep the paper formula unchanged as `canonical_formula`.** Do not simplify algebraically redundant-looking terms. Some formulas intentionally contain expressions that look redundant (for example, Alpha #59, #66, #89, #100).
2. **Day/window parameters: use `floor`, never round-to-nearest.** Appendix A explicitly states for the generic time-series day parameter `d` that a non-integer number of days is converted to `floor(d)`. Because the formulas also pass fractional day counts to named time-series functions such as `correlation`, `delta`, `decay_linear`, and `sum`, use one parser-level `floor_days(d)` rule for every argument whose semantic role is a trading-day count/window length: `delay`, `correlation`, `covariance`, `delta`, `decay_linear`, `ts_min`, `ts_max`, `ts_argmax`, `ts_argmin`, `ts_rank`, `sum`, `product`, `stddev`, and rolling `min/max`. This is the canonical implementation policy used by this document; coefficients such as `0.728317`, `0.318108`, etc. are **not** day counts and must not be floored.
3. Recommended representation: store both:
   - `canonical_formula`: exact paper expression with original decimals.
   - `resolved_formula` or parsed AST: day/window literals transformed by `d_int = floor(d)`.
4. **`^` means exponentiation.** Do not map it to Python bitwise XOR.
5. Expressions are **case-insensitive** according to the paper (`Ts_Rank`, `ts_rank`, `Sign`, `sign`, etc. are equivalent names).
6. `rank`, `scale`, and `indneutralize` are cross-sectional operations evaluated independently for each date. Time-series operators operate independently per instrument over the trailing window.
7. Boolean comparisons and ternaries must be vectorized elementwise. Formulas that return a comparison directly (e.g. #61, #75, #79, #95) require a numeric convention such as `True -> 1`, `False -> 0`; the paper does not separately spell out this cast, so record the convention explicitly in the implementation.
8. **Do not silently replace missing inputs.** In particular, `adv{d}` is average daily **dollar volume**, not rolling mean of raw share volume; `cap` is market capitalization; `IndClass` requires sector/industry/subindustry labels. If unavailable, mark the affected alpha unsupported or document an explicit proxy as a non-canonical variant.
### Floor examples
- Alpha #58: `correlation(..., 3.92795) -> correlation(..., 3)`, `decay_linear(..., 7.89291) -> 7`, `Ts_Rank(..., 5.50322) -> 5`.
- Alpha #65: `sum(adv60, 8.6911) -> 8`, `correlation(..., 6.40374) -> 6`, `ts_min(open, 13.635) -> 13`.
- Alpha #84: `ts_max(vwap, 15.3217) -> 15`, `Ts_Rank(..., 20.7127) -> 20`, `delta(close, 4.96796) -> 4`.
## 2. Operators and semantics from the paper
| Operator | Paper semantics |
|---|---|
| `abs(x)`, `log(x)`, `sign(x)` | standard definitions |
| `+`, `-`, `*`, `/`, `>`, `<`, `==`, `||`, `cond ? y : z` | standard arithmetic / comparison / logical / ternary operators |
| `rank(x)` | cross-sectional rank |
| `delay(x, d)` | value of `x` `d` days ago |
| `correlation(x, y, d)` | time-series correlation of `x` and `y` over the past `d` days |
| `covariance(x, y, d)` | time-series covariance of `x` and `y` over the past `d` days |
| `scale(x, a=1)` | cross-sectionally rescale `x` so that `sum(abs(x)) = a` |
| `delta(x, d)` | today's `x` minus `x` `d` days ago |
| `signedpower(x, a)` | `x^a` as written in the paper |
| `decay_linear(x, d)` | linearly decaying weighted moving average over the past `d` days; weights `d, d-1, ..., 1`, normalized to sum to 1 |
| `indneutralize(x, g)` | cross-sectional demeaning within each group `g` |
| `ts_min(x, d)` / `ts_max(x, d)` | rolling min / max over the past `d` days |
| `ts_argmax(x, d)` / `ts_argmin(x, d)` | which day the rolling max / min occurred on |
| `ts_rank(x, d)` | time-series rank in the past `d` days |
| `min(x, d)` / `max(x, d)` | paper aliases for `ts_min(x,d)` / `ts_max(x,d)` when the second argument is a day count |
| `sum(x, d)` | time-series sum over the past `d` days |
| `product(x, d)` | time-series product over the past `d` days |
| `stddev(x, d)` | moving time-series standard deviation over the past `d` days |

**Important overload note:** formulas #71, #73, #76, #77, #82, #87, #88, #92, and #96 use `min/max` with **two expressions**, which cannot be interpreted as a rolling day-window alias. For those occurrences, implement pointwise elementwise `min/max`. This behavior is implied by the formulas but is not separately defined in Appendix A.
## 3. Input data
| Input | Definition in paper |
|---|---|
| `returns` | daily close-to-close returns |
| `open`, `close`, `high`, `low`, `volume` | standard daily price and volume data |
| `vwap` | daily volume-weighted average price |
| `cap` | market capitalization |
| `adv{d}` | average daily **dollar volume** over the past `d` days |
| `IndClass.level` | sector / industry / subindustry classification used by `indneutralize` |

Special dependencies in the 101 formulas:
- `IndClass`: 18 alphas - 48, 58, 59, 63, 67, 69, 70, 76, 79, 80, 82, 87, 89, 90, 91, 93, 97, 100
- `cap`: 1 alpha - 56
- `adv{d}`: 45 alphas

The paper explicitly notes that multiple `IndClass` occurrences within the same alpha do **not** have to correspond to the same industry-classification system.
## 4. Execution-timing note
The paper identifies **Alpha #42, #48, #53, and #54 as delay-0 alphas**, intended to be traded at or as close as possible to the close of the day for which they are computed. Keep this as metadata; do not modify the formulas when ASB applies a common execution protocol.
## 5. Semantics the paper does not fully specify
For reproducible ASB implementation, do **not** silently choose these details. Fix them in code/config and test them against a trusted reference implementation where possible:
- exact normalization and tie handling for cross-sectional `rank`;
- exact normalization, tie handling, and current-observation convention for `ts_rank`;
- 0-based vs 1-based output and tie handling for `ts_argmax/ts_argmin`;
- `ddof` / sample-vs-population convention for `stddev` and `covariance`;
- NaN propagation, `min_periods`, suspension/missing-data behavior;
- division-by-zero / invalid-log / invalid-power handling;
- exact construction of dollar volume for `adv{d}` if the dataset does not provide traded amount directly.
## 6. Canonical Alpha101 formulas

### Alpha #1-#20

#### Alpha #1

```text
(rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)
```

#### Alpha #2

```text
(-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))
```

#### Alpha #3

```text
(-1 * correlation(rank(open), rank(volume), 10))
```

#### Alpha #4

```text
(-1 * Ts_Rank(rank(low), 9))
```

#### Alpha #5

```text
(rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))
```

#### Alpha #6

```text
(-1 * correlation(open, volume, 10))
```

#### Alpha #7

```text
((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))
```

#### Alpha #8

```text
(-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) * sum(returns, 5)), 10))))
```

#### Alpha #9

```text
((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))
```

#### Alpha #10

```text
rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))
```

#### Alpha #11

```text
((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(delta(volume, 3)))
```

#### Alpha #12

```text
(sign(delta(volume, 1)) * (-1 * delta(close, 1)))
```

#### Alpha #13

```text
(-1 * rank(covariance(rank(close), rank(volume), 5)))
```

#### Alpha #14

```text
((-1 * rank(delta(returns, 3))) * correlation(open, volume, 10))
```

#### Alpha #15

```text
(-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))
```

#### Alpha #16

```text
(-1 * rank(covariance(rank(high), rank(volume), 5)))
```

#### Alpha #17

```text
(((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1))) * rank(ts_rank((volume / adv20), 5)))
```

#### Alpha #18

```text
(-1 * rank(((stddev(abs((close - open)), 5) + (close - open)) + correlation(close, open, 10))))
```

#### Alpha #19

```text
((-1 * sign(((close - delay(close, 7)) + delta(close, 7)))) * (1 + rank((1 + sum(returns, 250)))))
```

#### Alpha #20

```text
(((-1 * rank((open - delay(high, 1)))) * rank((open - delay(close, 1)))) * rank((open - delay(low, 1))))
```

### Alpha #21-#40

#### Alpha #21

```text
((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : (((1 < (volume / adv20)) || ((volume / adv20) == 1)) ? 1 : (-1 * 1))))
```

#### Alpha #22

```text
(-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))
```

#### Alpha #23

```text
(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)
```

#### Alpha #24

```text
((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) || ((delta((sum(close, 100) / 100), 100) / delay(close, 100)) == 0.05)) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))
```

#### Alpha #25

```text
rank(((((-1 * returns) * adv20) * vwap) * (high - close)))
```

#### Alpha #26

```text
(-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))
```

#### Alpha #27

```text
((0.5 < rank((sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0))) ? (-1 * 1) : 1)
```

#### Alpha #28

```text
scale(((correlation(adv20, low, 5) + ((high + low) / 2)) - close))
```

#### Alpha #29

```text
(min(product(rank(rank(scale(log(sum(ts_min(rank(rank((-1 * rank(delta((close - 1), 5))))), 2), 1))))), 1), 5) + ts_rank(delay((-1 * returns), 6), 5))
```

#### Alpha #30

```text
(((1.0 - rank(((sign((close - delay(close, 1))) + sign((delay(close, 1) - delay(close, 2)))) + sign((delay(close, 2) - delay(close, 3)))))) * sum(volume, 5)) / sum(volume, 20))
```

#### Alpha #31

```text
((rank(rank(rank(decay_linear((-1 * rank(rank(delta(close, 10)))), 10)))) + rank((-1 * delta(close, 3)))) + sign(scale(correlation(adv20, low, 12))))
```

#### Alpha #32

```text
(scale(((sum(close, 7) / 7) - close)) + (20 * scale(correlation(vwap, delay(close, 5), 230))))
```

#### Alpha #33

```text
rank((-1 * ((1 - (open / close))^1)))
```

#### Alpha #34

```text
rank(((1 - rank((stddev(returns, 2) / stddev(returns, 5)))) + (1 - rank(delta(close, 1)))))
```

#### Alpha #35

```text
((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) * (1 - Ts_Rank(returns, 32)))
```

#### Alpha #36

```text
(((((2.21 * rank(correlation((close - open), delay(volume, 1), 15))) + (0.7 * rank((open - close)))) + (0.73 * rank(Ts_Rank(delay((-1 * returns), 6), 5)))) + rank(abs(correlation(vwap, adv20, 6)))) + (0.6 * rank((((sum(close, 200) / 200) - open) * (close - open)))))
```

#### Alpha #37

```text
(rank(correlation(delay((open - close), 1), close, 200)) + rank((open - close)))
```

#### Alpha #38

```text
((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))
```

#### Alpha #39

```text
((-1 * rank((delta(close, 7) * (1 - rank(decay_linear((volume / adv20), 9)))))) * (1 + rank(sum(returns, 250))))
```

#### Alpha #40

```text
((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))
```

### Alpha #41-#60

#### Alpha #41

```text
(((high * low)^0.5) - vwap)
```

#### Alpha #42

```text
(rank((vwap - close)) / rank((vwap + close)))
```

#### Alpha #43

```text
(ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))
```

#### Alpha #44

```text
(-1 * correlation(high, rank(volume), 5))
```

#### Alpha #45

```text
(-1 * ((rank((sum(delay(close, 5), 20) / 20)) * correlation(close, volume, 2)) * rank(correlation(sum(close, 5), sum(close, 20), 2))))
```

#### Alpha #46

```text
((0.25 < (((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10))) ? (-1 * 1) : (((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < 0) ? 1 : ((-1 * 1) * (close - delay(close, 1)))))
```

#### Alpha #47

```text
((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) / (sum(high, 5) / 5))) - rank((vwap - delay(vwap, 5))))
```

#### Alpha #48

```text
(indneutralize(((correlation(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1)) / close), IndClass.subindustry) / sum(((delta(close, 1) / delay(close, 1))^2), 250))
```

#### Alpha #49

```text
(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.1)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))
```

#### Alpha #50

```text
(-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))
```

#### Alpha #51

```text
(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.05)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))
```

#### Alpha #52

```text
((((-1 * ts_min(low, 5)) + delay(ts_min(low, 5), 5)) * rank(((sum(returns, 240) - sum(returns, 20)) / 220))) * ts_rank(volume, 5))
```

#### Alpha #53

```text
(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))
```

#### Alpha #54

```text
((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))
```

#### Alpha #55

```text
(-1 * correlation(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12)))), rank(volume), 6))
```

#### Alpha #56

```text
(0 - (1 * (rank((sum(returns, 10) / sum(sum(returns, 2), 3))) * rank((returns * cap)))))
```

#### Alpha #57

```text
(0 - (1 * ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))))
```

#### Alpha #58

```text
(-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.sector), volume, 3.92795), 7.89291), 5.50322))
```

#### Alpha #59

```text
(-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(((vwap * 0.728317) + (vwap * (1 - 0.728317))), IndClass.industry), volume, 4.25197), 16.2289), 8.19648))
```

#### Alpha #60

```text
(0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume)))) - scale(rank(ts_argmax(close, 10))))))
```

### Alpha #61-#80

#### Alpha #61

```text
(rank((vwap - ts_min(vwap, 16.1219))) < rank(correlation(vwap, adv180, 17.9282)))
```

#### Alpha #62

```text
((rank(correlation(vwap, sum(adv20, 22.4101), 9.91009)) < rank(((rank(open) + rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)
```

#### Alpha #63

```text
((rank(decay_linear(delta(IndNeutralize(close, IndClass.industry), 2.25164), 8.22237)) - rank(decay_linear(correlation(((vwap * 0.318108) + (open * (1 - 0.318108))), sum(adv180, 37.2467), 13.557), 12.2883))) * -1)
```

#### Alpha #64

```text
((rank(correlation(sum(((open * 0.178404) + (low * (1 - 0.178404))), 12.7054), sum(adv120, 12.7054), 16.6208)) < rank(delta(((((high + low) / 2) * 0.178404) + (vwap * (1 - 0.178404))), 3.69741))) * -1)
```

#### Alpha #65

```text
((rank(correlation(((open * 0.00817205) + (vwap * (1 - 0.00817205))), sum(adv60, 8.6911), 6.40374)) < rank((open - ts_min(open, 13.635)))) * -1)
```

#### Alpha #66

```text
((rank(decay_linear(delta(vwap, 3.51013), 7.23052)) + Ts_Rank(decay_linear(((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))), 11.4157), 6.72611)) * -1)
```

#### Alpha #67

```text
((rank((high - ts_min(high, 2.14593)))^rank(correlation(IndNeutralize(vwap, IndClass.sector), IndNeutralize(adv20, IndClass.subindustry), 6.02936))) * -1)
```

#### Alpha #68

```text
((Ts_Rank(correlation(rank(high), rank(adv15), 8.91644), 13.9333) < rank(delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)
```

#### Alpha #69

```text
((rank(ts_max(delta(IndNeutralize(vwap, IndClass.industry), 2.72412), 4.79344))^Ts_Rank(correlation(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 4.92416), 9.0615)) * -1)
```

#### Alpha #70

```text
((rank(delta(vwap, 1.29456))^Ts_Rank(correlation(IndNeutralize(close, IndClass.industry), adv50, 17.8256), 17.9171)) * -1)
```

#### Alpha #71

```text
max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180, 12.0647), 18.0175), 4.20501), 15.6948), Ts_Rank(decay_linear((rank(((low + open) - (vwap + vwap)))^2), 16.4662), 4.4388))
```

#### Alpha #72

```text
(rank(decay_linear(correlation(((high + low) / 2), adv40, 8.93345), 10.1519)) / rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671), 2.95011)))
```

#### Alpha #73

```text
(max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)), Ts_Rank(decay_linear(((delta(((open * 0.147155) + (low * (1 - 0.147155))), 2.03608) / ((open * 0.147155) + (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)
```

#### Alpha #74

```text
((rank(correlation(close, sum(adv30, 37.4843), 15.1365)) < rank(correlation(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4791))) * -1)
```

#### Alpha #75

```text
(rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low), rank(adv50), 12.4413)))
```

#### Alpha #76

```text
(max(rank(decay_linear(delta(vwap, 1.24383), 11.8259)), Ts_Rank(decay_linear(Ts_Rank(correlation(IndNeutralize(low, IndClass.sector), adv81, 8.14941), 19.569), 17.1543), 19.383)) * -1)
```

#### Alpha #77

```text
min(rank(decay_linear(((((high + low) / 2) + high) - (vwap + high)), 20.0451)), rank(decay_linear(correlation(((high + low) / 2), adv40, 3.1614), 5.64125)))
```

#### Alpha #78

```text
(rank(correlation(sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428), sum(adv40, 19.7428), 6.83313))^rank(correlation(rank(vwap), rank(volume), 5.77492)))
```

#### Alpha #79

```text
(rank(delta(IndNeutralize(((close * 0.60733) + (open * (1 - 0.60733))), IndClass.sector), 1.23438)) < rank(correlation(Ts_Rank(vwap, 3.60973), Ts_Rank(adv150, 9.18637), 14.6644)))
```

#### Alpha #80

```text
((rank(Sign(delta(IndNeutralize(((open * 0.868128) + (high * (1 - 0.868128))), IndClass.industry), 4.04545)))^Ts_Rank(correlation(high, adv10, 5.11456), 5.53756)) * -1)
```

### Alpha #81-#100

#### Alpha #81

```text
((rank(Log(product(rank((rank(correlation(vwap, sum(adv10, 49.6054), 8.47743))^4)), 14.9655))) < rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1)
```

#### Alpha #82

```text
(min(rank(decay_linear(delta(open, 1.46063), 14.8717)), Ts_Rank(decay_linear(correlation(IndNeutralize(volume, IndClass.sector), ((open * 0.634196) + (open * (1 - 0.634196))), 17.4842), 6.92131), 13.4283)) * -1)
```

#### Alpha #83

```text
((rank(delay(((high - low) / (sum(close, 5) / 5)), 2)) * rank(rank(volume))) / (((high - low) / (sum(close, 5) / 5)) / (vwap - close)))
```

#### Alpha #84

```text
SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))
```

#### Alpha #85

```text
(rank(correlation(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 9.61331))^rank(correlation(Ts_Rank(((high + low) / 2), 3.70596), Ts_Rank(volume, 10.1595), 7.11408)))
```

#### Alpha #86

```text
((Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) < rank(((open + close) - (vwap + open)))) * -1)
```

#### Alpha #87

```text
(max(rank(decay_linear(delta(((close * 0.369701) + (vwap * (1 - 0.369701))), 1.91233), 2.65461)), Ts_Rank(decay_linear(abs(correlation(IndNeutralize(adv81, IndClass.industry), close, 13.4132)), 4.89768), 14.4535)) * -1)
```

#### Alpha #88

```text
min(rank(decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), 8.06882)), Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728), Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))
```

#### Alpha #89

```text
(Ts_Rank(decay_linear(correlation(((low * 0.967285) + (low * (1 - 0.967285))), adv10, 6.94279), 5.51607), 3.79744) - Ts_Rank(decay_linear(delta(IndNeutralize(vwap, IndClass.industry), 3.48158), 10.1466), 15.3012))
```

#### Alpha #90

```text
((rank((close - ts_max(close, 4.66719)))^Ts_Rank(correlation(IndNeutralize(adv40, IndClass.subindustry), low, 5.38375), 3.21856)) * -1)
```

#### Alpha #91

```text
((Ts_Rank(decay_linear(decay_linear(correlation(IndNeutralize(close, IndClass.industry), volume, 9.74928), 16.398), 3.83219), 4.8667) - rank(decay_linear(correlation(vwap, adv30, 4.01303), 2.6809))) * -1)
```

#### Alpha #92

```text
min(Ts_Rank(decay_linear(((((high + low) / 2) + close) < (low + open)), 14.7221), 18.8683), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555), 6.94024), 6.80584))
```

#### Alpha #93

```text
(Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.industry), adv81, 17.4193), 19.848), 7.54455) / rank(decay_linear(delta(((close * 0.524434) + (vwap * (1 - 0.524434))), 2.77377), 16.2664)))
```

#### Alpha #94

```text
((rank((vwap - ts_min(vwap, 11.5783)))^Ts_Rank(correlation(Ts_Rank(vwap, 19.6462), Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)
```

#### Alpha #95

```text
(rank((open - ts_min(open, 12.4105))) < Ts_Rank((rank(correlation(sum(((high + low) / 2), 19.1351), sum(adv40, 19.1351), 12.8742))^5), 11.7584))
```

#### Alpha #96

```text
(max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83878), 4.16783), 8.38151), Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404), Ts_Rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)
```

#### Alpha #97

```text
((rank(decay_linear(delta(IndNeutralize(((low * 0.721001) + (vwap * (1 - 0.721001))), IndClass.industry), 3.3705), 20.4523)) - Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low, 7.87871), Ts_Rank(adv60, 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1)
```

#### Alpha #98

```text
(rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088)) - rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187), 8.62571), 6.95668), 8.07206)))
```

#### Alpha #99

```text
((rank(correlation(sum(((high + low) / 2), 19.8975), sum(adv60, 19.8975), 8.8136)) < rank(correlation(low, volume, 6.28259))) * -1)
```

#### Alpha #100

```text
(0 - (1 * (((1.5 * scale(indneutralize(indneutralize(rank(((((close - low) - (high - close)) / (high - low)) * volume)), IndClass.subindustry), IndClass.subindustry))) - scale(indneutralize((correlation(close, rank(adv20), 5) - rank(ts_argmin(close, 30))), IndClass.subindustry))) * (volume / adv20))))
```

### Alpha #101-#101

#### Alpha #101

```text
((close - open) / ((high - low) + .001))
```
## 7. Verification record
- Extracted all **101/101** formulas from Appendix A; numbering verified to be contiguous from #1 through #101.
- Extracted the formulas independently with **PyMuPDF** and **pdftotext**; after removing printed page-number artifacts, the two normalized extractions matched **101/101 formulas exactly**.
- Rendered PDF pages 8-16 and visually checked the formula/definition pages, including the decimal-window formulas and Appendix A operator definitions.
- Programmatically checked balanced parentheses for all 101 extracted formulas.
- Preserved suspicious-looking/redundant expressions exactly as printed rather than “correcting” them.

"""tensor_eval.py — 패널 프리로드(텐서) 방식 표현식 평가기. 별도 실험 트랙.

원시 필드 10개를 시작 시 1회만 메모리에 적재(dense (일자 × 종목) 패널)하고,
gplearn이 생성하는 Qlib 표현식 문자열을 직접 파싱·계산한다.

qlib(0.9.0)과의 일치를 위해 소스 수준에서 확인한 의미론을 그대로 따른다:
  * 모든 rolling은 min_periods=1                       (qlib/data/ops.py Rolling)
  * N==0 은 expanding, Ref(x,0)은 종목별 첫 관측값     (ops.py)
  * Greater/Less = np.maximum/np.minimum               (비교 아님!)
  * Sign 은 float32 캐스팅 후 np.sign                  (ops.py Sign)
  * Slope/Rsquare/Resi 는 qlib의 Cython 함수를 그대로 호출
  * Rsquare 는 rolling std ≈ 0 (atol=2e-5) 위치를 NaN 마스킹
  * WMA = nanmean(w·x), w=(1..len)/합 — rolling.apply(raw=True) 의미론
  * EMA = ewm(span=N, min_periods=1).mean()
  * 표현식 결과는 최종적으로 float32 캐스팅            (LocalExpressionProvider)
  * **warm-up 절단 미러링**: qlib은 트리의 get_extended_window_size 만큼만
    과거를 붙여 계산한다(EMA·rolling var 등 스트리밍 연산의 값이 이 절단에
    의존). 표현식마다 동일한 좌측 절단 위치에서 계산을 시작한다.
  * universe(csi300 등)는 값 계산 후 membership span으로 행 마스킹 (inst_calculator)

정밀도 구현 노트:
  * elem/pair 연산은 ndarray로 수행 (pandas DataFrame 블록 경로의 ulp 차이 회피)
  * 윈도우 벡터화는 전치(N,T) 연속 배열로 수행 — strided 축의 순차 합산 대신
    numpy pairwise 합산이 되어 qlib(rolling.apply의 압축 배열 연산)과 비트 일치.
    NaN→0 치환은 부동소수 덧셈의 정확한 항등원이므로 합산 결과를 바꾸지 않는다.

이 트랙은 '결과 불변' 보장이 아니라 '최대한 일치'가 목표다.
일치 수준은 scripts/verify_tensor_eval.py 가 연산자·IC 단위로 측정한다.
"""

import re
import warnings

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from qlib.data import D
from qlib.data._libs.rolling import rolling_slope, rolling_rsquare, rolling_resi
from qlib.data._libs.expanding import expanding_slope, expanding_rsquare, expanding_resi

FEATURE_LIST = ["$adjclose", "$amount", "$change", "$close", "$factor",
                "$high", "$low", "$open", "$volume", "$vwap"]

WARMUP_START = "2005-01-04"        # 캘린더 시작 — 어떤 중첩 rolling의 절단점도 커버
LABEL_EXPR = "Ref($close, -1)/$close - 1"

# ---------------------------------------------------------------- 파서
_TOKEN = re.compile(r"\s*(\$[a-z_]+|[A-Za-z_][A-Za-z_0-9]*|-?\d+\.\d*|-?\d+|[(),])")


def parse_expression(s):
    """'Div(Mean($close, 30), $volume)' → 중첩 튜플 트리."""
    tokens = _TOKEN.findall(s)
    if "".join(tokens) != re.sub(r"\s+", "", s):
        raise ValueError(f"unparseable characters in: {s!r}")
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def take():
        t = peek()
        pos[0] += 1
        return t

    def expr():
        t = take()
        if t is None:
            raise ValueError("unexpected end of expression")
        if t.startswith("$"):
            return ("f", t)
        if re.fullmatch(r"-?\d+\.\d*", t):
            return ("c", float(t))
        if re.fullmatch(r"-?\d+", t):
            return ("c", int(t))
        if t in "(),":
            raise ValueError(f"unexpected token {t!r}")
        if take() != "(":
            raise ValueError(f"expected '(' after {t}")
        args = [expr()]
        while peek() == ",":
            take()
            args.append(expr())
        if take() != ")":
            raise ValueError(f"expected ')' in {t}(...)")
        return ("call", t, args)

    tree = expr()
    if pos[0] != len(tokens):
        raise ValueError(f"trailing tokens in: {s!r}")
    return tree


_ELEM = {"Abs", "Sign", "Log"}
_PAIR = {"Add": "add", "Sub": "subtract", "Mul": "multiply", "Div": "divide",
         "Power": "power", "Greater": "maximum", "Less": "minimum"}
# 결과가 입력의 정확한 함수가 아닌(초월함수 근사 경로가 pandas dispatch에 따라
# 달라지는) 연산 — qlib과 동일하게 pd.Series 단위로 계산해야 비트 일치한다.
_PAIR_VIA_SERIES = {"Power"}
_ROLL_NATIVE = {"Mean": "mean", "Sum": "sum", "Std": "std", "Var": "var",
                "Skew": "skew", "Kurt": "kurt", "Min": "min", "Max": "max",
                "Med": "median"}
_ROLL_ALL = set(_ROLL_NATIVE) | {"Ref", "Delta", "Slope", "Rsquare", "Resi",
                                 "WMA", "EMA", "IdxMax", "IdxMin", "Mad"}


def extended_window(node):
    """qlib ops.py 의 get_extended_window_size 를 트리 그대로 미러링."""
    kind = node[0]
    if kind in ("f", "c"):
        return (0, 0)
    name, args = node[1], node[2]
    if name in _ELEM:
        return extended_window(args[0])
    if name in _PAIR:
        l0, l1 = extended_window(args[0])
        r0, r1 = extended_window(args[1])
        return (max(l0, r0), max(l1, r1))
    if name in _ROLL_ALL:
        if len(args) != 2 or args[1][0] != "c":
            raise ValueError(f"{name} expects (expr, int window)")
        n = args[1][1]
        lft, rght = extended_window(args[0])
        if n == 0:
            return (lft, rght)
        if name == "Ref":                       # ops.py Ref.get_extended_window_size
            return (max(lft + n, lft), max(rght - n, rght))
        if isinstance(n, float) and 0 < n < 1:  # ops.py Rolling (ewm alpha)
            size = int(np.log(1e-6) / np.log(1 - n))
            return (max(lft + size - 1, lft), rght)
        return (max(lft + n - 1, lft), rght)    # ops.py Rolling
    raise ValueError(f"unknown operator {name}")


# ---------------------------------------------------------------- qlib fn 재현 (짧은 창 정확 계산용)
def _fn_wma(x):
    w = np.arange(len(x)) + 1
    w = w / w.sum()
    return np.nanmean(w * x)


def _fn_idxmax(x):
    return x.argmax() + 1


def _fn_idxmin(x):
    return x.argmin() + 1


def _fn_mad(x):
    x1 = x[~np.isnan(x)]
    return np.mean(np.abs(x1 - x1.mean()))


def _fn_ema(x):    # qlib EMA의 expanding(N==0) 분기 전용
    a = 1 - 2 / (1 + len(x))
    w = a ** np.arange(len(x))[::-1]
    w /= w.sum()
    return np.nansum(w * x)


_SHORT_FN = {"wma": _fn_wma, "idxmax": _fn_idxmax, "idxmin": _fn_idxmin, "mad": _fn_mad}


def _first_valid(vals):
    """열별 첫 관측 행 (전부 NaN이면 T)."""
    notna = ~np.isnan(vals)
    return np.where(notna.any(axis=0), notna.argmax(axis=0), vals.shape[0])


class TensorEvaluator:
    """패널 프리로드 표현식 평가기. qlib은 이미 init 되어 있어야 한다."""

    def __init__(self, start_time, end_time, market="all",
                 warmup_start=WARMUP_START, right_buffer_days=20, block_cols=256):
        self.start_time = pd.Timestamp(start_time)
        self.end_time = pd.Timestamp(end_time)
        self.market = market
        self.block_cols = block_cols

        end_ext = str((self.end_time + pd.Timedelta(days=right_buffer_days)).date())
        raw = D.features(D.instruments(market="all"), FEATURE_LIST,
                         start_time=warmup_start, end_time=end_ext, freq="day")
        # dense (날짜 × 종목) ndarray 패널, 원본 dtype(float32) 유지
        wide = raw["$close"].unstack(level="instrument")
        self.dates = wide.index
        self.columns = wide.columns
        self.panels = {f: np.ascontiguousarray(raw[f].unstack(level="instrument").to_numpy())
                       for f in FEATURE_LIST}
        self._s = self.dates.searchsorted(self.start_time)
        self._e = self.dates.searchsorted(self.end_time, side="right")
        self.sel_dates = self.dates[self._s:self._e]

        # 종목별 bin 커버리지 시작 행 (qlib 시리즈의 index 시작 — NaN 값이어도 행은 존재).
        # $close 첫 관측을 커버리지 시작의 근사로 사용한다.
        self._coverage_start = _first_valid(self.panels["$close"])

        # label = Ref($close,-1)/$close - 1  (positionwise — 절단 무관)
        close = self.panels["$close"]
        shifted = np.full_like(close, np.nan)
        shifted[:-1] = close[1:]
        with np.errstate(all="ignore"):
            label = np.subtract(np.divide(shifted, close), 1)
        self.label = label.astype(np.float32)[self._s:self._e]

        self.universe_mask = self._build_universe_mask(market)
        self.ic_memo = {}
        self.n_memo_hits = 0
        self.n_fallbacks = 0

    # ------------------------------------------------------------ universe span 마스킹
    def _build_universe_mask(self, market):
        spans_d = D.list_instruments(D.instruments(market=market),
                                     start_time=str(self.start_time.date()),
                                     end_time=str(self.end_time.date()),
                                     freq="day", as_list=False)
        mask = np.zeros((len(self.sel_dates), len(self.columns)), dtype=bool)
        col_pos = {c: i for i, c in enumerate(self.columns)}
        for inst, spans in spans_d.items():
            j = col_pos.get(inst)
            if j is None:
                continue
            for b, e in spans:
                i0 = self.sel_dates.searchsorted(pd.Timestamp(b))
                i1 = self.sel_dates.searchsorted(pd.Timestamp(e), side="right")
                mask[i0:i1, j] = True
        return mask

    # ------------------------------------------------------------ 공개 API
    def frame(self, expr):
        """표현식 → float32 (요청 구간 × 전 종목) DataFrame.

        LocalExpressionProvider와 동일: 트리의 extended window 만큼만 왼쪽에
        붙여 계산(warm-up 절단 미러링) → float32 캐스팅 → 구간 절단.
        """
        tree = parse_expression(expr)
        lft, rght = extended_window(tree)
        off = max(0, self._s - lft)                       # 좌측 절단 행
        hi = min(len(self.dates), self._e + rght)         # 우측 절단 행
        # 우측 절단이 중요: pandas roll_skew/roll_kurt는 배열 전체 평균으로
        # 중심화하므로 query end 이후의 행이 과거 값에 영향을 준다.
        # qlib은 정확히 [S-lft .. E+rght]만 로드한다 — 동일하게 자른다.
        res = self._eval(tree, off, hi)
        if np.isscalar(res):
            raise ValueError("constant-only expression")
        out = res.astype(np.float32)[self._s - off:self._e - off]
        return pd.DataFrame(out, index=self.sel_dates, columns=self.columns)

    # fast_eval.make_fast_parallel_evolve 가 기대하는 평가기 인터페이스 -------
    def evaluate(self, exprs):
        """표현식 리스트 → IC 리스트 (입력 순서 보존, memo 적용)."""
        return [self.ic(e) for e in exprs]

    def stats(self):
        return (f"evaluated={len(self.ic_memo)} memo_hits={self.n_memo_hits} "
                f"parse_fallbacks={self.n_fallbacks}")

    def ic(self, expr):
        """ICBacktester.calculate1 과 동일한 집계의 일별 cross-sectional IC."""
        if expr in self.ic_memo:
            self.n_memo_hits += 1
            return self.ic_memo[expr]
        try:
            F = self.frame(expr).to_numpy()
        except Exception:
            # 원본과 동일한 폴백: 실패 수식은 $close 패널로 대체
            self.n_fallbacks += 1
            F = self.panels["$close"].astype(np.float32)[self._s:self._e]
        ic = self._daily_ic(F)
        self.ic_memo[expr] = ic
        return ic

    # ------------------------------------------------------------ 트리 평가 (ndarray)
    def _eval(self, node, off, hi):
        kind = node[0]
        if kind == "f":
            try:
                return self.panels[node[1]][off:hi]
            except KeyError:
                raise ValueError(f"unknown field {node[1]}")
        if kind == "c":
            return node[1]
        name, args = node[1], node[2]

        if name == "Abs":
            return np.abs(self._eval(args[0], off, hi))
        if name == "Sign":
            return np.sign(self._eval(args[0], off, hi).astype(np.float32))
        if name == "Log":
            with np.errstate(all="ignore"):
                return np.log(self._eval(args[0], off, hi))
        if name in _PAIR:
            left = self._eval(args[0], off, hi)
            right = self._eval(args[1], off, hi)
            if np.isscalar(left) and np.isscalar(right):
                raise ValueError("constant-only expression")   # qlib도 series를 만들지 못함
            if name in _PAIR_VIA_SERIES:
                return self._pair_series_op(_PAIR[name], left, right)
            with np.errstate(all="ignore"):
                return getattr(np, _PAIR[name])(left, right)
        if name in _ROLL_ALL:
            n = args[1][1]
            if not isinstance(n, (int, np.integer)):
                raise ValueError(f"{name} window must be int, got {n!r}")
            child = self._eval(args[0], off, hi)
            if np.isscalar(child):
                raise ValueError("rolling over constant")
            return self._roll(name, child, int(n), off)
        raise ValueError(f"unknown operator {name}")

    @staticmethod
    def _pair_series_op(func, left, right):
        """qlib의 np.func(pd.Series, ...) dispatch를 열 단위로 재현."""
        f = getattr(np, func)
        arr = right if np.isscalar(left) else left
        T, N = arr.shape
        out = None
        for j in range(N):
            l = left if np.isscalar(left) else pd.Series(np.ascontiguousarray(left[:, j]))
            r = right if np.isscalar(right) else pd.Series(np.ascontiguousarray(right[:, j]))
            with np.errstate(all="ignore"):
                res = f(l, r)
            v = res.to_numpy() if hasattr(res, "to_numpy") else res
            if out is None:
                out = np.empty((T, N), dtype=v.dtype)
            out[:, j] = v
        return out

    def _series_start(self, off, T):
        """qlib per-instrument 시리즈의 시작 행 (절단 좌표계).

        시리즈 index는 bin 커버리지 ∩ 질의 구간 — 값이 NaN이어도 행은 존재하므로
        '첫 유효값'이 아니라 '커버리지 시작'이 기준이다.
        """
        return np.minimum(np.maximum(self._coverage_start - off, 0), T)

    def _roll(self, name, vals, n, off):
        if name == "Ref":
            return self._shift(vals, n, off)
        if name == "Delta":
            if n == 0:
                first = self._first_series_value(vals, off)
                return vals - first
            return vals - self._shift(vals, n, off)
        if name in _ROLL_NATIVE:
            df = pd.DataFrame(vals)
            roller = df.expanding(min_periods=1) if n == 0 else df.rolling(n, min_periods=1)
            return getattr(roller, _ROLL_NATIVE[name])().to_numpy()
        if name == "EMA":
            if n == 0:
                return self._apply_expanding(vals, _fn_ema, off)
            return pd.DataFrame(vals).ewm(span=n, min_periods=1).mean().to_numpy()
        if name in ("Slope", "Rsquare", "Resi"):
            fns = {"Slope": (rolling_slope, expanding_slope),
                   "Rsquare": (rolling_rsquare, expanding_rsquare),
                   "Resi": (rolling_resi, expanding_resi)}[name]
            out = np.empty(vals.shape, dtype=np.float64)
            for j in range(vals.shape[1]):
                col = np.ascontiguousarray(vals[:, j])
                out[:, j] = fns[0](col, n) if n != 0 else fns[1](col)
            if name == "Rsquare" and n != 0:        # ops.py Rsquare의 추가 마스킹
                std = pd.DataFrame(vals).rolling(n, min_periods=1).std().to_numpy()
                with np.errstate(invalid="ignore"):
                    out[np.isclose(std, 0, atol=2e-05)] = np.nan
            return out
        if name in ("WMA", "IdxMax", "IdxMin", "Mad"):
            kind = name.lower()
            if n == 0:
                return self._apply_expanding(vals, _SHORT_FN[kind], off)
            return self._roll_apply_vectorized(vals, n, kind, off)
        raise ValueError(f"unknown operator {name}")

    def _shift(self, vals, n, off):
        out = np.full_like(vals, np.nan)
        if n == 0:                                  # Ref(x,0): 시리즈 첫 행 값 (iloc[0] 그대로)
            out[:] = self._first_series_value(vals, off)
            return out
        if n > 0:
            out[n:] = vals[:-n]
        else:
            out[:n] = vals[-n:]
        return out

    def _first_series_value(self, vals, off):
        """qlib Ref(x,0)/Delta(x,0)의 series.iloc[0] — NaN이어도 그대로."""
        T = vals.shape[0]
        s0 = self._series_start(off, T)
        first = np.full(vals.shape[1], np.nan, dtype=vals.dtype)
        ok = s0 < T
        first[ok] = vals[s0[ok], np.where(ok)[0]]
        return first

    def _apply_expanding(self, vals, fn, off):
        """qlib expanding.apply와 동일: 시리즈 시작(커버리지 시작) 이후 구간에 적용."""
        T = vals.shape[0]
        out = np.full(vals.shape, np.nan, dtype=np.float64)
        s0s = self._series_start(off, T)
        for j in range(vals.shape[1]):
            s0 = s0s[j]
            if s0 >= T:
                continue
            col = pd.Series(vals[s0:, j])
            out[s0:, j] = col.expanding(min_periods=1).apply(fn, raw=True).to_numpy()
        return out

    def _roll_apply_vectorized(self, vals, n, kind, off):
        """rolling.apply(qlib fn, raw=True) 의 벡터화 재현.

        전치된 (종목 × 일자) 연속 배열 위에서 창 축이 메모리 연속이 되게 하여
        numpy pairwise 합산이 qlib(압축 배열 연산)과 비트 단위로 일치하게 한다.
        본체(창 길이 == n)는 블록 연산, 상장 직후 n-1일(qlib에서 창이 짧아지는
        구간)은 qlib fn을 그대로 호출한다.
        """
        T, N = vals.shape
        out = np.full((T, N), np.nan, dtype=np.float64)
        vt = np.ascontiguousarray(vals.T)                      # (N, T) — 창 축 연속
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            for j0 in range(0, N, self.block_cols):
                j1 = min(j0 + self.block_cols, N)
                win = sliding_window_view(vt[j0:j1], n, axis=1)   # (bc, T-n+1, n) 연속
                cnt = (~np.isnan(win)).sum(axis=-1)
                if kind == "wma":
                    w = (np.arange(n) + 1.0)
                    w = w / w.sum()                               # float64 — qlib과 동일
                    s = np.nansum(win * w, axis=-1)
                    r = s / cnt
                elif kind in ("idxmax", "idxmin"):
                    fn = np.argmax if kind == "idxmax" else np.argmin
                    r = (fn(win, axis=-1) + 1).astype(np.float64)
                else:                                             # mad — pandas apply는 창을 f64로 전달
                    c = np.where(cnt == 0, 1, cnt).astype(np.float64)
                    s = np.nansum(win, axis=-1, dtype=np.float64)
                    m = s / c
                    d = np.abs(win - m[..., None])
                    r = np.nansum(d, axis=-1, dtype=np.float64) / c
                r = np.where(cnt == 0, np.nan, r)
                out[n - 1:, j0:j1] = r.T
        # 시리즈 시작(커버리지 시작) 직후 n-1일: qlib에서 창 길이가 짧아지는 구간.
        # pandas apply는 창을 float64로 캐스팅해 fn에 전달하므로 동일하게 맞춘다.
        fn = _SHORT_FN[kind]
        s0s = self._series_start(off, T)
        for j in range(N):
            s0 = s0s[j]
            if s0 >= T:
                continue
            for t in range(s0, min(s0 + n - 1, T)):
                x = vals[s0:t + 1, j].astype(np.float64)
                if np.isnan(x).all():                 # min_periods=1: 유효값 0개 → 호출 안 함
                    out[t, j] = np.nan
                else:
                    out[t, j] = fn(x)
        return out

    # ------------------------------------------------------------ IC
    def _daily_ic(self, F):
        L = self.label
        valid = ~np.isnan(F) & ~np.isnan(L) & self.universe_mask   # dropna와 동일(±inf 유지)
        cnt = valid.sum(axis=1)
        f = np.where(valid, F, 0).astype(np.float64)
        l = np.where(valid, L, 0).astype(np.float64)
        with np.errstate(all="ignore"):
            sf, sl = f.sum(1), l.sum(1)
            safe = np.where(cnt == 0, 1, cnt)
            cov = (f * l).sum(1) - sf * sl / safe
            vf = (f * f).sum(1) - sf * sf / safe
            vl = (l * l).sum(1) - sl * sl / safe
            r = cov / np.sqrt(vf * vl)
        r[cnt < 2] = np.nan
        r = r[cnt >= 1]                     # 유효 쌍 0개인 날은 groupby에 등장하지 않음
        if len(r) == 0:
            return 0.0
        if np.isnan(r).mean() > 0.5:        # calculate1의 NaN 과반 방어
            return 0.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            ic = float(np.nanmean(r))
        return 0.0 if np.isnan(ic) else ic

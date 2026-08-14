"""FormulaEngine — 패널 프리로드 기반 Qlib 표현식 평가기.

Provenance: AlphaEval `scripts/tensor_eval.py` TensorEvaluator의 독립 재구현.
원본은 qlib 0.9.0 경로와 37/37 표현식 float32 비트 일치가 검증되었다
(AlphaEval/docs/new_Eval_blueprint_v2.md 부록). 여기서는 다음을 변경한다:

  1. **silent fallback 제거** — 평가 실패 시 `$close` 대체 대신
     FormulaEvalError(reason)를 발생시킨다 (Validity Gate가 hard invalid 처리).
  2. 평가 구간을 인스턴스 고정이 아니라 `compute(formula, start, end)` 호출
     단위로 일반화 — 하나의 패널로 train/valid/test 어느 split이든 평가한다.

qlib 0.9.0 의미론 미러링 (원본 조사에서 소스 수준 확인):
  * 모든 rolling: min_periods=1; N==0은 expanding; Ref(x,0)=시리즈 첫 행 값
  * Greater/Less = np.maximum/np.minimum (비교 아님)
  * Sign은 float32 캐스팅 후 np.sign
  * Slope/Rsquare/Resi는 qlib의 Cython 함수를 직접 호출 (외부 dependency)
  * Rsquare는 rolling std ≈ 0 (atol=2e-5) 위치를 NaN 마스킹
  * WMA/Mad/IdxMax/IdxMin: pandas rolling.apply(raw=True) 의미론 — 창은
    float64로 전달되고, 시리즈 시작은 '첫 유효값'이 아니라 'bin 커버리지
    시작'(값이 NaN이어도 행 존재) 기준
  * 표현식 결과는 최종 float32 캐스팅
  * warmup **좌·우 절단**: 트리의 get_extended_window_size 만큼만 계산 구간을
    확장한다 — pandas roll_skew/kurt가 배열 전체 평균으로 중심화하므로 질의
    우측 끝도 값에 영향을 준다 (qlib과 동일하게 절단해야 일치)
  * np.power는 pd.Series dispatch 경유가 qlib과 일치 (ndarray 직접 호출과 다름)

주의: qlib은 `qlib.data._libs`까지 포함해 외부 dependency로 사용한다.
AlphaEval 내부 모듈(backtest/, scripts/, ...)은 import하지 않는다.
"""
from __future__ import annotations

import re
import warnings
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from qlib.data._libs.rolling import rolling_slope, rolling_rsquare, rolling_resi
from qlib.data._libs.expanding import expanding_slope, expanding_rsquare, expanding_resi

FEATURE_LIST = ["$adjclose", "$amount", "$change", "$close", "$factor",
                "$high", "$low", "$open", "$volume", "$vwap"]

CALENDAR_START = "2005-01-04"


class FormulaEvalError(Exception):
    """formula 평가 실패 — silent fallback 금지, reason을 담아 전파."""

    def __init__(self, reason: str, formula: str = ""):
        super().__init__(f"{reason}: {formula}" if formula else reason)
        self.reason = reason
        self.formula = formula


# ---------------------------------------------------------------- 파서
_TOKEN = re.compile(r"\s*(\$[a-z_]+|[A-Za-z_][A-Za-z_0-9]*|-?\d+\.\d*|-?\d+|[(),])")


def parse_expression(s: str):
    """'Div(Mean($close, 30), $volume)' → 중첩 튜플 트리."""
    tokens = _TOKEN.findall(s)
    if "".join(tokens) != re.sub(r"\s+", "", s):
        raise FormulaEvalError("parse_error:unparseable_characters", s)
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
            raise FormulaEvalError("parse_error:unexpected_end", s)
        if t.startswith("$"):
            return ("f", t)
        if re.fullmatch(r"-?\d+\.\d*", t):
            return ("c", float(t))
        if re.fullmatch(r"-?\d+", t):
            return ("c", int(t))
        if t in "(),":
            raise FormulaEvalError(f"parse_error:unexpected_token:{t}", s)
        if take() != "(":
            raise FormulaEvalError("parse_error:expected_paren", s)
        args = [expr()]
        while peek() == ",":
            take()
            args.append(expr())
        if take() != ")":
            raise FormulaEvalError("parse_error:unclosed_call", s)
        return ("call", t, args)

    tree = expr()
    if pos[0] != len(tokens):
        raise FormulaEvalError("parse_error:trailing_tokens", s)
    return tree


_ELEM = {"Abs", "Sign", "Log"}
_PAIR = {"Add": "add", "Sub": "subtract", "Mul": "multiply", "Div": "divide",
         "Power": "power", "Greater": "maximum", "Less": "minimum"}
# pandas Series dispatch 경유가 qlib과 비트 일치하는 연산 (초월함수 근사 경로)
_PAIR_VIA_SERIES = {"Power"}
_ROLL_NATIVE = {"Mean": "mean", "Sum": "sum", "Std": "std", "Var": "var",
                "Skew": "skew", "Kurt": "kurt", "Min": "min", "Max": "max",
                "Med": "median"}
_ROLL_ALL = set(_ROLL_NATIVE) | {"Ref", "Delta", "Slope", "Rsquare", "Resi",
                                 "WMA", "EMA", "IdxMax", "IdxMin", "Mad"}


def extended_window(node) -> Tuple[int, int]:
    """qlib ops.py의 get_extended_window_size 미러 (좌, 우)."""
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
            raise FormulaEvalError(f"eval_error:{name}_expects_int_window")
        n = args[1][1]
        lft, rght = extended_window(args[0])
        if n == 0:
            return (lft, rght)
        if name == "Ref":
            return (max(lft + n, lft), max(rght - n, rght))
        if isinstance(n, float) and 0 < n < 1:
            size = int(np.log(1e-6) / np.log(1 - n))
            return (max(lft + size - 1, lft), rght)
        return (max(lft + n - 1, lft), rght)
    raise FormulaEvalError(f"eval_error:unknown_operator:{name}")


# ------------------------------------------------- qlib fn 재현 (짧은 창)
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


def _fn_ema(x):
    a = 1 - 2 / (1 + len(x))
    w = a ** np.arange(len(x))[::-1]
    w /= w.sum()
    return np.nansum(w * x)


_SHORT_FN = {"wma": _fn_wma, "idxmax": _fn_idxmax, "idxmin": _fn_idxmin, "mad": _fn_mad}


def _first_valid(vals: np.ndarray) -> np.ndarray:
    notna = ~np.isnan(vals)
    return np.where(notna.any(axis=0), notna.argmax(axis=0), vals.shape[0])


class FormulaEngine:
    """패널 1회 적재 + 임의 구간 formula 평가. qlib은 bootstrap 완료 상태여야 한다."""

    def __init__(self, panel_start: str, panel_end: str,
                 warmup_start: Optional[str] = None,
                 right_buffer_days: int = 20, block_cols: int = 256):
        from qlib.data import D
        self.block_cols = block_cols
        w0 = warmup_start or CALENDAR_START
        end_ext = str((pd.Timestamp(panel_end) + pd.Timedelta(days=right_buffer_days)).date())
        raw = D.features(D.instruments(market="all"), FEATURE_LIST,
                         start_time=w0, end_time=end_ext, freq="day")
        wide = raw["$close"].unstack(level="instrument")
        self.dates: pd.DatetimeIndex = wide.index
        self.columns: pd.Index = wide.columns
        self.panels: Dict[str, np.ndarray] = {
            f: np.ascontiguousarray(raw[f].unstack(level="instrument").to_numpy())
            for f in FEATURE_LIST
        }
        # bin 커버리지 시작($close 첫 관측 근사) — qlib 시리즈 index 시작 규칙
        self._coverage_start = _first_valid(self.panels["$close"])
        self.warmup_start = w0
        self.panel_end = panel_end
        self._frame_cache: Dict[Tuple[str, str, str], np.ndarray] = {}

    # ---------------- 공개 API ----------------
    def row_range(self, start: str, end: str) -> Tuple[int, int]:
        s = int(self.dates.searchsorted(pd.Timestamp(start)))
        e = int(self.dates.searchsorted(pd.Timestamp(end), side="right"))
        return s, e

    def sel_dates(self, start: str, end: str) -> pd.DatetimeIndex:
        s, e = self.row_range(start, end)
        return self.dates[s:e]

    def compute(self, formula: str, start: str, end: str,
                use_cache: bool = True) -> np.ndarray:
        """formula → float32 (구간 내 일자 × 전 종목) 행렬.

        실패 시 FormulaEvalError — silent fallback 없음.
        """
        key = (formula, start, end)
        if use_cache and key in self._frame_cache:
            return self._frame_cache[key]
        try:
            tree = parse_expression(formula)
            lft, rght = extended_window(tree)
        except FormulaEvalError:
            raise
        except Exception as e:  # 방어적
            raise FormulaEvalError(f"parse_error:{type(e).__name__}", formula)

        s, e = self.row_range(start, end)
        off = max(0, s - lft)
        hi = min(len(self.dates), e + rght)
        if off > 0 and (s - lft) < 0:
            # warmup_start가 좌측 절단점을 커버하지 못함 — 값이 qlib과 어긋날
            # 수 있으므로 명시적으로 실패시킨다 (조용한 편차 금지).
            raise FormulaEvalError(
                f"eval_error:insufficient_warmup(lft={lft},panel_start={self.warmup_start})",
                formula)
        try:
            res = self._eval(tree, off, hi)
        except FormulaEvalError:
            raise
        except Exception as ex:
            raise FormulaEvalError(f"eval_error:{type(ex).__name__}:{ex}", formula)
        if np.isscalar(res):
            raise FormulaEvalError("eval_error:constant_only_expression", formula)
        out = res.astype(np.float32)[s - off:e - off]
        if use_cache:
            self._frame_cache[key] = out
        return out

    def frame(self, formula: str, start: str, end: str) -> pd.DataFrame:
        return pd.DataFrame(self.compute(formula, start, end),
                            index=self.sel_dates(start, end), columns=self.columns)

    def field(self, name: str, start: str, end: str) -> np.ndarray:
        """원시 필드 슬라이스 (float32)."""
        s, e = self.row_range(start, end)
        return self.panels[name][s:e]

    # ---------------- 트리 평가 ----------------
    def _eval(self, node, off: int, hi: int):
        kind = node[0]
        if kind == "f":
            try:
                return self.panels[node[1]][off:hi]
            except KeyError:
                raise FormulaEvalError(f"eval_error:unknown_field:{node[1]}")
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
                raise FormulaEvalError("eval_error:constant_only_expression")
            if name in _PAIR_VIA_SERIES:
                return self._pair_series_op(_PAIR[name], left, right)
            with np.errstate(all="ignore"):
                return getattr(np, _PAIR[name])(left, right)
        if name in _ROLL_ALL:
            n = args[1][1]
            if not isinstance(n, (int, np.integer)):
                raise FormulaEvalError(f"eval_error:{name}_window_not_int:{n!r}")
            child = self._eval(args[0], off, hi)
            if np.isscalar(child):
                raise FormulaEvalError("eval_error:rolling_over_constant")
            return self._roll(name, child, int(n), off)
        raise FormulaEvalError(f"eval_error:unknown_operator:{name}")

    @staticmethod
    def _pair_series_op(func, left, right):
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

    def _series_start(self, off: int, T: int) -> np.ndarray:
        return np.minimum(np.maximum(self._coverage_start - off, 0), T)

    def _roll(self, name, vals, n, off):
        if name == "Ref":
            return self._shift(vals, n, off)
        if name == "Delta":
            if n == 0:
                return vals - self._first_series_value(vals, off)
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
            if name == "Rsquare" and n != 0:
                std = pd.DataFrame(vals).rolling(n, min_periods=1).std().to_numpy()
                with np.errstate(invalid="ignore"):
                    out[np.isclose(std, 0, atol=2e-05)] = np.nan
            return out
        if name in ("WMA", "IdxMax", "IdxMin", "Mad"):
            kind = name.lower()
            if n == 0:
                return self._apply_expanding(vals, _SHORT_FN[kind], off)
            return self._roll_apply_vectorized(vals, n, kind, off)
        raise FormulaEvalError(f"eval_error:unknown_operator:{name}")

    def _shift(self, vals, n, off):
        out = np.full_like(vals, np.nan)
        if n == 0:
            out[:] = self._first_series_value(vals, off)
            return out
        if n > 0:
            out[n:] = vals[:-n]
        else:
            out[:n] = vals[-n:]
        return out

    def _first_series_value(self, vals, off):
        T = vals.shape[0]
        s0 = self._series_start(off, T)
        first = np.full(vals.shape[1], np.nan, dtype=vals.dtype)
        ok = s0 < T
        first[ok] = vals[s0[ok], np.where(ok)[0]]
        return first

    def _apply_expanding(self, vals, fn, off):
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
        T, N = vals.shape
        out = np.full((T, N), np.nan, dtype=np.float64)
        vt = np.ascontiguousarray(vals.T)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            for j0 in range(0, N, self.block_cols):
                j1 = min(j0 + self.block_cols, N)
                win = sliding_window_view(vt[j0:j1], n, axis=1)
                cnt = (~np.isnan(win)).sum(axis=-1)
                if kind == "wma":
                    w = (np.arange(n) + 1.0)
                    w = w / w.sum()
                    r = np.nansum(win * w, axis=-1) / cnt
                elif kind in ("idxmax", "idxmin"):
                    fn = np.argmax if kind == "idxmax" else np.argmin
                    r = (fn(win, axis=-1) + 1).astype(np.float64)
                else:  # mad — pandas apply는 창을 float64로 전달
                    c = np.where(cnt == 0, 1, cnt).astype(np.float64)
                    s = np.nansum(win, axis=-1, dtype=np.float64)
                    m = s / c
                    d = np.abs(win - m[..., None])
                    r = np.nansum(d, axis=-1, dtype=np.float64) / c
                r = np.where(cnt == 0, np.nan, r)
                out[n - 1:, j0:j1] = r.T
        fn = _SHORT_FN[kind]
        s0s = self._series_start(off, T)
        for j in range(N):
            s0 = s0s[j]
            if s0 >= T:
                continue
            for t in range(s0, min(s0 + n - 1, T)):
                x = vals[s0:t + 1, j].astype(np.float64)
                if np.isnan(x).all():
                    out[t, j] = np.nan
                else:
                    out[t, j] = fn(x)
        return out

"""fast_eval.py — 결과 불변(result-invariant) Qlib 호출 최적화 모듈.

원본(backtest/ictester.py의 ICBacktester.calculate1)이 개체마다 수행하던

    factor 조회 1회(execute, 길이검증용) + factor 조회 1회 + label 조회 1회

를 다음으로 대체한다. 산출되는 IC 값은 원본과 동일하다.

  * LabelCache      : 불변인 label 패널을 (universe, 기간, freq)당 1회만 조회
  * ClosePanelCache : 실패 수식의 "$close" 폴백 패널도 1회만 조회
  * batch_ic        : 표현식 N개를 chunk 단위 D.features 1회로 묶어 조회,
                      chunk 실패 시 개별 조회로 폴백(개별 실패는 원본과 동일하게 $close 대체)
  * ic_memo         : 표현식 문자열 → IC 메모 (IC는 표현식의 결정적 함수이므로 결과 불변)

이 모듈은 원본 파일을 일절 수정하지 않는다. 원복 = scripts/ 신규 파일 삭제.
"""

import os
import sys

import numpy as np
import pandas as pd

from qlib.data import D


def ensure_backtest_importable(repo_root):
    """backtest 패키지의 누락 모듈을 원본 무수정으로 보완.

    backtest/__init__.py 는 `from .backtester import FactorBacktester` 를 하지만
    저장소에 backtest/backtester.py 가 없다 (원본 gplearn.py도 이 지점에서
    ModuleNotFoundError). 동일 내용의 파일이 Alphaagent/backtester.py 로 존재하므로
    (첫 줄 주석이 `# qlib_backtester/backtester.py`) 그것을 sys.modules 에
    "backtest.backtester" 로 사전 등록해 import 를 성립시킨다.
    """
    import importlib.util
    name = "backtest.backtester"
    if name in sys.modules:
        return
    src = os.path.join(repo_root, "Alphaagent", "backtester.py")
    spec = importlib.util.spec_from_file_location(name, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)

# ICBacktester / gplearn 양쪽과 동일한 label (문자열까지 ictester와 동일)
LABEL_EXPR = "Ref($close, -1)/$close - 1"


def _univ_key(instruments):
    """D.instruments()가 주는 config dict를 캐시 키로 변환."""
    try:
        return repr(sorted(instruments.items())) if isinstance(instruments, dict) else repr(instruments)
    except Exception:
        return repr(instruments)


class _PanelCache:
    """(universe, start, end, freq)당 단일 필드 패널을 1회만 조회해 재사용."""

    def __init__(self, field):
        self.field = field
        self._cache = {}

    def get(self, instruments, start_time, end_time, freq):
        key = (_univ_key(instruments), str(start_time), str(end_time), str(freq))
        if key not in self._cache:
            self._cache[key] = D.features(
                instruments=instruments,
                fields=[self.field],
                start_time=start_time,
                end_time=end_time,
                freq=freq,
            )
        return self._cache[key]


class FastICEvaluator:
    """ICBacktester.calculate1과 수치적으로 동일한 IC를 배치/캐시 경로로 계산."""

    def __init__(self, instruments, start_time, end_time, freq="day", chunk_size=24):
        self.instruments = instruments
        self.start_time = start_time
        self.end_time = end_time
        self.freq = freq
        self.chunk_size = int(chunk_size)
        self.label_cache = _PanelCache(LABEL_EXPR)
        self.close_cache = _PanelCache("$close")
        self.ic_memo = {}          # expr(str) -> float
        # 통계 (문서/로그용)
        self.n_memo_hits = 0
        self.n_evaluated = 0
        self.n_chunk_calls = 0
        self.n_single_fallbacks = 0
        self.n_close_fallbacks = 0

    # ---- 원본 calculate1 로직의 충실한 재현 -------------------------------
    def _ic_pair(self, factor_onecol: pd.DataFrame, label_df: pd.DataFrame) -> float:
        """backtest/ictester.py ICBacktester.calculate1 과 동일한 수식.

        컬럼 쌍(factor, label)에 대해서만 dropna 하는 것이 핵심 —
        다중 컬럼 일괄 dropna는 원본과 결과가 달라진다.
        """
        all_data = factor_onecol.join(label_df, how="inner").dropna()
        all_data.columns = ["factor", "label"]
        ic_series = all_data.groupby(level="datetime").apply(
            lambda x: x["factor"].corr(x["label"])
        )
        try:
            if ic_series.isna().mean() > 0.5:
                return 0.0
        except Exception:
            return 0.0
        ic = ic_series.dropna().mean()
        ic = 0.0 if (not isinstance(ic, float) or np.isnan(ic)) else ic
        return ic

    def _label(self) -> pd.DataFrame:
        return self.label_cache.get(self.instruments, self.start_time, self.end_time, self.freq)

    def _close_ic(self) -> float:
        """원본의 예외 폴백과 동일: 실패 수식은 $close 패널의 IC."""
        self.n_close_fallbacks += 1
        close_df = self.close_cache.get(self.instruments, self.start_time, self.end_time, self.freq)
        return self._ic_pair(close_df, self._label())

    def _eval_single(self, expr: str) -> float:
        """원본 ICBacktester.__init__의 try/except와 동일한 개별 경로."""
        try:
            fdf = D.features(
                instruments=self.instruments,
                fields=[expr],
                start_time=self.start_time,
                end_time=self.end_time,
                freq=self.freq,
            )
        except Exception:
            return self._close_ic()
        return self._ic_pair(fdf, self._label())

    # ---- 공개 API ----------------------------------------------------------
    def evaluate(self, exprs):
        """표현식 리스트 → IC(float) 리스트. 입력 순서를 보존한다."""
        label_df = self._label()
        results = {}

        todo = []
        for e in exprs:
            if e in self.ic_memo:
                self.n_memo_hits += 1
            elif e not in results and e not in todo:
                todo.append(e)

        for i in range(0, len(todo), self.chunk_size):
            chunk = todo[i:i + self.chunk_size]
            self.n_chunk_calls += 1
            try:
                bdf = D.features(
                    instruments=self.instruments,
                    fields=list(chunk),
                    start_time=self.start_time,
                    end_time=self.end_time,
                    freq=self.freq,
                )
                for k, e in enumerate(chunk):
                    results[e] = self._ic_pair(bdf.iloc[:, [k]], label_df)
            except Exception:
                # chunk 안 어딘가가 Qlib에서 거절됨 → 원본과 동일한 개별 경로로 폴백
                self.n_single_fallbacks += 1
                for e in chunk:
                    results[e] = self._eval_single(e)

        self.ic_memo.update(results)
        self.n_evaluated += len(todo)
        return [self.ic_memo[e] for e in exprs]

    def stats(self) -> str:
        return (f"evaluated={self.n_evaluated} memo_hits={self.n_memo_hits} "
                f"chunk_calls={self.n_chunk_calls} single_fallbacks={self.n_single_fallbacks} "
                f"close_fallbacks={self.n_close_fallbacks}")


def make_fast_parallel_evolve(evaluator: FastICEvaluator):
    """gplearn.genetic._parallel_evolve 의 결과 불변 대체 구현을 생성.

    원본과의 차이는 '평가 시점'뿐이다:
      원본 = 개체 생성 직후 개체별로 raw_fitness(qlib 3회)
      여기 = 세대의 프로그램을 전부 생성한 뒤 표현식을 모아 배치 평가

    개체 생성은 개체별 독립 RNG(seeds[i])를 원본과 동일한 순서로 소비하므로
    (method 추첨 → tournament → 유전연산 → get_all_indices)
    같은 seed에서 생성되는 프로그램이 완전히 동일하다.
    """
    from gplearn._program import _Program
    from gplearn.utils import check_random_state

    def fast_parallel_evolve(n_programs, parents, X_shape, y, sample_weight, seeds, params):
        n_samples, n_features = X_shape
        tournament_size = params['tournament_size']
        function_set = params['function_set']
        arities = params['arities']
        init_depth = params['init_depth']
        init_method = params['init_method']
        const_range = params['const_range']
        metric = params['_metric']
        transformer = params['_transformer']
        parsimony_coefficient = params['parsimony_coefficient']
        method_probs = params['method_probs']
        p_point_replace = params['p_point_replace']
        max_samples = params['max_samples']
        feature_names = params['feature_names']
        qlib_config = params['qlib_config']

        max_samples = int(max_samples * n_samples)

        def _tournament(random_state):
            contenders = random_state.randint(0, len(parents), tournament_size)
            fitness = [parents[p].fitness_ for p in contenders]
            if metric.greater_is_better:
                parent_index = contenders[np.argmax(fitness)]
            else:
                parent_index = contenders[np.argmin(fitness)]
            return parents[parent_index], parent_index

        # ---- phase A: 프로그램 생성 (원본과 동일한 RNG 소비 순서) ----------
        programs = []
        for i in range(n_programs):
            random_state = check_random_state(seeds[i])

            if parents is None:
                program = None
                genome = None
            else:
                method = random_state.uniform()
                parent, parent_index = _tournament(random_state)

                if method < method_probs[0]:
                    donor, donor_index = _tournament(random_state)
                    program, removed, remains = parent.crossover(donor.program, random_state)
                    genome = {'method': 'Crossover',
                              'parent_idx': parent_index,
                              'parent_nodes': removed,
                              'donor_idx': donor_index,
                              'donor_nodes': remains}
                elif method < method_probs[1]:
                    program, removed, _ = parent.subtree_mutation(random_state)
                    genome = {'method': 'Subtree Mutation',
                              'parent_idx': parent_index,
                              'parent_nodes': removed}
                elif method < method_probs[2]:
                    program, removed = parent.hoist_mutation(random_state)
                    genome = {'method': 'Hoist Mutation',
                              'parent_idx': parent_index,
                              'parent_nodes': removed}
                elif method < method_probs[3]:
                    program, mutated = parent.point_mutation(random_state)
                    genome = {'method': 'Point Mutation',
                              'parent_idx': parent_index,
                              'parent_nodes': mutated}
                else:
                    program = parent.reproduce()
                    genome = {'method': 'Reproduction',
                              'parent_idx': parent_index,
                              'parent_nodes': []}

            program = _Program(function_set=function_set,
                               arities=arities,
                               init_depth=init_depth,
                               init_method=init_method,
                               n_features=n_features,
                               metric=metric,
                               transformer=transformer,
                               const_range=const_range,
                               p_point_replace=p_point_replace,
                               parsimony_coefficient=parsimony_coefficient,
                               feature_names=feature_names,
                               random_state=random_state,
                               program=program,
                               qlib_config=qlib_config)
            program.parents = genome

            # 원본과 동일하게 RNG를 소비한다 (결과 불변성의 필수 조건)
            indices, not_indices = program.get_all_indices(n_samples, max_samples, random_state)

            programs.append(program)

        # ---- phase B: 표현식 배치 평가 -------------------------------------
        exprs = [str(p) for p in programs]
        ics = evaluator.evaluate(exprs)
        for p, ic in zip(programs, ics):
            p.raw_fitness_ = abs(ic)
            if max_samples < n_samples:
                # 원본도 동일 값을 재계산할 뿐이다 (raw_fitness가 sample_weight를 무시)
                p.oob_fitness_ = p.raw_fitness_

        print(f"[fast_eval] generation batch done: {evaluator.stats()}")
        return programs

    return fast_parallel_evolve

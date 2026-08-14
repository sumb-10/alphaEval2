"""[Optional integration adapter] gplearn(AlphaEval fork) trajectory 수집.

이 모듈은 **optional adapter**다 — AlphaSearchBench core runtime의 필수
dependency가 아니며, core는 표준 trajectory schema(inputs/schemas.py)에만
의존한다. Search-QD는 스키마만 만족하면 어떤 miner의 결과도 평가할 수 있다.

adapter 특성상 miner(AlphaEval gplearn 패키지) 내부를 lazy import한다 —
production core의 AlphaEval-import 금지 검사에서 instrumentation/은
명시적 예외다 (scripts/check_no_alphaeval_imports.py 참조).

provenance: AlphaEval scripts/fast_eval.py make_fast_parallel_evolve의
phase-A(프로그램 생성) 로직 사본 + trajectory 로깅. 원본 gplearn 소스는
수정하지 않는다 (monkey-patch).

사용 예 (러너에서):
    from alphasearchbench.instrumentation.gplearn import make_logging_parallel_evolve
    import gplearn.genetic as G
    G._parallel_evolve = make_logging_parallel_evolve(evaluator, writer)
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..inputs.trajectory import TrajectoryWriter


def make_logging_parallel_evolve(evaluator, writer: TrajectoryWriter):
    """gplearn.genetic._parallel_evolve 대체 — 배치 평가 + trajectory 로깅.

    evaluator: .evaluate(list[str]) -> list[signed IC] 와 .ic_memo를 가진 객체
               (AlphaEval fast/tensor evaluator 호환 인터페이스)
    """
    from gplearn._program import _Program            # lazy — optional adapter
    from gplearn.utils import check_random_state

    gen_counter = {"gen": 0}

    def logging_parallel_evolve(n_programs, parents, X_shape, y,
                                sample_weight, seeds, params):
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

        programs, genomes = [], []
        for i in range(n_programs):
            random_state = check_random_state(seeds[i])
            if parents is None:
                program, genome = None, None
            else:
                method = random_state.uniform()
                parent, parent_index = _tournament(random_state)
                if method < method_probs[0]:
                    donor, donor_index = _tournament(random_state)
                    program, removed, remains = parent.crossover(donor.program, random_state)
                    genome = {"operation": "Crossover", "parent_idx": int(parent_index),
                              "donor_idx": int(donor_index)}
                elif method < method_probs[1]:
                    program, removed, _ = parent.subtree_mutation(random_state)
                    genome = {"operation": "Subtree Mutation", "parent_idx": int(parent_index)}
                elif method < method_probs[2]:
                    program, removed = parent.hoist_mutation(random_state)
                    genome = {"operation": "Hoist Mutation", "parent_idx": int(parent_index)}
                elif method < method_probs[3]:
                    program, mutated = parent.point_mutation(random_state)
                    genome = {"operation": "Point Mutation", "parent_idx": int(parent_index)}
                else:
                    program = parent.reproduce()
                    genome = {"operation": "Reproduction", "parent_idx": int(parent_index)}
            prog = _Program(function_set=function_set, arities=arities,
                            init_depth=init_depth, init_method=init_method,
                            n_features=n_features, metric=metric,
                            transformer=transformer, const_range=const_range,
                            p_point_replace=p_point_replace,
                            parsimony_coefficient=parsimony_coefficient,
                            feature_names=feature_names, random_state=random_state,
                            program=program, qlib_config=qlib_config)
            prog.parents = None if genome is None else genome
            prog.get_all_indices(n_samples, max_samples, random_state)  # RNG 소비 보존
            programs.append(prog)
            genomes.append(genome or {"operation": "Init"})

        exprs = [str(p) for p in programs]
        memo_before = set(getattr(evaluator, "ic_memo", {}).keys())
        ics = evaluator.evaluate(exprs)
        gen = gen_counter["gen"]
        for idx, (p, expr, ic, genome) in enumerate(zip(programs, exprs, ics, genomes)):
            p.raw_fitness_ = abs(ic)
            if max_samples < n_samples:
                p.oob_fitness_ = p.raw_fitness_
            writer.write(generation=gen, idx_in_population=idx, formula=expr,
                         raw_fitness=float(abs(ic)), signed_train_IC=float(ic),
                         program_length=int(p.length_), program_depth=int(p.depth_),
                         memo_hit=bool(expr in memo_before), **genome)
        gen_counter["gen"] = gen + 1
        return programs

    return logging_parallel_evolve

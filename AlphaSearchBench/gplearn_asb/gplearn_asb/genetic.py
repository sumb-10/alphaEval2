"""make_asb_parallel_evolve — vendored gplearn의 _parallel_evolve 대체.

phase-A(프로그램 생성): alphasearchbench/instrumentation/gplearn.py:59-104
(= scripts/fast_eval.py:225-285 = gplearn/genetic.py:73-145) 의 verbatim 포팅.
**RNG 소비 순서 절대 보존** — uniform(method) → _tournament(+crossover 2회)
→ 유전연산 → get_all_indices. 같은 seed면 원본과 동일한 프로그램이 생성된다.

phase-B(평가·penalty): 원본은 여기서 개별 qlib 평가(또는 fast 배치)를 하지만,
이 구현은 MiningEvaluator.diagnose(신호+IC+validity 상시 진단, 캐시) 후
constraint mode에 따른 effective fitness를 `p.raw_fitness_`에 주입한다 —
selection(_tournament의 fitness_)·HOF(raw_fitness_ argsort) 둘 다 이 값을
소비하므로 invalid candidate는 **삭제 없이** 자연스럽게 최하위가 된다.
population_size는 원본과 동일하게 무조건 append로 유지된다 (reject 경로 없음).
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import numpy as np

from .evaluator import MiningEvaluator
from .fitness import apply_constraint
from .trajectory import GenStatsCollector, generation_row


def make_asb_parallel_evolve(evaluator: MiningEvaluator,
                             mode: str,
                             thresholds: Dict[str, Optional[float]],
                             worst_fitness: float,
                             writer,                     # ASB TrajectoryWriter
                             gen_stats: GenStatsCollector,
                             constraint_mode_field: str,
                             vendored_program_cls,
                             vendored_check_random_state,
                             fitness_opts: Optional[Dict[str, Any]] = None):
    """vendored gplearn genetic._parallel_evolve 대체 함수 생성."""
    _Program = vendored_program_cls
    check_random_state = vendored_check_random_state
    gen_counter = {"gen": 0}

    def asb_parallel_evolve(n_programs, parents, X_shape, y,
                            sample_weight, seeds, params):
        t0 = time.perf_counter()
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

        # ---------------- phase-B: 진단 + constraint 적용 + 로깅 ----------------
        exprs = [str(p) for p in programs]
        memo_before = {f for f in exprs if f in evaluator.cache}
        gen = gen_counter["gen"]
        infos = []
        for idx, (p, expr, genome) in enumerate(zip(programs, exprs, genomes)):
            diag = evaluator.diagnose(expr)
            info = apply_constraint(mode, diag, thresholds, worst_fitness,
                                    evaluator.close_signed_ic,
                                    fitness_metric=getattr(evaluator, "fitness_metric", "abs_ic"),
                                    close_net_sharpe=getattr(evaluator, "close_net_sharpe", float("nan")),
                                    fitness_opts=fitness_opts,
                                    close_raw_fitness=getattr(evaluator, "close_raw_fitness", None))
            info["formula"] = expr
            info["mean_daily_coverage_ratio"] = diag.get("mean_daily_coverage_ratio")
            info["median_daily_n_valid"] = diag.get("median_daily_n_valid")
            info["valid_day_ratio"] = diag.get("valid_day_ratio")

            # selection·HOF가 소비하는 값 — worst-fitness penalty의 주입 지점
            p.raw_fitness_ = info["effective_fitness"]
            if max_samples < n_samples:
                p.oob_fitness_ = p.raw_fitness_

            writer.write(
                generation=gen, idx_in_population=idx, formula=expr,
                raw_fitness=info["raw_fitness"],
                effective_fitness=info["effective_fitness"],
                signed_train_IC=info["signed_train_IC"],
                abs_train_IC=info["abs_train_IC"],
                fitness_metric=info.get("fitness_metric", "abs_ic"),
                net_sharpe=diag.get("net_sharpe"),
                ic_tstat=diag.get("ic_tstat"),
                static_invalid_reason=diag.get("static_invalid_reason"),
                static_flag_constant_subtree=diag.get("static_flag_constant_subtree"),
                fitness_condition_failed=info.get("fitness_condition_failed"),
                constraint_mode=constraint_mode_field,
                hard_invalid=info["hard_invalid"],
                research_invalid=info["research_invalid"],
                validity_pass=info["validity_pass"],
                invalid_reason=info["invalid_reason"],
                fallback_used=info["fallback_used"],
                mean_daily_coverage_ratio=info["mean_daily_coverage_ratio"],
                median_daily_n_valid=info["median_daily_n_valid"],
                valid_day_ratio=info["valid_day_ratio"],
                program_length=int(p.length_), program_depth=int(p.depth_),
                memo_hit=bool(expr in memo_before), **genome)
            infos.append(info)

        gen_stats.add(generation_row(
            gen, infos, genomes,
            wall_seconds=time.perf_counter() - t0,
            n_memo_hits=int(sum(1 for e in exprs if e in memo_before))))
        gen_counter["gen"] = gen + 1
        return programs

    return asb_parallel_evolve

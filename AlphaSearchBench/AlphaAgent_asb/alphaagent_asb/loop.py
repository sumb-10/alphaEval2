"""메인 마이닝 루프 — 원형 alphaagent.py:63-96의 seed×round 구조 보존.

시간축 (지도 원칙 2): trajectory의 `generation = round_id`,
`idx_in_population = seed_idx` (ASB 호환 필드). seed 간에는 재생산 관계가
없다 — manifest의 trajectory_semantics 문구 참조.

feedback(LLM이 보는 수치)과 ASB diagnostics는 분리 경로 (지도 원칙 1):
  feedback = vendored FactorBacktester (원형 그대로)
  diagnostics = gplearn_asb.MiningEvaluator (기록 전용; constraint overlay는
  config로만 acceptance에 개입 — 기본 "off")
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from . import METHOD_NAME, TRAJECTORY_SEMANTICS
from .agents import IdeaAgentA, FactorAgentA, EvalAgentA
from .feedback import FeedbackEvaluator
from .prompts import SEED_EXPRESSIONS
from .similarity import ast_similarity_by_common_subtree_ast


def _evaluate_candidate(expr, expr_ast, pool_asts, feedback_eval, eval_agent,
                        distinguish_terminals: bool) -> Dict[str, Any]:
    """원형 EvalAgent.evaluate(eval_agent.py:74-112) 구조 보존 —
    백테스트→유사도→LLM 판정이 한 try 안에 있고, 어느 단계든 실패하면
    summary=에러 문자열, verdict None (LLM 미호출)."""
    result = {"expression": expr, "is_valid": False, "performance": None,
              "summary": "", "recommendation": "", "is_high_quality": None,
              "ast_similarity": None, "feedback": None}
    fb = feedback_eval.evaluate(expr)
    result["feedback"] = fb
    try:
        if not fb["ok"]:
            raise RuntimeError(fb["error"])
        max_corr = 0
        if pool_asts:
            for prev_ast in pool_asts:
                similarity = ast_similarity_by_common_subtree_ast(
                    expr_ast, prev_ast, distinguish_terminals)
                if similarity > max_corr:
                    max_corr = similarity
        # 원형 perf dict — LLM이 보는 값 (prompt 값, eval_agent.py:99)
        perf = {"AnnRet": fb["feedback_AnnRet_prompt"],
                "IC": fb["feedback_IC_prompt"],
                "Similarity to Previous": max_corr}
        report = eval_agent.assess(perf, expr)
        result.update({"is_valid": True, "performance": perf,
                       "ast_similarity": max_corr,
                       "summary": report.get("summary", ""),
                       "recommendation": report.get("recommendation", ""),
                       "is_high_quality": report.get("is_high_quality", None)})
    except Exception as e:  # noqa: BLE001 — 원형: 예외 삼킴
        result["summary"] = f"[EvalAgent] Failed due to error: {str(e)}"
    return result


def run_mining(cfg, llm, mining_eval, traj_writer, constraint_mode: str,
               thresholds: Dict[str, Optional[float]], worst_fitness: float,
               instruments) -> Dict[str, Any]:
    from gplearn_asb.fitness import apply_constraint

    compat = str(cfg.get("compatibility.mode", "parity"))
    max_rounds = int(cfg.get("agent.max_rounds", 3))
    lo, hi = (cfg.get("agent.seed_range") or [20, None])
    seeds = list(enumerate(SEED_EXPRESSIONS))[lo:hi]
    distinguish = bool(cfg.get("similarity.distinguish_terminals", False))

    idea_agent = IdeaAgentA(llm, compat)
    factor_agent = FactorAgentA(llm, compat, int(cfg.get("llm.max_retries", 5)))
    eval_agent = EvalAgentA(llm, compat)
    feedback_eval = FeedbackEvaluator(str(cfg.require("search.start_date")),
                                      str(cfg.require("search.end_date")),
                                      instruments)

    pool: List[str] = []
    pool_asts: List[Any] = []
    pool_meta: List[Dict[str, Any]] = []
    all_rows: List[Dict[str, Any]] = []
    candidate_idx = 0
    n_seed_aborted = 0

    for seed_idx, example in seeds:
        try:
            idea = idea_agent.generate(example)
        except Exception as e:  # noqa: BLE001 — D-2: seed 단위 격리
            n_seed_aborted += 1
            traj_writer.write(generation=0, idx_in_population=seed_idx,
                              formula="", raw_fitness=float("nan"),
                              seed_idx=seed_idx, seed_formula=example,
                              round_id=0, candidate_idx=candidate_idx,
                              seed_aborted=True, abort_reason=str(e),
                              constraint_mode=constraint_mode)
            candidate_idx += 1
            continue

        previous_expr = None
        for round_id in range(max_rounds):
            t0 = time.perf_counter()
            expr, expr_ast = factor_agent.generate(idea)
            result = _evaluate_candidate(expr, expr_ast, pool_asts,
                                         feedback_eval, eval_agent, distinguish)
            fb = result["feedback"]

            # ASB diagnostics (기록 전용) — 빈 수식도 diagnose가 eval_failed로 처리
            diag = mining_eval.diagnose(expr if expr else "<empty>")
            cinfo = apply_constraint(
                "off" if constraint_mode == "off" else constraint_mode,
                diag, thresholds, worst_fitness, mining_eval.close_signed_ic)

            llm_verdict = result["is_high_quality"]
            overlay_blocked = (constraint_mode != "off"
                               and not cinfo["validity_pass"])
            accepted = bool(llm_verdict) and not overlay_blocked

            ic_raw = fb["feedback_IC_raw"]
            raw_fitness = abs(ic_raw) if ic_raw is not None else float("nan")
            idea_text = (f'{idea.get("hypothesis", "")}\n{idea.get("description", "")}'
                         if isinstance(idea, dict) else str(idea))
            eval_feedback_text = result["summary"] + "\n" + result["recommendation"]

            row = {
                # ASB 호환 축 (지도 원칙 2)
                "generation": round_id, "idx_in_population": seed_idx,
                "formula": expr, "raw_fitness": raw_fitness,
                # 명시 축
                "seed_idx": seed_idx, "seed_formula": example,
                "round_id": round_id, "candidate_idx": candidate_idx,
                # 원형 지표 (raw/prompt 분리)
                "feedback_IC_raw": ic_raw,
                "feedback_IC_prompt": fb["feedback_IC_prompt"],
                "feedback_AnnRet_raw": fb["feedback_AnnRet_raw"],
                "feedback_AnnRet_prompt": fb["feedback_AnnRet_prompt"],
                "feedback_error": fb["error"],
                "ast_similarity": result["ast_similarity"],
                "llm_verdict": llm_verdict,
                "accepted": accepted,
                "overlay_blocked": overlay_blocked,
                # ASB 진단
                "signed_train_IC": diag.get("signed_train_IC"),
                "abs_train_IC": diag.get("abs_train_IC"),
                "hard_invalid": diag.get("hard_invalid"),
                "invalid_reason": cinfo.get("invalid_reason"),
                "research_invalid": cinfo.get("research_invalid"),
                "validity_pass": cinfo.get("validity_pass"),
                "mean_daily_coverage_ratio": diag.get("mean_daily_coverage_ratio"),
                "median_daily_n_valid": diag.get("median_daily_n_valid"),
                "valid_day_ratio": diag.get("valid_day_ratio"),
                "diagnostics_source": diag.get("diagnostics_source"),
                # 자연어 궤적
                "idea_text": idea_text,
                "eval_feedback_text": eval_feedback_text,
                "previous_formula": previous_expr,
                "constraint_mode": constraint_mode,
                "compatibility_mode": compat,
                "wall_seconds": time.perf_counter() - t0,
            }
            traj_writer.write(**row)
            all_rows.append(row)
            candidate_idx += 1

            if accepted:                                   # 원형 alphaagent.py:86-90
                pool.append(expr)
                pool_asts.append(expr_ast)
                pool_meta.append({"seed_idx": seed_idx, "round_id": round_id,
                                  **{k: row[k] for k in
                                     ("feedback_IC_raw", "feedback_IC_prompt",
                                      "feedback_AnnRet_prompt", "ast_similarity",
                                      "signed_train_IC", "abs_train_IC",
                                      "validity_pass", "invalid_reason",
                                      "mean_daily_coverage_ratio")}})
                break
            elif round_id < max_rounds - 1:                # 원형 :91-96
                eval_report_str = result["summary"] + "\n" + result["recommendation"]
                previous_expr = expr
                try:
                    idea = idea_agent.generate(example, idea, previous_expr,
                                               eval_report_str)
                except Exception as e:  # noqa: BLE001 — D-2
                    n_seed_aborted += 1
                    traj_writer.write(generation=round_id, idx_in_population=seed_idx,
                                      formula="", raw_fitness=float("nan"),
                                      seed_idx=seed_idx, seed_formula=example,
                                      round_id=round_id, candidate_idx=candidate_idx,
                                      seed_aborted=True, abort_reason=str(e),
                                      constraint_mode=constraint_mode)
                    candidate_idx += 1
                    break

    return {"pool": pool, "pool_meta": pool_meta, "rows": all_rows,
            "n_candidates": candidate_idx, "n_seed_aborted": n_seed_aborted,
            "n_seeds": len(seeds), "trajectory_semantics": TRAJECTORY_SEMANTICS,
            "method": METHOD_NAME}

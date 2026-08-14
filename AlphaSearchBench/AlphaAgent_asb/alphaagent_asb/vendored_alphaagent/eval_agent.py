import openai
from typing import Dict, Any
from ..backtester import FactorBacktester
import json
import ast


import ast

class ASTNodeWrapper:
    def __init__(self, node):
        self.node = node
        self.children = [ASTNodeWrapper(child) for child in ast.iter_child_nodes(node)]
        self.label = type(node).__name__

    def __eq__(self, other):
        return isinstance(other, ASTNodeWrapper) and self.label == other.label

    def __hash__(self):
        return hash(self.label)

def count_nodes(node: ASTNodeWrapper) -> int:
    return 1 + sum(count_nodes(child) for child in node.children)

def max_common_subtree_size(node1: ASTNodeWrapper, node2: ASTNodeWrapper, memo=None) -> int:
    if memo is None:
        memo = dict()
    key = (id(node1), id(node2))
    if key in memo:
        return memo[key]

    if node1.label != node2.label:
        memo[key] = 0
        return 0

    match_count = 1
    children1 = node1.children
    children2 = node2.children

    dp = [[0] * (len(children2) + 1) for _ in range(len(children1) + 1)]
    for i in range(len(children1)):
        for j in range(len(children2)):
            dp[i+1][j+1] = max(
                dp[i][j+1],
                dp[i+1][j],
                dp[i][j] + max_common_subtree_size(children1[i], children2[j], memo)
            )
    match_count += dp[-1][-1]
    memo[key] = match_count
    return match_count

def ast_similarity_by_common_subtree_ast(tree1: ast.AST, tree2: ast.AST) -> float:
    wrapped1 = ASTNodeWrapper(tree1)
    wrapped2 = ASTNodeWrapper(tree2)

    shared = max_common_subtree_size(wrapped1, wrapped2)
    size1 = count_nodes(wrapped1)
    size2 = count_nodes(wrapped2)

    avg_size = (size1 + size2) / 2
    return shared / avg_size if avg_size > 0 else 0.0



class EvalAgent:
    def __init__(self, model="gpt-4o", temperature=0.4, start_date="2020-01-01", end_date="2023-12-31", instruments=None, freq="day"):
        self.model = model
        self.temperature = temperature
        self.start_date = start_date
        self.end_date = end_date
        self.instruments = instruments if instruments is not None else ["CSI300"]
        self.freq = freq

    def evaluate(self, expr: str, expr_ast, results_ast) -> Dict[str, Any]:
        result = {
            "expression": expr,
            "is_valid": False,
            "performance": None,
            "summary": "",
            "recommendation": "",
            "is_high_quality": None
        }

        try:
            backtester = FactorBacktester(factor_expr=expr,
                                start_date=self.start_date,
                                end_date=self.end_date,
                                instruments=self.instruments,
                                freq=self.freq)
            backtester.load_data()
            perf = backtester.calculate_performance().to_dict()
            # 计算和results中的相似度
            max_corr = 0
            if results_ast:
                for prev_ast in results_ast:
                    similarity = ast_similarity_by_common_subtree_ast(expr_ast, prev_ast)
                    if similarity > max_corr:
                        max_corr = similarity
            perf = {"AnnRet": perf["AnnRet"]["total"], "IC": perf["IC"]["total"], "Similarity to Previous": max_corr}
            report = self._llm_assess_json(perf, expr)
            result.update({
                "is_valid": True,
                "performance": perf,
                "summary": report.get("summary", ""),
                "recommendation": report.get("recommendation", ""),
                "is_high_quality": report.get("is_high_quality", None)
            })

        except Exception as e:
            result["summary"] = f"[EvalAgent] Failed due to error: {str(e)}"""

        return result

    def _llm_assess_json(self, perf: Dict[str, float], expr: str) -> Dict[str, Any]:
        perf_str = json.dumps(perf, indent=2)
        system_prompt = (
            "You are a quantitative investment assistant.\n"
            "You will receive the backtest results of a factor and its expression. "
            "Your job is to summarize the performance and give a recommendation.\n"
            "When the annual return > 10% and IC > 0.03, it is considered a high-quality factor.\n"
            "The similarity the lower, the better.\n"
            "Return your answer strictly in the following format:\n\n"
            "{\n"
            "  \"summary\": \"<Natural language summary of return, risk, predictive power>\",\n"
            "  \"recommendation\": \"<Should it be deployed, improved, or discarded? Why?>\",\n"
            "  \"is_high_quality\": true or false\n"
            "}\n\n"
        )
        user_prompt = (
            f"Backtest result:\n{perf_str}\n\n"
            f"Factor expression: {expr}"
        )

        response = openai.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )

        reply = response.choices[0].message.content.strip()

        try:
            report = json.loads(reply)
            print("[EvalAgent] LLM response:", report)
        except Exception as e:
            print("[EvalAgent] JSON parsing failed:", e)
            report = {"summary": "", "recommendation": "", "is_high_quality": None}

        return report
    

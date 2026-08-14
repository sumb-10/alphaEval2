# run_pipeline.py

import time
from Alphaagent.agents.idea_agent import IdeaAgent
from Alphaagent.agents.factor_agent import FactorAgent
from Alphaagent.agents.eval_agent import EvalAgent
import qlib
from qlib.data import D
import ast
import json
import openai
openai.api_key = "<Your API Key>"
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region="cn")
results = []
results_ast = []

if __name__ == "__main__":
    # === Step 0: 定义你的市场假设 ===
    hypothesis = None
    expressions = [
        '($close-$open)/$open',
        '($high-$low)/$open',
        '($close-$open)/($high-$low+1e-12)',
        '($high-Greater($open, $close))/$open',
        '($high-Greater($open, $close))/($high-$low+1e-12)',
        '(Less($open, $close)-$low)/$open',
        '(Less($open, $close)-$low)/($high-$low+1e-12)',
        '(2*$close-$high-$low)/$open',
        '(2*$close-$high-$low)/($high-$low+1e-12)',
        '$open/$close',
        '$high/$close',
        '$low/$close',
        '$vwap/$close',
        'Ref($close, 5)/$close',
        'Mean($close, 60)/$close',
        'Std($close, 10)/$close',
        'Max($high, 20)/$close',
        'Min($low, 30)/$close',
        'Rank($close, 5)',
        '($close-Min($low, 10))/(Max($high, 10)-Min($low, 10)+1e-12)',
        'IdxMax($high, 20)/20',
        'IdxMin($low, 30)/30',
        '(IdxMax($high, 60)-IdxMin($low, 60))/60',
        'Corr($close, Log($volume+1), 5)',
        'Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), 10)',
        'Mean($close>Ref($close, 1), 20)',
        'Mean($close<Ref($close, 1), 30)',
        'Mean($close>Ref($close, 1), 60)-Mean($close<Ref($close, 1), 60)',
        'Sum(Greater($close-Ref($close, 1), 0), 5)/(Sum(Abs($close-Ref($close, 1)), 5)+1e-12)',
        'Sum(Greater(Ref($close, 1)-$close, 0), 10)/(Sum(Abs($close-Ref($close, 1)), 10)+1e-12)',
        '(Sum(Greater($close-Ref($close, 1), 0), 20)-Sum(Greater(Ref($close, 1)-$close, 0), 20))/(Sum(Abs($close-Ref($close, 1)), 20)+1e-12)',
        'Mean($volume, 30)/($volume+1e-12)',
        'Std($volume, 60)/($volume+1e-12)',
        'Std(Abs($close/Ref($close, 1)-1)*$volume, 5)/(Mean(Abs($close/Ref($close, 1)-1)*$volume, 5)+1e-12)',
        'Sum(Greater($volume-Ref($volume, 1), 0), 10)/(Sum(Abs($volume-Ref($volume, 1)), 10)+1e-12)',
        'Sum(Greater(Ref($volume, 1)-$volume, 0), 20)/(Sum(Abs($volume-Ref($volume, 1)), 20)+1e-12)',
        '(Sum(Greater($volume-Ref($volume, 1), 0), 60)-Sum(Greater(Ref($volume, 1)-$volume, 0), 60))/(Sum(Abs($volume-Ref($volume, 1)), 60)+1e-12)'
    ]
    # 初始化所有 agent
    idea_agent = IdeaAgent()
    factor_agent = FactorAgent()
    eval_agent = EvalAgent(start_date="2010-01-01", end_date="2019-12-31", instruments=D.instruments(market='all'), freq="day")
    for example in expressions[20:]:
        # === Step 1: 初始因子 idea 生成 ===
        idea = idea_agent.generate(example)
        print(f"\n📌 [IdeaAgent] Generated Idea:\n{idea}")

        # 多轮迭代控制（最多迭代 3 次）
        max_rounds = 3
        previous_expr = None
        eval_report_str = None

        for round_id in range(max_rounds):
            print(f"\n🔄 Round {round_id + 1} ======================")
            # === Step 2: 生成表达式 ===
            expr, expr_ast = factor_agent.generate(idea)
            print(f"\n🧮 [FactorAgent] Expression:\n{expr}")

            # === Step 3: 回测评估 ===
            result = eval_agent.evaluate(expr, expr_ast, results_ast)
            print(f"\n📊 [EvalAgent] Summary:\n{result['summary']}")
            print(f"\n💡 [EvalAgent] Recommendation:\n{result['recommendation']}")
            print(f"\n✅ Is High Quality?: {result['is_high_quality']}")

            # === Step 4: 判断是否继续优化 ===
            if result["is_high_quality"]:
                print("\n✅ High quality factor found. Pipeline completed.")
                results.append(expr)
                results_ast.append(expr_ast)
                break
            elif round_id < max_rounds - 1:
                print("\n⚠️ Factor not good enough. Let’s improve or re-invent it.")
                eval_report_str = result["summary"] + "\n" + result["recommendation"]
                previous_expr = expr
                # 让 IdeaAgent 迭代出改进思路
                idea = idea_agent.generate(example, idea, previous_expr, eval_report_str)
json.dump(results, open("alpha_agent_results.json", "w", encoding="utf-8"), indent=2)
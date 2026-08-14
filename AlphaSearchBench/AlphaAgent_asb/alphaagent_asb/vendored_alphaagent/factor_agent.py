import openai
import ast
from typing import Tuple


class FactorAgent:
    def __init__(self, model="gpt-4o", temperature=0.3):
        self.model = model
        self.temperature = temperature

        # 运算符和特征定义
        self.function_definition = (
            "You can use the following features: $open, $high, $low, $close, $volume\n"
            "The following functions and operators are available:\n"
            "Abs(x), Log(x), Sign(x) = standard definitions; same for the operators '+', '-', '*', '/', '**'\n"
            "Ref(x, d) = value of x d days ago\n"
            "Corr(x, y, d) = time-serial correlation of x and y for the past d days\n"
            "Cov(x, y, d) = time-serial covariance of x and y for the past d days\n"
            "Delta(x, d) = today's value of x minus the value of x d days ago\n"
            "WMA(x, d) = weighted moving average over the past d days with linearly decaying weights d, d – 1, …, 1 (rescaled to sum up to 1)\n"
            "Min(x, d) = time-series min over the past d days\n"
            "Max(x, d) = time-series max over the past d days\n"
            "IdxMax(x, d) = which day Max(x, d) occurred on\n"
            "IdxMin(x, d) = which day Min(x, d) occurred on\n"
            "Rank(x, d) = time-series rank in the past d days\n"
            "Sum(x, d) = time-series sum over the past d days\n"
            "Std(x, d) = moving time-series standard deviation over the past d days\n"
            "Greater(x, y) = 1 if x > y, else 0\n"
            "Less(x, y) = 1 if x < y, else 0\n"
        )

    def generate(self, description: str) -> Tuple[str, ast.AST]:
        """
        根据自然语言因子描述生成表达式字符串和AST
        """
        system_prompt = (
            "You are a quant researcher assistant. Given a natural language description of a factor idea, "
            "your job is to output a valid expression using ONLY the allowed features and functions.\n"
            + self.function_definition +
            "\nOutput only a single-line expression string. Do NOT explain or format as code."
        )

        user_prompt = (f"Description: {description}\n"
                    f"Generate the factor expression:")
        try_times = 0
        try:
            response = openai.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            expr = response.choices[0].message.content.strip().replace('"',"")
            expr_ast = self.parse_ast(expr.replace("$", ""))
        except Exception as e:
            try_times += 1
            if try_times < 5:
                print(f"[Warning] LLM generation failed: {e}. Retrying...")
                return self.generate(description)
            else:
                print("[Error] Failed to generate expression after multiple attempts.")
                return "", None
        return expr, expr_ast

    def parse_ast(self, expr: str) -> ast.AST:
        try:
            return ast.parse(expr, mode='eval')
        except SyntaxError as e:
            print(f"[Syntax Error] Cannot parse expression: {expr}")
            return None




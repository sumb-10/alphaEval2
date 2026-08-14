import openai
from typing import Dict, Optional
import os

class IdeaAgent:
    def __init__(self, model="gpt-4o", temperature=1.0):
        self.model = model
        self.temperature = temperature
        self.system_prompt_new = (
            "You are a quantitative researcher. Your task is to propose a factor idea. "
            "Please generate:\n"
            "1. A concise market hypothesis.\n"
            "2. A natural language description of a potential alpha factor related to this hypothesis.\n"
            "Format your response as follows:\n"
            '{ "hypothesis": "<your hypothesis>", '
            '"description": "<your factor description>" }\n'
        )
        self.system_prompt_enhance = (
            "You are a quantitative factor researcher.\n"
            "Given a previous hypothesis and a previous alpha factor (in expression form), as well as its backtest report, "
            "decide whether to improve the existing factor or discard it and propose a new one.\n\n"
            "Now choose one of the following:\n"
            "(A) Improve the existing factor by modifying its logic or smoothing it\n"
            "(B) Discard it and generate a new alpha idea based on the hypothesis\n\n"
            "Please generate:\n"
            "1. A concise market hypothesis.\n"
            "2. A natural language description of a potential alpha factor related to this hypothesis.\n"
            "Format your response as follows:\n"
            '{ "hypothesis": "<your hypothesis>", '
            '"description": "<your factor description>" }\n'
        )

    def generate(self, context: Optional[str] = None, hypothesis: Optional[str] = None, previous_expr: Optional[str] = None,
        eval_report: Optional[str] = None) -> Dict[str, str]:
        """
        使用 LLM 根据市场背景生成 hypothesis + factor description, 用json格式返回
        :param context: 一段自然语言的市场观察、研报摘要等
        :return: dict，包含 'hypothesis' 与 'description'
        """
        if context is not None:
            user_prompt = (
                f"Given the following example factor:\n\n\"{context}\"\n\n"
                f"Generate a market hypothesis and a factor description based on the example.\n"
                f"Do not repeat the example factor, but use it as inspiration.\n\n"
            )

            response = openai.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.system_prompt_new},
                    {"role": "user", "content": user_prompt}
                ]
            )
            # 匹配'{''}'中的内容
            content = response.choices[0].message.content.strip()
            print("[Info] LLM response:", content)
            return self.parse_response(content)
        elif context is None and hypothesis is None and previous_expr is None and eval_report is None:
            user_prompt = ("Please provide a market hypothesis and a factor description.")
            response = openai.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.system_prompt_new},
                    {"role": "user", "content": user_prompt}
                ]
            )
            content = response.choices[0].message.content.strip()
            print("[Info] LLM response:", content)
            return self.parse_response(content)
        elif hypothesis is not None and previous_expr is not None and eval_report is not None:
            user_prompt = (
                f"example factor:\n\n\"{context}\"\n\n"
                f"Previous hypothesis: \"{hypothesis}\"\n"
                f"Previous factor expression: \"{previous_expr}\"\n"
                f"Backtest report: \"{eval_report}\"\n\n"
            )

            response = openai.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[
                    {"role": "system", "content": self.system_prompt_enhance},
                    {"role": "user", "content": user_prompt}
                ]
            )
            # 匹配'{''}'中的内容
            content = response.choices[0].message.content.strip()
            start = content.find('{')
            end = content.rfind('}') + 1
            print(f"[Info] LLM response content length: {len(content)}, start: {start}, end: {end}")
            content = content[start:end]
            if not content.startswith('{') or not content.endswith('}'):
                raise ValueError("LLM response does not match expected JSON format.")
            print("[Info] LLM response:", content)
            return self.parse_response(content)
        else:
            raise ValueError(f"context: {context}, hypothesis: {hypothesis}, previous_expr: {previous_expr}, eval_report: {eval_report} ")

    def parse_response(self, text: str) -> Dict[str, str]:
        """
        解析LLM响应文本，提取 hypothesis 与 description
        """
        import json

        try:
            # 尝试将文本解析为JSON格式
            data = json.loads(text)
            hypothesis = data.get("hypothesis", "").strip()
            description = data.get("description", "").strip()

            if not hypothesis or not description:
                raise ValueError("Missing hypothesis or description in response.")
        except Exception as e:
            print("[Warning] Parse failed:", e)
            return {"hypothesis": "", "description": ""}

        return {
            "hypothesis": hypothesis,
            "description": description
        }



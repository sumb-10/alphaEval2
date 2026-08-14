"""AST 최대공통부분트리 유사도 — 원형 verbatim 포팅.

provenance: vendored_alphaagent/eval_agent.py:10-61.
원형 라벨 정의 `type(node).__name__`는 `$close`와 `$volume`을 모두 `Name`으로
동일 취급한다 (라벨 버그 — 기본 보존). `distinguish_terminals=True`는 수정판
(Name.id / Constant.value / 함수명을 라벨에 포함) — ablation 전용 옵션.
"""
from __future__ import annotations

import ast


class ASTNodeWrapper:
    def __init__(self, node, distinguish_terminals: bool = False):
        self.node = node
        self.children = [ASTNodeWrapper(child, distinguish_terminals)
                         for child in ast.iter_child_nodes(node)]
        self.label = type(node).__name__
        if distinguish_terminals:
            if isinstance(node, ast.Name):
                self.label += f":{node.id}"
            elif isinstance(node, ast.Constant):
                self.label += f":{node.value!r}"
            elif isinstance(node, ast.Attribute):
                self.label += f":{node.attr}"

    def __eq__(self, other):
        return isinstance(other, ASTNodeWrapper) and self.label == other.label

    def __hash__(self):
        return hash(self.label)


def count_nodes(node: ASTNodeWrapper) -> int:
    return 1 + sum(count_nodes(child) for child in node.children)


def max_common_subtree_size(node1: ASTNodeWrapper, node2: ASTNodeWrapper,
                            memo=None) -> int:
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
            dp[i + 1][j + 1] = max(
                dp[i][j + 1],
                dp[i + 1][j],
                dp[i][j] + max_common_subtree_size(children1[i], children2[j], memo)
            )
    match_count += dp[-1][-1]
    memo[key] = match_count
    return match_count


def ast_similarity_by_common_subtree_ast(tree1: ast.AST, tree2: ast.AST,
                                         distinguish_terminals: bool = False) -> float:
    wrapped1 = ASTNodeWrapper(tree1, distinguish_terminals)
    wrapped2 = ASTNodeWrapper(tree2, distinguish_terminals)

    shared = max_common_subtree_size(wrapped1, wrapped2)
    size1 = count_nodes(wrapped1)
    size2 = count_nodes(wrapped2)

    avg_size = (size1 + size2) / 2
    return shared / avg_size if avg_size > 0 else 0.0

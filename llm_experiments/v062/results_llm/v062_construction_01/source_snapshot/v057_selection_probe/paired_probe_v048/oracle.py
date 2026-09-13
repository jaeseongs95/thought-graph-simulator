"""오프라인 채점 전용. runner/프롬프트 생성 경로에서 import하지 않는다."""
from __future__ import annotations
import re
from .contracts import ContractError, require

# 손으로 명시한 유한 진리표. 열 순서: 원식 최종값, NOT(b).
TABLE = {(False, False): (False, True), (False, True): (False, False),
         (True, False): (True, True), (True, True): (False, False)}
AND_TABLE = {(False, False): False, (False, True): False,
             (True, False): False, (True, True): True}

def evaluate(expression: str, a: bool, b: bool) -> bool:
    """표를 사용하지 않는 별도 재귀 하강 파서. eval()은 사용하지 않는다."""
    require(type(a) is bool and type(b) is bool, "bool 입력 필요")
    require(isinstance(expression, str) and len(expression) <= 2000, "식 크기 오류")
    tokens = re.findall(r"NOT|AND|a|b|\(|\)", expression)
    require("".join(tokens) == re.sub(r"\s+", "", expression), "식의 미지원 토큰")
    index = 0
    def factor(depth=0):
        nonlocal index
        require(depth < 100 and index < len(tokens), "불완전한 식/너무 깊은 식")
        token = tokens[index]; index += 1
        if token == "NOT":
            return not factor(depth + 1)
        if token == "(":
            value = conjunction(depth + 1)
            require(index < len(tokens) and tokens[index] == ")", "닫는 괄호 누락")
            index += 1
            return value
        require(token in ("a", "b"), "피연산자 오류")
        return a if token == "a" else b
    def conjunction(depth=0):
        nonlocal index
        value = factor(depth)
        while index < len(tokens) and tokens[index] == "AND":
            index += 1
            right = factor(depth)  # 단락평가 때문에 파싱을 건너뛰지 않는다.
            value = value and right
        return value
    value = conjunction()
    require(index == len(tokens), "식 뒤의 불필요한 토큰")
    return value

def score_pipeline(a: bool, b: bool, parent: bool | None, final: bool | None) -> dict:
    final_expected, not_expected = TABLE[a, b]
    parent_valid = type(parent) is bool
    final_valid = type(final) is bool
    not_correct = parent_valid and parent is not_expected
    local_correct = parent_valid and final_valid and final is AND_TABLE[a, parent]
    final_correct = final_valid and final is final_expected
    return {"not_correct": not_correct, "and_local_correct": local_correct,
            "final_correct": final_correct,
            "trace_correct": not_correct and local_correct and final_correct}

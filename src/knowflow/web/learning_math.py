"""Bounded, non-evaluating answer comparison for local formative practice."""

from __future__ import annotations

import ast
import re
import unicodedata
from fractions import Fraction


def normalize(value):
    value = str(value).replace("²", "**2").replace("³", "**3")
    value = unicodedata.normalize("NFKC", value).strip().lower()
    return (
        re.sub(r"\s+", "", value)
        .replace("−", "-")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("≤", "<=")
        .replace("≥", ">=")
        .replace("^", "**")
    )


def polynomial(text):
    """Return sparse exact coefficients; never eval user or model strings."""
    text = re.sub(r"(?<=[0-9a-z)])(?=[a-z(])", "*", text)
    text = re.sub(r"(?<=\))(?=\d)", "*", text)
    if len(text) > 180 or not re.fullmatch(r"[a-z0-9.+*/()\-]+", text):
        raise ValueError("unsupported expression")
    tree = ast.parse(text, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 90:
        raise ValueError("expression too complex")

    def add(a, b, sign=1):
        out = dict(a)
        for k, v in b.items():
            out[k] = out.get(k, Fraction(0)) + sign * v
        return {k: v for k, v in out.items() if v}

    def multiply(a, b):
        out = {}
        if len(a) * len(b) > 150:
            raise ValueError("expression too complex")
        for x, v in a.items():
            for y, w in b.items():
                k = "".join(sorted(x + y))
                out[k] = out.get(k, Fraction(0)) + v * w
        return {k: v for k, v in out.items() if v}

    def visit(n):
        if isinstance(n, ast.Constant) and type(n.value) in (int, float) and abs(n.value) < 1e12:
            return {"": Fraction(str(n.value))} if n.value else {}
        if isinstance(n, ast.Name) and len(n.id) == 1 and n.id.isascii():
            return {n.id: Fraction(1)}
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            return {
                k: (-v if isinstance(n.op, ast.USub) else v) for k, v in visit(n.operand).items()
            }
        if isinstance(n, ast.BinOp):
            a, b = visit(n.left), visit(n.right)
            if isinstance(n.op, ast.Add):
                return add(a, b)
            if isinstance(n.op, ast.Sub):
                return add(a, b, -1)
            if isinstance(n.op, ast.Mult):
                return multiply(a, b)
            if isinstance(n.op, ast.Div) and set(b) == {""} and b[""]:
                return {k: v / b[""] for k, v in a.items()}
            if isinstance(n.op, ast.Pow) and set(b) <= {""}:
                power = b.get("", 0)
                if power.denominator == 1 and 0 <= power <= 5:
                    out = {"": Fraction(1)}
                    for _ in range(int(power)):
                        out = multiply(out, a)
                    return out
        raise ValueError("unsupported expression")

    return visit(tree.body)


def relation(text):
    parts = re.split(r"(<=|>=|<|>|=)", text)
    if len(parts) == 1:
        return ("expression", tuple(sorted(polynomial(text).items())))
    if len(parts) not in (3, 5):
        raise ValueError("unsupported relation")
    values = []
    for i in range(0, len(parts) - 2, 2):
        left, op, right = parts[i : i + 3]
        a, b = polynomial(left), polynomial(right)
        for k, v in b.items():
            a[k] = a.get(k, Fraction(0)) - v
        a = {k: v for k, v in a.items() if v}
        if op in (">", ">="):
            a = {k: -v for k, v in a.items()}
            op = {">": "<", ">=": "<="}[op]
        if a:
            scale = next(v for _, v in sorted(a.items()))
            if op != "=":
                scale = abs(scale)
            a = {k: v / scale for k, v in a.items()}
        values.append((op, tuple(sorted(a.items()))))
    return ("relations", tuple(sorted(values)))


def grade_answer(question, answer):
    actual, expected = normalize(answer), normalize(question["answer"])
    if not actual:
        raise ValueError("请先填写答案。")
    if question.get("options"):
        if actual.upper() not in "ABCD" or len(actual) != 1:
            raise ValueError("请选择一个选项。")
        return actual == expected
    if actual == expected:
        return True
    if expected in ("是", "否", "对", "错", "无解", ">", "<", "=", ">=", "<="):
        choices = {"是", "否", "对", "错", "无解", ">", "<", "=", ">=", "<="}
        return False if actual in choices else None
    try:
        # A bare numeric answer is accepted for a single-variable solved equation.
        eq = re.fullmatch(r"[a-z]=(.+)", expected)
        if eq and "=" not in actual:
            expected = eq[1]
        if re.fullmatch(r"[a-z]=.+", actual) and "=" not in expected:
            actual = actual.split("=", 1)[1]
        return relation(actual) == relation(expected)
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError):
        return None

"""
Math Tool - Mathematical calculations using SymPy for safety
"""
from sympy import (
    sqrt, sin, cos, tan, asin, acos, atan, log, exp,
    pi, E, Abs, factorial, ceiling, floor,
    Integer, Float, Rational, Symbol,
)
from sympy.parsing.sympy_parser import (
    parse_expr, standard_transformations, implicit_multiplication_application,
)

from utils.response import ToolResponse

_TRANSFORMATIONS = standard_transformations + (implicit_multiplication_application,)
_SAFE_LOCALS = {
    "sqrt": sqrt, "sin": sin, "cos": cos, "tan": tan,
    "asin": asin, "acos": acos, "atan": atan,
    "log": log, "exp": exp, "pi": pi, "e": E,
    "abs": Abs, "factorial": factorial,
    "ceil": ceiling, "floor": floor,
}
# parse_expr's auto_number / implicit-multiplication transformations emit calls
# to these sympy constructors (e.g. 16 → Integer(16)). They MUST be reachable
# in global_dict, otherwise every literal raises "name 'Integer' is not defined".
# We expose only these constructors (no __builtins__/__import__) to keep eval safe.
_SAFE_GLOBALS = {
    "Integer": Integer, "Float": Float, "Rational": Rational, "Symbol": Symbol,
}


def calculate_math(expression: str) -> str:
    """
    Perform precise mathematical calculations.
    Args:
        expression: Math expression (e.g., 'sqrt(144) + 10', 'sin(pi/2)')
    """
    print(f"🧮 [Math] Calculating: {expression}")
    try:
        # parse_expr with empty global_dict prevents __import__ and arbitrary eval
        expr = parse_expr(
            expression,
            local_dict=_SAFE_LOCALS,
            global_dict=_SAFE_GLOBALS,
            transformations=_TRANSFORMATIONS,
        )
        result = float(expr.evalf())
        return ToolResponse.success({"expression": expression, "result": result})
    except Exception as e:
        return ToolResponse.error(str(e))

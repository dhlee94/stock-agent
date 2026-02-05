"""
Math Tool - Mathematical calculations
"""
import json
import math


def calculate_math(expression: str) -> str:
    """
    Perform precise mathematical calculations.
    Args:
        expression: Math expression (e.g., 'sqrt(144) + 10', 'sin(pi/2)')
    """
    print(f"🧮 [Math] Calculating: {expression}")
    try:
        allowed = {
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "log": math.log, "log10": math.log10, "exp": math.exp,
            "pi": math.pi, "e": math.e, "pow": pow, "abs": abs
        }
        result = eval(expression, {"__builtins__": {}}, allowed)
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})

"""
Math Tool - Mathematical calculations using SymPy for safety
"""
import json
import sympy


from utils.response import ToolResponse

def calculate_math(expression: str) -> str:
    """
    Perform precise mathematical calculations.
    Args:
        expression: Math expression (e.g., 'sqrt(144) + 10', 'sin(pi/2)')
    """
    print(f"🧮 [Math] Calculating: {expression}")
    try:
        # Use sympy to safely evaluate the expression
        expr = sympy.sympify(expression)
        result = float(expr.evalf())
        return ToolResponse.success({"expression": expression, "result": result})
    except Exception as e:
        return ToolResponse.error(str(e))

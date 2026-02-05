"""
Code Tool - Python code execution in sandboxed environment
"""
import json
import math


def execute_python(code: str) -> str:
    """
    Execute Python code in a sandboxed environment.
    Args:
        code: Python code string to execute.
    """
    print(f"💻 [Code] Executing:\n{code[:100]}...")
    try:
        local_scope = {}
        safe_builtins = {
            "print": print, "len": len, "range": range, "str": str, 
            "int": int, "float": float, "list": list, "dict": dict,
            "sum": sum, "max": max, "min": min, "abs": abs, "round": round
        }
        exec(code, {"__builtins__": safe_builtins, "math": math}, local_scope)
        return json.dumps({"status": "success", "variables": str(local_scope)})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

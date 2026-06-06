"""
Code Tool - Python code execution in sandboxed environment
"""
import json
import math
import numpy as np
import pandas as pd


from utils.response import ToolResponse

def execute_python(code: str) -> str:
    """
    Execute Python code for data analysis.
    Args:
        code: Python code string to execute.
    """
    print(f"💻 [Code] Executing:\n{code[:100]}...")
    try:
        # Block module-access patterns and Python object-model escape chains.
        # String-matching cannot prevent all sandbox escapes — for production use
        # RestrictedPython or subprocess-based isolation instead.
        _FORBIDDEN = [
            # Module / system access
            "os.", "subprocess.", "sys.", "pathlib", "socket", "shutil",
            "eval(", "exec(", "open(", "__import__", "importlib",
            # Object-model escape: ().__class__.__bases__[0].__subclasses__() etc.
            "__class__", "__bases__", "__subclasses__", "__globals__",
            "__builtins__", "__spec__", "__loader__", "__init__",
            "__dict__", "__module__", "mro(", "getattr(", "setattr(",
            "delattr(", "vars(", "dir(",
        ]
        for pattern in _FORBIDDEN:
            if pattern in code:
                return ToolResponse.error(f"Forbidden pattern detected: {pattern!r}")

        local_scope = {}
        safe_builtins = {
            "print": print, "len": len, "range": range, "str": str,
            "int": int, "float": float, "list": list, "dict": dict,
            "sum": sum, "max": max, "min": min, "abs": abs, "round": round,
            "enumerate": enumerate, "zip": zip, "sorted": sorted,
            "isinstance": isinstance, "bool": bool, "tuple": tuple,
        }
        globals_scope = {
            "__builtins__": safe_builtins,
            "math": math,
            "np": np,
            "pd": pd,
            "numpy": np,
            "pandas": pd,
        }

        exec(code, globals_scope, local_scope)
        
        # Filter local_scope to only include JSON serializable types for the response
        serializable_vars = {}
        for k, v in local_scope.items():
            if isinstance(v, (int, float, str, bool, list, dict, type(None))):
                serializable_vars[k] = v
            elif isinstance(v, (pd.DataFrame, pd.Series)):
                serializable_vars[k] = v.head(5).to_dict()
            elif isinstance(v, np.ndarray):
                serializable_vars[k] = v.tolist()[:10]
        
        return ToolResponse.success({"variables": str(serializable_vars)})
    except Exception as e:
        return ToolResponse.error(str(e))

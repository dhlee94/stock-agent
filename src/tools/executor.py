"""
Code Tool - Python code execution in sandboxed environment
"""
import builtins as _builtins
import math
import numpy as np

from utils.response import ToolResponse

# numpy/math 서브모듈만 허용하는 제한된 __import__.
# exec()에 커스텀 __builtins__ dict를 넘기면 Python이 그 dict에서 __import__를 찾음.
# numpy 3.x는 .mean() 같은 연산 중 서브모듈을 지연 로딩하므로 반드시 필요.
_ALLOWED_IMPORT_TOPS = frozenset({
    "numpy", "math", "cmath", "decimal", "fractions", "statistics",
})

def _sandbox_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in _ALLOWED_IMPORT_TOPS:
        raise ImportError(f"import of '{name}' is blocked in sandbox")
    return _builtins.__import__(name, globals, locals, fromlist, level)


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
            # pandas/numpy escape vectors: pd.eval(), np.vectorize(eval), np.frompyfunc
            ".eval(", ".vectorize", ".frompyfunc",
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
            "__import__": _sandbox_import,   # numpy 내부 지연 로딩 허용 (허용 목록 한정)
            "print": print, "len": len, "range": range, "str": str,
            "int": int, "float": float, "list": list, "dict": dict,
            "sum": sum, "max": max, "min": min, "abs": abs, "round": round,
            "enumerate": enumerate, "zip": zip, "sorted": sorted,
            "isinstance": isinstance, "bool": bool, "tuple": tuple,
        }
        # pd is intentionally excluded: pd.eval() / DataFrame.eval() can execute
        # arbitrary expressions and bypass all pattern-based blacklists.
        globals_scope = {
            "__builtins__": safe_builtins,
            "math": math,
            "np": np,
            "numpy": np,
        }

        exec(code, globals_scope, local_scope)
        
        # Filter local_scope to only include JSON serializable types for the response
        serializable_vars = {}
        for k, v in local_scope.items():
            if isinstance(v, (int, float, str, bool, list, dict, type(None))):
                serializable_vars[k] = v
            elif isinstance(v, np.ndarray):
                serializable_vars[k] = v.tolist()[:10]
        
        return ToolResponse.success({"variables": str(serializable_vars)})
    except Exception as e:
        return ToolResponse.error(str(e))

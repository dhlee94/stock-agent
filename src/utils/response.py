import json
from typing import Any, Dict, Optional

class ToolResponse:
    """Standardized tool response formatter."""
    
    @staticmethod
    def success(data: Any) -> str:
        """Return a successful JSON response."""
        response = {"status": "success"}
        if isinstance(data, dict):
            response.update(data)
        else:
            response["result"] = data
        return json.dumps(response, ensure_ascii=False)

    @staticmethod
    def error(message: str, details: Optional[Dict] = None) -> str:
        """Return an error JSON response."""
        response = {
            "status": "error",
            "message": message
        }
        if details:
            response["details"] = details
        return json.dumps(response, ensure_ascii=False)

"""
Document Tool - File reading functionality
"""
import json
import os


from utils.response import ToolResponse

def read_document(filepath: str) -> str:
    """
    Read the content of a local document file (txt, md, py, json, etc.).
    Args:
        filepath: Relative or absolute path to the file.
    """
    print(f"📄 [Doc] Reading: {filepath}")
    
    # Security: Resolve absolute path and restrict to project root
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        abs_path = os.path.abspath(filepath)
        
        # Check if it's within project root (os.sep 포함으로 형제 디렉터리 우회 방지)
        if not (abs_path == project_root or abs_path.startswith(project_root + os.sep)):
            return ToolResponse.error("Access denied: Path is outside project root", {"path": filepath})
            
        # Block sensitive files
        filename = os.path.basename(abs_path)
        if filename in [".env", "database.py", "mcp_server.py"] or filename.startswith(".git"):
             return ToolResponse.error("Access denied: Sensitive file", {"path": filepath})

        if not os.path.exists(abs_path):
            return ToolResponse.error("File not found", {"path": abs_path})

        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return ToolResponse.success({
            "path": abs_path,
            "size": len(content),
            "content": content[:5000] + ("..." if len(content) > 5000 else "")
        })
    except Exception as e:
        return ToolResponse.error(str(e))

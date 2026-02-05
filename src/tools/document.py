"""
Document Tool - File reading functionality
"""
import json
import os


def read_document(filepath: str) -> str:
    """
    Read the content of a local document file (txt, md, py, json, etc.).
    Args:
        filepath: Absolute path to the file.
    """
    print(f"📄 [Doc] Reading: {filepath}")
    if not os.path.exists(filepath):
        return json.dumps({"error": "File not found", "path": filepath})
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return json.dumps({
            "path": filepath,
            "size": len(content),
            "content": content[:5000] + ("..." if len(content) > 5000 else "")
        })
    except Exception as e:
        return json.dumps({"error": str(e)})

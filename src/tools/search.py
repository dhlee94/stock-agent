"""
Search Tool - Web search functionality
"""
import json


def search_web(query: str) -> str:
    """
    Search the web for information.
    Args:
        query: The search query.
    """
    print(f"🔎 [Search] Query: '{query}'")
    return json.dumps({
        "results": [
            {"title": f"Result for {query}", "snippet": "This is a mock search result describing the topic.", "link": "http://example.com/1"},
            {"title": "Another related page", "snippet": "More information relevant to the search query.", "link": "http://example.com/2"}
        ]
    }, ensure_ascii=False)

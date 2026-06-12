"""
Search Tool - Web search functionality using DuckDuckGo
"""
import json
from ddgs import DDGS

def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the web for real-time information.
    Args:
        query: The search query.
        max_results: Maximum number of results to return.
    """
    max_results = min(max(1, int(max_results)), 20)
    print(f"🔎 [Search] Query: '{query}'")
    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get('title'),
                    "snippet": r.get('body'),
                    "link": r.get('href')
                })
            
            if not results:
                return json.dumps({"error": f"No results found for '{query}'"}, ensure_ascii=False)
                
            return json.dumps({"results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Search failed: {str(e)}"}, ensure_ascii=False)

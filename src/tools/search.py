"""
Search Tool - 웹 검색 기능을 제공하는 도구
"""
import json


def search_web(query: str) -> str:
    """
    간단한 웹 검색을 수행하는 Mock 도구입니다.
    실제 검색 대신 예시 결과를 반환합니다.
    
    Args:
        query: 검색어 문자열
    """
    print(f"🔎 [Search] 검색 질의: '{query}'")
    return json.dumps(
        {
            "results": [
                {
                    "title": f"{query} 관련 검색 결과 1",
                    "snippet": "해당 주제에 대한 예시 설명입니다 (Mock Result).",
                    "link": "http://example.com/1",
                },
                {
                    "title": f"{query} 관련 추가 페이지",
                    "snippet": "검색어와 연관된 추가 정보 예시입니다 (Mock Result).",
                    "link": "http://example.com/2",
                },
            ]
        },
        ensure_ascii=False,
    )

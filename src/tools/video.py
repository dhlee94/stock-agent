"""
Video Tool - Video search functionality
"""
import json


def search_video(keywords: str) -> str:
    """
    Search for videos on YouTube or other platforms.
    Args:
        keywords: Keywords to search for videos.
    """
    print(f"🎥 [Video] Searching: {keywords}")
    return json.dumps({
        "results": [
            {"title": f"{keywords} Tutorial", "channel": "TechChannel", "link": "https://youtube.com/watch?v=abc123", "views": "1.2M"},
            {"title": f"Learn {keywords} in 10 minutes", "channel": "QuickLearn", "link": "https://youtube.com/watch?v=xyz789", "views": "500K"}
        ]
    }, ensure_ascii=False)

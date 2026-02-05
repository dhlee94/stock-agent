from mcp.server.fastmcp import FastMCP
from playwright.sync_api import sync_playwright
import json
import os
import math
from .memory_store import MemoryStore

# Initialize Server
mcp = FastMCP("Memento Agent Tools")
memory_store = MemoryStore()

# =========================================================
# 🔎 1. Search Tool
# =========================================================
@mcp.tool()
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

# =========================================================
# 🕷️ 2. Crawl Tool
# =========================================================
@mcp.tool()
def crawl_url(url: str) -> str:
    """
    Crawl a URL and return its text content using a headless browser.
    Args:
        url: The URL to crawl.
    """
    print(f"🕷️ [Crawl] Visiting: {url}")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            content = page.locator("body").inner_text()
            browser.close()
            return f"--- Content of {url} ---\n{content[:3000]}..."
    except Exception as e:
        return f"Failed to crawl {url}. Error: {str(e)}"

# =========================================================
# 🎥 3. Video Tool
# =========================================================
@mcp.tool()
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

# =========================================================
# 🖼️ 4. Image Tool
# =========================================================
@mcp.tool()
def process_image(action: str, prompt: str) -> str:
    """
    Generate or analyze images.
    Args:
        action: 'generate' to create an image, 'analyze' to describe an image.
        prompt: Description for generation OR image URL for analysis.
    """
    print(f"🖼️ [Image] Action: {action}, Prompt: {prompt}")
    if action == "generate":
        return json.dumps({
            "status": "success",
            "image_url": "https://storage.example.com/generated_image_123.png",
            "prompt": prompt
        })
    elif action == "analyze":
        return json.dumps({
            "status": "success",
            "description": f"This image shows: {prompt[:50]}... Analysis complete.",
            "objects_detected": ["person", "building", "sky"]
        })
    return "Invalid action. Use 'generate' or 'analyze'."

# =========================================================
# 💻 5. Code Tool
# =========================================================
@mcp.tool()
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

# =========================================================
# 🧮 6. Math Tool
# =========================================================
@mcp.tool()
def calculate_math(expression: str) -> str:
    """
    Perform precise mathematical calculations.
    Args:
        expression: Math expression (e.g., 'sqrt(144) + 10', 'sin(pi/2)')
    """
    print(f"🧮 [Math] Calculating: {expression}")
    try:
        allowed = {
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
            "log": math.log, "log10": math.log10, "exp": math.exp,
            "pi": math.pi, "e": math.e, "pow": pow, "abs": abs
        }
        result = eval(expression, {"__builtins__": {}}, allowed)
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return json.dumps({"error": str(e)})

# =========================================================
# 📄 7. Document Tool
# =========================================================
@mcp.tool()
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

# =========================================================
# 🧠 8. Memory Tool (Save Feedback)
# =========================================================
@mcp.tool()
def save_feedback(task: str, plan: str, result: str, feedback_score: float) -> str:
    """
    Save the task execution result to memory for future reference.
    Args:
        task: The original task description.
        plan: The plan that was executed.
        result: The final output or summary of the execution.
        feedback_score: A score from 0.0 to 1.0 indicating success.
    """
    print(f"🧠 [Memory] Saving trajectory for task: {task[:50]}...")
    try:
        memory_store.save_trajectory(task, plan, result, feedback_score)
        return json.dumps({"status": "success", "message": "Trajectory saved to memory."})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

# =========================================================
# 📈 9. Stock Analysis Tool
# =========================================================
@mcp.tool()
def analyze_stock(ticker: str, name: str, market: str = "KR") -> str:
    """
    Analyze a stock using AI (Chronos + FinBERT multimodal fusion).
    Returns current price, AI sentiment score, and buy/sell recommendation.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "NVDA" for NVIDIA)
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" for Korean stocks, "US" for US stocks
    """
    print(f"📈 [Stock] Analyzing: {name} ({ticker}) in {market} market")
    try:
        from .stock_tool import analyze_stock as _analyze
        result = _analyze(ticker, name, market)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})

if __name__ == "__main__":
    print("🚀 Memento MCP Server Started!")
    print("   Tools: search_web, crawl_url, search_video, process_image, execute_python, calculate_math, read_document, save_feedback, analyze_stock")
    mcp.run()


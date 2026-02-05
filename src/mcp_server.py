"""
Memento MCP Server - Tool Server with Modular Architecture

This server exposes various tools via the MCP protocol.
Each tool is implemented in a separate module under src/tools/
"""
from mcp.server.fastmcp import FastMCP

# Import all tools from the tools package
from .tools import (
    search_web,
    crawl_url,
    search_video,
    process_image,
    execute_python,
    calculate_math,
    read_document,
    save_feedback,
    analyze_stock,
)

# Initialize MCP Server
mcp = FastMCP("Memento Agent Tools")

# =========================================================
# Register Tools with MCP Decorators
# =========================================================

@mcp.tool()
def search_web_tool(query: str) -> str:
    """
    Search the web for information.
    Args:
        query: The search query.
    """
    return search_web(query)


@mcp.tool()
def crawl_url_tool(url: str) -> str:
    """
    Crawl a URL and return its text content using a headless browser.
    Args:
        url: The URL to crawl.
    """
    return crawl_url(url)


@mcp.tool()
def search_video_tool(keywords: str) -> str:
    """
    Search for videos on YouTube or other platforms.
    Args:
        keywords: Keywords to search for videos.
    """
    return search_video(keywords)


@mcp.tool()
def process_image_tool(action: str, prompt: str) -> str:
    """
    Generate or analyze images.
    Args:
        action: 'generate' to create an image, 'analyze' to describe an image.
        prompt: Description for generation OR image URL for analysis.
    """
    return process_image(action, prompt)


@mcp.tool()
def execute_python_tool(code: str) -> str:
    """
    Execute Python code in a sandboxed environment.
    Args:
        code: Python code string to execute.
    """
    return execute_python(code)


@mcp.tool()
def calculate_math_tool(expression: str) -> str:
    """
    Perform precise mathematical calculations.
    Args:
        expression: Math expression (e.g., 'sqrt(144) + 10', 'sin(pi/2)')
    """
    return calculate_math(expression)


@mcp.tool()
def read_document_tool(filepath: str) -> str:
    """
    Read the content of a local document file (txt, md, py, json, etc.).
    Args:
        filepath: Absolute path to the file.
    """
    return read_document(filepath)


@mcp.tool()
def save_feedback_tool(task: str, plan: str, result: str, feedback_score: float) -> str:
    """
    Save the task execution result to memory for future reference.
    Args:
        task: The original task description.
        plan: The plan that was executed.
        result: The final output or summary of the execution.
        feedback_score: A score from 0.0 to 1.0 indicating success.
    """
    return save_feedback(task, plan, result, feedback_score)


@mcp.tool()
def analyze_stock_tool(ticker: str, name: str, market: str = "KR") -> str:
    """
    Analyze a stock using AI (Chronos + FinBERT multimodal fusion).
    Returns current price, AI sentiment score, and buy/sell recommendation.
    Args:
        ticker: Stock ticker symbol (e.g., "005930.KS" for Samsung, "NVDA" for NVIDIA)
        name: Company name (e.g., "Samsung Electronics", "NVIDIA")
        market: "KR" for Korean stocks, "US" for US stocks
    """
    return analyze_stock(ticker, name, market)


# =========================================================
# Main Entry Point
# =========================================================
if __name__ == "__main__":
    print("🚀 Memento MCP Server Started!")
    print("   Tools: search_web, crawl_url, search_video, process_image,")
    print("          execute_python, calculate_math, read_document,")
    print("          save_feedback, analyze_stock")
    mcp.run()

"""
Crawl Tool - URL content extraction using Playwright
"""
from playwright.sync_api import sync_playwright


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

"""
Crawl Tool - URL content extraction using Playwright
"""
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

_ALLOWED_SCHEMES = {"http", "https"}
# Block internal/cloud-metadata endpoints
_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.169.254",   # AWS/GCP metadata
    "metadata.google.internal",
}


def _validate_url(url: str) -> str | None:
    """Return error string if URL should be blocked, None if safe."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"Scheme '{parsed.scheme}' not allowed (http/https only)"
    host = parsed.hostname or ""
    if host in _BLOCKED_HOSTS or host.startswith("192.168.") or host.startswith("10."):
        return f"Host '{host}' is blocked (internal network)"
    return None


def crawl_url(url: str) -> str:
    """
    Crawl a URL and return its text content using a headless browser.
    Args:
        url: The URL to crawl.
    """
    err = _validate_url(url)
    if err:
        return f"Blocked: {err}"

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

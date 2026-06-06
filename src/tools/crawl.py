"""
Crawl Tool - URL content extraction using Playwright
"""
import ipaddress
import socket
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

_ALLOWED_SCHEMES = {"http", "https"}
# Block well-known internal hostnames and cloud metadata endpoints
_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",    # AWS/GCP/Azure IMDS
    "100.100.100.200",    # Alibaba Cloud metadata
}


def _is_blocked_ip(addr: str) -> bool:
    """Return True if the resolved IP is private/loopback/link-local/reserved."""
    try:
        ip = ipaddress.ip_address(addr)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        )
    except ValueError:
        return False


def _validate_url(url: str) -> str | None:
    """Return error string if URL should be blocked, None if safe."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"Scheme '{parsed.scheme}' not allowed (http/https only)"
    host = parsed.hostname or ""
    if not host:
        return "Missing host"
    if host in _BLOCKED_HOSTS:
        return f"Host '{host}' is blocked (internal network)"
    # Resolve hostname and reject any private/internal IP address.
    # This catches RFC-1918 (10/8, 172.16/12, 192.168/16), IPv6 loopback (::1),
    # link-local (fe80::/10), and ULA (fc00::/7).
    try:
        resolved = socket.getaddrinfo(host, None)
        for info in resolved:
            addr = info[4][0]
            if _is_blocked_ip(addr):
                return f"Host '{host}' resolves to blocked address '{addr}'"
    except socket.gaierror:
        return f"Cannot resolve host '{host}'"
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

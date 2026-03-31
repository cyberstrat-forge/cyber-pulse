"""Shared HTTP headers for browser-like requests."""

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: Only include encodings that httpx supports natively (gzip, deflate)
    # Brotli (br) requires additional dependencies (brotli/brotlicffi)
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


def get_browser_headers(custom: dict | None = None) -> dict[str, str]:
    """Get browser-like headers for HTTP requests.

    Args:
        custom: Optional custom headers to merge.

    Returns:
        Dictionary of HTTP headers.
    """
    headers = DEFAULT_HEADERS.copy()
    if custom:
        headers.update(custom)
    return headers

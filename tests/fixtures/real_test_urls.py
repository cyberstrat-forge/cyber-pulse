"""Real problematic URLs for integration testing.

These URLs are extracted from issues/ directory and validated through
manual testing. They represent real-world content extraction challenges.
"""

# URLs that work with Level 1 (httpx + trafilatura)
LEVEL1_SUCCESS_URLS = [
    # paulgraham.com - classic essays, no JS
    ("http://www.paulgraham.com/superlinear.html", "paulgraham.com"),
    # mitchellh.com - technical blog
    ("https://mitchellh.com/writing/my-ai-adoption-journey", "mitchellh.com"),
]

# URLs that need Level 2 (Jina AI) - Level 1 returns 403
LEVEL2_RESCUE_URLS = [
    # OpenAI blog - Cloudflare protection
    ("https://openai.com/index/chatgpt/", "openai"),
    # Anthropic Research - Cloudflare
    ("https://www.anthropic.com/research/alignment-faking", "anthropic"),
]

# URLs with known title-body similarity issue
TITLE_AS_BODY_URLS = [
    # Anthropic Research - title sometimes extracted as body
    ("https://www.anthropic.com/research/constitutional-classifiers", "anthropic"),
]

# URLs that fail both levels (for testing REJECTED status)
EXPECTED_FAIL_URLS = [
    # WeChat requires special handling
    ("https://mp.weixin.qq.com/s?__biz=MzU3ODQ0NjA3Mg==&mid=2247486001", "wechat"),
]

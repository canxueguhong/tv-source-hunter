# -*- coding: utf-8 -*-
"""Module 2 — Page Analyzer: Fetch pages and extract TVBox interface URLs."""

import re
import asyncio
import httpx
import config


# Compiled regex patterns for URL extraction
_JSON_URL_RE = re.compile(r'https?://[^\s"\'<>\)\]\}\uff09\u3011]{5,500}\.json(?:\b|$)', re.IGNORECASE)
_GENERIC_URL_RE = re.compile(r'https?://[^\s"\'<>\)\]\}\uff09\u3011]{10,500}', re.IGNORECASE)

_MAX_URL_LENGTH = 500  # discard absurdly long regex matches

# TVBox-related generic keywords (stable)
_TVBOX_CONTEXT_KEYWORDS = [
    "tvbox", "影视仓", "storeHouse", "sites", "spider",
    "接口", "多仓", "线路", "配置", "source", "repo",
    "json", "raw.githubusercontent", "gh-proxy", "gitlab",
]

# Active source authors — update this list as authors change
# (separated for easy maintenance)
_TVBOX_AUTHOR_KEYWORDS = [
    "饭太硬", "肥猫", "高天流云", "香雅情", "南风",
]

_ALL_CONTEXT_KEYWORDS = _TVBOX_CONTEXT_KEYWORDS + _TVBOX_AUTHOR_KEYWORDS

# File extensions and patterns to skip
_SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3", ".zip",
    ".tar", ".gz", ".pdf", ".doc", ".docx", ".apk",
)


def _clean_url(url: str) -> str:
    """Clean up extracted URL by removing trailing punctuation and brackets."""
    # Remove trailing characters that are likely not part of the URL
    url = url.rstrip(".,;:!?。，；：！？\"'」】》）")
    # Remove trailing English parentheses if unbalanced
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    # Remove trailing Chinese parentheses if unbalanced
    while url.endswith("\uff09") and url.count("\uff08") < url.count("\uff09"):
        url = url[:-1]
    # Remove trailing 】 if unbalanced
    while url.endswith("\u3011") and url.count("\u3010") < url.count("\u3011"):
        url = url[:-1]
    # Length sanity check
    if len(url) > _MAX_URL_LENGTH:
        return ""
    return url


def _is_candidate_url(url: str) -> bool:
    """Check if URL looks like a potential TVBox interface URL."""
    lower = url.lower()

    # Skip non-relevant file types
    for ext in _SKIP_EXTENSIONS:
        if lower.endswith(ext):
            return False

    # Length check
    if len(url) > _MAX_URL_LENGTH:
        return False

    # Skip common non-TVBox sites
    skip_domains = [
        "google.com", "youtube.com", "facebook.com", "twitter.com",
        "wikipedia.org", "amazon.com", "apple.com", "microsoft.com",
        "stackoverflow.com", "reddit.com",
    ]
    for domain in skip_domains:
        if domain in lower:
            return False

    # Filter baidu search result pages (but NOT baidu share/pan links)
    if "baidu.com/s?" in lower:
        return False

    # Accept .json URLs directly
    if lower.endswith(".json"):
        return True

    # Accept URLs with TVBox-related path segments
    tvbox_path_hints = [
        "/tv/", "/tvbox", "/storeHouse", "/sites",
        "raw.githubusercontent.com", "gh-proxy", "gitlab.com",
        "/box/",
    ]
    for hint in tvbox_path_hints:
        if hint in url:
            return True

    return False


def extract_urls_from_text(text: str) -> list[str]:
    """Extract candidate TVBox interface URLs from page text."""
    candidates = set()

    # 1) Extract all .json URLs
    for match in _JSON_URL_RE.finditer(text):
        url = _clean_url(match.group(0))
        if url and _is_candidate_url(url):
            candidates.add(url)

    # 2) Look for URLs near TVBox keywords
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line_lower = line.lower()
        has_keyword = any(kw in line_lower for kw in _ALL_CONTEXT_KEYWORDS)
        if not has_keyword:
            continue

        # Check this line and nearby lines for URLs
        context_start = max(0, i - 2)
        context_end = min(len(lines), i + 3)
        context = "\n".join(lines[context_start:context_end])

        for match in _GENERIC_URL_RE.finditer(context):
            url = _clean_url(match.group(0))
            if url and _is_candidate_url(url):
                candidates.add(url)

    return list(candidates)


async def fetch_page(client: httpx.AsyncClient, url: str, semaphore: asyncio.Semaphore) -> str:
    """Fetch a single page and return its text content."""
    async with semaphore:
        try:
            resp = await client.get(
                url,
                timeout=config.REQUEST_TIMEOUT,
                follow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.text
            else:
                return ""
        except Exception:
            return ""


async def analyze_pages(search_results: list[dict]) -> list[str]:
    """
    Fetch all search result pages and extract candidate TVBox interface URLs.
    Returns deduplicated list of candidate URLs.
    """
    if not search_results:
        return []

    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
    all_candidates: set[str] = set()

    print(f"\n[分析] 开始抓取 {len(search_results)} 个页面...")

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        verify=False,  # some TVBox sources use self-signed certs
    ) as client:

        tasks = []
        for item in search_results:
            tasks.append(fetch_page(client, item["url"], semaphore))

        pages = await asyncio.gather(*tasks)

        for item, page_text in zip(search_results, pages):
            if not page_text:
                continue

            urls = extract_urls_from_text(page_text)
            if urls:
                print(f"  ✓ {item['url'][:60]:60s} → 提取 {len(urls)} 个候选 URL")
                all_candidates.update(urls)

    # Also check if any search result URL itself is a .json endpoint
    for item in search_results:
        url = item["url"]
        if _is_candidate_url(url):
            all_candidates.add(url)

    print(f"\n[分析] 完成! 共提取 {len(all_candidates)} 个不重复的候选接口 URL")
    return list(all_candidates)


if __name__ == "__main__":
    # Quick test with a sample URL
    test_text = '''
    TVBox接口地址: https://example.com/tvbox/config.json
    多仓源: https://gh-proxy.com/raw.githubusercontent.com/user/repo/main/tv.json
    普通链接: https://google.com
    '''
    urls = extract_urls_from_text(test_text)
    print("Extracted:", urls)

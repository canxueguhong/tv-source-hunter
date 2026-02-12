# -*- coding: utf-8 -*-
"""
Live Source — Page Analyzer: Extract m3u/m3u8 **file** URLs from pages.

IMPORTANT: We only extract URLs pointing to .m3u / .m3u8 FILES and
raw code-hosting links that likely contain playlist files — NOT individual
stream URLs (e.g. http://xxx.ts or http://xxx:port/live/...).
This is critical to avoid extracting 10,000+ individual channel streams
from pages that display m3u file contents.
"""

import re
import asyncio
import httpx
import config


# Only match URLs ending in .m3u or .m3u8 (playlist files)
_M3U_FILE_RE = re.compile(
    r'https?://[^\s"\'<>\)\]\}\uff09\u3011]{5,500}\.m3u8?(?:\b|["\'\s<>\)\]\}])',
    re.IGNORECASE,
)

# Raw content URLs on code hosting platforms (likely playlist files)
_CODE_RAW_URL_RE = re.compile(
    r'https?://(?:'
    r'raw\.githubusercontent\.com|'
    r'gist\.githubusercontent\.com|'
    r'gitlab\.com/[^\s"\'<>]+/-/raw|'
    r'gitee\.com/[^\s"\'<>]+/raw|'
    r'jihulab\.com/[^\s"\'<>]+/-/raw|'
    r'codeberg\.org/[^\s"\'<>]+/raw|'
    r'gh-proxy\.[^\s"\'<>]+|'
    r'ghproxy\.[^\s"\'<>]+'
    r')[^\s"\'<>\)\]\}]{5,500}',
    re.IGNORECASE,
)

# Keywords that tell us a code-hosting URL is live-source related
_LIVE_PATH_HINTS = [
    "m3u", "iptv", "live", "playlist", "channel", "tv", "stream",
    "adult", "nsfw", "documentary", "variety",
]

# Non-relevant domains to skip
_SKIP_DOMAINS = [
    "google.com", "youtube.com", "facebook.com", "twitter.com",
    "wikipedia.org", "amazon.com", "apple.com", "microsoft.com",
    "stackoverflow.com",
]

_MAX_URL_LENGTH = 500


def _clean_url(url: str) -> str:
    """Clean extracted URL."""
    url = url.rstrip(".,;:!?。，；：！？\"'」】》）\t\r\n ")
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    while url.endswith("\uff09") and url.count("\uff08") < url.count("\uff09"):
        url = url[:-1]
    if len(url) > _MAX_URL_LENGTH:
        return ""
    return url


def _is_live_file_candidate(url: str) -> bool:
    """
    Only accept URLs that point to m3u/m3u8 FILES or
    code-hosting raw URLs with IPTV/live path hints.
    Reject individual stream URLs.
    """
    lower = url.lower()

    if len(url) > _MAX_URL_LENGTH:
        return False

    for domain in _SKIP_DOMAINS:
        if domain in lower:
            return False

    # Direct m3u/m3u8 file — always accept
    if lower.endswith(".m3u") or lower.endswith(".m3u8"):
        return True

    # Code-hosting raw URL — only if path contains live-related hints
    code_hosts = [
        "raw.githubusercontent.com", "gist.githubusercontent.com",
        "gitlab.com", "codeberg.org", "gitee.com", "jihulab.com",
        "gh-proxy", "ghproxy",
    ]
    for host in code_hosts:
        if host in lower:
            if any(hint in lower for hint in _LIVE_PATH_HINTS):
                return True
            break  # matched a code host but no live hints

    return False


def extract_live_urls_from_text(text: str) -> list[str]:
    """
    Extract candidate live source FILE URLs from page text.
    Strictly only .m3u/.m3u8 file links and code-hosting raw links.
    """
    candidates = set()

    # 1) Direct .m3u / .m3u8 file URLs
    for match in _M3U_FILE_RE.finditer(text):
        raw = match.group(0)
        url = _clean_url(raw)
        if url and _is_live_file_candidate(url):
            candidates.add(url)

    # 2) Code-hosting raw URLs near IPTV/live keywords (contextual)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line_lower = line.lower()
        # Only scan lines with live-related keywords
        has_keyword = any(kw in line_lower for kw in [
            "m3u", "iptv", "playlist", "直播", "live", "channel",
            "adult", "nsfw", "documentary", "纪录片", "综艺",
        ])
        if not has_keyword:
            continue

        context_start = max(0, i - 2)
        context_end = min(len(lines), i + 3)
        context = "\n".join(lines[context_start:context_end])

        for match in _CODE_RAW_URL_RE.finditer(context):
            url = _clean_url(match.group(0))
            if url and _is_live_file_candidate(url):
                candidates.add(url)

    return list(candidates)


async def fetch_page(client: httpx.AsyncClient, url: str,
                     semaphore: asyncio.Semaphore) -> str:
    """Fetch a page and return text content (Chinese/English only)."""
    async with semaphore:
        try:
            resp = await client.get(
                url, timeout=config.REQUEST_TIMEOUT, follow_redirects=True,
            )
            if not (200 <= resp.status_code < 300):
                return ""

            text = resp.text

            # Language filter: check first 2000 chars
            sample = text[:2000]
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in sample)
            ascii_ratio = sum(1 for c in sample if ord(c) < 128) / max(len(sample), 1)
            if not has_chinese and ascii_ratio < 0.5:
                return ""  # likely non-CN/EN page

            return text
        except Exception:
            return ""


async def analyze_live_pages(search_results: list[dict]) -> list[dict]:
    """
    Fetch search result pages and extract live source FILE URLs.
    Returns list of {url, category}.
    """
    if not search_results:
        return []

    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)
    all_candidates: list[dict] = []
    seen_urls: set[str] = set()

    print(f"\n[直播分析] 抓取 {len(search_results)} 个页面...")

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        verify=False,
        proxy=None,
        trust_env=False,
    ) as client:

        tasks = [fetch_page(client, item["url"], semaphore) for item in search_results]
        pages = await asyncio.gather(*tasks)

        for item, page_text in zip(search_results, pages):
            if not page_text:
                continue

            urls = extract_live_urls_from_text(page_text)
            if urls:
                print(f"  ✓ {item['url'][:55]:55s} → {len(urls)} 个m3u文件链接")
                for u in urls:
                    if u not in seen_urls:
                        seen_urls.add(u)
                        all_candidates.append({
                            "url": u,
                            "category": item.get("category", "unknown"),
                        })

    # Also check if search result URLs themselves are m3u files
    for item in search_results:
        url = item["url"]
        if url not in seen_urls and _is_live_file_candidate(url):
            seen_urls.add(url)
            all_candidates.append({
                "url": url,
                "category": item.get("category", "unknown"),
            })

    print(f"\n[直播分析] 完成! {len(all_candidates)} 个候选 m3u 文件链接")
    return all_candidates

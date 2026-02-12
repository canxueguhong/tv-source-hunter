# -*- coding: utf-8 -*-
"""Module 1 — Search Collector: Use SerpAPI to find TVBox-related pages."""

import json
from serpapi import GoogleSearch
import config


def build_search_params(query: str, start: int = 0) -> dict:
    """Build SerpAPI search parameters."""
    return {
        "q": query,
        "api_key": config.SERPAPI_KEY,
        "engine": "google",
        "num": 10,
        "start": start,
        "hl": "zh-CN",
        "gl": "cn",
    }


def collect_search_results() -> list[dict]:
    """
    Run SerpAPI searches across all configured keywords.
    Returns deduplicated list of {url, title, snippet}.
    Respects MAX_SERPAPI_CALLS limit.
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()
    api_calls_used = 0

    # Distribute calls: 2 per keyword (page 0 and page 1) for 10 keywords = 20 calls
    calls_per_keyword = max(1, config.MAX_SERPAPI_CALLS // len(config.SEARCH_KEYWORDS))

    print(f"[搜索] 共 {len(config.SEARCH_KEYWORDS)} 个关键词, 每个关键词 {calls_per_keyword} 次调用")
    print(f"[搜索] SerpAPI 调用上限: {config.MAX_SERPAPI_CALLS}")
    print()

    for keyword in config.SEARCH_KEYWORDS:
        if api_calls_used >= config.MAX_SERPAPI_CALLS:
            print(f"[搜索] 已达到 API 调用上限 ({config.MAX_SERPAPI_CALLS}), 停止搜索")
            break

        for page in range(calls_per_keyword):
            if api_calls_used >= config.MAX_SERPAPI_CALLS:
                break

            start = page * 10
            params = build_search_params(keyword, start)

            print(f"  [{api_calls_used + 1}/{config.MAX_SERPAPI_CALLS}] 搜索: \"{keyword}\" (start={start})")

            try:
                search = GoogleSearch(params)
                data = search.get_dict()
                api_calls_used += 1

                organic = data.get("organic_results", [])
                count = 0
                for item in organic:
                    url = item.get("link", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append({
                            "url": url,
                            "title": item.get("title", ""),
                            "snippet": item.get("snippet", ""),
                        })
                        count += 1

                print(f"       → 获取 {len(organic)} 条结果, 新增 {count} 条")

            except Exception as e:
                print(f"       → 搜索出错: {e}")
                api_calls_used += 1  # still count failed calls

    print(f"\n[搜索] 完成! 共使用 {api_calls_used} 次 API 调用, 获取 {len(all_results)} 个不重复 URL")
    return all_results


if __name__ == "__main__":
    results = collect_search_results()
    print(f"\n共找到 {len(results)} 个搜索结果:")
    for r in results[:10]:
        print(f"  {r['title'][:50]:50s} | {r['url']}")

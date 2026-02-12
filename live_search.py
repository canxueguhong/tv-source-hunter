# -*- coding: utf-8 -*-
"""Live Source — Search Collector: Use SerpAPI to find m3u/m3u8 live playlists."""

from serpapi import GoogleSearch
import config


def build_search_params(query: str, start: int = 0) -> dict:
    return {
        "q": query,
        "api_key": config.SERPAPI_KEY,
        "engine": "google",
        "num": 10,
        "start": start,
        "hl": "en",  # English primary, Chinese keywords handled in query
    }


def collect_live_search_results() -> list[dict]:
    """
    Search for live source m3u/m3u8 playlists across all categories.
    Returns deduplicated list of {url, title, snippet, category}.
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()
    api_calls_used = 0

    total_keywords = sum(len(v) for v in config.LIVE_SEARCH_KEYWORDS.values())
    print(f"[直播搜索] 共 {total_keywords} 个关键词, 上限 {config.MAX_LIVE_SERPAPI_CALLS} 次调用")
    print()

    for category, keywords in config.LIVE_SEARCH_KEYWORDS.items():
        print(f"  ── 分类: {category} ({len(keywords)} 个关键词) ──")

        for keyword in keywords:
            if api_calls_used >= config.MAX_LIVE_SERPAPI_CALLS:
                print(f"[直播搜索] 已达上限 ({config.MAX_LIVE_SERPAPI_CALLS}), 停止")
                break

            params = build_search_params(keyword)
            print(f"  [{api_calls_used + 1}/{config.MAX_LIVE_SERPAPI_CALLS}] \"{keyword}\"")

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
                            "category": category,
                        })
                        count += 1

                print(f"       → {len(organic)} 条结果, 新增 {count} 条")

            except Exception as e:
                print(f"       → 出错: {e}")
                api_calls_used += 1

        if api_calls_used >= config.MAX_LIVE_SERPAPI_CALLS:
            break

    print(f"\n[直播搜索] 完成! {api_calls_used} 次调用, {len(all_results)} 个不重复 URL")
    return all_results

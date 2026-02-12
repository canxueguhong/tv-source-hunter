# -*- coding: utf-8 -*-
"""Cache Manager: Local caching of validation results to avoid redundant requests."""

import json
import os
from datetime import datetime, timedelta, timezone
import config


CACHE_FILE = os.path.join(config.CACHE_DIR, "validated.json")


def load_cache() -> dict:
    """Load the cache file. Returns {url: {result_data..., cached_at: ISO}}."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_cache(results: list[dict]) -> None:
    """Update cache with new validation results."""
    cache = load_cache()
    now = datetime.now(timezone.utc).isoformat()

    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        entry = dict(r)
        entry["cached_at"] = now
        cache[url] = entry

    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print(f"[缓存] 已更新 {CACHE_FILE} ({len(cache)} 条记录)")


def get_cached(url: str) -> dict | None:
    """
    Return cached result for a URL if it exists and hasn't expired.
    Returns None if no valid cache entry.
    """
    cache = load_cache()
    entry = cache.get(url)
    if not entry:
        return None

    cached_at = entry.get("cached_at")
    if not cached_at:
        return None

    try:
        cached_time = datetime.fromisoformat(cached_at)
        expiry = cached_time + timedelta(hours=config.CACHE_EXPIRY_HOURS)
        if datetime.now(timezone.utc) > expiry:
            return None  # expired
    except (ValueError, TypeError):
        return None

    return entry


def filter_uncached(urls: list[str]) -> tuple[list[str], list[dict]]:
    """
    Split URLs into uncached (need validation) and cached (reuse results).
    Returns (urls_to_validate, cached_results).
    """
    to_validate = []
    cached_results = []

    for url in urls:
        cached = get_cached(url)
        if cached:
            cached_results.append(cached)
        else:
            to_validate.append(url)

    if cached_results:
        print(f"[缓存] 命中 {len(cached_results)} 条, 需验证 {len(to_validate)} 条")

    return to_validate, cached_results

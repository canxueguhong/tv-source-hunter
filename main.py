# -*- coding: utf-8 -*-
"""
TVBox Source Auto-Collector & Validator — Main Orchestrator

Usage:
    python main.py              # full pipeline
    python main.py --dry-run    # search + analyze only, no validation
"""

import argparse
import asyncio
import sys
import time
import warnings
from urllib.parse import urlparse

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from search_collector import collect_search_results
from page_analyzer import analyze_pages
from validator import validate_urls
from integrator import integrate_sources, save_json, save_report, save_markdown_list
from cache_manager import filter_uncached, save_cache
import config


def parse_args():
    parser = argparse.ArgumentParser(description="TVBox Source Auto-Collector & Validator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只执行搜索和页面分析, 不进行验证和输出",
    )
    return parser.parse_args()


def apply_blacklist(urls: list[str]) -> list[str]:
    """Filter out URLs matching any entry in config.BLACKLIST."""
    if not config.BLACKLIST:
        return urls

    filtered = []
    blocked = 0
    for url in urls:
        hostname = urlparse(url).hostname or ""
        is_blocked = any(
            bl in url or bl in hostname
            for bl in config.BLACKLIST
        )
        if is_blocked:
            blocked += 1
        else:
            filtered.append(url)

    if blocked:
        print(f"[黑名单] 过滤 {blocked} 个 URL")

    return filtered


def print_banner():
    print("=" * 70)
    print("  TVBox Source Auto-Collector & Validator  v2.0")
    print("  自动采集 · 页面分析 · 五层验证 · 去重整合")
    print("=" * 70)
    print()


async def run_pipeline(dry_run: bool = False):
    """Run the full pipeline."""
    overall_start = time.monotonic()

    # ── Module 1: Search Collection ──────────────────────────────────
    print("━" * 70)
    print("  模块 1/4 — 搜索采集 (SerpAPI)")
    print("━" * 70)
    search_results = collect_search_results()

    # ── Module 2: Page Analysis ──────────────────────────────────────
    print("\n" + "━" * 70)
    print("  模块 2/4 — 页面分析 (提取候选 URL)")
    print("━" * 70)
    candidate_urls = await analyze_pages(search_results)

    # Add user sample URLs
    sample_urls = [s["url"] for s in config.SAMPLE_SOURCES]
    all_candidates = list(set(candidate_urls + sample_urls))

    # Apply blacklist
    all_candidates = apply_blacklist(all_candidates)

    # ── Dry-run exit point ───────────────────────────────────────────
    if dry_run:
        elapsed = round(time.monotonic() - overall_start, 1)
        print("\n" + "=" * 70)
        print("  📋 Dry-Run 结果 (仅搜索+分析)")
        print("=" * 70)
        print(f"  搜索结果页面数:   {len(search_results)}")
        print(f"  提取候选 URL:     {len(candidate_urls)} (新发现) + {len(sample_urls)} (用户样本)")
        print(f"  去黑名单后:       {len(all_candidates)}")
        print(f"  耗时:             {elapsed}s")
        print()
        print("  候选 URL 列表:")
        for i, url in enumerate(all_candidates, 1):
            print(f"    {i:3d}. {url}")
        print("=" * 70)
        return

    # ── Cache check ──────────────────────────────────────────────────
    urls_to_validate, cached_results = filter_uncached(all_candidates)

    # ── Module 3: Validation ─────────────────────────────────────────
    print("\n" + "━" * 70)
    print("  模块 3/4 — 有效性检测 (五层验证)")
    print("━" * 70)

    if urls_to_validate:
        new_results = await validate_urls(urls_to_validate)
    else:
        new_results = []
        print("[验证] 所有 URL 均已缓存, 跳过验证")

    # Merge new + cached results
    all_results = new_results + cached_results

    # Save to cache
    if new_results:
        save_cache(new_results)

    # ── Module 4: Integration & Output ───────────────────────────────
    print("\n" + "━" * 70)
    print("  模块 4/4 — 去重整合 · 输出")
    print("━" * 70)

    output, stats = integrate_sources(all_results)
    elapsed = round(time.monotonic() - overall_start, 1)

    # Save all outputs
    save_json(output)
    save_report(stats, elapsed)
    save_markdown_list(output, all_results)

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  📊 最终报告")
    print("=" * 70)
    print(f"  搜索结果页面数:     {len(search_results)}")
    print(f"  提取候选接口 URL:   {len(candidate_urls)} (新发现) + {len(sample_urls)} (用户样本)")
    print(f"  缓存命中:           {len(cached_results)}")
    print(f"  新验证:             {len(new_results)}")
    print(f"  通过验证 (去重前):  {stats['valid_before_dedup']}")
    print(f"  内容去重移除:       {stats['duplicates_removed']}")
    print(f"  最终保留:           {stats['final_count']}")
    print(f"  总耗时:             {elapsed}s")
    print(f"  输出文件:")
    print(f"    JSON:     {config.OUTPUT_FILE}")
    print(f"    报告:     {config.REPORT_FILE}")
    print(f"    源列表:   {config.SOURCES_FILE}")
    print("=" * 70)


def main():
    args = parse_args()
    print_banner()

    if args.dry_run:
        print("  ⚠️  DRY-RUN 模式: 只搜索和分析, 不验证\n")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_pipeline(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

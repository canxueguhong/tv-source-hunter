# -*- coding: utf-8 -*-
"""
Live Source Auto-Collector & Validator — Orchestrator

Usage:
    python live_main.py              # full pipeline
    python live_main.py --dry-run    # search + analyze only
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
import warnings
from collections import Counter
from datetime import datetime

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

from live_search import collect_live_search_results
from live_analyzer import analyze_live_pages
from live_validator import validate_live_sources
import config


def parse_args():
    parser = argparse.ArgumentParser(description="Live Source Auto-Collector & Validator")
    parser.add_argument("--dry-run", action="store_true", help="只搜索和分析, 不验证")
    return parser.parse_args()


def _dedup_by_hash(results: list[dict]) -> tuple[list[dict], int]:
    """Dedup valid results by content hash, keep fastest."""
    hash_groups: dict[str, list[dict]] = {}
    for r in results:
        if not r.get("valid"):
            continue
        h = r.get("content_hash", r["url"])
        hash_groups.setdefault(h, []).append(r)

    deduped = []
    removed = 0
    for h, group in hash_groups.items():
        group.sort(key=lambda x: x.get("response_time_ms", 9999))
        deduped.append(group[0])
        removed += len(group) - 1

    return deduped, removed


def save_m3u(valid_results: list[dict]) -> str:
    """Save all valid sources as a combined M3U playlist index."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    lines = ["#EXTM3U"]
    for i, r in enumerate(valid_results, 1):
        cat = r.get("category", "unknown")
        ch_count = r.get("channel_count", 0)
        alive = r.get("sample_alive", 0)
        total = r.get("sample_total", 0)
        alive_str = f" 存活{alive}/{total}" if total else ""

        lines.append(f'#EXTINF:-1 group-title="{cat}",🔴{i}-{cat} ({ch_count}频道{alive_str})')
        lines.append(r["url"])

    with open(config.LIVE_OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[输出] M3U → {config.LIVE_OUTPUT_M3U}")
    return config.LIVE_OUTPUT_M3U


def save_json_output(valid_results: list[dict]) -> str:
    """Save structured JSON output."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_sources": len(valid_results),
        "sources": [],
    }

    for i, r in enumerate(valid_results, 1):
        output["sources"].append({
            "index": i,
            "url": r["url"],
            "category": r.get("category", "unknown"),
            "channel_count": r.get("channel_count", 0),
            "groups": r.get("groups", []),
            "sample_alive": r.get("sample_alive", 0),
            "sample_total": r.get("sample_total", 0),
            "domestic_ratio": r.get("domestic_ratio", 0),
            "response_time_ms": r.get("response_time_ms", -1),
        })

    with open(config.LIVE_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)

    print(f"[输出] JSON → {config.LIVE_OUTPUT_JSON}")
    return config.LIVE_OUTPUT_JSON


def save_report(all_results: list[dict], valid: list[dict],
                dupes: int, elapsed: float) -> str:
    """Generate live_report.md."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    invalid = [r for r in all_results if not r.get("valid")]

    # Error stats
    error_counts = Counter()
    for r in invalid:
        err = r.get("error", "未知")
        if "超时" in err:
            error_counts["超时"] += 1
        elif "连接" in err:
            error_counts["连接失败"] += 1
        elif "HTTP" in err:
            error_counts["HTTP错误"] += 1
        elif "m3u" in err.lower():
            error_counts["非m3u格式"] += 1
        elif "国内" in err:
            error_counts["国内IPTV过滤"] += 1
        elif "频道抽样" in err:
            error_counts["频道全部不通"] += 1
        elif "无有效频道" in err:
            error_counts["无有效频道"] += 1
        elif "内容为空" in err:
            error_counts["内容为空"] += 1
        else:
            error_counts["其他"] += 1

    # Category distribution
    cat_dist = Counter(r.get("category", "unknown") for r in valid)

    lines = [
        f"# 直播源采集报告",
        f"",
        f"**生成时间**: {now}  ",
        f"**总耗时**: {elapsed:.1f}s",
        f"",
        f"## 📊 总览",
        f"",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 候选源总数 | {len(all_results)} |",
        f"| 通过验证 | {len(valid) + dupes} |",
        f"| 内容去重 | {dupes} |",
        f"| **最终保留** | **{len(valid)}** |",
        f"| 淘汰总数 | {len(invalid)} |",
        f"",
        f"## 📁 分类分布",
        f"",
        f"| 分类 | 数量 |",
        f"|---|---|",
    ]
    cat_names = {"adult": "🔞 成人/夜间", "documentary": "🎬 纪录片", "variety": "🎭 综艺/娱乐"}
    for cat, count in cat_dist.items():
        lines.append(f"| {cat_names.get(cat, cat)} | {count} |")
    lines.append("")

    if error_counts:
        lines += [
            f"## ❌ 淘汰原因",
            f"",
            f"| 原因 | 数量 |",
            f"|---|---|",
        ]
        for reason, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {reason} | {count} |")
        lines.append("")

    # Top sources
    if valid:
        lines += [
            f"## 🏆 最佳源 (按频道数)",
            f"",
            f"| # | 分类 | 频道数 | 存活检测 | URL |",
            f"|---|---|---|---|---|",
        ]
        top = sorted(valid, key=lambda x: x.get("channel_count", 0), reverse=True)[:10]
        for i, r in enumerate(top, 1):
            alive_str = f"{r.get('sample_alive',0)}/{r.get('sample_total',0)}"
            cat = cat_names.get(r.get("category", ""), r.get("category", ""))
            lines.append(f"| {i} | {cat} | {r.get('channel_count',0)} | {alive_str} | `{r['url'][:80]}` |")
        lines.append("")

    with open(config.LIVE_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[输出] 报告 → {config.LIVE_REPORT_FILE}")
    return config.LIVE_REPORT_FILE


async def run_live_pipeline(dry_run: bool = False):
    overall_start = time.monotonic()

    # ── Search ───────────────────────────────────────────────────────
    print("━" * 70)
    print("  直播源 模块 1/3 — 搜索采集")
    print("━" * 70)
    search_results = collect_live_search_results()

    # ── Analysis ─────────────────────────────────────────────────────
    print("\n" + "━" * 70)
    print("  直播源 模块 2/3 — 页面分析")
    print("━" * 70)
    candidates = await analyze_live_pages(search_results)

    if dry_run:
        elapsed = round(time.monotonic() - overall_start, 1)
        print(f"\n{'=' * 70}")
        print(f"  📋 Dry-Run 完成 ({elapsed}s)")
        print(f"{'=' * 70}")
        print(f"  搜索页面: {len(search_results)}")
        print(f"  候选源:   {len(candidates)}")
        for i, c in enumerate(candidates, 1):
            print(f"    {i:3d}. [{c['category']}] {c['url']}")
        return

    # ── Validation ───────────────────────────────────────────────────
    print("\n" + "━" * 70)
    print("  直播源 模块 3/3 — 验证 · 过滤 · 输出")
    print("━" * 70)
    all_results = await validate_live_sources(candidates)

    # Dedup
    deduped, dupes_removed = _dedup_by_hash(all_results)

    # Sort: most channels first
    deduped.sort(key=lambda x: (-x.get("channel_count", 0), x.get("response_time_ms", 9999)))

    # Output
    elapsed = round(time.monotonic() - overall_start, 1)
    save_m3u(deduped)
    save_json_output(deduped)
    save_report(all_results, deduped, dupes_removed, elapsed)

    # Summary
    print(f"\n{'=' * 70}")
    print(f"  📊 直播源采集报告")
    print(f"{'=' * 70}")
    print(f"  搜索页面:   {len(search_results)}")
    print(f"  候选源:     {len(candidates)}")
    print(f"  通过验证:   {len(deduped) + dupes_removed}")
    print(f"  去重移除:   {dupes_removed}")
    print(f"  最终保留:   {len(deduped)}")
    print(f"  总耗时:     {elapsed}s")
    print(f"  输出:")
    print(f"    M3U:   {config.LIVE_OUTPUT_M3U}")
    print(f"    JSON:  {config.LIVE_OUTPUT_JSON}")
    print(f"    报告:  {config.LIVE_REPORT_FILE}")
    print(f"{'=' * 70}")


def main():
    args = parse_args()

    print("=" * 70)
    print("  Live Source Auto-Collector & Validator")
    print("  直播源自动采集 · m3u解析 · 国内IPTV过滤 · 频道验证")
    print("=" * 70)
    print()

    if args.dry_run:
        print("  ⚠️  DRY-RUN 模式\n")

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_live_pipeline(dry_run=args.dry_run))


if __name__ == "__main__":
    main()

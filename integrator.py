# -*- coding: utf-8 -*-
"""
Module 4 — Integrator: Dedup, merge, label, and output validated sources.

Features:
  - MD5 content hash deduplication (keep fastest per hash group)
  - Speed labels (⚡快 / 🔶中 / 🐢慢)
  - Dual output: JSON (tvbox_multi.json) + Markdown (sources.md)
  - Report generation (report.md) with failure reason statistics
"""

import json
import os
from collections import Counter
from datetime import datetime
from urllib.parse import urlparse

import config


# ─── Name Generation ────────────────────────────────────────────────

def _generate_name(url: str) -> str:
    """Generate a display name from URL when none is provided."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if host:
            if host.startswith("www."):
                host = host[4:]

            parts = host.split(".")
            name = parts[0] if len(parts) >= 2 else host

            # GitHub / gh-proxy: extract repo name
            if "github" in host.lower() or "githubusercontent" in host.lower():
                path_parts = [p for p in parsed.path.split("/") if p]
                if len(path_parts) >= 2:
                    name = path_parts[1]

            if "gh-proxy" in host.lower():
                path_parts = [p for p in parsed.path.split("/") if p]
                for i, part in enumerate(path_parts):
                    if "githubusercontent" in part or "github" in part:
                        if i + 2 < len(path_parts):
                            name = path_parts[i + 2]
                        break

            return name.capitalize() if name else "未命名"
        return "未命名"
    except Exception:
        return "未命名"


# ─── MD5 Dedup ──────────────────────────────────────────────────────

def _dedup_by_hash(valid_results: list[dict]) -> tuple[list[dict], int]:
    """
    Group by content_hash, keep fastest response per group.
    Returns (deduped_list, duplicates_removed_count).
    """
    hash_groups: dict[str, list[dict]] = {}
    for r in valid_results:
        h = r.get("content_hash", "")
        if not h:
            h = r["url"]  # fallback: use URL as unique key
        hash_groups.setdefault(h, []).append(r)

    deduped = []
    removed = 0
    for h, group in hash_groups.items():
        group.sort(key=lambda x: x.get("response_time_ms", 9999))
        deduped.append(group[0])
        if len(group) > 1:
            removed += len(group) - 1
            print(f"  🔗 去重: 保留 {group[0]['url'][:60]}")
            for dupe in group[1:]:
                print(f"       移除 {dupe['url'][:60]}")

    return deduped, removed


# ─── Integration ────────────────────────────────────────────────────

def integrate_sources(validated_results: list[dict]) -> tuple[dict, dict]:
    """
    Full integration pipeline:
      1. Filter valid results
      2. MD5 content hash dedup
      3. Sort by speed (fastest first)
      4. Build multi-repo JSON with speed labels
      5. Generate statistics for report

    Returns (output_json, stats_dict).
    """
    valid = [r for r in validated_results if r.get("valid")]
    invalid = [r for r in validated_results if not r.get("valid")]

    print(f"\n[整合] 有效源: {len(valid)}, 无效源: {len(invalid)}")

    # Dedup
    deduped, dupes_removed = _dedup_by_hash(valid)
    print(f"[整合] 去重移除: {dupes_removed}, 去重后: {len(deduped)}")

    # Sort by response time
    deduped.sort(key=lambda x: x.get("response_time_ms", 9999))

    # Build output
    urls_list = []
    for i, src in enumerate(deduped, 1):
        name = src.get("name", "") or _generate_name(src["url"])
        label = src.get("speed_label", "")
        sites = src.get("sites_count", 0)
        urls_count = src.get("urls_count", 0)

        # Build info tag
        tags = []
        if label:
            tags.append(label)
        if sites:
            tags.append(f"{sites}站")
        if urls_count:
            tags.append(f"{urls_count}仓")
        suffix = f" ({', '.join(tags)})" if tags else ""

        urls_list.append({
            "url": src["url"],
            "name": f"🚀{i}-{name}{suffix}",
        })

    output = {"urls": urls_list}

    # Failure reason statistics
    error_counts = Counter()
    for r in invalid:
        err = r.get("error", "未知错误")
        # Categorize errors
        if "超时" in err:
            error_counts["超时"] += 1
        elif "连接失败" in err:
            error_counts["连接失败"] += 1
        elif err.startswith("HTTP"):
            error_counts["HTTP错误状态码"] += 1
        elif "JSON" in err:
            error_counts["JSON解析失败"] += 1
        elif "内容过小" in err:
            error_counts["内容过小 (<1KB)"] += 1
        elif "非TVBox" in err:
            error_counts["非TVBox格式"] += 1
        elif "站点抽样" in err:
            error_counts["站点抽样全挂 (源过期)"] += 1
        else:
            error_counts["其他"] += 1

    # Speed distribution
    speed_dist = Counter()
    for src in deduped:
        speed_dist[src.get("speed_label", "未知")] += 1

    # Type distribution
    type_dist = Counter()
    for src in deduped:
        type_dist[src.get("type", "unknown")] += 1

    stats = {
        "total_candidates": len(validated_results),
        "valid_before_dedup": len(valid),
        "duplicates_removed": dupes_removed,
        "final_count": len(deduped),
        "invalid_count": len(invalid),
        "error_counts": dict(error_counts),
        "speed_distribution": dict(speed_dist),
        "type_distribution": dict(type_dist),
        "fastest_source": deduped[0] if deduped else None,
    }

    return output, stats


# ─── Output Functions ───────────────────────────────────────────────

def save_json(output: dict) -> str:
    """Save multi-repo JSON to output/tvbox_multi.json."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    with open(config.OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    print(f"\n[输出] JSON → {config.OUTPUT_FILE} ({len(output.get('urls', []))} 个源)")
    return config.OUTPUT_FILE


def save_report(stats: dict, elapsed_s: float) -> str:
    """Generate report.md with full statistics."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# TVBox 源采集报告",
        f"",
        f"**生成时间**: {now}  ",
        f"**总耗时**: {elapsed_s:.1f}s",
        f"",
        f"## 📊 总览",
        f"",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 候选 URL 总数 | {stats['total_candidates']} |",
        f"| 通过验证 (去重前) | {stats['valid_before_dedup']} |",
        f"| 内容去重移除 | {stats['duplicates_removed']} |",
        f"| **最终保留** | **{stats['final_count']}** |",
        f"| 淘汰总数 | {stats['invalid_count']} |",
        f"",
    ]

    # Fastest source
    fastest = stats.get("fastest_source")
    if fastest:
        lines += [
            f"## 🏆 最快源",
            f"",
            f"**{fastest.get('name', '未命名')}** — `{fastest['url']}`  ",
            f"响应时间: {fastest.get('response_time_ms', 'N/A')}ms | "
            f"类型: {fastest.get('type', 'unknown')}",
            f"",
        ]

    # Failure reasons
    errors = stats.get("error_counts", {})
    if errors:
        lines += [
            f"## ❌ 淘汰原因统计",
            f"",
            f"| 原因 | 数量 |",
            f"|---|---|",
        ]
        for reason, count in sorted(errors.items(), key=lambda x: -x[1]):
            lines.append(f"| {reason} | {count} |")
        lines.append("")

    # Speed distribution
    speed = stats.get("speed_distribution", {})
    if speed:
        lines += [
            f"## ⚡ 速度分布",
            f"",
            f"| 等级 | 数量 |",
            f"|---|---|",
        ]
        for label, count in speed.items():
            lines.append(f"| {label} | {count} |")
        lines.append("")

    # Type distribution
    types = stats.get("type_distribution", {})
    if types:
        type_names = {"single_repo": "单仓源", "multi_repo": "多仓源", "storeHouse": "仓库源"}
        lines += [
            f"## 📁 源类型分布",
            f"",
            f"| 类型 | 数量 |",
            f"|---|---|",
        ]
        for t, count in types.items():
            lines.append(f"| {type_names.get(t, t)} | {count} |")
        lines.append("")

    with open(config.REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[输出] 报告 → {config.REPORT_FILE}")
    return config.REPORT_FILE


def save_markdown_list(output: dict, all_results: list[dict]) -> str:
    """Save sources.md — Markdown table with speed labels and site counts."""
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # Build lookup from URL to validation result
    result_map = {r["url"]: r for r in all_results if r.get("valid")}

    lines = [
        "# TVBox 可用源列表",
        "",
        f"*共 {len(output.get('urls', []))} 个源，按响应速度排序*",
        "",
        "| # | 名称 | 速度 | 类型 | 站点数 | 响应 | URL |",
        "|---|---|---|---|---|---|---|",
    ]

    type_names = {"single_repo": "单仓", "multi_repo": "多仓", "storeHouse": "仓库"}

    for i, item in enumerate(output.get("urls", []), 1):
        url = item["url"]
        r = result_map.get(url, {})
        speed = r.get("speed_label", "")
        src_type = type_names.get(r.get("type", ""), "未知")
        sites = r.get("sites_count", 0) or r.get("urls_count", 0) or "-"
        resp = f"{r.get('response_time_ms', 'N/A')}ms"
        lines.append(f"| {i} | {item['name']} | {speed} | {src_type} | {sites} | {resp} | `{url}` |")

    with open(config.SOURCES_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[输出] 源列表 → {config.SOURCES_FILE}")
    return config.SOURCES_FILE

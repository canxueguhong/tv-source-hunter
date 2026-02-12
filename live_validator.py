# -*- coding: utf-8 -*-
"""
Live Source — Validator: Validate m3u/m3u8 live playlists.

Validation layers:
  1. HTTP reachability (2xx)
  2. Content is valid m3u/m3u8 (starts with #EXTM3U or contains #EXTINF)
  3. Domestic IPTV filter (discard if > 50% channels are CCTV/卫视)
  4. Channel stream sampling (check if sample streams are accessible)
"""

import asyncio
import hashlib
import random
import re
import time

import httpx
import config
from validator import _resolve_dns, _build_resolved_url


def _parse_m3u(content: str) -> list[dict]:
    """
    Parse m3u/m3u8 content into a list of channels.
    Each channel: {name, url, group}.
    """
    channels = []
    lines = content.strip().split('\n')
    lines = [line.strip() for line in lines if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF'):
            # Parse channel name from #EXTINF line
            name = ""
            group = ""

            # Extract group-title if present
            group_match = re.search(r'group-title="([^"]*)"', line)
            if group_match:
                group = group_match.group(1)

            # Channel name is after the last comma
            comma_idx = line.rfind(',')
            if comma_idx >= 0:
                name = line[comma_idx + 1:].strip()

            # Next non-comment line should be the URL
            i += 1
            while i < len(lines) and lines[i].startswith('#'):
                i += 1

            if i < len(lines) and lines[i].startswith('http'):
                channels.append({
                    "name": name,
                    "url": lines[i].strip(),
                    "group": group,
                })
        i += 1

    return channels


def _check_domestic_ratio(channels: list[dict]) -> float:
    """Calculate ratio of domestic IPTV channels."""
    if not channels:
        return 0.0

    domestic_count = 0
    for ch in channels:
        name_upper = (ch.get("name", "") + " " + ch.get("group", "")).upper()
        if any(kw.upper() in name_upper for kw in config.DOMESTIC_IPTV_KEYWORDS):
            domestic_count += 1

    return domestic_count / len(channels)


async def _check_stream(client: httpx.AsyncClient, url: str,
                        semaphore: asyncio.Semaphore) -> bool:
    """Check if a stream URL is accessible (returns any 2xx with content)."""
    async with semaphore:
        try:
            resolved_url, extra_headers = _build_resolved_url(url)
            resp = await client.get(
                resolved_url,
                headers=extra_headers,
                timeout=config.LIVE_STREAM_TIMEOUT,
                follow_redirects=True,
            )
            return 200 <= resp.status_code < 300
        except Exception:
            return False


async def validate_single_live_source(
    client: httpx.AsyncClient,
    url: str,
    category: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """
    Validate a single live source URL.
    Returns result dict with all metadata.
    """
    result = {
        "url": url,
        "valid": False,
        "category": category,
        "channel_count": 0,
        "domestic_ratio": 0.0,
        "groups": [],
        "sample_alive": 0,
        "sample_total": 0,
        "response_time_ms": -1,
        "content_hash": "",
        "error": "",
    }

    async with semaphore:
        # ── Layer 1: HTTP Reachability ───────────────────────────────
        try:
            resolved_url, extra_headers = _build_resolved_url(url)
            t0 = time.monotonic()
            resp = await client.get(
                resolved_url,
                headers=extra_headers,
                timeout=config.VALIDATION_TIMEOUT,
                follow_redirects=True,
            )
            elapsed = round((time.monotonic() - t0) * 1000)
            result["response_time_ms"] = elapsed

            if not (200 <= resp.status_code < 300):
                result["error"] = f"HTTP {resp.status_code}"
                return result

        except httpx.TimeoutException:
            result["error"] = "超时"
            return result
        except Exception as e:
            result["error"] = f"连接失败: {type(e).__name__}"
            return result

        # ── Layer 2: Valid m3u Content ───────────────────────────────
        text = resp.text.strip()
        if not text:
            result["error"] = "内容为空"
            return result

        # Must contain m3u markers
        if "#EXTM3U" not in text and "#EXTINF" not in text:
            result["error"] = "非m3u格式 (缺少 #EXTM3U/#EXTINF)"
            return result

        channels = _parse_m3u(text)
        result["channel_count"] = len(channels)

        if len(channels) == 0:
            result["error"] = "无有效频道"
            return result

        # Content hash
        result["content_hash"] = hashlib.md5(text.encode("utf-8")).hexdigest()

        # Collect groups
        groups = set(ch.get("group", "") for ch in channels if ch.get("group"))
        result["groups"] = list(groups)[:20]  # cap at 20

        # ── Layer 3: Domestic IPTV Filter ────────────────────────────
        domestic_ratio = _check_domestic_ratio(channels)
        result["domestic_ratio"] = round(domestic_ratio, 2)

        if domestic_ratio > config.DOMESTIC_THRESHOLD:
            result["error"] = f"国内IPTV占比 {domestic_ratio:.0%} > {config.DOMESTIC_THRESHOLD:.0%}"
            return result

    # ── Layer 4: Channel Stream Sampling ─────────────────────────
    # Sample a few channels and check if their streams are accessible
    stream_urls = [ch["url"] for ch in channels if ch.get("url", "").startswith("http")]
    if stream_urls:
        sample = random.sample(stream_urls, min(config.LIVE_SAMPLE_CHANNELS, len(stream_urls)))
        result["sample_total"] = len(sample)

        alive = 0
        for stream_url in sample:
            if await _check_stream(client, stream_url, semaphore):
                alive += 1
        result["sample_alive"] = alive

        if alive == 0:
            result["error"] = f"频道抽样全部不通 ({len(sample)}个)"
            return result

    result["valid"] = True
    return result


async def validate_live_sources(candidates: list[dict]) -> list[dict]:
    """
    Validate all candidate live sources concurrently with real-time progress.
    candidates: list of {url, category}
    """
    if not candidates:
        return []

    import sys

    total = len(candidates)
    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)

    print(f"\n[直播验证] 验证 {total} 个候选源...")
    print(f"[直播验证] DNS: {config.DNS_SERVER} | 并发: {config.MAX_CONCURRENT_REQUESTS} | 国内IPTV阈值: {config.DOMESTIC_THRESHOLD:.0%}")
    print()

    results: list[dict] = [None] * total
    completed = 0
    valid_count = 0
    t_start = time.monotonic()

    async with httpx.AsyncClient(
        headers={
            "User-Agent": config.SMARTTV_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        verify=False,
        proxy=None,
        trust_env=False,
    ) as client:

        async def _run_one(idx: int, c: dict) -> tuple[int, dict]:
            r = await validate_single_live_source(
                client, c["url"], c["category"], semaphore
            )
            return idx, r

        tasks = [
            asyncio.ensure_future(_run_one(i, c))
            for i, c in enumerate(candidates)
        ]

        for coro in asyncio.as_completed(tasks):
            idx, result = await coro
            results[idx] = result
            completed += 1
            if result["valid"]:
                valid_count += 1

            # Progress bar
            elapsed = time.monotonic() - t_start
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = (total - completed) / rate if rate > 0 else 0
            pct = completed / total * 100
            bar_len = 30
            filled = int(bar_len * completed / total)
            bar = "█" * filled + "░" * (bar_len - filled)

            sys.stdout.write(
                f"\r  [{bar}] {pct:5.1f}% | "
                f"{completed}/{total} | "
                f"✓{valid_count} | "
                f"{elapsed:.0f}s / 剩余~{remaining:.0f}s"
            )
            sys.stdout.flush()

    print()  # newline after progress bar
    elapsed_total = round(time.monotonic() - t_start, 1)
    print(f"\n[直播验证] 完成! {valid_count}/{total} 通过验证 ({elapsed_total}s)")

    for r in results:
        if r is None:
            continue
        s = "✓" if r["valid"] else "✗"
        t = f"{r['response_time_ms']}ms" if r["response_time_ms"] >= 0 else "N/A"
        if r["valid"]:
            alive_str = f"{r['sample_alive']}/{r['sample_total']}" if r["sample_total"] else "-"
            detail = f"[{r['category']}] {r['channel_count']}频道 存活{alive_str}"
        else:
            detail = r["error"]
        print(f"  {s} {t:>8s} | {r['url'][:60]:60s} | {detail}")

    return [r for r in results if r is not None]

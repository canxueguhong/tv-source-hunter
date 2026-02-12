# -*- coding: utf-8 -*-
"""
Module 3 — Validator: Five-layer validation of TVBox interface URLs.

Layers:
  1. HTTP reachability (2xx status)
  2. Valid JSON parse
  2.5. Content size >= 1KB
  3. TVBox format check (sites/storeHouse/urls)
  4. Sites sampling liveness (single_repo only)

Network simulation:
  - SmartTV User-Agent
  - DNS resolved via 223.5.5.5 (China public DNS)
  - No system proxy (proxy=None, trust_env=False)
"""

import asyncio
import hashlib
import json
import random
import time
from urllib.parse import urlparse

import dns.resolver
import httpx

import config

# ─── DNS Cache (in-memory with TTL) ─────────────────────────────────

_dns_cache: dict[str, tuple[str, float]] = {}  # {hostname: (ip, timestamp)}


def _resolve_dns(hostname: str) -> str | None:
    """
    Resolve hostname via config.DNS_SERVER (223.5.5.5).
    Results are cached in-memory with config.DNS_CACHE_TTL.
    Returns IP string or None on failure.
    """
    now = time.monotonic()

    # Check cache
    if hostname in _dns_cache:
        ip, cached_at = _dns_cache[hostname]
        if now - cached_at < config.DNS_CACHE_TTL:
            return ip

    try:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [config.DNS_SERVER]
        resolver.lifetime = 5  # 5s timeout for DNS
        answers = resolver.resolve(hostname, "A")
        ip = str(answers[0])
        _dns_cache[hostname] = (ip, now)
        return ip
    except Exception:
        # Fallback: try system DNS
        try:
            import socket
            ip = socket.gethostbyname(hostname)
            _dns_cache[hostname] = (ip, now)
            return ip
        except Exception:
            return None


def _build_resolved_url(url: str) -> tuple[str, dict]:
    """
    Resolve the URL's hostname via China DNS and return
    (url_with_ip, headers_with_host) for direct-IP request.
    If DNS fails, returns original URL with empty extra headers.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return url, {}

        ip = _resolve_dns(hostname)
        if not ip or ip == hostname:
            return url, {}

        # Build URL with IP instead of hostname
        port_str = f":{parsed.port}" if parsed.port else ""
        resolved_url = f"{parsed.scheme}://{ip}{port_str}{parsed.path}"
        if parsed.query:
            resolved_url += f"?{parsed.query}"
        if parsed.fragment:
            resolved_url += f"#{parsed.fragment}"

        return resolved_url, {"Host": hostname}

    except Exception:
        return url, {}


# ─── TVBox Format Check ─────────────────────────────────────────────

def _check_tvbox_format(data) -> dict:
    """
    Check if parsed JSON data conforms to TVBox config format.
    Returns {valid, type, name, sites_count, urls_count}.
    """
    if not isinstance(data, dict):
        return {"valid": False, "type": "unknown", "name": "", "sites_count": 0, "urls_count": 0}

    # Multi-repo format: has "urls" array
    if "urls" in data and isinstance(data["urls"], list):
        return {"valid": True, "type": "multi_repo", "name": "多仓源",
                "sites_count": 0, "urls_count": len(data["urls"])}

    # storeHouse format
    if "storeHouse" in data:
        return {"valid": True, "type": "storeHouse", "name": "仓库源",
                "sites_count": 0, "urls_count": 0}

    # Single-repo format: has "sites" array
    if "sites" in data and isinstance(data["sites"], list):
        name = data.get("name", data.get("title", "单仓源"))
        return {"valid": True, "type": "single_repo", "name": str(name) if name else "单仓源",
                "sites_count": len(data["sites"]), "urls_count": 0}

    # Has "spider" field (common in TVBox configs)
    if "spider" in data:
        return {"valid": True, "type": "single_repo", "name": "单仓源",
                "sites_count": 0, "urls_count": 0}

    return {"valid": False, "type": "unknown", "name": "", "sites_count": 0, "urls_count": 0}


# ─── Sites Sampling Liveness Check ──────────────────────────────────

async def _sample_check_sites(
    client: httpx.AsyncClient,
    data: dict,
    semaphore: asyncio.Semaphore,
) -> bool:
    """
    For single_repo sources: pick up to SITES_SAMPLE_COUNT sites with HTTP api URLs,
    test if they respond. Returns True if at least one site is alive.
    Returns True (pass) if no testable HTTP sites found (skip check).
    """
    sites = data.get("sites", [])
    if not isinstance(sites, list) or not sites:
        return True  # no sites to test, skip

    # Filter sites with HTTP api URLs
    testable = []
    for site in sites:
        api = site.get("api", "")
        if isinstance(api, str) and api.lower().startswith("http"):
            testable.append(api)

    if not testable:
        return True  # all sites use spider protocols, skip check

    # Random sample
    sample = random.sample(testable, min(config.SITES_SAMPLE_COUNT, len(testable)))

    alive = 0
    for api_url in sample:
        async with semaphore:
            try:
                resolved_url, extra_headers = _build_resolved_url(api_url)
                resp = await client.get(
                    resolved_url,
                    headers=extra_headers,
                    timeout=config.SITES_SAMPLE_TIMEOUT,
                    follow_redirects=True,
                )
                if 200 <= resp.status_code < 300:
                    alive += 1
            except Exception:
                pass

    return alive > 0


# ─── Main Validation ────────────────────────────────────────────────

async def validate_single_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict:
    """
    Validate a single URL with five-layer check.
    Returns result dict with url, valid, type, name, response_time_ms,
    content_hash, body_bytes, sites_count, urls_count, quality, speed_label, error.
    """
    result = {
        "url": url,
        "valid": False,
        "type": "unknown",
        "name": "",
        "response_time_ms": -1,
        "content_hash": "",
        "body_bytes": 0,
        "sites_count": 0,
        "urls_count": 0,
        "quality": "",
        "speed_label": "",
        "error": "",
    }

    async with semaphore:
        # ── Layer 1: HTTP Reachability ───────────────────────────────
        try:
            resolved_url, extra_headers = _build_resolved_url(url)
            start_time = time.monotonic()
            resp = await client.get(
                resolved_url,
                headers=extra_headers,
                timeout=config.VALIDATION_TIMEOUT,
                follow_redirects=True,
            )
            elapsed_ms = round((time.monotonic() - start_time) * 1000)
            result["response_time_ms"] = elapsed_ms

            if not (200 <= resp.status_code < 300):
                result["error"] = f"HTTP {resp.status_code}"
                return result

        except httpx.TimeoutException:
            result["error"] = "超时"
            return result
        except Exception as e:
            result["error"] = f"连接失败: {type(e).__name__}"
            return result

        # ── Layer 2: Valid JSON ──────────────────────────────────────
        try:
            text = resp.text.strip()
            if text.startswith("\ufeff"):
                text = text[1:]
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            result["error"] = f"JSON解析失败: {str(e)[:50]}"
            return result

        # ── Layer 2.5: Content Size ──────────────────────────────────
        body_bytes = len(text.encode("utf-8"))
        result["body_bytes"] = body_bytes
        if body_bytes < config.MIN_JSON_BYTES:
            result["error"] = f"内容过小 ({body_bytes}B < {config.MIN_JSON_BYTES}B)"
            return result

        # ── Layer 3: TVBox Format Check ──────────────────────────────
        fmt = _check_tvbox_format(data)
        if not fmt["valid"]:
            result["error"] = "非TVBox格式 (缺少 sites/storeHouse/urls)"
            return result

        result["type"] = fmt["type"]
        result["name"] = fmt["name"]
        result["sites_count"] = fmt["sites_count"]
        result["urls_count"] = fmt["urls_count"]

        # Content hash (MD5 for dedup)
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        result["content_hash"] = hashlib.md5(canonical.encode("utf-8")).hexdigest()

        # Speed label
        fast, medium = config.SPEED_THRESHOLDS
        if elapsed_ms < fast:
            result["speed_label"] = "⚡快"
        elif elapsed_ms < medium:
            result["speed_label"] = "🔶中"
        else:
            result["speed_label"] = "🐢慢"

    # ── Layer 4: Sites Sampling (single_repo only, outside main semaphore) ──
    if fmt["type"] == "single_repo" and fmt["sites_count"] > 0:
        sites_alive = await _sample_check_sites(client, data, semaphore)
        if not sites_alive:
            result["error"] = "站点抽样全部不通 (源已过期)"
            result["quality"] = "dead"
            # Mark as invalid — dead sources don't enter final output
            return result

    result["valid"] = True
    result["quality"] = "good"
    return result


async def validate_urls(candidate_urls: list[str]) -> list[dict]:
    """
    Validate all candidate URLs concurrently.
    Returns list of result dicts.
    """
    if not candidate_urls:
        return []

    semaphore = asyncio.Semaphore(config.MAX_CONCURRENT_REQUESTS)

    print(f"\n[验证] 开始验证 {len(candidate_urls)} 个候选接口 URL...")
    print(f"[验证] DNS: {config.DNS_SERVER} | UA: SmartTV | Proxy: 禁用")

    async with httpx.AsyncClient(
        headers={
            "User-Agent": config.SMARTTV_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        verify=False,
        proxy=None,
        trust_env=False,
    ) as client:

        tasks = [
            validate_single_url(client, url, semaphore)
            for url in candidate_urls
        ]
        results = await asyncio.gather(*tasks)

    # Print summary
    valid_count = sum(1 for r in results if r["valid"])
    print(f"\n[验证] 完成! {valid_count}/{len(results)} 个 URL 通过验证")

    for r in results:
        status = "✓" if r["valid"] else "✗"
        time_str = f"{r['response_time_ms']}ms" if r["response_time_ms"] >= 0 else "N/A"
        if r["valid"]:
            detail = f"[{r['type']}] {r['speed_label']} {r['sites_count']}站"
        else:
            detail = r["error"]
        print(f"  {status} {time_str:>8s} | {r['url'][:65]:65s} | {detail}")

    return list(results)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

    test_urls = [
        "http://xhztv.top/4k.json",
        "https://www.wya6.cn/tv/yc.json",
    ]
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    results = asyncio.run(validate_urls(test_urls))
    for r in results:
        print(f"  {r['url']}: valid={r['valid']} hash={r['content_hash'][:8]}")

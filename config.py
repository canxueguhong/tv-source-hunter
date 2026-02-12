# -*- coding: utf-8 -*-
"""Central configuration for TVBox Source Collector."""

# ─── SerpAPI ────────────────────────────────────────────────────────
SERPAPI_KEY = "6ac123cc31a23dd5e20d5c426e5a0b5a713212d45aa34e220e17d66ace857aca"
MAX_SERPAPI_CALLS = 20  # hard cap from user

# ─── Search Keywords ────────────────────────────────────────────────
SEARCH_KEYWORDS = [
    "TVBox 接口 2026",
    "影视仓 多仓源 最新",
    "tvbox json github",
    "tvbox 配置 sites storeHouse",
    "TVBox 接口地址 最新可用",
    "影视仓 接口 json 2026",
    "tvbox multi repo json",
    "tvbox 线路 接口 订阅",
    "TVBox 多仓 源地址 github",
    "影视仓 tvbox 免费接口",
]

# ─── HTTP Settings ──────────────────────────────────────────────────
REQUEST_TIMEOUT = 15          # seconds for page fetching
VALIDATION_TIMEOUT = 10       # seconds for interface URL validation
MAX_CONCURRENT_REQUESTS = 100  # semaphore for async requests

# ─── Network Simulation (模拟盒子真实环境) ───────────────────────────
SMARTTV_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; SmartTV) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DNS_SERVER = "223.5.5.5"      # 阿里公共 DNS
DNS_CACHE_TTL = 600           # DNS 缓存 TTL (秒), 10 分钟

# ─── Validation Thresholds ──────────────────────────────────────────
MIN_JSON_BYTES = 1024         # <1KB 的 JSON 视为空壳
SITES_SAMPLE_COUNT = 3        # 抽样检测站点数
SITES_SAMPLE_TIMEOUT = 5      # 站点探测超时 (秒)
SPEED_THRESHOLDS = (500, 2000)  # fast < 500ms, medium < 2000ms, slow >= 2000ms

# ─── Cache ──────────────────────────────────────────────────────────
CACHE_DIR = "cache"
CACHE_EXPIRY_HOURS = 72       # 缓存有效期 (小时)

# ─── Blacklist ──────────────────────────────────────────────────────
BLACKLIST = [
    # 域名或完整 URL，运行时自动跳过
    # "example.com",
]

# ─── TVBox Detection ────────────────────────────────────────────────
TVBOX_JSON_KEYWORDS = ["sites", "storeHouse", "spider", "urls"]
TVBOX_URL_PATTERNS = [
    r'https?://[^\s"\'<>]+\.json',                     # any .json URL
    r'https?://[^\s"\'<>]+/tv/',                        # /tv/ path pattern
    r'https?://[^\s"\'<>]+raw\.githubusercontent\.com[^\s"\'<>]+', # GitHub raw
    r'https?://gh-proxy\.[^\s"\'<>]+',                  # gh-proxy URLs
    r'https?://gitlab\.com/[^\s"\'<>]+/-/raw/[^\s"\'<>]+',  # GitLab raw
]

# ─── User-Provided Sample Sources ──────────────────────────────────
SAMPLE_SOURCES = [
    {"url": "http://肥猫.com", "name": "肥猫"},
    {"url": "http://www.饭太硬.com/tv/", "name": "饭太硬推荐"},
    {"url": "http://xhztv.top/4k.json", "name": "小盒子4K"},
    {"url": "https://gitlab.com/noimank/tvbox/-/raw/main/tvbox1.json", "name": "健康家用"},
    {"url": "http://tvbox.xn--4kq62z5rby2qupq9ub.top/", "name": "王二小"},
    {"url": "https://gh-proxy.com/raw.githubusercontent.com//gaotianliuyun/gao/master/0827.json", "name": "FongMI线路"},
    {"url": "https://gh-proxy.org/https:/raw.githubusercontent.com/xyq254245/xyqonlinerule/main/XYQTVBox.json", "name": "香雅情"},
    {"url": "http://pandown.pro/tvbox/tvbox.json", "name": "巧计线路"},
    {"url": "http://tv.nxog.top/m/", "name": "欧歌4K"},
    {"url": "https://gh-proxy.com/raw.githubusercontent.com/gaotianliuyun/gao/master/js.json", "name": "高天流云js"},
    {"url": "https://gh-proxy.com/raw.githubusercontent.com/gaotianliuyun/gao/master/XYQ.json", "name": "高天流云 XYQ"},
    {"url": "http://www.lyyytv.cn/yt/yt.json", "name": "影探线路"},
    {"url": "https://gh-proxy.com/https://raw.githubusercontent.com/yoursmile66/TVBox/main/XC.json", "name": "南风"},
    {"url": "https://www.wya6.cn/tv/yc.json", "name": "无意线路"},
]

# ─── Output ─────────────────────────────────────────────────────────
OUTPUT_DIR = "output"
OUTPUT_FILE = "output/tvbox_multi.json"
REPORT_FILE = "output/report.md"
SOURCES_FILE = "output/sources.md"

# ═══════════════════════════════════════════════════════════════════
# Live Source Collector Configuration
# ═══════════════════════════════════════════════════════════════════

LIVE_SEARCH_KEYWORDS = {
    # Adult / Night channels (10 calls)
    "adult": [
        "adult iptv m3u github",
        "18+ live channels m3u8 2026",
        "nsfw iptv playlist free",
        "adult tv live stream m3u",
        "xxx iptv m3u8 github",
        "adult channel playlist 2026",
        "night channels m3u free",
        "成人直播源 m3u8",
        "adult iptv-org m3u",
        "premium adult live m3u8 free",
    ],
    # Documentary channels (5 calls)
    "documentary": [
        "documentary channel live m3u8",
        "documentary 24/7 stream playlist",
        "BBC documentary live m3u github",
        "NHK documentary live stream m3u8",
        "纪录片频道 直播源 m3u",
    ],
    # Variety / Entertainment channels (5 calls)
    "variety": [
        "variety show live stream m3u8",
        "korea variety 24/7 m3u github",
        "entertainment channel playlist m3u 2026",
        "综艺直播源 m3u8 github",
        "reality tv live stream playlist free",
    ],
}

MAX_LIVE_SERPAPI_CALLS = 20

# Domestic IPTV filter — discard sources where > 50% channels match these
DOMESTIC_IPTV_KEYWORDS = [
    "CCTV", "cctv", "卫视", "央视", "中央",
    "湖南卫视", "浙江卫视", "江苏卫视", "北京卫视", "东方卫视",
    "广东卫视", "山东卫视", "河南卫视", "四川卫视", "安徽卫视",
    "CGTN", "凤凰", "翡翠台",
]
DOMESTIC_THRESHOLD = 0.5  # if > 50% channels are domestic, discard

# Live source validation
LIVE_STREAM_TIMEOUT = 8       # seconds to check if a stream responds
LIVE_SAMPLE_CHANNELS = 5      # number of channels to sample-check per source

# Live output files
LIVE_OUTPUT_M3U = "output/live_sources.m3u"
LIVE_OUTPUT_JSON = "output/live_sources.json"
LIVE_REPORT_FILE = "output/live_report.md"

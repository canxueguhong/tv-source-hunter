# TV Source Hunter 📡

**自动采集、分析、验证 TVBox 影视接口 & 直播源的一站式工具。**

通过 SerpAPI 搜索引擎自动发现网络上公开分享的 TVBox 多仓接口和 M3U/M3U8 直播源，经过多层验证后输出可直接使用的配置文件。

---

## ✨ 功能特性

### TVBox 接口采集 (`main.py`)
- 🔍 **SerpAPI 搜索采集** — 自动使用多组关键词搜索 TVBox 接口地址
- 📄 **页面深度分析** — 解析搜索结果页面，提取候选接口 URL
- ✅ **五层验证体系** — JSON 格式校验、内容关键词检测、大小过滤、站点抽样探测、速度测试
- 🔗 **去重整合** — 基于内容哈希去重，输出干净的多仓 JSON 配置
- 💾 **智能缓存** — 72 小时缓存已验证结果，避免重复检测
- 🚫 **黑名单过滤** — 支持自定义域名/URL 黑名单

### 直播源采集 (`live_main.py`)
- 📺 **分类搜索** — 按纪录片、综艺等分类搜索直播源
- 🌐 **M3U/M3U8 解析** — 自动识别和解析直播源格式
- 🏠 **国内源过滤** — 自动过滤以 CCTV/卫视为主的国内 IPTV 源
- ⚡ **流可达性检测** — 抽样检测频道流地址是否可访问
- 📝 **多格式输出** — 同时输出 M3U 播放列表和结构化 JSON

---

## 📁 项目结构

```
tv-source-hunter/
├── main.py              # TVBox 接口采集主入口
├── live_main.py         # 直播源采集主入口
├── config.py            # 全局配置（API Key、关键词、阈值等）
├── search_collector.py  # SerpAPI 搜索采集模块
├── page_analyzer.py     # 页面分析与 URL 提取
├── validator.py         # TVBox 接口五层验证
├── integrator.py        # 去重整合与输出
├── cache_manager.py     # 验证结果缓存管理
├── live_search.py       # 直播源搜索采集
├── live_analyzer.py     # 直播源页面分析
├── live_validator.py    # 直播源验证
├── requirements.txt     # Python 依赖
└── output/              # 输出目录（自动生成）
    ├── tvbox_multi.json # TVBox 多仓配置
    ├── sources.md       # 可用接口列表
    ├── report.md        # 运行报告
    ├── live_sources.m3u # 直播源 M3U
    ├── live_sources.json# 直播源 JSON
    └── live_report.md   # 直播源报告
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `config.py`，填入你的 [SerpAPI](https://serpapi.com/) Key：

```python
SERPAPI_KEY = "your_serpapi_key_here"
```

### 3. 运行

**采集 TVBox 接口：**

```bash
# 完整流程：搜索 → 分析 → 验证 → 输出
python main.py

# 仅搜索和分析，不验证（快速预览）
python main.py --dry-run
```

**采集直播源：**

```bash
# 完整流程
python live_main.py

# 仅搜索和分析
python live_main.py --dry-run
```

---

## ⚙️ 配置说明

主要配置项位于 `config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MAX_SERPAPI_CALLS` | 20 | SerpAPI 调用次数上限 |
| `REQUEST_TIMEOUT` | 15s | 页面抓取超时 |
| `VALIDATION_TIMEOUT` | 10s | 接口验证超时 |
| `MAX_CONCURRENT_REQUESTS` | 100 | 异步并发请求数 |
| `MIN_JSON_BYTES` | 1024 | JSON 最小字节数阈值 |
| `CACHE_EXPIRY_HOURS` | 72h | 缓存有效期 |
| `DOMESTIC_THRESHOLD` | 0.5 | 国内源占比过滤阈值 |

---

## 📊 输出示例

运行完成后，终端会显示汇总报告：

```
══════════════════════════════════════════════════════════════════════
  📊 最终报告
══════════════════════════════════════════════════════════════════════
  搜索结果页面数:     42
  提取候选接口 URL:   85 (新发现) + 14 (用户样本)
  通过验证 (去重前):  31
  内容去重移除:       6
  最终保留:           25
  总耗时:             128.3s
══════════════════════════════════════════════════════════════════════
```

---

## 🛠️ 技术栈

- **Python 3.10+**
- **httpx** — 异步 HTTP 客户端
- **SerpAPI** — 搜索引擎 API
- **dnspython** — DNS 解析（阿里公共 DNS）
- **asyncio** — 异步并发处理

---

## 📄 License

MIT

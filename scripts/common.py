#!/usr/bin/env python3
"""
公共工具：编码转换、HTTP 请求、字段映射、ETF 代码表。
被 quote.py / finance.py / kline.py / announcements.py 复用。
"""
import hashlib
import os
import random
import sys
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
CACHE_DIR = PACKAGE_ROOT / ".cache"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "stock-analyzer-skill/1.0",
]

# ---------- 磁盘缓存 ----------

def _ensure_cache_dir():
    CACHE_DIR.mkdir(exist_ok=True)


def cache_get(key: str, ttl_seconds: int = 21600) -> bytes | None:
    """读取缓存，TTL 超时返回 None。默认 6 小时。"""
    _ensure_cache_dir()
    cache_file = CACHE_DIR / f"{key}.cache"
    if not cache_file.exists():
        return None
    if time.time() - cache_file.stat().st_mtime > ttl_seconds:
        cache_file.unlink(missing_ok=True)
        return None
    return cache_file.read_bytes()


def cache_set(key: str, data: bytes):
    """写入缓存。"""
    _ensure_cache_dir()
    cache_file = CACHE_DIR / f"{key}.cache"
    cache_file.write_bytes(data)


def cache_key(url: str) -> str:
    """用 URL 的 SHA256 生成缓存键。"""
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def cache_key_for_stock(prefix: str, code: str, **params) -> str:
    """生成股票相关的缓存键，支持按代码清除。
    格式: {prefix}_{code}_{param_hash}
    """
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8] if param_str else ""
    return f"{prefix}_{code}_{param_hash}".rstrip("_")


def http_get_cached(url: str, timeout: int = 10, ttl: int = 21600) -> bytes:
    """带缓存的 HTTP GET。先读缓存，未命中则请求并写入缓存。"""
    key = cache_key(url)
    cached = cache_get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache_set(key, data)
    return data


def http_get_cached_keyed(url: str, key: str, timeout: int = 10, ttl: int = 21600) -> bytes:
    """带语义缓存键的 HTTP GET。"""
    cached = cache_get(key, ttl)
    if cached is not None:
        return cached
    data = http_get(url, timeout)
    cache_set(key, data)
    return data

# ---------- HTTP ----------

def http_get(url: str, timeout: int = 10, max_retries: int = 3) -> bytes:
    """GET 请求，指数退避重试，UA 随机轮换。"""
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": random.choice(USER_AGENTS),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, urllib.error.HTTPError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
    raise RuntimeError(f"GET {url} 失败（重试 {max_retries} 次）: {last_err}")

# ---------- 编码 ----------

def decode_gbk(data: bytes) -> str:
    """腾讯接口 GBK → UTF-8。"""
    return data.decode("gbk", errors="replace")

# ---------- 腾讯行情字段映射 ----------

# 字段位（按 ~ 分隔，0-based 索引，已剥除 v_sh600989=" 前缀）
# 方法论文档的 1-based 编号 - 1 = 本表 0-based
TENCENT_FIELDS = {
    "market": 0,            # 市场代码
    "name": 1,              # 名称
    "code": 2,              # 股票代码
    "price": 3,             # 当前价
    "prev_close": 4,        # 昨收
    "open": 5,              # 今开
    "change_amt": 31,       # 涨跌额
    "change_pct": 32,       # 涨跌幅%
    "high": 33,             # 最高
    "low": 34,              # 最低
    "volume": 36,           # 成交量(手)
    "amount": 37,           # 成交额(万)
    "turnover": 38,         # 换手率%
    "pe": 39,               # PE(动)
    "amplitude": 43,        # 振幅%
    "total_cap": 44,        # 总市值(亿)
    "circulating_cap": 45,  # 流通市值(亿)
    "pb": 46,               # PB
    "limit_up": 47,         # 涨停价
    "limit_down": 48,       # 跌停价
}

def parse_tencent_line(line: str) -> dict:
    """解析单行腾讯行情（v_sh600989="..." 形式）。"""
    if "=" not in line or '"' not in line:
        return {}
    payload = line.split('"', 1)[1].rstrip('";\n')
    parts = payload.split("~")
    if len(parts) < 50:
        return {}
    return {
        "code": parts[TENCENT_FIELDS["code"]],
        "name": parts[TENCENT_FIELDS["name"]],
        "price": parts[TENCENT_FIELDS["price"]],
        "prev_close": parts[TENCENT_FIELDS["prev_close"]],
        "open": parts[TENCENT_FIELDS["open"]],
        "change_pct": parts[TENCENT_FIELDS["change_pct"]],
        "change_amt": parts[TENCENT_FIELDS["change_amt"]],
        "high": parts[TENCENT_FIELDS["high"]],
        "low": parts[TENCENT_FIELDS["low"]],
        "volume": parts[TENCENT_FIELDS["volume"]],
        "amount": parts[TENCENT_FIELDS["amount"]],
        "turnover": parts[TENCENT_FIELDS["turnover"]],
        "pe": parts[TENCENT_FIELDS["pe"]],
        "pb": parts[TENCENT_FIELDS["pb"]],
        "total_cap": parts[TENCENT_FIELDS["total_cap"]],
        "circulating_cap": parts[TENCENT_FIELDS["circulating_cap"]],
    }

# ---------- 东财财务字段 ----------

EAST_MONEY_FIELDS = {
    "EPSJB": "每股收益",
    "ROEJQ": "ROE(加权)%",
    "TOTALOPERATEREVETZ": "营收同比%",
    "PARENTNETPROFITTZ": "净利同比%",
    "XSMLL": "毛利率%",
    "XSJLL": "净利率%",
    "ZCFZL": "负债率%",
    "BPS": "每股净资产",
    "MGJYXJJE": "每股经营现金流",
    "XSGJ": "销售净利率%",
    "YSHZ": "营收环比%",
    "SJLTZ": "净利润环比%",
}

# ---------- 工具 ----------

def split_codes(arg: str) -> list:
    """支持逗号分隔或文件路径（@file）。"""
    if arg.startswith("@"):
        return [line.strip() for line in Path(arg[1:]).read_text().splitlines() if line.strip()]
    return [c.strip() for c in arg.split(",") if c.strip()]

def plain_code(code: str) -> str:
    """返回 6 位证券代码。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        c = c[2:]
    return c.upper()

def infer_exchange(code: str) -> str:
    """按 A 股代码段推断交易所前缀。"""
    c = plain_code(code)
    if c.startswith(("60", "68", "51", "56", "58")):
        return "sh"
    if c.startswith(("00", "30", "15", "16", "18")):
        return "sz"
    if c.startswith(("43", "83", "87", "88", "92")):
        return "bj"
    return code.strip()[:2].lower() if code.strip()[:2].lower() in {"sh", "sz", "bj"} else ""

def normalize_quote_code(code: str) -> str:
    """归一化为腾讯/新浪使用的小写交易所前缀代码。"""
    c = plain_code(code)
    market = infer_exchange(code)
    return f"{market}{c}" if market else code.strip().lower()

def normalize_finance_code(code: str) -> str:
    """归一化为东财财务接口使用的大写交易所前缀代码。"""
    q = normalize_quote_code(code)
    return q[:2].upper() + q[2:] if len(q) >= 8 else q.upper()

def board_type(code: str) -> str:
    """粗分 A 股板块，用于风险提示和涨跌幅判断。"""
    c = plain_code(code)
    if c.startswith("688"):
        return "科创板"
    if c.startswith(("300", "301")):
        return "创业板"
    if c.startswith(("43", "83", "87", "88", "92")):
        return "北交所"
    if c.startswith(("60", "00")):
        return "主板"
    return "其他"

def batchify(items: list, size: int = 15):
    """将列表按 size 分批。腾讯单次 ≤15。"""
    for i in range(0, len(items), size):
        yield items[i:i + size]

def to_float(value, default=0.0):
    """安全转浮点数，空值/异常返回默认值。"""
    try:
        if value in (None, "", "-"):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def clamp(value, low=0.0, high=100.0):
    """将值限制在 [low, high] 区间。"""
    return max(low, min(high, value))


def err(msg: str):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def parallel_map(fn, items, max_workers=8, timeout=60):
    """并发执行 fn(item)，返回 {item: result} 字典。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fn, item): item for item in items}
        for future in as_completed(futures, timeout=timeout):
            item = futures[future]
            try:
                results[item] = future.result()
            except Exception:
                results[item] = None
    return results

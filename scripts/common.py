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
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
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


def cache_cleanup(prefix: str = None, max_age_seconds: int = 86400):
    """清理过期缓存。prefix 为空时清理所有过期文件。"""
    _ensure_cache_dir()
    cleaned = 0
    for f in CACHE_DIR.glob("*.cache"):
        if prefix and not f.name.startswith(prefix):
            continue
        if time.time() - f.stat().st_mtime > max_age_seconds:
            f.unlink(missing_ok=True)
            cleaned += 1
    return cleaned


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
    """GET 请求，指数退避重试，UA 随机轮换。429 立即抛出不重试。"""
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": random.choice(USER_AGENTS),
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                raise RateLimitError(f"429 Too Many Requests: {url}")
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
            if attempt < max_retries - 1:
                delay = min(1.0 * (2 ** attempt), 8.0)
                jitter = random.uniform(0, delay * 0.5)
                time.sleep(delay + jitter)
    raise DataSourceUnavailableError(f"GET {url} 失败（重试 {max_retries} 次）: {last_err}")

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


# ---------- 新浪行情字段映射 ----------

SINA_QUOTE_URL = "https://hq.sinajs.cn/list={codes}"

def parse_sina_quote_line(line: str) -> dict:
    """解析新浪行情单行: var hq_str_sh600989="名称,今开,昨收,当前价,最高,最低,..."; """
    if '="' not in line:
        return {}
    var_part, data_part = line.split('="', 1)
    code = var_part.split("_")[-1]  # sh600989
    fields = data_part.rstrip('";\n').split(",")
    if len(fields) < 32:
        return {}
    return {
        "code": code,
        "name": fields[0],
        "open": fields[1],
        "prev_close": fields[2],
        "price": fields[3],
        "high": fields[4],
        "low": fields[5],
        "volume": fields[8],      # 成交量(股)
        "amount": fields[9],      # 成交额
        "change_pct": str(round((float(fields[3]) / float(fields[2]) - 1) * 100, 2)) if float(fields[2]) > 0 else "0",
        "change_amt": str(round(float(fields[3]) - float(fields[2]), 2)) if float(fields[2]) > 0 else "0",
        "turnover": "",  # 新浪不直接提供换手率
        "pe": "",        # 新浪不直接提供 PE
        "pb": "",        # 新浪不直接提供 PB
        "total_cap": "", # 新浪不直接提供总市值
        "circulating_cap": "",
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
    """抛出 DataError 异常（替代原来的 sys.exit）。"""
    print(f"❌ {msg}", file=sys.stderr)
    raise DataError(msg)


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


# ---------- 异常分类 ----------

class RateLimitError(Exception):
    """429 Too Many Requests"""
    pass

class DataSourceUnavailableError(Exception):
    """数据源不可用（连接失败、超时等）"""
    pass

class DataParseError(Exception):
    """数据解析失败"""
    pass

class DataError(Exception):
    """通用数据错误，用于替代 err() 的 sys.exit。"""
    pass


# ---------- 熔断器 ----------

from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"        # 正常
    OPEN = "open"            # 熔断
    HALF_OPEN = "half_open"  # 试探

class CircuitBreaker:
    """线程安全的熔断器：连续失败 N 次后熔断，超时后半开试探。"""

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 60, half_open_max: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max

        self._lock = threading.Lock()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_success = 0

    def can_execute(self) -> bool:
        """判断是否允许请求（线程安全）。"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_success = 0
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return True
            return False

    def record_success(self):
        """记录成功（线程安全）。"""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.half_open_success += 1
                if self.half_open_success >= self.half_open_max:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    def record_failure(self):
        """记录失败（线程安全）。"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN

    def reset(self):
        """重置熔断器（线程安全）。"""
        with self._lock:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_failure_time = 0


# 全局熔断器实例（线程安全）
_circuit_breakers = {}
_circuit_breakers_lock = threading.Lock()

def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """获取或创建熔断器实例（线程安全）。"""
    with _circuit_breakers_lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, **kwargs)
        return _circuit_breakers[name]


# ---------- 数据源抽象基类 ----------

from abc import ABC, abstractmethod

class BaseFetcher(ABC):
    """数据源抽象基类。"""

    def __init__(self, name: str, priority: int = 0):
        self.name = name
        self.priority = priority
        self.circuit_breaker = get_circuit_breaker(name)

    @abstractmethod
    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """获取数据。返回 None 表示失败。"""
        pass

    def is_available(self) -> bool:
        """检查数据源是否可用（熔断器状态）。"""
        return self.circuit_breaker.can_execute()

    def on_success(self):
        """记录成功。"""
        self.circuit_breaker.record_success()

    def on_failure(self):
        """记录失败。"""
        self.circuit_breaker.record_failure()


class DataFetcherManager:
    """数据源策略管理器：按优先级尝试，自动故障切换。"""

    def __init__(self, fetchers: list):
        self.fetchers = sorted(fetchers, key=lambda f: f.priority, reverse=True)

    def fetch(self, code: str, **kwargs) -> dict | list | None:
        """按优先级尝试各数据源。"""
        last_error = None
        for fetcher in self.fetchers:
            if not fetcher.is_available():
                continue
            try:
                result = fetcher.fetch(code, **kwargs)
                if result is not None:
                    fetcher.on_success()
                    return result
                fetcher.on_failure()
            except RateLimitError:
                fetcher.on_failure()
                raise  # 限流直接抛出
            except Exception as e:
                fetcher.on_failure()
                last_error = e
                continue
        return None

    def fetch_with_fallback(self, code: str, fallback=None, **kwargs):
        """带默认值的获取。"""
        result = self.fetch(code, **kwargs)
        return result if result is not None else fallback

    def fetch_with_cache_fallback(self, code: str, cache_prefix: str = None,
                                   cache_ttl: int = 21600, fallback=None, **kwargs):
        """带缓存降级的获取：优先实时数据 → 缓存数据 → 默认值。"""
        result = self.fetch(code, **kwargs)
        if result is not None:
            return result

        # 尝试从缓存降级
        if cache_prefix:
            key = cache_key_for_stock(cache_prefix, code, **kwargs)
            cached = cache_get(key, cache_ttl)
            if cached is not None:
                try:
                    import json
                    return json.loads(cached)
                except (json.JSONDecodeError, Exception):
                    pass

        return fallback

"""工具函数：代码转换、类型转换、并发执行。"""
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from common.exceptions import DataError

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"


# ---------- 代码转换 ----------

def split_codes(arg: str) -> list:
    """支持逗号分隔或文件路径（@file）。"""
    if arg.startswith("@"):
        file_path = Path(arg[1:]).resolve()
        if not str(file_path).startswith(str(DATA_DIR.resolve())):
            raise ValueError(f"文件路径不在允许范围内: {arg[1:]}")
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {arg[1:]}")
        return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
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


def to_secid(code: str) -> str:
    """转换为东方财富 secid 格式（如 1.600519, 0.000858）。"""
    c = code.strip().lower()
    if c.startswith("sh"):
        return f"1.{c[2:]}"
    if c.startswith("sz"):
        return f"0.{c[2:]}"
    plain = c.lstrip("shszbj")
    if plain.startswith(("60", "68", "51", "56", "58")):
        return f"1.{plain}"
    return f"0.{plain}"


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


# ---------- 类型转换 ----------

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


def to_int(value, default=0):
    """安全转整数，空值/异常返回默认值。"""
    try:
        if value in (None, "", "-"):
            return default
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def clamp(value, low=0.0, high=100.0):
    """将值限制在 [low, high] 区间。"""
    return max(low, min(high, value))


# ---------- 数据单位归一化 ----------
# 统一规范：volume=股, amount=元, total_cap/circulating_cap=亿

def normalize_volume(raw, source: str) -> int:
    """将不同数据源的成交量归一化为股。
    腾讯: 手 → 股 (×100)
    新浪/东财: 股 (原值)
    """
    v = to_int(raw)
    if source == "tencent":
        return v * 100
    return v


def normalize_amount(raw, source: str) -> float:
    """将不同数据源的成交额归一化为元。
    腾讯: 万元 → 元 (×10000)
    东财: 元 (原值)
    新浪: 元 (原值)
    """
    v = to_float(raw)
    if source == "tencent":
        return v * 10000
    return v


# ---------- 错误处理 ----------

def err(msg: str):
    """抛出 DataError 异常（替代原来的 sys.exit）。"""
    print(f"❌ {msg}", file=sys.stderr)
    raise DataError(msg, {"source": "common.err"})


# ---------- 并发 ----------

def parallel_map(fn, items, max_workers=8, timeout=60):
    """并发执行 fn(item)，返回 {item: result} 字典。"""
    import logging
    logger = logging.getLogger(__name__)
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fn, item): item for item in items}
        for future in as_completed(futures, timeout=timeout):
            item = futures[future]
            try:
                results[item] = future.result()
            except Exception as e:
                logger.warning("parallel_map 任务失败: %s -> %s", item, e)
                results[item] = None
    return results


__all__ = [
    "PACKAGE_ROOT", "DATA_DIR",
    "split_codes", "plain_code", "infer_exchange",
    "normalize_quote_code", "normalize_finance_code", "to_secid",
    "board_type", "batchify", "to_float", "to_int", "clamp",
    "normalize_volume", "normalize_amount",
    "err", "parallel_map",
]

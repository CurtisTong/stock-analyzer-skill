"""工具函数：代码转换、类型转换、并发执行。"""

import concurrent.futures
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from common.exceptions import DataError

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"


# ---------- 代码转换 ----------


def split_codes(arg: str) -> list[str]:
    """支持逗号分隔或文件路径（@file）。"""
    if arg.startswith("@"):
        file_path = Path(arg[1:]).resolve()
        if not str(file_path).startswith(str(DATA_DIR.resolve())):
            raise ValueError(f"文件路径不在允许范围内: {arg[1:]}")
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {arg[1:]}")
        return [
            line.strip()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return [c.strip() for c in arg.split(",") if c.strip()]


def plain_code(code: str) -> str:
    """返回 6 位证券代码。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        c = c[2:]
    return c.upper()


def infer_exchange(code: str) -> str:
    """按 A 股代码段推断交易所前缀。如果代码已带前缀则直接使用。"""
    c = code.strip().lower()
    # 如果已带交易所前缀，直接返回
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    # 否则按代码段推断
    c = c.upper()
    if c.startswith(("60", "68", "51", "56", "58")):
        return "sh"
    if c.startswith(("00", "30", "15", "16", "18")):
        return "sz"
    if c.startswith(("43", "83", "87", "88", "92")):
        return "bj"
    return ""


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
    if is_etf(code):
        return "ETF"
    if c.startswith("688"):
        return "科创板"
    if c.startswith(("300", "301")):
        return "创业板"
    if c.startswith(("43", "83", "87", "88", "92")):
        return "北交所"
    if c.startswith(("60", "00")):
        return "主板"
    return "其他"


def is_etf(code: str) -> bool:
    """判断是否为 ETF 代码。
    上交所 ETF: 51xxxx, 56xxxx, 58xxxx
    深交所 ETF: 15xxxx, 16xxxx, 18xxxx
    """
    c = plain_code(code)
    return c.startswith(("51", "56", "58", "15", "16", "18"))


# ---------- 类型转换 ----------


def batchify(items: list[str], size: int = 15) -> list[list[str]]:
    """将列表按 size 分批。腾讯单次 ≤15。"""
    return [items[i : i + size] for i in range(0, len(items), size)]


def to_float(value: object, default: float = 0.0) -> float:
    """安全转浮点数，空值/异常返回默认值。"""
    try:
        if value in (None, "", "-"):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def to_int(value: object, default: int = 0) -> int:
    """安全转整数，空值/异常返回默认值。"""
    try:
        if value in (None, "", "-"):
            return default
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """将值限制在 [low, high] 区间。"""
    return max(low, min(high, value))


def compute_volume_ratio(
    volumes: list[float], recent_window: int = 5, base_window: int = 10
) -> float:
    """计算量比（最近 N 日平均 / 基础 N 日平均）。

    base_window 包含 recent_window，语义为"最近 N 日放量程度"，
    与 detect_market_state 原始逻辑一致。
    """
    if len(volumes) < base_window:
        return 1.0
    recent_vol = statistics.mean(volumes[-recent_window:])
    base_vol = statistics.mean(volumes[-base_window:])
    return recent_vol / base_vol if base_vol > 0 else 1.0


def compute_optimal_workers(item_count: int = 0) -> int:
    """动态计算最优工作线程数。"""
    cpu_count = os.cpu_count() or 4
    if item_count > 0:
        return min(max(item_count // 10, 4), cpu_count * 2)
    return min(cpu_count * 2, 32)


# ---------- 数据单位归一化 ----------
# 统一规范：volume=股, amount=元, total_cap/circulating_cap=亿


def normalize_volume(raw: int | str | None, source: str) -> int:
    """将不同数据源的成交量归一化为股。
    腾讯: 手 → 股 (×100)
    东财: 手 → 股 (×100)
    新浪: 股 (原值)
    """
    v = to_int(raw)
    if source in ("tencent", "eastmoney"):
        return v * 100
    return v


def normalize_amount(raw: object, source: str) -> float:
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


def err(msg: str) -> None:
    """抛出 DataError 异常（替代原来的 sys.exit）。"""
    print(f"❌ {msg}", file=sys.stderr)
    raise DataError(msg, {"source": "common.err"})


# ---------- 并发 ----------

# 模块级共享线程池（惰性初始化）
_shared_executor = None
_shared_executor_lock = __import__("threading").Lock()


def get_shared_executor(max_workers: int | None = None) -> ThreadPoolExecutor:
    """获取共享线程池，线程安全的惰性初始化。

    Args:
        max_workers: 最大线程数，首次调用时生效，后续调用忽略此参数。
                    默认为 min(32, os.cpu_count() + 4)。
    Returns:
        ThreadPoolExecutor 实例（不会被 shutdown，由进程退出时自动清理）
    """
    global _shared_executor
    if _shared_executor is not None:
        return _shared_executor
    with _shared_executor_lock:
        if _shared_executor is None:
            if max_workers is None:
                max_workers = min(32, (os.cpu_count() or 4) + 4)
            _shared_executor = ThreadPoolExecutor(max_workers=max_workers)
    return _shared_executor


def parallel_map(
    fn: Callable[[str], Any],
    items: list[str],
    max_workers: int = 8,
    timeout: int = 60,
) -> dict[str, Any]:
    """并发执行 fn(item)，返回 {item: result} 字典。

    超时时返回已完成的部分结果，而非抛出异常丢失所有结果。
    RateLimitError 始终向上抛出。
    """
    import logging
    from concurrent.futures import Future
    from common.exceptions import RateLimitError

    logger = logging.getLogger(__name__)
    results: dict[str, Any] = {}
    ex = get_shared_executor(max_workers)
    futures: dict[Future[object], str] = {ex.submit(fn, item): item for item in items}  # type: ignore[arg-type]
    try:
        for future in as_completed(futures, timeout=timeout):
            item = futures[future]
            try:
                results[item] = future.result()
            except RateLimitError:
                raise
            except Exception as e:
                logger.warning("parallel_map 任务失败: %s -> %s", item, e)
                results[item] = None
    except concurrent.futures.TimeoutError:
        logger.warning(
            "parallel_map 超时，返回部分结果 (%d/%d)", len(results), len(items)
        )
        for future in futures:
            future.cancel()
    return results


def board_limit_pct(board: str) -> float:
    """获取板块涨跌停限制（%）。"""
    _DEFAULTS = {
        "主板": 9.5,
        "创业板": 19.5,
        "科创板": 19.5,
        "北交所": 29.5,
    }
    return _DEFAULTS.get(board, 9.5)


__all__ = [
    "PACKAGE_ROOT",
    "DATA_DIR",
    "split_codes",
    "plain_code",
    "infer_exchange",
    "normalize_quote_code",
    "normalize_finance_code",
    "to_secid",
    "board_type",
    "batchify",
    "to_float",
    "to_int",
    "clamp",
    "compute_volume_ratio",
    "compute_optimal_workers",
    "normalize_volume",
    "normalize_amount",
    "err",
    "parallel_map",
    "get_shared_executor",
    "board_limit_pct",
]

"""
股票池刷新业务逻辑层。

从 refresh_pool.py 下沉的纯业务逻辑，CLI 层（refresh_pool.py）只保留
print_diff 和 main。所有进度信息通过 logging.info 输出，CLI 层
负责面向用户的 print。

依赖：common.http_get_cached / common.board_type / common.infer_exchange
"""

import json
import logging
import os
import sys
import time
from datetime import datetime


def _get_common_deps():
    """延迟导入 common，避免模块顶层 sys.path 修改破坏包隔离。"""
    from common import http_get_cached, board_type, infer_exchange

    return http_get_cached, board_type, infer_exchange


def _get_filter():
    """延迟导入筛选配置。"""
    from strategies.filters import PRE_SCREEN_FILTER as FILTER

    return FILTER

logger = logging.getLogger(__name__)

# ---------- 常量 ----------

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
MAPPING_FILE = os.path.join(DATA_DIR, "sector_mapping.json")
POOL_FILE = os.path.join(DATA_DIR, "sector_stocks.json")
ALL_STOCKS_FILE = os.path.join(DATA_DIR, "all_stocks.json")

API_BASE = "https://push2.eastmoney.com/api/qt/clist/get"
API_TOKEN = os.environ.get("EASTMONEY_API_TOKEN", "")
FIELDS = "f12,f14,f2,f3,f6,f8,f9,f20"  # code,name,price,chg%,amount,turnover,pe,cap

# 预置默认股票池文件
DEFAULT_POOL_FILE = os.path.join(DATA_DIR, "sector_stocks.default.json")

# 东方财富选股器 API
XUANGU_API_BASE = "https://data.eastmoney.com/dataapi/xuangu/list"
XUANGU_FIELDS = "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,MARKET"


# ---------- API 调用 ----------


def fetch_board_stocks(bk_code: str, max_retries: int = 2) -> list[dict]:
    """获取板块成分股，返回 [{code, name, price, change_pct, amount, turnover, pe, cap}]"""
    http_get_cached, _, infer_exchange = _get_common_deps()
    ut_param = f"&ut={API_TOKEN}" if API_TOKEN else ""
    url = (
        f"{API_BASE}?pn=1&pz=500&np=1{ut_param}"
        f"&fltt=2&invt=2&fid=f3&fs=b:{bk_code}&fields={FIELDS}"
    )
    for attempt in range(max_retries + 1):
        try:
            raw = http_get_cached(url, ttl=3600)  # 缓存 1 小时
            data = json.loads(raw)
            if not data or "data" not in data or not data["data"]:
                return []
            items = data["data"].get("diff", [])
            results = []
            for item in items:
                code6 = str(item.get("f12", ""))
                if not code6 or len(code6) != 6:
                    continue
                full_code = f"{infer_exchange(code6)}{code6}"
                results.append(
                    {
                        "code": full_code,
                        "name": item.get("f14", ""),
                        "price": item.get("f2"),
                        "change_pct": item.get("f3"),
                        "amount": item.get("f6"),  # 成交额（元）
                        "turnover": item.get("f8"),  # 换手率
                        "pe": item.get("f9"),  # PE(动)
                        "cap": item.get("f20"),  # 总市值（元）
                    }
                )
            return results
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
            logger.warning("API 请求失败 (%s): %s", bk_code, e)
            return []


def fetch_multiple_boards(bk_codes: list[str]) -> list[dict]:
    """合并多个板块的成分股，去重"""
    seen = {}
    for bk in bk_codes:
        stocks = fetch_board_stocks(bk)
        for s in stocks:
            if s["code"] not in seen:
                seen[s["code"]] = s
        time.sleep(0.5)  # 限流
    return list(seen.values())


# ---------- 全市场股票池 ----------


def _fetch_xuangu_page(
    page: int = 1, page_size: int = 1000, market_filter: str = "", max_retries: int = 2
) -> tuple[list[dict], int]:
    """从东方财富选股器 API 获取一页股票数据。

    Returns:
        (stocks_list, total_count)
    """
    import urllib.parse
    import urllib.request

    params = {
        "st": "SECURITY_CODE",
        "sr": "1",
        "ps": str(page_size),
        "p": str(page),
        "sty": XUANGU_FIELDS,
        "filter": market_filter,
    }

    query = urllib.parse.urlencode(params)
    url = f"{XUANGU_API_BASE}?{query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/",
    }

    req = urllib.request.Request(url, headers=headers)

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)

                if data.get("success"):
                    records = data.get("result", {}).get("data", [])
                    total = data.get("result", {}).get("count", 0)
                    return records, total
                return [], 0
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
            logger.warning(
                "选股器 API 请求失败 (第 %d 页, 重试 %d 次后放弃): %s",
                page,
                max_retries,
                e,
            )
            return [], 0


def fetch_all_market_stocks() -> dict[str, list[str]]:
    """拉取全市场 A 股列表，按上市板块分组返回。

    优先使用 push2 API，如果失败则回退到选股器 API。

    Returns:
        {"主板沪": ["sh600519", ...], "主板深": [...], ...}
    """
    boards: dict[str, list[str]] = {
        "主板沪": [],
        "主板深": [],
        "创业板": [],
        "科创板": [],
        "北交所": [],
    }

    # 方案 1: 尝试使用 push2 API
    logger.info("尝试使用 push2 API 获取全市场股票...")
    try:
        _fetch_push2_market(boards)
        total = sum(len(v) for v in boards.values())
        if total > 1000:
            logger.info("push2 API 成功获取 %d 只股票", total)
            return boards
        else:
            logger.warning("push2 API 数据不足 (%d 只)，切换到选股器 API", total)
    except Exception as e:
        logger.warning("push2 API 失败: %s，切换到选股器 API", e)

    # 方案 2: 使用选股器 API（使用 SECURITY_TYPE_CODE 过滤条件）
    logger.info("使用选股器 API 获取全市场股票...")

    # 清空之前的数据
    for key in boards:
        boards[key] = []

    # 使用 SECURITY_TYPE_CODE 过滤条件获取所有 A 股
    # 058001001 = A 股
    all_stocks = []
    page = 1
    page_size = 1000

    while True:
        stocks, total = _fetch_xuangu_page(
            page, page_size, '(SECURITY_TYPE_CODE="058001001")'
        )
        if not stocks:
            break

        all_stocks.extend(stocks)
        logger.info("第 %d 页: %d 只 (总计: %d)", page, len(stocks), total)

        if len(all_stocks) >= total:
            break

        page += 1
        time.sleep(0.3)

    # 按板块分类
    _, board_type, infer_exchange = _get_common_deps()
    for s in all_stocks:
        code = str(s.get("SECURITY_CODE", ""))
        name = str(s.get("SECURITY_NAME_ABBR", ""))
        if not code or len(code) != 6:
            continue
        # 排除 ST 股
        if "ST" in name.upper():
            continue
        board = board_type(code)
        if board in boards:
            exchange = infer_exchange(code)
            full_code = f"{exchange}{code}"
            boards[board].append(full_code)

    return boards


def _fetch_push2_market(boards: dict[str, list[str]]) -> None:
    """使用 push2 API 获取全市场股票（原始方案）。"""
    http_get_cached, board_type, infer_exchange = _get_common_deps()
    FULL_MARKET_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81"
    page = 1
    page_size = 5000

    while True:
        url = (
            f"{API_BASE}?pn={page}&pz={page_size}&np=1"
            f"&fltt=2&invt=2&fid=f3&fs={FULL_MARKET_FS}&fields={FIELDS}"
        )
        raw = http_get_cached(url, ttl=3600)
        data = json.loads(raw)

        if not data or "data" not in data or not data["data"]:
            if page == 1:
                raise ValueError("push2 API 返回空数据")
            break

        items = data["data"].get("diff", [])
        if not items:
            break

        for item in items:
            code6 = str(item.get("f12", ""))
            name = str(item.get("f14", ""))
            if not code6 or len(code6) != 6:
                continue
            # 排除 ST 股
            if "ST" in name.upper():
                continue
            board = board_type(code6)
            if board == "其他":
                continue
            exchange = infer_exchange(code6)
            full_code = f"{exchange}{code6}"
            boards[board].append(full_code)

        total = data["data"].get("total", 0)
        if page * page_size >= total:
            break
        page += 1
        time.sleep(0.3)


def save_all_market_stocks(stocks_by_board: dict[str, list[str]]) -> None:
    """保存全市场股票池到 all_stocks.json。"""
    total = sum(len(v) for v in stocks_by_board.values())
    output = {
        "_meta": {
            "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "eastmoney_full_market",
            "total_stocks": total,
        },
    }
    output.update(stocks_by_board)
    with open(ALL_STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("已写入 %s (%d 只)", ALL_STOCKS_FILE, total)
    for board, codes in stocks_by_board.items():
        logger.info("  %s: %d 只", board, len(codes))


# ---------- 过滤 ----------


def is_st(name: str) -> bool:
    return "ST" in name.upper()


def passes_filter(stock: dict) -> tuple[bool, str]:
    """硬过滤，返回 (通过, 原因)"""
    _, board_type, _ = _get_common_deps()
    FILTER = _get_filter()
    name = stock.get("name", "")
    code = stock.get("code", "")
    bt = board_type(code)

    if is_st(name):
        return False, "ST"

    amount = stock.get("amount")
    if amount is not None:
        amount_wan = amount / 10000  # 元→万元
        min_amt = FILTER["min_amount"].get(bt, 5000)
        if amount_wan < min_amt:
            return False, f"成交额{amount_wan:.0f}万<{min_amt}万"

    cap = stock.get("cap")
    if cap is not None:
        cap_yi = cap / 100000000  # 元→亿元
        min_cap = FILTER["min_cap"].get(bt, 40)
        if cap_yi < min_cap:
            return False, f"市值{cap_yi:.0f}亿<{min_cap}亿"

    return True, ""


# ---------- 排序与筛选 ----------


def sort_stocks(stocks: list[dict], key: str = "amount") -> list[dict]:
    """排序，降序"""
    keys = {
        "amount": lambda s: s.get("amount") or 0,
        "cap": lambda s: s.get("cap") or 0,
        "pe": lambda s: s.get("pe") or 9999,
        "turnover": lambda s: s.get("turnover") or 0,
    }
    return sorted(stocks, key=keys.get(key, keys["amount"]), reverse=True)


def build_sector_pool(
    stocks: list[dict], top_n: int = 20, sort_by: str = "amount"
) -> list[str]:
    """过滤+排序+截取，返回代码列表"""
    filtered = []
    reasons = {}
    for s in stocks:
        ok, reason = passes_filter(s)
        if ok:
            filtered.append(s)
        else:
            reasons[s["code"]] = reason

    sorted_stocks = sort_stocks(filtered, sort_by)
    return [s["code"] for s in sorted_stocks[:top_n]]


# ---------- 高股息特殊处理 ----------


def build_dividend_pool(
    all_pools: dict[str, list[str]], code_to_stock: dict[str, dict]
) -> list[str]:
    """从所有板块中筛选 PE<20 的标的（按成交额取 Top 20）。

    Args:
        all_pools: 板块 → 代码列表的映射
        code_to_stock: 代码 → 行情 dict 的映射（含 pe/amount）
    """
    candidates = []
    seen = set()
    for sector, codes in all_pools.items():
        if sector == "高股息":
            continue
        for code in codes:
            if code in seen:
                continue
            seen.add(code)
            s = code_to_stock.get(code, {})
            pe = s.get("pe")
            if pe is not None and 0 < pe < 20:
                candidates.append(s)
    sorted_c = sort_stocks(candidates, "amount")
    return [s["code"] for s in sorted_c[:20]]


# ---------- 主流程 ----------


def load_mapping() -> dict:
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_default_pool() -> dict:
    """加载预置默认股票池数据。"""
    if not os.path.exists(DEFAULT_POOL_FILE):
        return {}
    try:
        with open(DEFAULT_POOL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (json.JSONDecodeError, OSError):
        return {}


def load_current_pool() -> dict:
    if not os.path.exists(POOL_FILE):
        return {}
    with open(POOL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _log_diff(current: dict, new_pool: dict) -> None:
    """通过 logging 输出新旧池对比（业务层用，CLI 层有 print_diff）。"""
    all_sectors = sorted(set(list(current.keys()) + list(new_pool.keys())))

    for sector in all_sectors:
        old = set(current.get(sector, []))
        new = set(new_pool.get(sector, []))
        added = new - old
        removed = old - new
        if not added and not removed:
            continue
        parts = []
        if added:
            parts.append(f"+新增 {len(added)}: {', '.join(sorted(added))}")
        if removed:
            parts.append(f"-移除 {len(removed)}: {', '.join(sorted(removed))}")
        logger.info("【%s】%s", sector, " | ".join(parts))

    total_old = sum(len(v) for v in current.values())
    total_new = sum(len(v) for v in new_pool.values())
    logger.info("总计: %d → %d (%+d)", total_old, total_new, total_new - total_old)


def refresh_pool(
    sectors: list[str] | None = None,
    top_n: int = 20,
    sort_by: str = "amount",
    dry_run: bool = False,
    show_diff: bool = False,
    use_default: bool = True,
) -> dict:
    """刷新股票池，返回新池。

    Args:
        use_default: API 失败时是否使用预置默认数据（默认 True）
    """
    mapping = load_mapping()
    current = load_current_pool()
    default_pool = load_default_pool() if use_default else {}

    target_sectors = sectors or [k for k in mapping if not k.startswith("_")]
    new_pool = dict(current)  # 以当前池为基础，只更新目标板块
    all_stocks_raw = {}  # code → stock dict，用于高股息筛选

    for sector in target_sectors:
        if sector not in mapping:
            logger.warning("板块 '%s' 不在映射配置中，跳过", sector)
            continue

        cfg = mapping[sector]
        bk_codes = cfg.get("bk_codes", [])

        if cfg.get("filter") == "dividend":
            # 高股息板块延迟处理
            continue

        if not bk_codes:
            logger.warning("板块 '%s' 无 BK 代码，跳过", sector)
            continue

        logger.info("获取 %s (%s)...", sector, ", ".join(bk_codes))
        stocks = fetch_multiple_boards(bk_codes)
        logger.info("%s: %d 只原始", sector, len(stocks))

        if stocks:
            pool = build_sector_pool(stocks, top_n, sort_by)
            new_pool[sector] = pool
        elif sector in current:
            new_pool[sector] = current[sector]
            logger.warning("API 失败，保留现有 %d 只", len(current[sector]))
        elif sector in default_pool:
            new_pool[sector] = default_pool[sector][:top_n]
            logger.warning("API 失败，使用预置默认 %d 只", len(new_pool[sector]))

        # 保存原始数据供高股息筛选
        for s in stocks:
            all_stocks_raw[s["code"]] = s

        time.sleep(0.3)

    # 高股息板块
    if "高股息" in target_sectors and "高股息" in mapping:
        if all_stocks_raw:
            dividend_pool = build_dividend_pool(new_pool, all_stocks_raw)
            new_pool["高股息"] = dividend_pool
            logger.info(
                "高股息: 从 %d 只中筛选 %d 只", len(all_stocks_raw), len(dividend_pool)
            )

    # 对比
    if show_diff:
        _log_diff(current, new_pool)

    # 写入（仅当新池与当前池有差异时）
    if not dry_run and new_pool and new_pool != current:
        output = {
            "_meta": {
                "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "eastmoney_push2",
                "total_sectors": len(new_pool),
                "total_stocks": sum(len(v) for v in new_pool.values()),
            }
        }
        output.update(new_pool)
        with open(POOL_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("已写入 %s (%d 只)", POOL_FILE, output["_meta"]["total_stocks"])
    elif dry_run:
        logger.info("dry-run 模式，未写入")
    elif not dry_run and new_pool == current:
        logger.info("股票池无变化，跳过写入")

    return new_pool


# ---------- 默认数据初始化 ----------


def init_from_default(top_n: int = 20, dry_run: bool = False) -> dict:
    """从预置默认数据初始化股票池（不访问 API）。"""
    default_pool = load_default_pool()
    if not default_pool:
        logger.error("预置默认数据不可用")
        return {}

    new_pool = {}
    for sector, codes in default_pool.items():
        new_pool[sector] = codes[:top_n]
        logger.info("%s: %d 只（预置数据）", sector, len(new_pool[sector]))

    if not dry_run and new_pool:
        output = {
            "_meta": {
                "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "preset_default",
                "total_sectors": len(new_pool),
                "total_stocks": sum(len(v) for v in new_pool.values()),
            }
        }
        output.update(new_pool)
        with open(POOL_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        logger.info("已写入 %s (%d 只)", POOL_FILE, output["_meta"]["total_stocks"])
    elif dry_run:
        logger.info("dry-run 模式，未写入")

    return new_pool


def main():
    """CLI 入口：刷新股票池（委托 refresh_pool 业务逻辑）。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse

    parser = argparse.ArgumentParser(description="刷新股票池")
    parser.add_argument("--top", type=int, default=20, help="每板块取 Top N")
    parser.add_argument("--sort", default="amount", help="排序字段")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--diff", action="store_true", help="显示变更对比")
    args = parser.parse_args()

    refresh_pool(
        top_n=args.top,
        sort_by=args.sort,
        dry_run=args.dry_run,
        show_diff=args.diff,
    )


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()

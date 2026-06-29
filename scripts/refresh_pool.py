#!/usr/bin/env python3
"""
股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股。

用法:
  python3 scripts/refresh_pool.py                     # 刷新全部板块
  python3 scripts/refresh_pool.py --sector 机器人      # 只刷新指定板块
  python3 scripts/refresh_pool.py --top 30             # 每板块取 Top 30
  python3 scripts/refresh_pool.py --sort cap           # 按市值排序（默认 amount）
  python3 scripts/refresh_pool.py --dry-run            # 只打印不写入
  python3 scripts/refresh_pool.py --diff               # 对比当前池显示变更

数据源: 东财 push2.eastmoney.com 板块成分股 API
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# 复用 common.py 的 HTTP 和编码工具
sys.path.insert(0, os.path.dirname(__file__))
from common import http_get_cached, board_type

# ---------- 常量 ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
MAPPING_FILE = os.path.join(DATA_DIR, "sector_mapping.json")
POOL_FILE = os.path.join(DATA_DIR, "sector_stocks.json")
ALL_STOCKS_FILE = os.path.join(DATA_DIR, "all_stocks.json")

API_BASE = "https://push2.eastmoney.com/api/qt/clist/get"
API_TOKEN = os.environ.get("EASTMONEY_API_TOKEN", "")
FIELDS = "f12,f14,f2,f3,f6,f8,f9,f20"  # code,name,price,chg%,amount,turnover,pe,cap

# 预置默认股票池文件
DEFAULT_POOL_FILE = os.path.join(DATA_DIR, "sector_stocks.default.json")

# 硬过滤阈值（v1.7.1 起从 strategies.filters 导入，保留本地 FILTER 别名向后兼容）
from strategies.filters import PRE_SCREEN_FILTER as FILTER  # noqa: F401

# ---------- 代码分类工具 ----------


def _classify_board(code6: str) -> str:
    """根据 6 位代码推断上市板块（与 common.board_type 输出一致）。"""
    if code6.startswith(("43", "83", "87", "88", "92")):
        return "北交所"
    if code6.startswith("68"):
        return "科创板"
    if code6.startswith("30"):
        return "创业板"
    if code6.startswith(("60", "00")):
        return "主板"
    return "其他"


def _infer_exchange(code6: str) -> str:
    """根据 6 位代码推断交易所前缀。"""
    if code6.startswith(("60", "68")):
        return "sh"
    if code6.startswith(("00", "30", "15", "16", "18")):
        return "sz"
    if code6.startswith(("43", "83", "87", "88", "92")):
        return "bj"
    return "sz"


# ---------- API 调用 ----------


def fetch_board_stocks(bk_code: str, max_retries: int = 2) -> list[dict]:
    """获取板块成分股，返回 [{code, name, price, change_pct, amount, turnover, pe, cap}]"""
    # ut 参数可选，有 token 时使用，无 token 时也能访问部分数据
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
                full_code = f"{_infer_exchange(code6)}{code6}"
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
            print(f"  ⚠ API 请求失败 ({bk_code}): {e}", file=sys.stderr)
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

# 东方财富选股器 API
XUANGU_API_BASE = "https://data.eastmoney.com/dataapi/xuangu/list"
XUANGU_FIELDS = "SECUCODE,SECURITY_CODE,SECURITY_NAME_ABBR,MARKET"


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
            print(
                f"  ⚠ 选股器 API 请求失败 (第 {page} 页, 重试 {max_retries} 次后放弃): {e}",
                file=sys.stderr,
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
    print("📡 尝试使用 push2 API 获取全市场股票...", flush=True)
    try:
        _fetch_push2_market(boards)
        total = sum(len(v) for v in boards.values())
        if total > 1000:
            print(f"✅ push2 API 成功获取 {total} 只股票", flush=True)
            return boards
        else:
            print(f"⚠ push2 API 数据不足 ({total} 只)，切换到选股器 API", flush=True)
    except Exception as e:
        print(f"⚠ push2 API 失败: {e}，切换到选股器 API", flush=True)

    # 方案 2: 使用选股器 API（使用 SECURITY_TYPE_CODE 过滤条件）
    print("📡 使用选股器 API 获取全市场股票...", flush=True)

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
        print(f"  第 {page} 页: {len(stocks)} 只 (总计: {total})", flush=True)

        if len(all_stocks) >= total:
            break

        page += 1
        time.sleep(0.3)

    # 按板块分类
    for s in all_stocks:
        code = str(s.get("SECURITY_CODE", ""))
        name = str(s.get("SECURITY_NAME_ABBR", ""))
        if not code or len(code) != 6:
            continue
        # 排除 ST 股
        if "ST" in name.upper():
            continue
        board = _classify_board(code)
        if board in boards:
            exchange = _infer_exchange(code)
            full_code = f"{exchange}{code}"
            boards[board].append(full_code)

    return boards


def _fetch_push2_market(boards: dict[str, list[str]]) -> None:
    """使用 push2 API 获取全市场股票（原始方案）。"""
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
            board = _classify_board(code6)
            if board == "其他":
                continue
            exchange = _infer_exchange(code6)
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
    print(f"\n✅ 已写入 {ALL_STOCKS_FILE} ({total} 只)")
    for board, codes in stocks_by_board.items():
        print(f"  {board}: {len(codes)} 只")


# ---------- 过滤 ----------


def is_st(name: str) -> bool:
    return "ST" in name.upper()


def passes_filter(stock: dict) -> tuple[bool, str]:
    """硬过滤，返回 (通过, 原因)"""
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
            print(f"⚠ 板块 '{sector}' 不在映射配置中，跳过", file=sys.stderr)
            continue

        cfg = mapping[sector]
        bk_codes = cfg.get("bk_codes", [])

        if cfg.get("filter") == "dividend":
            # 高股息板块延迟处理
            continue

        if not bk_codes:
            print(f"⚠ 板块 '{sector}' 无 BK 代码，跳过", file=sys.stderr)
            continue

        print(f"📡 获取 {sector} ({', '.join(bk_codes)})...", end=" ", flush=True)
        stocks = fetch_multiple_boards(bk_codes)
        print(f"{len(stocks)} 只原始")

        if stocks:
            pool = build_sector_pool(stocks, top_n, sort_by)
            new_pool[sector] = pool
        elif sector in current:
            new_pool[sector] = current[sector]
            print(f"  ⚠ API 失败，保留现有 {len(current[sector])} 只")
        elif sector in default_pool:
            new_pool[sector] = default_pool[sector][:top_n]
            print(f"  ⚠ API 失败，使用预置默认 {len(new_pool[sector])} 只")

        # 保存原始数据供高股息筛选
        for s in stocks:
            all_stocks_raw[s["code"]] = s

        time.sleep(0.3)

    # 高股息板块
    if "高股息" in target_sectors and "高股息" in mapping:
        if all_stocks_raw:
            dividend_pool = build_dividend_pool(new_pool, all_stocks_raw)
            new_pool["高股息"] = dividend_pool
            print(
                f"📡 高股息: 从 {len(all_stocks_raw)} 只中筛选 {len(dividend_pool)} 只"
            )

    # 对比
    if show_diff:
        print_diff(current, new_pool)

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
        print(f"\n✅ 已写入 {POOL_FILE} ({output['_meta']['total_stocks']} 只)")
    elif dry_run:
        print("\n📋 dry-run 模式，未写入")
    elif not dry_run and new_pool == current:
        print("\n📋 股票池无变化，跳过写入")

    return new_pool


def print_diff(current: dict, new_pool: dict):
    """打印新旧池对比"""
    print("\n" + "=" * 60)
    print("📊 股票池变更对比")
    print("=" * 60)

    all_sectors = sorted(set(list(current.keys()) + list(new_pool.keys())))

    for sector in all_sectors:
        old = set(current.get(sector, []))
        new = set(new_pool.get(sector, []))
        added = new - old
        removed = old - new
        if not added and not removed:
            continue
        print(f"\n【{sector}】")
        if added:
            print(f"  + 新增 {len(added)}: {', '.join(sorted(added))}")
        if removed:
            print(f"  - 移除 {len(removed)}: {', '.join(sorted(removed))}")

    total_old = sum(len(v) for v in current.values())
    total_new = sum(len(v) for v in new_pool.values())
    print(f"\n总计: {total_old} → {total_new} ({total_new - total_old:+d})")


# ---------- 默认数据初始化 ----------


def init_from_default(top_n: int = 20, dry_run: bool = False) -> dict:
    """从预置默认数据初始化股票池（不访问 API）。"""
    default_pool = load_default_pool()
    if not default_pool:
        print("❌ 预置默认数据不可用", file=sys.stderr)
        return {}

    new_pool = {}
    for sector, codes in default_pool.items():
        new_pool[sector] = codes[:top_n]
        print(f"📋 {sector}: {len(new_pool[sector])} 只（预置数据）")

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
        print(f"\n✅ 已写入 {POOL_FILE} ({output['_meta']['total_stocks']} 只)")
    elif dry_run:
        print("\n📋 dry-run 模式，未写入")

    return new_pool


# ---------- CLI ----------


def main():
    from common.cache import cleanup_tmp_files

    cleanup_tmp_files()

    parser = argparse.ArgumentParser(description="股票池自动刷新")
    parser.add_argument("--sector", "-s", nargs="+", help="只刷新指定板块")
    parser.add_argument(
        "--top", "-n", type=int, default=20, help="每板块取 Top N（默认 20）"
    )
    parser.add_argument(
        "--sort",
        choices=["amount", "cap", "pe", "turnover"],
        default="amount",
        help="排序方式（默认 amount 成交额）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--diff", action="store_true", help="对比当前池显示变更")
    parser.add_argument(
        "--default", action="store_true", help="使用预置默认数据初始化（不访问 API）"
    )
    parser.add_argument(
        "--full-market",
        action="store_true",
        help="拉取全市场 A 股列表（约 5000 只），保存到 all_stocks.json",
    )
    parser.add_argument(
        "-j", "--json", action="store_true", help="输出机器可读 JSON 摘要"
    )
    args = parser.parse_args()

    if args.full_market:
        ret = fetch_all_market_stocks()
        if not args.dry_run:
            save_all_market_stocks(ret)
        result = {"mode": "full_market", "count": len(ret) if ret else 0}
    elif args.default:
        ret = init_from_default(top_n=args.top, dry_run=args.dry_run)
        result = {"mode": "default", "top_n": args.top}
    else:
        ret = refresh_pool(
            sectors=args.sector,
            top_n=args.top,
            sort_by=args.sort,
            dry_run=args.dry_run,
            show_diff=args.diff,
        )
        result = {
            "mode": "refresh",
            "sectors": args.sector or "all",
            "top_n": args.top,
            "sort_by": args.sort or "default",
        }

    if args.json:
        import json as _json

        print(_json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

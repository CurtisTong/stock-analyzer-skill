#!/usr/bin/env python3
"""
股票池自动刷新脚本 — 从东财 push2 API 拉取板块成分股。

用法:
  python3 scripts/refresh_pool.py                     # 刷新全部板块
  python3 scripts/refresh_pool.py --sector 机器人      # 只刷新指定板块
  python3 scripts/refresh_pool.py --top 20             # 每板块取 Top 20
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
from common import http_get_cached, normalize_quote_code, board_type

# ---------- 常量 ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
MAPPING_FILE = os.path.join(PROJECT_ROOT, "data", "sector_mapping.json")
POOL_FILE = os.path.join(PROJECT_ROOT, "data", "sector_stocks.json")

API_BASE = "https://push2.eastmoney.com/api/qt/clist/get"
API_TOKEN = "bd1d9ddb04089700cf9c27f6f7426281"
FIELDS = "f12,f14,f2,f3,f6,f8,f9,f20"  # code,name,price,chg%,amount,turnover,pe,cap

# 硬过滤阈值
FILTER = {
    "min_amount": {"主板": 5000, "创业板": 3500, "科创板": 3500, "北交所": 7500},  # 万元
    "min_cap":    {"主板": 40,   "创业板": 24,   "科创板": 24,   "北交所": 16},     # 亿元
}


# ---------- API 调用 ----------

def fetch_board_stocks(bk_code: str, max_retries: int = 2) -> list[dict]:
    """获取板块成分股，返回 [{code, name, price, change_pct, amount, turnover, pe, cap}]"""
    url = (
        f"{API_BASE}?pn=1&pz=500&np=1&ut={API_TOKEN}"
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
                # 推断交易所前缀
                if code6.startswith(("6",)):
                    full_code = f"sh{code6}"
                elif code6.startswith(("0", "3")):
                    full_code = f"sz{code6}"
                elif code6.startswith(("4", "8")):
                    full_code = f"bj{code6}"
                else:
                    full_code = f"sz{code6}"
                results.append({
                    "code": full_code,
                    "name": item.get("f14", ""),
                    "price": item.get("f2"),
                    "change_pct": item.get("f3"),
                    "amount": item.get("f6"),      # 成交额（元）
                    "turnover": item.get("f8"),     # 换手率
                    "pe": item.get("f9"),           # PE(动)
                    "cap": item.get("f20"),         # 总市值（元）
                })
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


# ---------- 过滤 ----------

def is_st(name: str) -> bool:
    return "ST" in name.upper() or "*ST" in name


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


def build_sector_pool(stocks: list[dict], top_n: int = 15, sort_by: str = "amount") -> list[str]:
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

def build_dividend_pool(all_pools: dict[str, list[str]], all_stocks: dict[str, dict]) -> list[str]:
    """从所有板块中筛选 PE<20 且 ROE>8% 的标的"""
    candidates = []
    seen = set()
    for sector, codes in all_pools.items():
        if sector == "高股息":
            continue
        for code in codes:
            if code in seen:
                continue
            seen.add(code)
            s = all_stocks.get(code, {})
            pe = s.get("pe")
            # ROE 需要额外查询，这里用 PE 作为第一轮筛选
            if pe is not None and 0 < pe < 20:
                candidates.append(s)
    # 按成交额排序取 Top 15
    sorted_c = sort_stocks(candidates, "amount")
    return [s["code"] for s in sorted_c[:15]]


# ---------- 主流程 ----------

def load_mapping() -> dict:
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_current_pool() -> dict:
    if not os.path.exists(POOL_FILE):
        return {}
    with open(POOL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def refresh_pool(sectors: list[str] | None = None, top_n: int = 15,
                 sort_by: str = "amount", dry_run: bool = False,
                 show_diff: bool = False) -> dict:
    """刷新股票池，返回新池"""
    mapping = load_mapping()
    current = load_current_pool()

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

        # 保存原始数据供高股息筛选
        for s in stocks:
            all_stocks_raw[s["code"]] = s

        time.sleep(0.3)

    # 高股息板块
    if "高股息" in target_sectors and "高股息" in mapping:
        if all_stocks_raw:
            dividend_pool = build_dividend_pool(new_pool, all_stocks_raw)
            new_pool["高股息"] = dividend_pool
            print(f"📡 高股息: 从 {len(all_stocks_raw)} 只中筛选 {len(dividend_pool)} 只")

    # 对比
    if show_diff:
        print_diff(current, new_pool)

    # 写入
    if not dry_run and new_pool:
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
        print(f"\n📋 dry-run 模式，未写入")

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


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description="股票池自动刷新")
    parser.add_argument("--sector", "-s", nargs="+", help="只刷新指定板块")
    parser.add_argument("--top", "-n", type=int, default=15, help="每板块取 Top N（默认 15）")
    parser.add_argument("--sort", choices=["amount", "cap", "pe", "turnover"],
                        default="amount", help="排序方式（默认 amount 成交额）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument("--diff", action="store_true", help="对比当前池显示变更")
    args = parser.parse_args()

    refresh_pool(
        sectors=args.sector,
        top_n=args.top,
        sort_by=args.sort,
        dry_run=args.dry_run,
        show_diff=args.diff,
    )


if __name__ == "__main__":
    main()

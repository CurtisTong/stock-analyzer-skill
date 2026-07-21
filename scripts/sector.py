#!/usr/bin/env python3
"""
板块查询——根据股票代码查找所属板块及板块内标的行情。

用法:
  sector.py sh600060                   # 查找股票所属板块 + 板块内标的行情
  sector.py 新能源                      # 按板块名称查询
  sector.py sh600060 -j                # JSON 输出
  sector.py --list                     # 列出所有板块
"""

import sys
import json
import argparse
from pathlib import Path

# 确保 scripts/ 在 import 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from data import get_quote, get_finance
from common import parallel_map, normalize_finance_code

DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_sector_stocks() -> dict:
    """加载板块股票映射。"""
    path = DATA_DIR / "sector_stocks.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_sector_by_code(code: str, data: dict) -> list:
    """根据股票代码查找所属板块名称列表。"""
    code_lower = code.lower()
    sectors = []
    for name, stocks in data.items():
        if name == "_meta":
            continue
        if isinstance(stocks, list) and code_lower in [s.lower() for s in stocks]:
            sectors.append(name)
    return sectors


def get_sector_stocks(sector_name: str, data: dict) -> list:
    """获取板块内标的代码列表。"""
    for name, stocks in data.items():
        if name == sector_name and isinstance(stocks, list):
            return stocks
    # 模糊匹配
    for name, stocks in data.items():
        if name == "_meta":
            continue
        if sector_name in name and isinstance(stocks, list):
            return stocks
    return []


def fetch_sector_quotes(codes: list) -> list:
    """批量并行获取板块内标的行情摘要。"""
    raw = parallel_map(get_quote, codes, timeout=30)
    results = []
    for code, q in raw.items():
        if q and q.has_basic_data():
            results.append(
                {
                    "code": code,
                    "name": q.name,
                    "price": q.price,
                    "change_pct": q.change_pct,
                    "pe": q.pe,
                    "pb": q.pb,
                    "turnover": q.turnover,
                    "total_cap": q.total_cap,
                }
            )
    return results


def _fetch_one_finance(code: str) -> tuple:
    """获取单只股票最新财务数据，返回 (code, fin_dict) 或 (code, None)。"""
    fin_code = normalize_finance_code(code)
    records = get_finance(fin_code)
    if records:
        latest = records[0]
        return code, {
            "eps": latest.eps,
            "roe": latest.roe,
            "revenue_yoy": latest.revenue_yoy,
            "net_profit_yoy": latest.net_profit_yoy,
            "gross_margin": latest.gross_margin,
            "debt_ratio": latest.debt_ratio,
        }
    return code, None


def fetch_sector_finance(codes: list) -> dict:
    """并行获取板块内标的最新财务数据。

    parallel_map 在任务异常时返回 None（而非 (code, None)），
    需先过滤 None 再解包，否则会抛 TypeError: cannot unpack non-iterable NoneType。
    """
    raw = parallel_map(_fetch_one_finance, codes, timeout=30)
    return {
        code: fin
        for code, fin in (v for v in raw.values() if v is not None)
        if fin is not None
    }


def print_table(quotes: list, finance: dict):
    """表格输出板块标的行情+财务。"""
    print(
        f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'PB':>6} "
        f"{'ROE%':>7} {'净利增%':>8} {'换手%':>6}"
    )
    print("-" * 85)

    # WP2: None 表示"未披露"——格式化为 "-"
    def _f(v, spec):
        return format(v, spec) if v is not None else "-"

    for q in quotes:
        fin = finance.get(q["code"], {})
        roe = fin.get("roe")
        np_yoy = fin.get("net_profit_yoy")
        print(
            f"{q['code']:<10} {q['name']:<10} {q['price']:>8.2f} {q['change_pct']:>7.2f} "
            f"{q['pe']:>7.1f} {q['pb']:>6.2f} {_f(roe, '>7.2f')} "
            f"{_f(np_yoy, '>8.2f')} {q['turnover']:>6.2f}"
        )


def main():
    parser = argparse.ArgumentParser(description="板块查询")
    parser.add_argument("query", nargs="?", help="股票代码或板块名称")
    parser.add_argument("-j", "--json", action="store_true", help="JSON 输出")
    parser.add_argument("--list", action="store_true", help="列出所有板块")
    args = parser.parse_args()

    data = _load_sector_stocks()
    if not data:
        print(
            "错误: sector_stocks.json 不存在，请先运行 python3 scripts/init_pool.py",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.list:
        sectors = [k for k in data if k != "_meta"]
        if args.json:
            print(json.dumps(sectors, ensure_ascii=False))
        else:
            print("可用板块:", ", ".join(sectors))
        return

    if not args.query:
        parser.print_help()
        return

    query = args.query

    # 判断是代码还是板块名
    is_code = query.lower().startswith(("sh", "sz")) or query.isdigit()

    if is_code:
        # 按代码查板块
        code = query.lower() if query.lower().startswith(("sh", "sz")) else f"sh{query}"
        sectors = find_sector_by_code(code, data)
        if not sectors:
            print(f"未找到 {code} 所属板块（未在预设股票池中）", file=sys.stderr)
            sys.exit(1)

        # 收集所有板块标的去重，一次性拉取
        sector_codes = {name: get_sector_stocks(name, data) for name in sectors}
        all_codes = list({c for codes in sector_codes.values() for c in codes})
        all_quotes = {q["code"]: q for q in fetch_sector_quotes(all_codes)}
        all_finance = fetch_sector_finance(all_codes)

        result = {
            "code": code,
            "sectors": [],
        }

        for sector_name in sectors:
            codes = sector_codes[sector_name]
            quotes = [all_quotes[c] for c in codes if c in all_quotes]
            finance = {c: all_finance[c] for c in codes if c in all_finance}

            sector_info = {
                "name": sector_name,
                "stocks": quotes,
                "finance": finance,
            }
            result["sectors"].append(sector_info)

            if not args.json:
                print(f"\n📊 板块: {sector_name}（{len(codes)} 只标的）")
                print_table(quotes, finance)

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        # 按板块名查
        codes = get_sector_stocks(query, data)
        if not codes:
            print(f"未找到板块: {query}", file=sys.stderr)
            print(
                f"可用板块: {', '.join(k for k in data if k != '_meta')}",
                file=sys.stderr,
            )
            sys.exit(1)

        quotes = fetch_sector_quotes(codes)
        finance = fetch_sector_finance(codes)

        result = {
            "sector": query,
            "count": len(codes),
            "stocks": quotes,
            "finance": finance,
        }

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"\n📊 板块: {query}（{len(codes)} 只标的）")
            print_table(quotes, finance)


if __name__ == "__main__":
    main()

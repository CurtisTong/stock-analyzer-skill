#!/usr/bin/env python3
"""
选股 CLI (API 层)。

重构自 scripts/screener.py，将用户交互逻辑与业务逻辑分离。
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import DATA_DIR, to_float
from data import get_quote, get_quotes
from common.exceptions import ValidationError, format_error


def load_universe(sector=None, codes=None):
    """加载股票池。"""
    import json
    
    if codes:
        return sorted({normalize_quote_code(c) for c in codes})
    
    path = DATA_DIR / "sector_stocks.json"
    sectors = json.loads(path.read_text(encoding="utf-8"))
    
    if sector:
        matched = []
        for name, items in sectors.items():
            if sector.lower() in name.lower():
                matched.extend(items)
        if not matched:
            raise SystemExit(f"未在内置标的库找到板块: {sector}")
        return sorted({normalize_quote_code(c) for c in matched})
    
    all_codes = []
    for items in sectors.values():
        all_codes.extend(items)
    return sorted({normalize_quote_code(c) for c in all_codes})


def normalize_quote_code(code: str) -> str:
    """标准化股票代码。"""
    c = code.strip().lower()
    if c.startswith(("sh", "sz", "bj")):
        return c
    
    # 纯数字
    digits = "".join(filter(str.isdigit, c))
    if len(digits) != 6:
        raise ValidationError("code", code, "必须是6位数字")
    
    if digits.startswith(("60", "68", "51", "56", "58")):
        return f"sh{digits}"
    return f"sz{digits}"


def normalize_finance_code(code: str) -> str:
    """标准化财务代码。"""
    q = normalize_quote_code(code)
    return q[:2].upper() + q[2:] if len(q) >= 8 else q.upper()


def render(rows, strategy, top):
    """渲染结果。"""
    from strategies import STRATEGIES
    
    accepted = [r for r in rows if not r.get("rejected")]
    accepted.sort(key=lambda r: r.get("score", 0), reverse=True)
    
    print(f"策略: {STRATEGIES[strategy]['label']} ({strategy})")
    print(f"入选: {len(accepted)} | 剔除: {len(rows) - len(accepted)}")
    print()
    
    header = "排名 | 代码 | 名称 | 行业 | 板块 | 总分 | 质量 | 估值 | 动量 | 流动性 | PE | ROE | RSI | 20日% | 趋势"
    print(header)
    print("-" * len(header))
    
    for idx, r in enumerate(accepted[:top], 1):
        print(
            f"{idx:>2} | {r['code']:<8} | {r['name']:<8} | {r.get('industry', '默认'):<4} | "
            f"{r.get('board', '主板'):<4} | {r.get('score', 0):>5} | {r.get('quality', 0):>5} | "
            f"{r.get('valuation', 0):>5} | {r.get('momentum', 0):>5} | {r.get('liquidity', 0):>6} | "
            f"{r.get('pe', '-'):>6} | {r.get('roe', '-'):>6} | {r.get('rsi', 50):>4} | "
            f"{r.get('ret20', 0):>5} | {r.get('trend', '震荡')}"
        )


def main():
    """主入口。"""
    parser = argparse.ArgumentParser(description="A 股多因子选股器")
    parser.add_argument("--strategy", default="balanced")
    parser.add_argument("--sector", help="板块名称")
    parser.add_argument("--codes", help="逗号分隔代码列表")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--min-amount", type=float, default=5000)
    parser.add_argument("--min-cap", type=float, default=40)
    parser.add_argument("--exclude-loss", action="store_true")
    parser.add_argument("-j", "--json", action="store_true")
    args = parser.parse_args()
    
    try:
        # 加载股票池
        codes = load_universe(args.sector, args.codes.split(",") if args.codes else None)
        
        # 获取行情
        quotes = get_quotes(codes)
        quote_dict = {q.code: q.to_dict() for q in quotes}
        
        # TODO: 调用业务层筛选
        # 暂时简单返回行情数据
        rows = []
        for code in codes[:args.top]:
            if code in quote_dict:
                q = quote_dict[code]
                rows.append({
                    "code": code,
                    "name": q.get("name", ""),
                    "score": 0,
                    "quality": 0,
                    "valuation": 0,
                    "momentum": 0,
                    "liquidity": 0,
                    "pe": q.get("pe", "-"),
                    "roe": "-",
                    "rsi": 50,
                    "ret20": 0,
                    "trend": "震荡",
                    "industry": "默认",
                    "board": "主板",
                })
        
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            render(rows, args.strategy, args.top)
            
    except ValidationError as e:
        print(f"❌ 输入错误: {e.message}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 系统错误: {format_error(e)}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

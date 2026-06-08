#!/usr/bin/env python3
"""
行情查询 CLI (API 层)。

重构自 scripts/quote.py，将用户交互逻辑与业务逻辑分离。
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (
    split_codes, 
    batchify, 
    normalize_quote_code, 
    parallel_map, 
    err,
    DataError,
    format_error,
)
from common.validators import validate_code
from data import get_quote, get_quotes
from common.exceptions import ValidationError


def fetch_batch(codes: list, use_cache: bool = True) -> list:
    """批量获取行情，返回 dict 列表。"""
    quotes = get_quotes(codes, use_cache=use_cache)
    return [q.to_dict() for q in quotes]


def render_table(records: list):
    """渲染表格输出。"""
    if not records:
        print("(无数据)")
        return
    print(f"{'代码':<10} {'名称':<10} {'现价':>8} {'涨跌%':>7} {'PE':>7} {'换手%':>6} {'市值亿':>8}")
    print("-" * 60)
    for r in records:
        print(f"{r['code']:<10} {r['name']:<10} {r['price']:>8} {r['change_pct']:>7} {r['pe']:>7} {r['turnover']:>6} {r['total_cap']:>8}")


def main():
    """主入口。"""
    if len(sys.argv) < 2:
        err("用法: python -m api.quote_cli <代码|@文件> [-j] [--sources]")
    
    args = sys.argv[1:]
    
    if "--sources" in args:
        from fetchers import get_quote_fetchers
        fetchers = get_quote_fetchers()
        print("可用行情数据源:")
        for f in fetchers:
            print(f"  - {f.name} (优先级 {f.priority})")
        return
    
    json_mode = "-j" in args
    args = [a for a in args if a not in ("-j", "--sources")]
    
    try:
        # 验证输入
        raw_codes = split_codes(args[0])
        codes = []
        for c in raw_codes:
            if not validate_code(c):
                raise ValidationError("code", c, "格式无效")
            codes.append(normalize_quote_code(c))
        
        if not codes:
            err("未提供代码")
        
        # 分批查询 (腾讯单次 ≤15)
        batches = list(batchify(codes, 15))
        if len(batches) > 1:
            results = parallel_map(
                lambda b: fetch_batch(b, use_cache=True), 
                batches, 
                max_workers=4, 
                timeout=30
            )
            all_records = []
            for batch in batches:
                all_records.extend(results.get(batch, []))
        else:
            all_records = fetch_batch(batches[0])
        
        if json_mode:
            print(json.dumps(all_records, ensure_ascii=False, indent=2))
        else:
            render_table(all_records)
            
    except ValidationError as e:
        print(f"❌ 输入错误: {e.message}", file=sys.stderr)
        sys.exit(1)
    except DataError as e:
        print(f"❌ 数据错误: {format_error(e)}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 系统错误: {format_error(e)}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

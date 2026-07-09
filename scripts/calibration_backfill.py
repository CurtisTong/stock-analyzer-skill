#!/usr/bin/env python3
"""
校准数据回填与管理 CLI（第六轮审查 v2.4.3 新增）。

提供预测状态查看、批量验证、历史预测导入功能。
不做合成回填--历史财务/市场特征无法还原，合成预测不可信，从今天起累积。

用法:
  # 查看预测状态（pending/verified/expert 准确率）
  python3 scripts/calibration_backfill.py status

  # 批量验证到期预测（使用真实价格回调）
  python3 scripts/calibration_backfill.py verify --days 30

  # 从 JSON 文件导入历史预测记录
  python3 scripts/calibration_backfill.py import --file predictions.json

  # 导入文件格式（每条记录）:
  # [{"stock": "sh600989", "date": "2026-06-01", "direction": "看多",
  #   "composite_score": 65.0,
  #   "expert_scores": {"value_institution": 72, "lynch": 65, ...}}, ...]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.calibration import (
    verify_predictions,
    get_calibration,
    get_pending_predictions,
    get_kline_return,
    record_prediction,
)


def cmd_status(args):
    """查看预测状态与专家准确率。"""
    pending = get_pending_predictions()
    cal = get_calibration()

    print("=" * 60)
    print("校准数据状态")
    print("=" * 60)
    print(f"\n待验证预测: {len(pending)} 条")
    for p in pending[:10]:
        print(
            f"  {p['stock']} ({p['date']}) -> {p['direction']} "
            f"| 验证日期: {p['verify_after']}"
        )
    if len(pending) > 10:
        print(f"  ... 共 {len(pending)} 条")

    print("\n专家准确率:")
    print(f"  {'专家':<25} {'事件数':>6} {'正确':>6} {'准确率':>8} {'更新日期':<12}")
    print(f"  {'-' * 25} {'-' * 6} {'-' * 6} {'-' * 8} {'-' * 12}")
    for name, rec in sorted(cal.items()):
        events = rec.get("events", 0)
        correct = rec.get("correct", 0)
        rate = f"{correct / events * 100:.0f}%" if events > 0 else "N/A"
        updated = rec.get("last_updated", "-") or "-"
        print(f"  {name:<25} {events:>6} {correct:>6} {rate:>8} {updated:<12}")


def cmd_verify(args):
    """批量验证到期预测。"""
    price_fn = None if args.no_price else get_kline_return
    result = verify_predictions(
        days=args.days, get_price_fn=price_fn, mark_only=args.no_price
    )
    print(f"验证完成: {result['verified']} 条记录")
    print(f"更新专家校准: {result['updated_experts']} 位")
    if result.get("skipped"):
        print(f"跳过（无价格数据）: {result['skipped']} 条")

    if result["details"] and args.verbose:
        print("\n详情:")
        for d in result["details"]:
            if d.get("skipped"):
                print(f"  ⏭ {d['stock']} ({d['direction']}) -> 跳过（无价格）")
                continue
            status = (
                "✓" if d.get("correct") else ("✗" if d.get("correct") is False else "?")
            )
            ret = (
                f"{d['actual_return']:+.1f}%"
                if d["actual_return"] is not None
                else "N/A"
            )
            print(f"  {status} {d['stock']} ({d['direction']}) -> {ret}")


def cmd_import(args):
    """从 JSON 文件导入历史预测记录。"""
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(file_path, encoding="utf-8") as f:
            records = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误: JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(records, list):
        print("错误: 文件内容应为 JSON 数组", file=sys.stderr)
        sys.exit(1)

    imported = 0
    skipped = 0
    for rec in records:
        stock = rec.get("stock")
        direction = rec.get("direction", "中性")
        scores = rec.get("expert_scores", {})
        composite = rec.get("composite_score", 0.0)
        date = rec.get("date")

        if not stock or not scores:
            skipped += 1
            continue

        try:
            pred_id = record_prediction(
                stock_code=stock,
                expert_scores=scores,
                direction=direction,
                composite_score=float(composite),
                timestamp=date,
            )
            imported += 1
            print(f"  ✓ {pred_id} ({stock} -> {direction})")
        except Exception as e:
            print(f"  ✗ {stock}: {e}", file=sys.stderr)
            skipped += 1

    print(f"\n导入完成: {imported} 条记录, 跳过 {skipped} 条")


def main():
    parser = argparse.ArgumentParser(description="校准数据回填与管理")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # status
    sub.add_parser("status", help="查看预测状态与专家准确率")

    # verify
    p_verify = sub.add_parser("verify", help="批量验证到期预测")
    p_verify.add_argument("--days", type=int, default=30, help="验证窗口天数 (默认30)")
    p_verify.add_argument(
        "--no-price", action="store_true", help="仅标记到期不获取价格"
    )
    p_verify.add_argument("-v", "--verbose", action="store_true", help="输出详情")

    # import
    p_import = sub.add_parser("import", help="从 JSON 文件导入历史预测")
    p_import.add_argument("--file", required=True, help="JSON 文件路径")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "status": cmd_status,
        "verify": cmd_verify,
        "import": cmd_import,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()

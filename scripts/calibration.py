#!/usr/bin/env python3
"""
专家校准数据管理 CLI。

用法:
  # 记录 debate 预测
  python3 scripts/calibration.py record --stock sh600989 --direction 看多 \
    --scores '{"buffett":72,"lynch":65,"soros":55,"duan_yongping":68,
               "xu_xiang":45,"zhao_laoge":50,"chaogu_yangjia":40,"zuoshou_xinyi":55}'

  # 验证到期预测（默认30天窗口）
  python3 scripts/calibration.py verify --days 30

  # 查看校准报告
  python3 scripts/calibration.py report

  # 查看待验证预测
  python3 scripts/calibration.py pending
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.calibration import (
    record_prediction,
    verify_predictions,
    get_calibration_report,
    get_pending_predictions,
    compute_calibration_factor,
)


def cmd_record(args):
    """记录一次 debate 预测。"""
    try:
        scores = json.loads(args.scores)
    except json.JSONDecodeError:
        print(f"错误: --scores 不是有效的 JSON: {args.scores}", file=sys.stderr)
        sys.exit(1)

    pred_id = record_prediction(
        stock_code=args.stock,
        expert_scores=scores,
        direction=args.direction,
        composite_score=args.composite or 0.0,
        verify_days=args.verify_days,
    )
    print(f"已记录预测: {pred_id}")
    print(f"股票: {args.stock} | 方向: {args.direction}")
    print(f"验证日期: {args.verify_days} 天后")


def cmd_verify(args):
    """验证到期的历史预测。"""
    result = verify_predictions(days=args.days)
    print(f"验证完成: {result['verified']} 条记录")
    print(f"更新专家校准: {result['updated_experts']} 位")

    if result["details"]:
        print("\n详情:")
        for d in result["details"]:
            status = "✓" if d.get("correct") else ("✗" if d.get("correct") is False else "?")
            ret = f"{d['actual_return']:+.1f}%" if d["actual_return"] is not None else "N/A"
            print(f"  {status} {d['stock']} ({d['direction']}) → {ret}")


def cmd_report(args):
    """查看校准报告。"""
    report = get_calibration_report()
    factor = compute_calibration_factor()
    if args.json:
        import json as _json
        print(_json.dumps({
            "report": report,
            "calibration_factor": round(factor, 4),
        }, ensure_ascii=False, indent=2))
        return
    print(report)
    print(f"\n校准因子: {factor:+.4f}")


def cmd_pending(args):
    """查看待验证预测。"""
    pending = get_pending_predictions()
    if args.json:
        import json as _json
        print(_json.dumps({
            "count": len(pending),
            "items": pending,
        }, ensure_ascii=False, indent=2))
        return
    if not pending:
        print("无待验证预测")
        return

    print(f"待验证预测: {len(pending)} 条")
    for p in pending:
        print(
            f"  {p['stock']} ({p['date']}) → {p['direction']} "
            f"| 验证日期: {p['verify_after']}"
        )


def main():
    parser = argparse.ArgumentParser(description="专家校准数据管理")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # record
    p_record = sub.add_parser("record", help="记录 debate 预测")
    p_record.add_argument("--stock", required=True, help="股票代码 (如 sh600989)")
    p_record.add_argument("--direction", required=True,
                          help="预测方向 (强烈看多/看多/中性/看空/强烈看空)")
    p_record.add_argument("--scores", required=True,
                          help='专家评分 JSON (如 \'{"buffett":72,...}\')')
    p_record.add_argument("--composite", type=float, default=0.0,
                          help="调整后综合分")
    p_record.add_argument("--verify-days", type=int, default=30,
                          help="验证窗口天数 (默认30)")

    # verify
    p_verify = sub.add_parser("verify", help="验证到期预测")
    p_verify.add_argument("--days", type=int, default=30,
                          help="验证窗口天数 (默认30)")

    # report
    p_report = sub.add_parser("report", help="查看校准报告")
    p_report.add_argument("-j", "--json", action="store_true", help="输出 JSON")

    # pending
    p_pending = sub.add_parser("pending", help="查看待验证预测")
    p_pending.add_argument("-j", "--json", action="store_true", help="输出 JSON")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    cmds = {
        "record": cmd_record,
        "verify": cmd_verify,
        "report": cmd_report,
        "pending": cmd_pending,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()

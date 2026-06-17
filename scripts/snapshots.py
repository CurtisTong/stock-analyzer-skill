"""
选股快照系统（review#16）。

解决问题：screener 每次输出因数据源状态不同无法复现。
本模块将每次筛选结果保存为 JSON 快照，含评分、数据源时间戳、API 版本。

路径：<DATA_DIR>/snapshots/<strategy>/<YYYY-MM-DD>/<hash>.json
其中 hash 由时间戳+策略+股票池 决定（保留可复现性）
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import DATA_DIR  # noqa: E402

SNAPSHOT_VERSION = "1.0.0"


def _snapshot_path(strategy: str, date_str: str, hash_id: str) -> Path:
    """构造快照文件路径。"""
    return Path(DATA_DIR) / "snapshots" / strategy / date_str / f"{hash_id}.json"


def _make_hash(strategy: str, codes: List[str], timestamp: str) -> str:
    """生成快照唯一 hash（前 12 位）。"""
    # 用微秒精度避免连续两次保存的 hash 冲突
    payload = (
        f"{strategy}|{','.join(sorted(codes))}|{timestamp}|"
        f"{datetime.now().microsecond}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def save_snapshot(
    strategy: str,
    rows: List[Dict],
    codes: List[str],
    regime: Optional[str] = None,
    extra: Optional[Dict] = None,
) -> Path:
    """保存筛选快照到磁盘。

    Args:
        strategy: 策略名
        rows: analyze_code 输出的候选股列表
        codes: 输入股票池
        regime: 市场状态（可选）
        extra: 附加元数据（可选）

    Returns:
        保存的快照文件路径
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.isoformat(timespec="microseconds")
    hash_id = _make_hash(strategy, codes, timestamp)

    # 仅保留可序列化的字段
    snapshot_rows = []
    for r in rows:
        snapshot_rows.append(
            {
                "code": r.get("code"),
                "name": r.get("name"),
                "score": r.get("score"),
                "industry": r.get("industry"),
                "board": r.get("board"),
                "quality": r.get("quality"),
                "valuation": r.get("valuation"),
                "momentum": r.get("momentum"),
                "liquidity": r.get("liquidity"),
                "volatility": r.get("volatility"),
                "dividend": r.get("dividend"),
                "price": r.get("price"),
                "change_pct": r.get("change_pct"),
                "pe": r.get("pe"),
                "pb": r.get("pb"),
                "roe": r.get("roe"),
                "rejected": r.get("rejected", []),
            }
        )

    snapshot = {
        "version": SNAPSHOT_VERSION,
        "timestamp": timestamp,
        "date": date_str,
        "strategy": strategy,
        "regime": regime,
        "pool_size": len(codes),
        "result_size": len(snapshot_rows),
        "rows": snapshot_rows,
        "extra": extra or {},
    }

    path = _snapshot_path(strategy, date_str, hash_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def list_snapshots(strategy: Optional[str] = None, limit: int = 20) -> List[Path]:
    """列出最近的快照（按修改时间倒序）。"""
    base = Path(DATA_DIR) / "snapshots"
    if not base.exists():
        return []
    if strategy:
        pattern = f"{strategy}/**/*.json"
    else:
        pattern = "**/*.json"
    files = sorted(base.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def load_snapshot(path: Path) -> Dict:
    """读取快照 JSON。"""
    return json.loads(path.read_text(encoding="utf-8"))


def diff_snapshots(path_a: Path, path_b: Path) -> Dict:
    """对比两期快照的差异。

    Returns:
        dict: {
            "added": [新进 top N 的代码],
            "removed": [退出 top N 的代码],
            "score_changes": [{code, name, score_a, score_b, delta}],
            "metadata_diff": {...}
        }
    """
    a = load_snapshot(path_a)
    b = load_snapshot(path_b)

    a_rows = {r["code"]: r for r in a["rows"]}
    b_rows = {r["code"]: r for r in b["rows"]}

    added = [c for c in b_rows if c not in a_rows]
    removed = [c for c in a_rows if c not in b_rows]
    common = [c for c in b_rows if c in a_rows]

    score_changes = []
    for c in common:
        sa = a_rows[c].get("score", 0) or 0
        sb = b_rows[c].get("score", 0) or 0
        delta = round(sb - sa, 1)
        if abs(delta) >= 0.1:
            score_changes.append(
                {
                    "code": c,
                    "name": b_rows[c].get("name"),
                    "score_a": sa,
                    "score_b": sb,
                    "delta": delta,
                }
            )
    score_changes.sort(key=lambda x: abs(x["delta"]), reverse=True)

    return {
        "snapshot_a": str(path_a),
        "snapshot_b": str(path_b),
        "timestamp_a": a.get("timestamp"),
        "timestamp_b": b.get("timestamp"),
        "strategy_a": a.get("strategy"),
        "strategy_b": b.get("strategy"),
        "added": added,
        "removed": removed,
        "score_changes": score_changes[:30],  # top 30 显著变化
    }


def main():
    parser = argparse.ArgumentParser(description="选股快照管理")
    sub = parser.add_subparsers(dest="command")

    list_cmd = sub.add_parser("list", help="列出快照")
    list_cmd.add_argument("--strategy", help="按策略过滤")
    list_cmd.add_argument("--limit", type=int, default=10)

    diff_cmd = sub.add_parser("diff", help="对比两个快照")
    diff_cmd.add_argument("path_a")
    diff_cmd.add_argument("path_b")

    args = parser.parse_args()

    if args.command == "list":
        paths = list_snapshots(args.strategy, args.limit)
        for p in paths:
            print(p)
    elif args.command == "diff":
        diff = diff_snapshots(Path(args.path_a), Path(args.path_b))
        if args.json if hasattr(args, "json") else False:
            print(json.dumps(diff, ensure_ascii=False, indent=2))
        else:
            print(f"A: {diff['snapshot_a']} ({diff['timestamp_a']})")
            print(f"B: {diff['snapshot_b']} ({diff['timestamp_b']})")
            print(f"新增: {len(diff['added'])} 只 → {diff['added'][:10]}")
            print(f"退出: {len(diff['removed'])} 只 → {diff['removed'][:10]}")
            print(f"分数变化 top 10:")
            for c in diff["score_changes"][:10]:
                print(
                    f"  {c['code']} {c['name']}: {c['score_a']} → {c['score_b']} ({c['delta']:+})"
                )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

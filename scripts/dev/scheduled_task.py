#!/usr/bin/env python3
"""统一调度入口：launchd 心跳驱动，runner 自己判断该跑什么（P0 基础设施）。

为什么不用「每个时点一条 launchd」：macOS 睡眠/关机期间 `StartCalendarInterval`
错过的时点不会补跑，N 条就得写 N 份补跑逻辑。改成**一条 5 分钟心跳 + 由本 runner
判槽**，唤醒后下一次 tick 自然把错过的时点补上。

为什么不用 DSH 会话 schedule 当唯一触发器：它只补「最近一次」漏跑的 occurrence，
且原文写明 `Delivery can repeat after a crash`（可能重复交付），拿它当钟会漏跑和
重跑。DSH 负责「有脑子」的部分，时钟由 launchd + 本 runner 负责。

三层防护（缺一不可）：
1. `is_trading_day()` 前置——**禁止**用 `is_trading_hours()`，后者 08:45/15:05/18:30
   一律 False，会把盘前盘后任务静默跳过；
2. 幂等键 `{date}__{task}__{slot}` + `fcntl.flock` 单实例锁——锁防「同时」，
   幂等键防「先后重复」，只做一层都会被绕过；
3. 数据就绪断言：canary 抽样判整体是否就绪，未就绪 exit 2 且**不写完成标记**，
   下个 tick 重试，到 deadline 仍未开始跑才告警。

设计要求（已定稿）：
- 19:00 的告警判「**仍未开始跑**」，不判「未跑完」：18:50 就绪、19:25 结束是正常的；
- 次日 08:00 对上一交易日的槽兜底重跑，必须在 08:45 盘前任务之前。

用法::

    python3 scripts/dev/scheduled_task.py --list           # 看槽位与今日状态
    python3 scripts/dev/scheduled_task.py --tick           # launchd 每 5 分钟调用
    python3 scripts/dev/scheduled_task.py --task NAME      # 手工跑单个任务
    python3 scripts/dev/scheduled_task.py --tick --dry-run # 空跑：只打日志，不执行

退出码：0 成功/跳过；2 数据未就绪；3 有任务失败。
P0 阶段只打日志，不推微信（`--push` 预留，P1 接 `monitor/push_wechat.py`）。

⚠️ 跑批正确性**禁止**复用 `technical/core.py:stale_trading_days()` 当门槛：
它 >3 个交易日才告警，是为「提示用户」设的，1 天滞后它会放行——详见
`docs/scheduling.md`。
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from data.config import (  # noqa: E402
    holiday_table_years,
    is_holiday_table_covering,
    is_trading_day,
)

DEFAULT_STATE_DIR = _SCRIPTS_DIR / "data" / ".run"

EXIT_OK = 0
EXIT_DATA_NOT_READY = 2
EXIT_FAILED = 3

# 数据 stale 比例阈值（screener 层用；runner 层只做 canary）
STALE_RATIO_THRESHOLD = 0.20


@dataclass(frozen=True)
class Task:
    """一个槽位。

    Attributes:
        name: 任务名（幂等键与日志都用它）
        at: 槽位时刻 "HH:MM"（本地时区）
        command: 要执行的命令；None 表示纯占位（P0 空跑用）
        deadline: 数据就绪重试截止时刻；到点后仍未开始跑才告警
        require_data_date: 是否要求 canary 的末根 K 线日期 == TARGET_DATE
        canaries: canary 代码（3–5 只大票即可，判断整体是否就绪）
        backfill_at: 次日兜底重跑窗口起点（None 表示不兜底）
    """

    name: str
    at: str
    command: tuple[str, ...] | None = None
    deadline: str = "19:00"
    require_data_date: bool = False
    canaries: tuple[str, ...] = ("sh601857", "sh600519", "sz000001")
    backfill_at: str | None = "08:00"


# P0 阶段不接业务槽位；P1 逐个接入（先 15:05 收盘快照）。
TASKS: tuple[Task, ...] = ()


# ---------- 时间与键 ----------


def parse_hhmm(value: str) -> dtime:
    hour, _, minute = value.partition(":")
    return dtime(int(hour), int(minute))


def task_key(day: date, task: Task) -> str:
    """幂等键：日期 + 任务名 + 槽位，槽位用 HHMM 避免文件名里有冒号。"""
    return f"{day.isoformat()}__{task.name}__{task.at.replace(':', '')}"


def previous_trading_day(day: date) -> date:
    probe = day - timedelta(days=1)
    for _ in range(14):
        if is_trading_day(probe):
            return probe
        probe -= timedelta(days=1)
    raise RuntimeError(f"{day} 往前 14 天找不到交易日")


# ---------- 状态存储（幂等） ----------


def state_path(state_dir: Path, key: str) -> Path:
    return state_dir / f"{key}.json"


def read_state(state_dir: Path, key: str) -> dict:
    path = state_path(state_dir, key)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_dir: Path, key: str, state: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(state_dir, key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def is_done(state: dict) -> bool:
    return state.get("status") == "ok"


# ---------- 单实例锁 ----------


@contextmanager
def task_lock(state_dir: Path, task: Task):
    """非阻塞单实例锁；拿不到锁 yield False。"""
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"{task.name}.lock"
    with open(path, "w", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# ---------- 数据就绪（canary 抽样） ----------


def probe_data_date(codes: tuple[str, ...]) -> dict[str, str]:
    """取每只 canary 的末根日 K 日期（只读公开 API，不做全池扫描）。

    **必须 `use_cache=False`**：`get_kline()` 命中缓存时不比对末根日期，TTL 1 小时内
    会把旧 K 线原样返回。走缓存的话「数据未就绪」会一直成立到 TTL 过期，重试永远
    过不去；3 只 canary 穿透取数成本可忽略。
    """
    from data import get_kline

    result: dict[str, str] = {}
    for code in codes:
        try:
            bars = get_kline(code, 240, 3, use_cache=False)
        except Exception:  # 取不到就是「未就绪」，交给上层决定重试
            result[code] = ""
            continue
        result[code] = (bars[-1].to_dict().get("day", "") if bars else "")
    return result


def data_ready(codes: tuple[str, ...], target: date) -> tuple[bool, dict[str, str]]:
    """canary 的末根日期是否都已到 target（None/空 codes 视为就绪）。"""
    if not codes:
        return True, {}
    found = probe_data_date(codes)
    expected = target.isoformat()
    return all(day == expected for day in found.values()), found


# ---------- 判定与执行 ----------


def decide(task: Task, now: datetime, state: dict, trading: bool) -> str:
    """返回该槽位在这一刻应当做什么：skip_* / run / alert。"""
    if is_done(state):
        return "skip_done"
    if not trading:
        return "skip_not_trading_day"
    if now.time() < parse_hhmm(task.at):
        return "skip_not_due"
    if state.get("status") == "running":
        return "skip_running"
    if now.time() >= parse_hhmm(task.deadline) and not state.get("started_at"):
        # 「仍未开始跑」才告警；已开跑但没结束是正常的长任务
        return "alert_not_started"
    return "run"


def _notify(message: str, enable_push: bool) -> None:
    """失败/告警通知。P0 只打日志；P1 接 monitor/push_wechat.py。"""
    print(f"ALERT {message}", flush=True)
    if not enable_push:
        return
    print(f"(push 通道未接线，已跳过) {message}", flush=True)


def run_task(
    task: Task,
    now: datetime,
    state_dir: Path,
    *,
    dry_run: bool = False,
    push: bool = False,
    target_date: date | None = None,
) -> int:
    """执行一个槽位，写幂等状态，返回退出码。"""
    day = target_date or now.date()
    key = task_key(day, task)
    state = read_state(state_dir, key)

    if is_done(state):
        print(f"SKIP {task.name} {key} 已完成")
        return EXIT_OK

    if dry_run:
        print(f"DRY-RUN {task.name} {key} 本应执行: {task.command}")
        return EXIT_OK

    with task_lock(state_dir, task) as acquired:
        if not acquired:
            print(f"SKIP {task.name} 已有实例在跑")
            return EXIT_OK

        state = read_state(state_dir, key)
        if is_done(state):
            return EXIT_OK

        state = {
            "task": task.name,
            "slot": task.at,
            "date": day.isoformat(),
            "status": "running",
            "started_at": now.isoformat(timespec="seconds"),
        }
        write_state(state_dir, key, state)

        if task.require_data_date:
            ready, found = data_ready(task.canaries, day)
            state["canary"] = found
            if not ready:
                state["status"] = "data_not_ready"
                state["finished_at"] = datetime.now().isoformat(timespec="seconds")
                write_state(state_dir, key, state)
                print(f"DATA-NOT-READY {task.name} 目标日 {day} canary={found}")
                return EXIT_DATA_NOT_READY

        env = dict(os.environ)
        env.update({"TARGET_DATE": day.isoformat(), "SLOT": task.at, "TASK": task.name})

        if task.command is None:
            state["status"] = "ok"
            state["exit"] = EXIT_OK
            state["finished_at"] = datetime.now().isoformat(timespec="seconds")
            write_state(state_dir, key, state)
            print(f"OK {task.name} {key}（占位任务）")
            return EXIT_OK

        try:
            completed = subprocess.run(  # noqa: S603 - 命令由代码内常量化，非用户输入
                list(task.command), cwd=_REPO_ROOT, env=env, check=False
            )
            code = completed.returncode
        except OSError as exc:
            code = EXIT_FAILED
            print(f"ERROR {task.name}: {exc}", file=sys.stderr)

        state["exit"] = code
        state["finished_at"] = datetime.now().isoformat(timespec="seconds")
        if code == EXIT_OK:
            state["status"] = "ok"
        elif code == EXIT_DATA_NOT_READY:
            state["status"] = "data_not_ready"
            _notify(f"{task.name} 数据未就绪(exit 2)，等待重试", push)
        else:
            state["status"] = "failed"
            _notify(f"{task.name} 失败(exit {code})", push)
        write_state(state_dir, key, state)
        print(f"DONE {task.name} {key} status={state['status']} exit={code}")
        return code


def tick(
    now: datetime,
    tasks: tuple[Task, ...],
    state_dir: Path,
    *,
    dry_run: bool = False,
    push: bool = False,
) -> int:
    """launchd 心跳入口：判断并执行到期的槽位。"""
    today = now.date()
    trading = is_trading_day(today)
    results: dict[str, int] = {}

    if not is_holiday_table_covering(today):
        # 整年缺失时，该年所有节假日都会被当成交易日——必须显式告警，不许静默放行
        print(
            f"ALERT 节假日表未覆盖 {today.year} 年（已覆盖 {sorted(holiday_table_years())}），"
            "该年休市日会被当作交易日",
            flush=True,
        )

    for task in tasks:
        state = read_state(state_dir, task_key(today, task))
        decision = decide(task, now, state, trading)
        if decision == "skip_done":
            results[task.name] = EXIT_OK
            continue
        if decision == "skip_not_trading_day":
            print(f"SKIP {task.name} 今日非交易日")
            results[task.name] = EXIT_OK
            continue
        if decision == "skip_not_due":
            results[task.name] = EXIT_OK
            continue
        if decision == "skip_running":
            print(f"SKIP {task.name} 正在运行")
            results[task.name] = EXIT_OK
            continue
        if decision == "alert_not_started":
            _notify(f"{task.name} 到 {task.deadline} 仍未开始跑（数据可能未就绪）", push)
            results[task.name] = EXIT_DATA_NOT_READY
            continue
        results[task.name] = run_task(
            task, now, state_dir, dry_run=dry_run, push=push, target_date=today
        )

        # 次日兜底：上一交易日的槽没跑成，在 backfill 窗口内重跑一次
        if task.backfill_at and results[task.name] != EXIT_OK:
            prev = previous_trading_day(today)
            prev_state = read_state(state_dir, task_key(prev, task))
            if not is_done(prev_state):
                window_start = parse_hhmm(task.backfill_at)
                if window_start <= now.time() <= parse_hhmm(task.at):
                    results[task.name] = run_task(
                        task, now, state_dir, dry_run=dry_run, push=push, target_date=prev
                    )

    if not tasks:
        print(
            f"TICK {now.isoformat(timespec='seconds')} trading_day={trading} "
            f"tasks=0（P0：未接入业务槽位）"
        )
        return EXIT_OK

    print(f"TICK {now.isoformat(timespec='seconds')} trading_day={trading} results={results}")
    if any(code == EXIT_FAILED for code in results.values()):
        return EXIT_FAILED
    if any(code == EXIT_DATA_NOT_READY for code in results.values()):
        return EXIT_DATA_NOT_READY
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="统一调度入口（launchd 心跳驱动）")
    parser.add_argument("--tick", action="store_true", help="心跳：判断并执行到期槽位")
    parser.add_argument("--task", help="只跑指定任务")
    parser.add_argument("--list", action="store_true", help="列出槽位与今日状态")
    parser.add_argument("--dry-run", action="store_true", help="只打日志，不执行命令")
    parser.add_argument("--push", action="store_true", help="失败时推微信（P1 接线，默认关）")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR), help="状态目录")
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    now = datetime.now()

    if args.list:
        trading = is_trading_day(now.date())
        print(f"今日 {now.date()} trading_day={trading}")
        for task in TASKS:
            state = read_state(state_dir, task_key(now.date(), task))
            print(f"  {task.at} {task.name:<16} status={state.get('status', 'pending')}")
        if not TASKS:
            print("  （P0：尚未接入业务槽位）")
        return EXIT_OK

    if args.task:
        matched = [t for t in TASKS if t.name == args.task]
        if not matched:
            print(f"❌ 未知任务: {args.task}；已注册: {[t.name for t in TASKS]}", file=sys.stderr)
            return EXIT_FAILED
        return run_task(
            matched[0], now, state_dir, dry_run=args.dry_run, push=args.push
        )

    if args.tick:
        return tick(now, TASKS, state_dir, dry_run=args.dry_run, push=args.push)

    parser.print_help()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

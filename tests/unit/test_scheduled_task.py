"""`scripts/dev/scheduled_task.py` 与 `data.config.is_trading_day` 的离线单测。

全部用 tmp_path + 注入 now，不触网、不依赖系统时钟与真实调度。
"""

from __future__ import annotations

import json
from datetime import date, datetime, time as dtime
from pathlib import Path

import pytest

from data.config import is_trading_day
from dev import scheduled_task as st


def _task(**kwargs) -> st.Task:
    base = {
        "name": "demo",
        "at": "15:05",
        "command": None,
        "deadline": "19:00",
        "require_data_date": False,
        "backfill_at": None,
    }
    base.update(kwargs)
    return st.Task(**base)


def _at(day: str, hh: int, mm: int) -> datetime:
    return datetime.combine(date.fromisoformat(day), dtime(hh, mm))


# ---------- is_trading_day ----------


def test_weekend_is_not_trading_day():
    assert is_trading_day(date(2026, 11, 21)) is False  # 周六
    assert is_trading_day(date(2026, 11, 22)) is False  # 周日


def test_weekday_is_trading_day():
    assert is_trading_day(date(2026, 11, 20)) is True  # 周五


def test_holiday_is_not_trading_day():
    assert is_trading_day(date(2026, 10, 1)) is False  # 国庆


def test_is_trading_day_is_not_is_trading_hours():
    """回归：盘前盘后时刻 is_trading_hours() 为 False，is_trading_day() 必须为 True。"""
    from data.config import is_trading_hours

    day = date(2026, 11, 20)
    assert is_trading_day(day) is True
    # is_trading_hours() 按「此刻」判，夜里必然 False——这正是不能拿它当前置的原因
    assert is_trading_hours() is False


# ---------- 幂等键与状态 ----------


def test_task_key_is_stable_and_colon_free():
    task = _task()
    key = st.task_key(date(2026, 11, 20), task)
    assert key == "2026-11-20__demo__1505"
    assert ":" not in key


def test_state_roundtrip(tmp_path: Path):
    key = "k1"
    assert st.read_state(tmp_path, key) == {}
    st.write_state(tmp_path, key, {"status": "ok", "exit": 0})
    assert st.read_state(tmp_path, key)["status"] == "ok"
    assert st.is_done(st.read_state(tmp_path, key)) is True


def test_corrupted_state_is_treated_as_empty(tmp_path: Path):
    (tmp_path / "k1.json").write_text("{not json", encoding="utf-8")
    assert st.read_state(tmp_path, "k1") == {}


# ---------- 单实例锁 ----------


def test_lock_is_exclusive(tmp_path: Path):
    task = _task()
    with st.task_lock(tmp_path, task) as first:
        assert first is True
        with st.task_lock(tmp_path, task) as second:
            assert second is False, "同一任务不能并发跑两个实例"


def test_lock_released_after_use(tmp_path: Path):
    task = _task()
    with st.task_lock(tmp_path, task) as acquired:
        assert acquired is True
    with st.task_lock(tmp_path, task) as acquired_again:
        assert acquired_again is True


# ---------- decide：什么情况下该跑 ----------


def test_decide_skips_on_non_trading_day():
    task = _task()
    assert st.decide(task, _at("2026-11-21", 15, 10), {}, trading=False) == (
        "skip_not_trading_day"
    )


def test_decide_skips_before_slot():
    task = _task()
    assert st.decide(task, _at("2026-11-20", 15, 0), {}, trading=True) == "skip_not_due"


def test_decide_runs_after_slot():
    task = _task()
    assert st.decide(task, _at("2026-11-20", 15, 10), {}, trading=True) == "run"


def test_decide_skips_when_done():
    task = _task()
    state = {"status": "ok", "started_at": "2026-11-20T15:05:00"}
    assert st.decide(task, _at("2026-11-20", 16, 0), state, trading=True) == "skip_done"


def test_decide_alerts_only_when_never_started():
    """19:00 判的是「仍未开始跑」——18:50 开跑、19:25 结束是正常的，不能误报。"""
    task = _task()
    late = _at("2026-11-20", 19, 5)
    assert st.decide(task, late, {}, trading=True) == "alert_not_started"
    running = {"status": "running", "started_at": "2026-11-20T18:50:00"}
    assert st.decide(task, late, running, trading=True) == "skip_running"


# ---------- run_task：幂等、dry-run、数据未就绪 ----------


def test_run_task_marks_done_and_is_idempotent(tmp_path: Path, capsys):
    task = _task()
    now = _at("2026-11-20", 15, 10)

    assert st.run_task(task, now, tmp_path) == st.EXIT_OK
    key = st.task_key(now.date(), task)
    assert st.read_state(tmp_path, key)["status"] == "ok"

    # 第二次直接跳过，不重复执行
    assert st.run_task(task, now, tmp_path) == st.EXIT_OK
    assert "已完成" in capsys.readouterr().out


def test_dry_run_does_not_mark_done(tmp_path: Path):
    task = _task()
    now = _at("2026-11-20", 15, 10)
    assert st.run_task(task, now, tmp_path, dry_run=True) == st.EXIT_OK
    assert st.read_state(tmp_path, st.task_key(now.date(), task)) == {}


def test_data_not_ready_does_not_mark_done(tmp_path: Path, monkeypatch):
    task = _task(require_data_date=True, canaries=("sh601857",))
    now = _at("2026-11-20", 18, 0)
    monkeypatch.setattr(
        st, "probe_data_date", lambda codes: {c: "2026-11-19" for c in codes}
    )

    assert st.run_task(task, now, tmp_path) == st.EXIT_DATA_NOT_READY
    state = st.read_state(tmp_path, st.task_key(now.date(), task))
    assert state["status"] == "data_not_ready"
    assert st.is_done(state) is False, "未就绪不能写完成标记，否则重试逻辑失效"


def test_data_ready_runs_command(tmp_path: Path, monkeypatch):
    task = _task(
        require_data_date=True,
        canaries=("sh601857",),
        command=("true",),
    )
    now = _at("2026-11-20", 18, 0)
    monkeypatch.setattr(
        st, "probe_data_date", lambda codes: {c: "2026-11-20" for c in codes}
    )

    assert st.run_task(task, now, tmp_path) == st.EXIT_OK
    assert st.is_done(st.read_state(tmp_path, st.task_key(now.date(), task)))


def test_failed_command_records_failure_and_retries(tmp_path: Path):
    task = _task(command=("false",))
    now = _at("2026-11-20", 16, 0)

    assert st.run_task(task, now, tmp_path) == 1
    key = st.task_key(now.date(), task)
    state = st.read_state(tmp_path, key)
    assert state["status"] == "failed"
    assert st.decide(task, _at("2026-11-20", 16, 5), state, trading=True) == "run"


# ---------- tick：整轮心跳 ----------


def test_tick_without_tasks_is_noop(tmp_path: Path):
    assert st.tick(_at("2026-11-20", 15, 5), (), tmp_path) == st.EXIT_OK


def test_tick_runs_due_task_once(tmp_path: Path):
    task = _task()
    now = _at("2026-11-20", 15, 10)

    assert st.tick(now, (task,), tmp_path) == st.EXIT_OK
    assert st.is_done(st.read_state(tmp_path, st.task_key(now.date(), task)))

    # 心跳再来一次（launchd 每 5 分钟）：幂等跳过
    before = st.state_path(tmp_path, st.task_key(now.date(), task)).stat().st_mtime
    assert st.tick(_at("2026-11-20", 15, 15), (task,), tmp_path) == st.EXIT_OK
    after = st.state_path(tmp_path, st.task_key(now.date(), task)).stat().st_mtime
    assert before == after


def test_tick_skips_on_non_trading_day(tmp_path: Path, capsys):
    task = _task()
    assert st.tick(_at("2026-11-21", 15, 10), (task,), tmp_path) == st.EXIT_OK
    assert "非交易日" in capsys.readouterr().out
    assert st.read_state(tmp_path, st.task_key(date(2026, 11, 21), task)) == {}


def test_previous_trading_day_skips_weekend():
    assert st.previous_trading_day(date(2026, 11, 23)) == date(2026, 11, 20)


# ---------- main：CLI 行为 ----------


def test_main_unknown_task_fails(tmp_path: Path):
    assert st.main(["--task", "nope", "--state-dir", str(tmp_path)]) == st.EXIT_FAILED


def test_main_list_shows_placeholder(tmp_path: Path, capsys):
    assert st.main(["--list", "--state-dir", str(tmp_path)]) == st.EXIT_OK
    out = capsys.readouterr().out
    assert "trading_day" in out


def test_state_files_are_json(tmp_path: Path):
    task = _task()
    now = _at("2026-11-20", 15, 10)
    st.run_task(task, now, tmp_path)
    payload = json.loads(st.state_path(tmp_path, st.task_key(now.date(), task)).read_text())
    assert payload["task"] == "demo"
    assert payload["slot"] == "15:05"


# ---------- canary 探针必须穿透缓存 ----------


def test_probe_uses_no_cache(monkeypatch):
    """回归：走缓存会拿到旧 K 线，导致「数据未就绪」永远成立、重试到 19:00 也过不去。"""
    import data as data_mod

    seen: list[bool] = []

    class _Bar:
        def to_dict(self):
            return {"day": "2026-11-20"}

    def _fake(code, scale, datalen, use_cache=True):
        seen.append(use_cache)
        return [_Bar()]

    monkeypatch.setattr(data_mod, "get_kline", _fake, raising=False)

    assert st.probe_data_date(("sh601857",)) == {"sh601857": "2026-11-20"}
    assert seen == [False], "canary 探针必须 use_cache=False"


# ---------- 节假日表覆盖（2027 缺失必须能发现） ----------


def test_holiday_table_covers_2026_not_2027():
    from data.config import holiday_table_years, is_holiday_table_covering

    assert 2026 in holiday_table_years()
    assert is_holiday_table_covering(date(2026, 11, 20)) is True
    # 2027 尚未录入：整年会静默把休市日当交易日，必须有告警路径
    assert is_holiday_table_covering(date(2027, 1, 4)) is False


def test_tick_alerts_when_holiday_table_missing_year(tmp_path: Path, capsys):
    st.tick(_at("2027-01-04", 15, 10), (), tmp_path)
    assert "节假日表未覆盖 2027" in capsys.readouterr().out


# ---------- --no-cache 不再是空开关 ----------


def test_kline_no_cache_flag_reaches_fetch(monkeypatch):
    """回归：--no-cache 只在 cli_base 声明、无人消费，加了也照样命中缓存。"""
    import kline

    seen = {}

    def _fake_fetch(symbol, scale, datalen, use_cache=True):
        seen["use_cache"] = use_cache
        return []

    monkeypatch.setattr(kline, "fetch", _fake_fetch)
    monkeypatch.setattr(
        "sys.argv", ["kline.py", "sh601857", "--no-cache", "-j"]
    )
    kline.main()

    assert seen["use_cache"] is False

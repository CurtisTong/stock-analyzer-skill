"""scripts/monitor/manager.py 的单元测试。

覆盖 NotificationManager 推送链路：
- send() 主路径：无通道/静默时段/限流/通道成功失败
- send_alert() 标题拼装（icon + name + alert_type + code）
- register_channel / get_active_channels
- _check_throttle 原子占位（并发场景）

按 FRAMEWORK.md 规范：mock channel 避免真实 HTTP 请求。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────
# 辅助：fake channel
# ────────────────────────────────────────────────────────────────


class _FakeChannel:
    """模拟通知通道，可控制 send 返回值。"""

    def __init__(self, name: str = "fake", ok: bool = True, error: str = ""):
        self.name = name
        self._ok = ok
        self._error = error
        self.calls: list = []

    def is_configured(self) -> bool:
        return True

    def send(self, title, body, url=None, group=None):
        self.calls.append({"title": title, "body": body, "url": url, "group": group})
        return (self._ok, self._error)


def _make_nm(channels: list | None = None) -> "NotificationManager":
    """构造 NotificationManager 注入 fake channels，绕过配置文件加载。"""
    from monitor.manager import NotificationManager

    nm = NotificationManager.__new__(NotificationManager)
    nm._channels = channels or []
    nm._config = {
        "throttle": {"dedup_window": 15, "daily_limit": 20},
        "quiet_hours": {"enabled": False},
    }
    nm._lock = threading.Lock()
    nm._throttle_log = {}
    nm._daily_count = 0
    nm._daily_date = datetime.now().strftime("%Y-%m-%d")
    nm._last_throttle_gc = time.time()
    nm._log_write_count = 0
    return nm


# ────────────────────────────────────────────────────────────────
# send() 主路径
# ────────────────────────────────────────────────────────────────


class TestSend:
    """send() 推送主路径。"""

    def test_no_channels_returns_no_channels_reason(self):
        """无已注册通道时返回 reason='no_channels'。"""
        nm = _make_nm(channels=[])
        result = nm.send("标题", "内容")
        assert result == {"sent": 0, "failed": 0, "results": {}, "reason": "no_channels"}

    def test_quiet_hours_blocks_all(self):
        """静默时段阻止所有发送（即使有通道）。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])
        with patch.object(nm, "_is_quiet_hours", return_value=True):
            result = nm.send("标题", "内容")
        assert result["reason"] == "quiet_hours"
        assert ch.calls == []  # channel 未被调用

    def test_throttled_returns_reason(self):
        """去重窗口内重复 key 返回 throttled。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])
        with patch.object(nm, "_is_quiet_hours", return_value=False):
            first = nm.send("标题", "内容", throttle_key="dup-key")
            second = nm.send("标题", "内容", throttle_key="dup-key")
        assert first["sent"] == 1
        assert second["reason"] == "throttled"

    def test_successful_send_increments_count(self):
        """通道返回 ok 时 sent+1，结果列表记录成功。"""
        ch1 = _FakeChannel(name="bark", ok=True)
        ch2 = _FakeChannel(name="wechat", ok=True)
        nm = _make_nm(channels=[ch1, ch2])

        result = nm.send("标题", "内容")

        assert result["sent"] == 2
        assert result["failed"] == 0
        assert result["results"] == {"bark": True, "wechat": True}

    def test_partial_failure_records_each_channel(self):
        """多通道部分失败时，sent/failed 分别计数。"""
        ch1 = _FakeChannel(name="bark", ok=True)
        ch2 = _FakeChannel(name="wechat", ok=False, error="网络超时")
        nm = _make_nm(channels=[ch1, ch2])

        result = nm.send("标题", "内容")

        assert result["sent"] == 1
        assert result["failed"] == 1
        assert result["results"] == {"bark": True, "wechat": False}

    def test_throttle_key_defaults_to_title(self):
        """未指定 throttle_key 时默认用 title 去重。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])

        with patch.object(nm, "_is_quiet_hours", return_value=False):
            nm.send("相同标题", "内容1")
            second = nm.send("相同标题", "内容2")
        # 第二次应被去重
        assert second["reason"] == "throttled"


# ────────────────────────────────────────────────────────────────
# send_alert() 标题拼装
# ────────────────────────────────────────────────────────────────


class TestSendAlert:
    """send_alert() 标准化股票预警格式。"""

    def test_alert_type_icon_mapping(self):
        """不同 alert_type 对应不同 emoji icon。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])

        cases = [
            ("price", "💰"),
            ("technical", "📊"),
            ("portfolio", "📋"),
            ("market", "🏛️"),
            ("risk", "⚠️"),
            ("break", "🔴"),
        ]
        for alert_type, expected_icon in cases:
            nm.send_alert(
                alert_type=alert_type,
                stock_name="测试",
                stock_code="sh600000",
                message="测试消息",
            )
            title = ch.calls[-1]["title"]
            assert title.startswith(expected_icon), f"{alert_type} 应以 {expected_icon} 开头，实际 {title}"

    def test_unknown_alert_type_uses_default_icon(self):
        """未知 alert_type 用默认 📌 icon。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])

        nm.send_alert(
            alert_type="unknown_type",
            stock_name="测试",
            stock_code="sh600000",
            message="测试",
        )
        assert ch.calls[0]["title"].startswith("📌")

    def test_title_includes_code(self):
        """title 应包含 stock_code。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])

        nm.send_alert(
            alert_type="price",
            stock_name="贵州茅台",
            stock_code="sh600519",
            message="突破 MA5",
        )
        assert "sh600519" in ch.calls[0]["title"]
        assert "贵州茅台" in ch.calls[0]["title"]

    def test_title_omits_code_when_empty(self):
        """stock_code 为空时 title 不附加括号。"""
        ch = _FakeChannel(name="bark", ok=True)
        nm = _make_nm(channels=[ch])

        nm.send_alert(
            alert_type="market",
            stock_name="大盘",
            stock_code="",
            message="市场异动",
        )
        assert "(" not in ch.calls[0]["title"]


# ────────────────────────────────────────────────────────────────
# register_channel / get_active_channels
# ────────────────────────────────────────────────────────────────


class TestChannelRegistry:
    """通道注册与查询。"""

    def test_register_and_list(self):
        """注册通道后 get_active_channels 返回名称列表。"""
        from monitor.manager import NotificationManager

        nm = NotificationManager.__new__(NotificationManager)
        nm._channels = []
        nm._config = {"throttle": {}, "quiet_hours": {}}
        nm._lock = threading.Lock()
        nm._throttle_log = {}
        nm._daily_count = 0
        nm._daily_date = datetime.now().strftime("%Y-%m-%d")
        nm._last_throttle_gc = time.time()
        nm._log_write_count = 0

        assert nm.get_active_channels() == []
        nm.register_channel(_FakeChannel(name="bark"))
        nm.register_channel(_FakeChannel(name="wechat"))
        assert sorted(nm.get_active_channels()) == ["bark", "wechat"]


# ────────────────────────────────────────────────────────────────
# _check_throttle 原子占位
# ────────────────────────────────────────────────────────────────


class TestThrottle:
    """_check_throttle 频率控制与去重窗口。"""

    def test_first_call_always_passes(self):
        """首次调用 throttle 通过。"""
        nm = _make_nm()
        assert nm._check_throttle("key1") is True

    def test_duplicate_within_window_throttled(self):
        """去重窗口内同 key 第二次调用返回 False。"""
        nm = _make_nm()
        assert nm._check_throttle("key1") is True
        assert nm._check_throttle("key1") is False

    def test_daily_limit_enforced(self):
        """非紧急消息达 daily_limit 后被限流。"""
        nm = _make_nm()
        nm._config["throttle"]["daily_limit"] = 3
        for i in range(3):
            assert nm._check_throttle(f"key{i}") is True
        # 第 4 个被拒
        assert nm._check_throttle("key3") is False

    def test_urgent_bypasses_daily_limit(self):
        """urgent=True 不受 daily_limit 限制（但仍受去重窗口限制）。"""
        nm = _make_nm()
        nm._config["throttle"]["daily_limit"] = 2
        assert nm._check_throttle("k1", urgent=True) is True
        assert nm._check_throttle("k2", urgent=True) is True
        # 达 daily_limit 后，urgent=True 仍可通过
        assert nm._check_throttle("k3", urgent=True) is True
        # 但去重窗口仍生效
        assert nm._check_throttle("k3", urgent=True) is False

    def test_atomic_under_concurrent_send(self):
        """并发场景下 _check_throttle 原子占位（P0-10 C1 修复验证）。

        多线程并发 send 同一 key，预期只有 1 个通过 throttle，
        其余应被去重窗口拒绝（不出现双双通过导致重复推送）。
        """
        nm = _make_nm()
        passed = []
        lock = threading.Lock()
        barrier = threading.Barrier(10)

        def worker(i):
            barrier.wait()
            ok = nm._check_throttle("concurrent-key")
            with lock:
                passed.append(ok)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 10 个并发请求只有 1 个通过（原子占位）
        assert passed.count(True) == 1
        assert passed.count(False) == 9

    def test_throttle_occupies_independent_of_send_result(self):
        """占位独立于发送结果（P0-10 C2）：失败的发送也占用去重窗口。"""
        ch = _FakeChannel(name="bark", ok=False, error="err")
        nm = _make_nm(channels=[ch])

        with patch.object(nm, "_is_quiet_hours", return_value=False):
            first = nm.send("标题", "内容", throttle_key="key1")
            second = nm.send("标题", "内容", throttle_key="key1")
        # 第一次失败（failed=1），第二次仍被去重（不会无限重试）
        assert first["failed"] == 1
        assert second["reason"] == "throttled"

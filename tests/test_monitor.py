"""
monitor 层单元测试：覆盖 NotificationManager 的频率控制、静默时段、紧急消息逻辑。
"""
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from monitor.manager import NotificationManager  # noqa: E402


def _make_manager(config=None):
    """构造一个不带通道的 NotificationManager，便于测试 throttle/quiet 逻辑。"""
    return NotificationManager(config=config or {})


# ═══════════════════════════════════════════════════════════════
# 1. 初始化
# ═══════════════════════════════════════════════════════════════
class TestInit:
    def test_no_channels_when_config_empty(self):
        mgr = _make_manager()
        assert mgr.get_active_channels() == []

    def test_load_default_config_when_no_file(self):
        """配置文件不存在时回退到空 dict，不抛异常。"""
        with patch("monitor.manager._config_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/path.yaml")
            mgr = NotificationManager()
        assert mgr._config == {}


# ═══════════════════════════════════════════════════════════════
# 2. 频率控制
# ═══════════════════════════════════════════════════════════════
class TestThrottle:
    def test_dedup_window_blocks_repeat(self):
        """15 分钟内同一 key 应被去重。"""
        mgr = _make_manager({"throttle": {"dedup_window": 15, "daily_limit": 100}})
        # 首次：允许（_throttle_log 空，last=0，永远满足 now - 0 >> dedup）
        assert mgr._check_throttle("key1") is True
        # 模拟已发送过：写入 _throttle_log
        mgr._throttle_log["key1"] = time.time()
        # 立即重复：拒绝
        assert mgr._check_throttle("key1") is False
        # 不同 key：允许
        assert mgr._check_throttle("key2") is True

    def test_daily_limit_enforced(self):
        """到达 daily_limit 后非紧急消息应被拒。"""
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 3}})
        # 模拟已发送 3 条（使用今天的日期，避免被重置）
        mgr._daily_count = 3
        mgr._daily_date = datetime.now().strftime("%Y-%m-%d")
        # 非紧急：被拒
        assert mgr._check_throttle("k1", urgent=False) is False
        # urgent 跳过 daily_limit
        assert mgr._check_throttle("k2", urgent=True) is True

    def test_urgent_bypasses_daily_limit(self):
        """urgent=True 不受 daily_limit 限制。"""
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 1}})
        mgr._daily_count = 5
        mgr._daily_date = datetime.now().strftime("%Y-%m-%d")
        # urgent 仍允许
        assert mgr._check_throttle("k1", urgent=True) is True
        # 非 urgent 被拒
        assert mgr._check_throttle("k2", urgent=False) is False

    def test_urgent_still_respects_dedup(self):
        """urgent=True 仍受去重窗口限制。"""
        mgr = _make_manager({"throttle": {"dedup_window": 15, "daily_limit": 0}})
        mgr._throttle_log["k1"] = time.time()
        # urgent 仍受去重限制
        assert mgr._check_throttle("k1", urgent=True) is False

    def test_dedup_window_expires(self):
        """15 分钟前发送的 key 不应被去重。"""
        mgr = _make_manager({"throttle": {"dedup_window": 15, "daily_limit": 100}})
        mgr._throttle_log["k1"] = time.time() - 16 * 60  # 16 分钟前
        # 已过窗口：允许
        assert mgr._check_throttle("k1") is True


# ═══════════════════════════════════════════════════════════════
# 3. 静默时段
# ═══════════════════════════════════════════════════════════════
class TestQuietHours:
    def test_empty_quiet_hours_disabled(self):
        mgr = _make_manager({"throttle": {"quiet_hours": ""}})
        assert mgr._is_quiet_hours() is False

    def test_within_quiet_hours(self):
        """配置 00:00-23:59 应覆盖全天。"""
        mgr = _make_manager({"throttle": {"quiet_hours": "00:00-23:59"}})
        assert mgr._is_quiet_hours() is True

    def test_outside_quiet_hours(self):
        """配置 03:00-03:01 几乎全天空闲。"""
        mgr = _make_manager({"throttle": {"quiet_hours": "03:00-03:01"}})
        # 大多数时间不在静默时段
        with patch("monitor.manager.datetime") as mock_dt:
            from datetime import datetime as real_dt
            mock_dt.now.return_value = real_dt(2026, 6, 10, 12, 0, 0)
            assert mgr._is_quiet_hours() is False

    def test_cross_midnight_quiet_hours(self):
        """跨午夜配置（如 22:00-06:00）。"""
        mgr = _make_manager({"throttle": {"quiet_hours": "22:00-06:00"}})
        from datetime import datetime as real_dt
        with patch("monitor.manager.datetime") as mock_dt:
            # 凌晨 3 点：处于 22:00-06:00 区间内
            mock_dt.now.return_value = real_dt(2026, 6, 10, 3, 0, 0)
            assert mgr._is_quiet_hours() is True
            # 中午 12 点：不在静默时段
            mock_dt.now.return_value = real_dt(2026, 6, 10, 12, 0, 0)
            assert mgr._is_quiet_hours() is False

    def test_invalid_quiet_hours_format_ignored(self):
        """非法格式应被忽略（不抛异常）。"""
        mgr = _make_manager({"throttle": {"quiet_hours": "invalid"}})
        assert mgr._is_quiet_hours() is False


# ═══════════════════════════════════════════════════════════════
# 4. 通道注册
# ═══════════════════════════════════════════════════════════════
class TestChannelRegistration:
    def test_register_unconfigured_channel_rejected(self):
        mgr = _make_manager()
        ch = MagicMock()
        ch.is_configured.return_value = False
        mgr.register_channel(ch)
        assert ch not in mgr._channels

    def test_register_configured_channel_accepted(self):
        mgr = _make_manager()
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "test_channel"
        mgr.register_channel(ch)
        assert ch in mgr._channels


# ═══════════════════════════════════════════════════════════════
# 5. send 端到端（带 mock 通道）
# ═══════════════════════════════════════════════════════════════
class TestSend:
    def test_no_active_channels_returns_no_channels(self):
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 100}})
        result = mgr.send("test", "body")
        assert result["sent"] == 0
        assert result["reason"] == "no_channels"

    def test_send_via_mock_channel(self):
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 100}})
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "mock"
        ch.send.return_value = (True, "")
        mgr.register_channel(ch)
        result = mgr.send("hello", "world")
        assert result["sent"] == 1
        assert result["failed"] == 0
        assert result["results"]["mock"] is True
        ch.send.assert_called_once()

    def test_send_failure_recorded(self):
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 100}})
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "failing"
        ch.send.return_value = (False, "connection timeout")
        mgr.register_channel(ch)
        result = mgr.send("hi", "body")
        assert result["sent"] == 0
        assert result["failed"] == 1
        assert result["results"]["failing"] is False

    def test_send_blocked_in_quiet_hours(self):
        mgr = _make_manager({
            "throttle": {"dedup_window": 0, "daily_limit": 100, "quiet_hours": "00:00-23:59"},
        })
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "mock"
        mgr.register_channel(ch)
        result = mgr.send("hi", "body")
        assert result["reason"] == "quiet_hours"
        ch.send.assert_not_called()

    def test_send_throttled(self):
        mgr = _make_manager({"throttle": {"dedup_window": 15, "daily_limit": 100}})
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "mock"
        ch.send.return_value = (True, "")
        mgr.register_channel(ch)
        mgr.send("k1", "body")
        result = mgr.send("k1", "body")  # 重复
        assert result["reason"] == "throttled"


# ═══════════════════════════════════════════════════════════════
# 6. send_alert 标准化格式
# ═══════════════════════════════════════════════════════════════
class TestSendAlert:
    def test_alert_format(self):
        """send_alert 自动加上图标和代码。"""
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 100}})
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "mock"
        ch.send.return_value = (True, "")
        mgr.register_channel(ch)

        mgr.send_alert("price", "贵州茅台", "sh600519", "突破 1800")
        ch.send.assert_called_once()
        title = ch.send.call_args[0][0]
        assert "贵州茅台" in title
        assert "sh600519" in title
        assert "price" in title

    def test_alert_unknown_type_uses_default_icon(self):
        mgr = _make_manager({"throttle": {"dedup_window": 0, "daily_limit": 100}})
        ch = MagicMock()
        ch.is_configured.return_value = True
        ch.name = "mock"
        ch.send.return_value = (True, "")
        mgr.register_channel(ch)
        mgr.send_alert("custom_type", "测试", "sh000001", "msg")
        title = ch.send.call_args[0][0]
        # 默认图标 📌
        assert "📌" in title

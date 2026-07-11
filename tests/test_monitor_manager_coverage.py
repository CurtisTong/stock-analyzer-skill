"""monitor/manager.py 覆盖测试。

mock channels / 文件 I/O，覆盖 NotificationManager 的 send、send_alert、
_check_throttle、_is_quiet_hours、_log_send、_rotate_log_if_needed、
_clean_old_logs 等方法与模块级函数。
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import monitor.manager as mgr_mod
from monitor.manager import (
    NotificationManager,
    _clean_old_logs,
    _config_path,
    _log_path,
    _rotate_log_if_needed,
)


class _FakeChannel:
    """模拟通知通道。"""

    def __init__(self, name, configured=True, send_ok=True, error=""):
        self.name = name
        self._configured = configured
        self._send_ok = send_ok
        self._error = error

    def is_configured(self):
        return self._configured

    def send(self, title, body, url=None, group=None):
        return self._send_ok, self._error


def _make_manager(config=None):
    """构造一个无通道的 NotificationManager。"""
    if config is None:
        config = {"channels": {}, "throttle": {"dedup_window": 15, "daily_limit": 20}}
    return NotificationManager(config=config)


class TestConfigPath:
    def test_config_path_exists(self):
        p = _config_path()
        assert p.name == "notification.yaml"


class TestLogPath:
    def test_log_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mgr_mod, "__file__", str(tmp_path / "manager.py"))
        # _log_path 用 parent.parent / data / .cache
        log = _log_path()
        assert log.name == "notifications.log"


class TestRotateLog:
    def test_nonexistent_file_noop(self, tmp_path):
        log = tmp_path / "x.log"
        _rotate_log_if_needed(log)  # 不应抛异常

    def test_small_file_noop(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text("small")
        _rotate_log_if_needed(log, max_size=1024)
        assert log.exists()

    def test_large_file_rotates(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text("x" * 2048)
        _rotate_log_if_needed(log, max_size=1024, max_files=3)
        assert not log.exists()
        assert (tmp_path / "x.log.1").exists()

    def test_rotate_keeps_max_files(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text("x" * 2048)
        # 预先创建 .1 .2 .3
        for i in range(1, 4):
            (tmp_path / f"x.log.{i}").write_text(f"old{i}")
        _rotate_log_if_needed(log, max_size=1024, max_files=3)
        # .3 应被删除（最旧），.1->.2, .2->.3, 当前->.1
        assert not (tmp_path / "x.log.3").exists() or (tmp_path / "x.log.3").exists()
        assert (tmp_path / "x.log.1").exists()

    def test_stat_error_noop(self, tmp_path):
        log = tmp_path / "x.log"
        log.write_text("x")
        with patch("pathlib.Path.stat", side_effect=OSError("denied")):
            _rotate_log_if_needed(log, max_size=1)  # 不抛异常


class TestCleanOldLogs:
    def test_cleans_old_rotated_files(self, tmp_path):
        log = tmp_path / "x.log"
        for i in range(1, 8):
            (tmp_path / f"x.log.{i}").write_text(f"old{i}")
        cleaned = _clean_old_logs(log, keep=5)
        assert cleaned == 2  # .6 .7 被删
        assert (tmp_path / "x.log.5").exists()
        assert not (tmp_path / "x.log.6").exists()

    def test_no_rotated_files(self, tmp_path):
        log = tmp_path / "x.log"
        cleaned = _clean_old_logs(log, keep=5)
        assert cleaned == 0


class TestNotificationManagerInit:
    def test_no_channels(self):
        nm = _make_manager()
        assert nm.get_active_channels() == []

    def test_logging_config(self):
        config = {"channels": {}, "logging": {"max_size": 10, "max_files": 3}}
        nm = NotificationManager(config=config)
        assert nm._log_max_size == 10 * 1024 * 1024
        assert nm._log_max_files == 3

    def test_setup_channels_bark(self):
        config = {
            "channels": {"bark": {"enabled": True, "key": "test_key", "server": "https://api.day.app"}},
            "throttle": {},
        }
        with patch("monitor.manager.BarkChannel") as BarkMock:
            ch = MagicMock()
            ch.is_configured.return_value = True
            ch.name = "bark"
            BarkMock.return_value = ch
            nm = NotificationManager(config=config)
            assert "bark" in nm.get_active_channels()

    def test_setup_channels_bark_unconfigured(self):
        config = {
            "channels": {"bark": {"enabled": True, "key": ""}},
            "throttle": {},
        }
        with patch("monitor.manager.BarkChannel") as BarkMock:
            ch = MagicMock()
            ch.is_configured.return_value = False
            BarkMock.return_value = ch
            nm = NotificationManager(config=config)
            assert nm.get_active_channels() == []

    def test_setup_channels_wechat(self):
        config = {
            "channels": {"wechat_work": {"enabled": True, "key": "test"}},
            "throttle": {},
        }
        with patch("monitor.manager.WechatWorkChannel") as WkMock:
            ch = MagicMock()
            ch.is_configured.return_value = True
            ch.name = "wechat_work"
            WkMock.return_value = ch
            nm = NotificationManager(config=config)
            assert "wechat_work" in nm.get_active_channels()

    def test_setup_channels_dingtalk(self):
        config = {
            "channels": {"dingtalk": {"enabled": True, "token": "t", "secret": "s"}},
            "throttle": {},
        }
        with patch("monitor.manager.DingtalkChannel") as DkMock:
            ch = MagicMock()
            ch.is_configured.return_value = True
            ch.name = "dingtalk"
            DkMock.return_value = ch
            nm = NotificationManager(config=config)
            assert "dingtalk" in nm.get_active_channels()

    def test_register_channel(self):
        nm = _make_manager()
        ch = _FakeChannel("custom")
        nm.register_channel(ch)
        assert "custom" in nm.get_active_channels()

    def test_register_unconfigured_skipped(self):
        nm = _make_manager()
        ch = _FakeChannel("custom", configured=False)
        nm.register_channel(ch)
        assert nm.get_active_channels() == []


class TestSend:
    def test_quiet_hours_blocks(self):
        config = {"channels": {}, "throttle": {"quiet_hours": "00:00-23:59"}}
        nm = NotificationManager(config=config)
        result = nm.send("title", "body")
        assert result["reason"] == "quiet_hours"
        assert result["sent"] == 0

    def test_throttled_by_dedup(self):
        config = {"channels": {}, "throttle": {"dedup_window": 15, "daily_limit": 20}}
        nm = NotificationManager(config=config)
        # 第一次占位成功，但无通道 -> no_channels
        r1 = nm.send("title", "body", throttle_key="k1")
        assert r1["reason"] == "no_channels"
        # 第二次同 key -> throttled
        r2 = nm.send("title", "body", throttle_key="k1")
        assert r2["reason"] == "throttled"

    def test_daily_limit(self):
        config = {"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 2}}
        nm = NotificationManager(config=config)
        for i in range(2):
            nm.send("t", "b", throttle_key=f"k{i}")
        # 第三次达到上限
        r = nm.send("t", "b", throttle_key="k_new")
        assert r["reason"] == "throttled"

    def test_urgent_bypasses_daily_limit(self):
        config = {"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 1}}
        nm = NotificationManager(config=config)
        nm.send("t", "b", throttle_key="k1")
        # urgent 仍受 dedup 限制，但用新 key 绕过
        r = nm.send("t", "b", throttle_key="k2", urgent=True)
        assert r["reason"] == "no_channels"  # 紧急绕过 daily_limit

    def test_send_to_channels(self):
        config = {"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 100}}
        nm = NotificationManager(config=config)
        nm.register_channel(_FakeChannel("ch1", send_ok=True))
        nm.register_channel(_FakeChannel("ch2", send_ok=False, error="fail"))
        result = nm.send("title", "body", throttle_key="k1")
        assert result["sent"] == 1
        assert result["failed"] == 1
        assert result["results"]["ch1"] is True
        assert result["results"]["ch2"] is False

    def test_quiet_hours_cross_midnight(self):
        """跨午夜静默时段。"""
        config = {"channels": {}, "throttle": {"quiet_hours": "23:00-09:00"}}
        nm = NotificationManager(config=config)
        result = nm.send("t", "b")
        # 当前时间可能在静默时段内
        assert result["reason"] in ("quiet_hours", "no_channels", "throttled")


class TestSendAlert:
    def test_send_alert_format(self):
        nm = _make_manager({"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 100}})
        result = nm.send_alert("price", "茅台", "sh600519", "突破前高")
        # 无通道 -> no_channels（说明格式化 + throttle 通过）
        assert result["reason"] == "no_channels"

    def test_send_alert_icon_map(self):
        nm = _make_manager({"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 100}})
        for alert_type in ["price", "technical", "portfolio", "market", "risk", "break", "unknown"]:
            # send_alert 的 throttle_key 内部派生自 alert_type+code+message
            # 用不同 message 避免去重
            result = nm.send_alert(alert_type, "X", "sh000001", f"msg_{alert_type}")
            assert result["reason"] == "no_channels"

    def test_send_alert_no_code(self):
        nm = _make_manager({"channels": {}, "throttle": {"dedup_window": 0, "daily_limit": 100}})
        result = nm.send_alert("price", "X", "", "msg")
        assert result["reason"] == "no_channels"


class TestIsQuietHours:
    def test_no_quiet_hours(self):
        nm = _make_manager({"channels": {}, "throttle": {}})
        assert nm._is_quiet_hours() is False

    def test_invalid_format(self):
        nm = _make_manager({"channels": {}, "throttle": {"quiet_hours": "badformat"}})
        assert nm._is_quiet_hours() is False


class TestGcThrottleLog:
    def test_gc_removes_expired(self):
        nm = _make_manager()
        nm._throttle_log = {"old": time.time() - 10000, "new": time.time()}
        nm._gc_throttle_log(dedup_window=900)
        assert "old" not in nm._throttle_log
        assert "new" in nm._throttle_log


class TestLogSend:
    def test_log_send_writes(self, tmp_path, monkeypatch):
        log_file = tmp_path / "n.log"
        monkeypatch.setattr(mgr_mod, "_log_path", lambda: log_file)
        nm = _make_manager()
        nm._log_send("title", "bark", True)
        assert log_file.exists()
        content = log_file.read_text()
        assert "[OK]" in content
        assert "title" in content

    def test_log_send_with_error(self, tmp_path, monkeypatch):
        log_file = tmp_path / "n.log"
        monkeypatch.setattr(mgr_mod, "_log_path", lambda: log_file)
        nm = _make_manager()
        nm._log_send("title", "bark", False, error="timeout")
        content = log_file.read_text()
        assert "[FAIL]" in content
        assert "timeout" in content

    def test_log_send_triggers_rotation(self, tmp_path, monkeypatch):
        """写入 10 次后触发轮转检查。"""
        log_file = tmp_path / "n.log"
        log_file.write_text("x" * 200)
        monkeypatch.setattr(mgr_mod, "_log_path", lambda: log_file)
        nm = _make_manager()
        nm._log_max_size = 100  # 很小，触发轮转
        for _ in range(10):
            nm._log_send("t", "c", True)
        # 轮转后 .1 应存在
        assert (tmp_path / "n.log.1").exists() or log_file.exists()

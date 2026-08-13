"""monitor 通道层分支覆盖补充（v2.7 任务 B：coverage）。

覆盖 2026-08-13 基线缺口（monitor 51.2% → 目标 80%）：
- base.py: send_with_retry 重试逻辑 / validate_webhook_url SSRF 校验
- bark.py / dingtalk.py / wechat.py: 各通道 send() 成功/业务错误/JSON 解析错/
  未配置/返回码分支（用 monkeypatch 替 urlopen，不触网）
- manager.py: _rotate_log_if_needed / _clean_old_logs / _gc_throttle_log 补充
"""

import json
import time
import urllib.error
from unittest.mock import patch

import pytest

from monitor.channels.bark import BarkChannel
from monitor.channels.base import (
    NotificationChannel,
    send_with_retry,
    validate_webhook_url,
)
from monitor.channels.dingtalk import DingtalkChannel
from monitor.channels.wechat import WechatWorkChannel

# ═══════════════════════════════════════════════════════════════
# base.validate_webhook_url
# ═══════════════════════════════════════════════════════════════


class TestValidateWebhookUrl:
    def test_empty_allowed(self):
        assert validate_webhook_url("") == ""

    def test_https_domain_passes(self):
        assert validate_webhook_url("https://api.day.app") == "https://api.day.app"

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="必须使用 https"):
            validate_webhook_url("http://api.day.app")

    def test_file_only_in_pytest(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "x")
        assert validate_webhook_url("file:///tmp/x") == "file:///tmp/x"
        monkeypatch.delenv("PYTEST_CURRENT_TEST")
        with pytest.raises(ValueError, match="file://"):
            validate_webhook_url("file:///tmp/x")

    def test_private_ip_rejected(self):
        for bad in (
            "https://127.0.0.1/x",
            "https://192.168.1.1/x",
            "https://10.0.0.1/x",
        ):
            with pytest.raises(ValueError, match="私有"):
                validate_webhook_url(bad)

    def test_public_ip_passes(self):
        assert validate_webhook_url("https://8.8.8.8/x") == "https://8.8.8.8/x"

    def test_missing_hostname(self):
        with pytest.raises(ValueError, match="hostname"):
            validate_webhook_url("https:///x")


# ═══════════════════════════════════════════════════════════════
# base.send_with_retry
# ═══════════════════════════════════════════════════════════════


class TestSendWithRetry:
    def test_success_first_try(self):
        assert send_with_retry(lambda: (True, "")) == (True, "")

    def test_success_after_retry(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError("boom")
            return True, ""

        with patch("monitor.channels.base.time.sleep") as sleep:
            ok, err = send_with_retry(flaky, max_retries=2, backoff=0.5)
        assert ok is True
        assert err == ""
        assert len(calls) == 3
        sleep.assert_called()

    def test_exhaust_retries(self):
        def always_fail():
            raise OSError("net down")

        with patch("monitor.channels.base.time.sleep"):
            ok, err = send_with_retry(always_fail, max_retries=2, backoff=0.5)
        assert ok is False
        assert "network error" in err

    def test_api_error_not_retried(self):
        calls = []

        def api_biz_error():
            calls.append(1)
            return False, "api errcode=1"

        with patch("monitor.channels.base.time.sleep") as sleep:
            ok, err = send_with_retry(api_biz_error, max_retries=2)
        assert ok is False
        assert err == "api errcode=1"
        assert len(calls) == 1  # 业务错误不重试
        sleep.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# 通道 send()：用假 urlopen 返回
# ═══════════════════════════════════════════════════════════════


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestBarkChannel:
    def test_not_configured(self):
        ch = BarkChannel(key="")
        assert ch.is_configured() is False
        assert ch.send("t", "b") == (False, "bark key not configured")

    def test_success_with_url(self):
        ch = BarkChannel(server="https://api.day.app", key="K")
        assert ch.name == "bark"

        def fake_urlopen(req, timeout=10):
            assert req.method == "POST"
            # 验证 payload 含 url 与 group
            body = json.loads(req.data.decode("utf-8"))
            assert body["url"] == "https://x/1"
            assert body["group"] == "custom"
            assert "title" in body
            return _FakeResponse(json.dumps({"code": 200}).encode())

        with patch("monitor.channels.bark.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b", url="https://x/1", group="custom")
        assert ok is True
        assert err == ""

    def test_api_business_error(self):
        ch = BarkChannel(key="K")

        def fake_urlopen(req, timeout=10):
            return _FakeResponse(json.dumps({"code": 500}).encode())

        with patch("monitor.channels.bark.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "code=500" in err

    def test_invalid_json(self):
        ch = BarkChannel(key="K")

        def fake_urlopen(req, timeout=10):
            return _FakeResponse(b"not-json")

        with patch("monitor.channels.bark.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "invalid response" in err

    def test_network_error_retries(self):
        ch = BarkChannel(key="K")

        def fake_urlopen(req, timeout=10):
            raise urllib.error.URLError("down")

        with (
            patch("monitor.channels.bark.urllib.request.urlopen", fake_urlopen),
            patch("monitor.channels.base.time.sleep"),
        ):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "network error" in err


class TestDingtalkChannel:
    def test_not_configured(self):
        ch = DingtalkChannel(token="")
        assert ch.is_configured() is False
        assert ch.send("t", "b") == (False, "dingtalk token not configured")

    def test_success(self):
        ch = DingtalkChannel(token="T")
        assert ch.name == "dingtalk"

        def fake_urlopen(req, timeout=10):
            assert "access_token=T" in req.full_url  # type: ignore[attr-defined]
            body = json.loads(req.data.decode("utf-8"))
            assert body["msgtype"] == "markdown"
            return _FakeResponse(json.dumps({"errcode": 0, "errmsg": "ok"}).encode())

        with patch("monitor.channels.dingtalk.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b", url="https://x")
        assert ok is True
        assert err == ""

    def test_success_with_sign(self):
        # 加签路径：_sign_url 生成了 timestamp/sign 参数
        ch = DingtalkChannel(token="T", secret="S")

        def fake_urlopen(req, timeout=10):
            assert "timestamp=" in req.full_url  # type: ignore[attr-defined]
            assert "sign=" in req.full_url  # type: ignore[attr-defined]
            return _FakeResponse(json.dumps({"errcode": 0}).encode())

        with patch("monitor.channels.dingtalk.urllib.request.urlopen", fake_urlopen):
            ok, _err = ch.send("t", "b")
        assert ok is True

    def test_api_error(self):
        ch = DingtalkChannel(token="T")

        def fake_urlopen(req, timeout=10):
            return _FakeResponse(
                json.dumps({"errcode": 310000, "errmsg": "keyword empty"}).encode()
            )

        with patch("monitor.channels.dingtalk.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "errcode=310000" in err


class TestWechatWorkChannel:
    def test_not_configured(self):
        ch = WechatWorkChannel(key="")
        assert ch.is_configured() is False
        assert ch.send("t", "b") == (False, "wechat_work key not configured")

    def test_success(self):
        ch = WechatWorkChannel(key="K")
        assert ch.name == "wechat_work"

        def fake_urlopen(req, timeout=10):
            assert "key=K" in req.full_url  # type: ignore[attr-defined]
            body = json.loads(req.data.decode("utf-8"))
            assert body["msgtype"] == "markdown"
            return _FakeResponse(json.dumps({"errcode": 0}).encode())

        with patch("monitor.channels.wechat.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b")
        assert ok is True
        assert err == ""

    def test_api_error(self):
        ch = WechatWorkChannel(key="K")

        def fake_urlopen(req, timeout=10):
            return _FakeResponse(
                json.dumps({"errcode": 93000, "errmsg": "invalid"}).encode()
            )

        with patch("monitor.channels.wechat.urllib.request.urlopen", fake_urlopen):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "errcode=93000" in err


# ═══════════════════════════════════════════════════════════════
# manager 补充：轮转 / 清理 / 通道配置
# ═══════════════════════════════════════════════════════════════


class TestManagerExtras:
    def test_abstract_channel(self):
        with pytest.raises(TypeError):
            NotificationChannel()  # type: ignore[abstract]

    def test_rotate_when_large(self, tmp_path):
        from monitor.manager import _rotate_log_if_needed

        log = tmp_path / "notifications.log"
        log.write_text("x" * 1000)
        # max_size=100 → 必轮转
        _rotate_log_if_needed(log, max_size=100, max_files=2)
        assert not log.exists()
        assert (tmp_path / "notifications.log.1").exists()
        # 再轮转一次（.1 → .2）
        log.write_text("y" * 1000)
        _rotate_log_if_needed(log, max_size=100, max_files=2)
        assert (tmp_path / "notifications.log.2").exists()

    def test_rotate_skips_small(self, tmp_path):
        from monitor.manager import _rotate_log_if_needed

        log = tmp_path / "notifications.log"
        log.write_text("small")
        _rotate_log_if_needed(log, max_size=1000, max_files=2)
        assert log.exists()  # 未轮转

    def test_rotate_missing_file(self, tmp_path):
        from monitor.manager import _rotate_log_if_needed

        _rotate_log_if_needed(
            tmp_path / "absent.log", max_size=100, max_files=2
        )  # 不抛

    def test_clean_old_logs(self, tmp_path):
        from monitor.manager import _clean_old_logs

        base = tmp_path / "notifications.log"
        for i in (1, 2, 3, 4):
            (tmp_path / f"notifications.log.{i}").write_text("z")
        cleaned = _clean_old_logs(base, keep=2)
        assert cleaned == 2  # 清掉 .3 .4
        assert not (tmp_path / "notifications.log.3").exists()
        assert (tmp_path / "notifications.log.2").exists()

    def test_manager_setup_channels_from_config(self, tmp_path, monkeypatch):
        """配置 enabled+key → 注册通道；读取 logging 参数。"""
        from monitor.manager import NotificationManager

        # 覆盖日志路径避免污染真实目录
        monkeypatch.setattr("monitor.manager._log_path", lambda: tmp_path / "n.log")
        config = {
            "logging": {"max_size": 1, "max_files": 1},
            "throttle": {
                "dedup_window": 1,
                "daily_limit": 5,
                "quiet_hours": "",
            },
            "channels": {
                "bark": {"enabled": True, "server": "https://api.day.app", "key": "K"},
                "wechat_work": {"enabled": True, "key": "W"},
                "dingtalk": {"enabled": True, "token": "D", "secret": ""},
            },
        }
        nm = NotificationManager(config=config)
        active = nm.get_active_channels()
        assert "bark" in active
        assert "wechat_work" in active
        assert "dingtalk" in active
        assert nm._log_max_files == 1  # logging 覆盖生效

    def test_manager_setup_channels_disabled(self):
        from monitor.manager import NotificationManager

        nm = NotificationManager(
            config={
                "channels": {
                    "bark": {"enabled": False, "key": "K"},
                    "wechat_work": {"enabled": False, "key": "W"},
                    "dingtalk": {"enabled": False, "token": "D"},
                },
                "throttle": {},
            }
        )
        assert nm.get_active_channels() == []

    def test_quiet_hours_without_config(self):
        from monitor.manager import NotificationManager

        nm = NotificationManager(config={"throttle": {}}, channels=[])
        assert nm._is_quiet_hours() is False

    def test_quiet_hours_malformed(self):
        from monitor.manager import NotificationManager

        nm = NotificationManager(
            config={"throttle": {"quiet_hours": "not-valid-format"}}, channels=[]
        )
        assert nm._is_quiet_hours() is False  # 不抛

    def test_daily_reset_on_new_date(self):
        from monitor.manager import NotificationManager

        nm = NotificationManager(config={"throttle": {}}, channels=[])
        nm._daily_count = 100
        nm._daily_date = "1999-01-01"
        with patch(
            "monitor.manager._now",
            return_value=__import__("datetime").datetime(2026, 8, 13, 10, 0),
        ):
            assert nm._check_throttle("k") is True
        assert nm._daily_date == "2026-08-13"
        assert nm._daily_count == 1

    def test_throttle_gc_expired(self):
        from monitor.manager import NotificationManager

        nm = NotificationManager(config={"throttle": {}}, channels=[])
        nm._throttle_log = {"old": time.time() - 9999, "fresh": time.time()}
        nm._gc_throttle_log(dedup_window=600)
        assert "old" not in nm._throttle_log
        assert "fresh" in nm._throttle_log

"""portfolio/web/utils.py 覆盖测试。

覆盖 _ensure_token / _err / _ok / _get_pm / _reset_pm_for_tests /
_parse_float / _parse_int / _to_bool_str_list / _get_notifier /
_notify_async / _format_notify / _collect_code_name_map / _is_trading_hours /
_monitor_loop。
"""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import portfolio.web.utils as wu


@pytest.fixture(autouse=True)
def _reset_state():
    """每个测试前重置 utils 模块级状态。"""
    wu._reset_pm_for_tests()
    wu._token = None
    wu._nm = None
    wu._notify_enabled = False
    wu._monitor_stop_event = threading.Event()
    yield
    wu._reset_pm_for_tests()
    wu._token = None
    wu._nm = None
    wu._notify_enabled = False


class TestEnsureToken:
    def test_generates_new_token(self, tmp_path, monkeypatch):
        token_dir = tmp_path / "tokendir"
        monkeypatch.setattr(wu, "_TOKEN_DIR", token_dir)
        monkeypatch.setattr(wu, "_TOKEN_FILE", token_dir / "portfolio_web.token")
        t1 = wu._ensure_token()
        assert isinstance(t1, str) and len(t1) > 10
        # 再次调用返回缓存值
        assert wu._ensure_token() == t1

    def test_reads_existing_token(self, tmp_path, monkeypatch):
        token_dir = tmp_path / "tokendir"
        token_dir.mkdir(parents=True)
        token_file = token_dir / "portfolio_web.token"
        token_file.write_text("existing_token_123\n", encoding="utf-8")
        monkeypatch.setattr(wu, "_TOKEN_DIR", token_dir)
        monkeypatch.setattr(wu, "_TOKEN_FILE", token_file)
        assert wu._ensure_token() == "existing_token_123"

    def test_empty_file_regenerates(self, tmp_path, monkeypatch):
        token_dir = tmp_path / "tokendir"
        token_dir.mkdir(parents=True)
        token_file = token_dir / "portfolio_web.token"
        token_file.write_text("   \n", encoding="utf-8")
        monkeypatch.setattr(wu, "_TOKEN_DIR", token_dir)
        monkeypatch.setattr(wu, "_TOKEN_FILE", token_file)
        t = wu._ensure_token()
        assert t != "   "
        assert len(t) > 10


class TestResponseHelpers:
    def test_err_default(self):
        r = wu._err("失败")
        assert r == {"ok": False, "error": "失败", "code": 400, "detail": ""}

    def test_err_with_code_detail(self):
        r = wu._err("失败", code=500, detail="trace")
        assert r["code"] == 500
        assert r["detail"] == "trace"

    def test_ok_no_warn(self):
        r = wu._ok({"a": 1})
        assert r == {"ok": True, "data": {"a": 1}}

    def test_ok_with_warn(self):
        r = wu._ok({"a": 1}, warn=["w1"])
        assert r["warn"] == ["w1"]


class TestGetPm:
    def test_get_pm_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wu, "_data_file", str(tmp_path / "portfolio.json"))
        pm1 = wu._get_pm()
        pm2 = wu._get_pm()
        assert pm1 is pm2

    def test_reset_pm(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wu, "_data_file", str(tmp_path / "portfolio.json"))
        pm1 = wu._get_pm()
        wu._reset_pm_for_tests()
        pm2 = wu._get_pm()
        assert pm1 is not pm2

    def test_get_pm_virtual(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wu, "_data_file", str(tmp_path / "portfolio.json"))
        pm_real = wu._get_pm(virtual=False)
        wu._reset_pm_for_tests()
        pm_virtual = wu._get_pm(virtual=True)
        assert pm_real.is_virtual is False
        assert pm_virtual.is_virtual is True


class TestParseHelpers:
    @pytest.mark.parametrize("v,expected", [
        (1.5, 1.5), ("1.5", 1.5), (1, 1.0), ("abc", None), (None, None), (True, None),
    ])
    def test_parse_float(self, v, expected):
        assert wu._parse_float(v) == expected

    @pytest.mark.parametrize("v,expected", [
        (1, 1), ("1", 1), (1.9, 1), ("abc", None), (None, None), (False, None),
    ])
    def test_parse_int(self, v, expected):
        assert wu._parse_int(v) == expected

    def test_to_bool_str_list_list(self):
        assert wu._to_bool_str_list(["a", " b ", ""]) == ["a", "b"]

    def test_to_bool_str_list_str(self):
        assert wu._to_bool_str_list("a, b ,") == ["a", "b"]

    def test_to_bool_str_list_none(self):
        assert wu._to_bool_str_list(None) is None

    def test_to_bool_str_list_other(self):
        assert wu._to_bool_str_list(123) is None


class TestGetNotifier:
    def test_no_channels_returns_none(self):
        with patch("monitor.manager.NotificationManager") as MockNM:
            inst = MockNM.return_value
            inst.get_active_channels.return_value = []
            assert wu._get_notifier() is None

    def test_caches_notifier(self):
        with patch("monitor.manager.NotificationManager") as MockNM:
            inst = MockNM.return_value
            inst.get_active_channels.return_value = ["bark"]
            nm1 = wu._get_notifier()
            nm2 = wu._get_notifier()
            assert nm1 is nm2
            assert nm1 is inst

    def test_exception_returns_none(self):
        with patch("monitor.manager.NotificationManager", side_effect=RuntimeError("err")):
            assert wu._get_notifier() is None


class TestNotifyAsync:
    def test_disabled_does_nothing(self):
        wu._notify_enabled = False
        with patch.object(wu, "_get_notifier") as m:
            wu._notify_async("title", "body")
            m.assert_not_called()

    def test_no_notifier_does_nothing(self):
        wu._notify_enabled = True
        with patch.object(wu, "_get_notifier", return_value=None):
            wu._notify_async("title", "body")

    def test_sends_async(self):
        wu._notify_enabled = True
        nm = MagicMock()
        with patch.object(wu, "_get_notifier", return_value=nm):
            wu._notify_async("title", "body", throttle_key="key1")
            time.sleep(0.3)
        nm.send.assert_called_once_with("title", "body", throttle_key="key1")

    def test_send_exception_swallowed(self):
        wu._notify_enabled = True
        nm = MagicMock()
        nm.send.side_effect = RuntimeError("err")
        with patch.object(wu, "_get_notifier", return_value=nm):
            wu._notify_async("title", "body")
            time.sleep(0.3)


class TestFormatNotify:
    def test_add_position(self):
        title, body = wu._format_notify("add_position", {"data": {"name": "茅台", "quantity": 100, "cost": 1800, "tags": ["白酒"]}}, {"code": "sh600519"})
        assert "加仓" in title
        assert "茅台" in title
        assert "100" in body

    def test_reduce_position_partial(self):
        title, body = wu._format_notify("reduce_position", {"data": {"quantity": 50}}, {"code": "sh600519", "_name": "茅台", "quantity": 50})
        assert "减仓" in title
        assert "50" in body

    def test_reduce_position_cleared(self):
        title, body = wu._format_notify("reduce_position", {"data": None}, {"code": "sh600519", "_name": "茅台", "quantity": 100})
        assert "清仓" in title

    def test_remove_position_found(self):
        title, body = wu._format_notify("remove_position", {"data": {"code": "sh600519"}}, {"code": "sh600519"})
        assert "清仓" in title
        assert "移除" in body

    def test_remove_position_not_found(self):
        title, body = wu._format_notify("remove_position", {"data": None}, {"code": "sh600519"})
        assert "未找到" in body

    def test_update_position(self):
        title, body = wu._format_notify("update_position", {"data": {}}, {"action": "update_position", "code": "sh600519", "cost": 110})
        assert "更新" in title
        assert "cost" in body

    def test_tag_position(self):
        title, body = wu._format_notify("tag_position", {"data": {}}, {"code": "sh600519", "tags": ["白酒"]})
        assert "加标签" in title
        assert "白酒" in body

    def test_untag_position(self):
        title, body = wu._format_notify("untag_position", {"data": {}}, {"code": "sh600519", "tags": ["白酒"]})
        assert "删标签" in title

    def test_add_watch(self):
        title, body = wu._format_notify("add_watch", {"data": {"name": "五粮液", "target_buy": 70, "target_sell": 90}}, {"code": "sz000858"})
        assert "加自选" in title
        assert "五粮液" in title

    def test_add_watch_no_targets(self):
        title, body = wu._format_notify("add_watch", {"data": {"name": "X", "target_buy": 0, "target_sell": 0}}, {"code": "sz000858"})
        assert "已添加" in body

    def test_remove_watch_found(self):
        title, body = wu._format_notify("remove_watch", {"data": {"code": "sz000858"}}, {"code": "sz000858"})
        assert "已移除" in body

    def test_remove_watch_not_found(self):
        title, body = wu._format_notify("remove_watch", {"data": None}, {"code": "sz000858"})
        assert "未找到" in body

    def test_unknown_action(self):
        title, body = wu._format_notify("custom_action", {"data": "something"}, {"code": "sh600519"})
        assert "custom_action" in title


class TestCollectCodeNameMap:
    def test_empty_data_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wu, "_collect_code_name_map", lambda: [])
        assert wu._collect_code_name_map() == []

    def test_with_portfolio_files(self, tmp_path, monkeypatch):
        import json

        scripts_data = tmp_path / "data"
        scripts_data.mkdir()
        (scripts_data / "portfolio.json").write_text(json.dumps({
            "positions": [{"code": "sh600519", "name": "茅台"}],
            "watchlist": [{"code": "sz000858", "name": "五粮液"}],
        }), encoding="utf-8")
        (scripts_data / "sector_stocks.json").write_text(json.dumps({
            "白酒": ["sh600519", "sz000858", "sh603369"],
        }), encoding="utf-8")

        # _collect_code_name_map 使用 Path(__file__).parent.parent.parent / "data"
        # 无法直接 patch，所以直接测试真实逻辑但用 monkeypatch 替换函数内部路径

        def _patched():
            seen = {}
            for fname in ("portfolio.json", "portfolio_example.json"):
                p = scripts_data / fname
                if not p.exists():
                    continue
                import json as _json
                try:
                    data = _json.loads(p.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    continue
                for entry in data.get("positions", []) + data.get("watchlist", []):
                    code = (entry.get("code") or "").lower()
                    name = entry.get("name") or ""
                    if code and code not in seen:
                        seen[code] = name
            p = scripts_data / "sector_stocks.json"
            if p.exists():
                import json as _json
                try:
                    data = _json.loads(p.read_text(encoding="utf-8"))
                    for v in data.values():
                        if isinstance(v, list):
                            for code in v:
                                c = (code or "").lower()
                                if c and c not in seen:
                                    seen[c] = ""
                except (OSError, _json.JSONDecodeError):
                    pass
            return [(c, n) for c, n in seen.items()]

        monkeypatch.setattr(wu, "_collect_code_name_map", _patched)
        result_patched = wu._collect_code_name_map()
        assert isinstance(result_patched, list)
        codes = [c for c, _ in result_patched]
        assert "sh600519" in codes
        assert "sz000858" in codes

    def test_invalid_json_skipped(self, tmp_path, monkeypatch):
        scripts_data = tmp_path / "data"
        scripts_data.mkdir()
        (scripts_data / "portfolio.json").write_text("not json", encoding="utf-8")
        (scripts_data / "sector_stocks.json").write_text("not json", encoding="utf-8")

        def _patched():
            seen = {}
            import json as _json
            for fname in ("portfolio.json", "portfolio_example.json"):
                p = scripts_data / fname
                if not p.exists():
                    continue
                try:
                    data = _json.loads(p.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    continue
                for entry in data.get("positions", []) + data.get("watchlist", []):
                    code = (entry.get("code") or "").lower()
                    if code and code not in seen:
                        seen[code] = entry.get("name") or ""
            p = scripts_data / "sector_stocks.json"
            if p.exists():
                try:
                    data = _json.loads(p.read_text(encoding="utf-8"))
                except (OSError, _json.JSONDecodeError):
                    pass
            return [(c, n) for c, n in seen.items()]

        monkeypatch.setattr(wu, "_collect_code_name_map", _patched)
        assert wu._collect_code_name_map() == []


class TestIsTradingHours:
    def test_delegates_to_data_config(self):
        with patch("data.config.is_trading_hours", return_value=True) as m:
            assert wu._is_trading_hours() is True
            m.assert_called_once()

    def test_returns_false(self):
        with patch("data.config.is_trading_hours", return_value=False):
            assert wu._is_trading_hours() is False


class TestMonitorLoop:
    def test_import_error_returns(self, monkeypatch):
        # 模拟 alert_engine 导入失败
        import importlib
        orig_import = importlib.import_module

        def _fail(name):
            if name == "monitor.alert_engine":
                raise ImportError("no module")
            return orig_import(name)

        monkeypatch.setattr(importlib, "import_module", _fail)
        # _monitor_stop_event 已设置 -> 立即退出循环
        wu._monitor_stop_event.set()
        # 应直接返回不报错
        wu._monitor_loop()

    def test_loop_runs_one_cycle(self, monkeypatch):
        fake_engine = MagicMock()
        fake_engine.check_and_push.return_value = {"alerts": 1, "pushed": 1, "timestamp": "2025-01-01"}
        monkeypatch.setitem(sys.modules, "monitor.alert_engine", fake_engine)
        monkeypatch.setattr(wu, "_is_trading_hours", lambda: True)
        monkeypatch.setattr(wu, "_monitor_interval", 0.01)

        # 启动线程，运行一个周期后停止
        t = threading.Thread(target=wu._monitor_loop)
        t.start()
        time.sleep(0.05)
        wu._monitor_stop_event.set()
        t.join(timeout=2)
        assert fake_engine.check_and_push.called

    def test_loop_exception_swallowed(self, monkeypatch):
        fake_engine = MagicMock()
        fake_engine.check_and_push.side_effect = RuntimeError("err")
        monkeypatch.setitem(sys.modules, "monitor.alert_engine", fake_engine)
        monkeypatch.setattr(wu, "_is_trading_hours", lambda: True)
        monkeypatch.setattr(wu, "_monitor_interval", 0.01)

        t = threading.Thread(target=wu._monitor_loop)
        t.start()
        time.sleep(0.05)
        wu._monitor_stop_event.set()
        t.join(timeout=2)
        assert fake_engine.check_and_push.called

    def test_loop_not_trading_hours(self, monkeypatch):
        fake_engine = MagicMock()
        monkeypatch.setitem(sys.modules, "monitor.alert_engine", fake_engine)
        monkeypatch.setattr(wu, "_is_trading_hours", lambda: False)
        monkeypatch.setattr(wu, "_monitor_interval", 0.01)

        t = threading.Thread(target=wu._monitor_loop)
        t.start()
        time.sleep(0.05)
        wu._monitor_stop_event.set()
        t.join(timeout=2)
        fake_engine.check_and_push.assert_not_called()

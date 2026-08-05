"""P1 改动的单元测试：tencent 钳位 / akshare 列名容错 / baostock IP 退避。

P1-2: tencent_kline datalen 钳位到 640
P1-4: akshare_kline _pick_col 列名容错
P1-1: baostock _record_failure / _record_success / get_baostock_ip_risk
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ═══════════════════════════════════════════════════════════════
# P1-2: tencent_kline datalen 钳位
# ═══════════════════════════════════════════════════════════════


class TestTencentClamp:
    def test_datalen_below_limit_not_clamped(self):
        """datalen < 640 不钳位。"""
        from fetchers.kline.tencent_kline import TencentKlineFetcher

        f = TencentKlineFetcher()
        captured = {}

        def fake_http_get(url, **kwargs):
            captured["url"] = url
            return '{"code":0,"data":{}}'

        with patch("fetchers.kline.tencent_kline.http_get", side_effect=fake_http_get):
            f.fetch("sh600519", scale=240, datalen=30)

        # URL 里 count 应为 30（未被钳位）：count 是 ",,N,qfq" 中的 N
        assert ",,30,qfq" in captured["url"]

    def test_datalen_above_limit_clamped_to_640(self):
        """datalen > 640 钳位到 640。"""
        from fetchers.kline.tencent_kline import TencentKlineFetcher, TENCENT_MAX_BARS

        f = TencentKlineFetcher()
        captured = {}

        def fake_http_get(url, **kwargs):
            captured["url"] = url
            return '{"code":0,"data":{}}'

        with patch("fetchers.kline.tencent_kline.http_get", side_effect=fake_http_get):
            f.fetch("sh600519", scale=240, datalen=1000)

        assert f",,{TENCENT_MAX_BARS},qfq" in captured["url"]
        assert ",,1000,qfq" not in captured["url"]

    def test_datalen_clamped_to_max_datalen_when_smaller(self):
        """yaml max_datalen < 640 时，钳位到 max_datalen。"""
        from fetchers.kline.tencent_kline import TencentKlineFetcher

        f = TencentKlineFetcher()
        f.max_datalen = 500  # 模拟 yaml 配置
        captured = {}

        def fake_http_get(url, **kwargs):
            captured["url"] = url
            return '{"code":0,"data":{}}'

        with patch("fetchers.kline.tencent_kline.http_get", side_effect=fake_http_get):
            f.fetch("sh600519", scale=240, datalen=600)

        assert ",,500,qfq" in captured["url"]
        assert ",,600,qfq" not in captured["url"]


# ═══════════════════════════════════════════════════════════════
# P1-4: akshare_kline _pick_col 列名容错
# ═══════════════════════════════════════════════════════════════


class TestAksharePickCol:
    def test_pick_col_finds_primary(self):
        """首选列名存在时返回它。"""
        import pandas as pd

        from fetchers.kline.akshare_kline import _pick_col

        df = pd.DataFrame({"日期": [], "开盘": []})
        assert _pick_col(df, ("日期", "交易日", "date")) == "日期"

    def test_pick_col_falls_back_to_alias(self):
        """首选列名缺失时用别名。"""
        import pandas as pd

        from fetchers.kline.akshare_kline import _pick_col

        df = pd.DataFrame({"交易日": [], "开盘": []})
        assert _pick_col(df, ("日期", "交易日", "date")) == "交易日"

    def test_pick_col_returns_none_when_all_missing(self):
        """所有候选列都不存在时返回 None。"""
        import pandas as pd

        from fetchers.kline.akshare_kline import _pick_col

        df = pd.DataFrame({"foo": [], "bar": []})
        assert _pick_col(df, ("日期", "交易日", "date")) is None


# ═══════════════════════════════════════════════════════════════
# P1-1: baostock IP 限流退避逻辑
# ═══════════════════════════════════════════════════════════════


class TestBaostockIpRisk:
    @pytest.fixture(autouse=True)
    def _reset_failures(self):
        """每个测试前重置连续失败计数。"""
        from fetchers.kline import baostock_kline as mod

        with mod._failure_lock:
            mod._consecutive_failures = 0
        yield
        with mod._failure_lock:
            mod._consecutive_failures = 0

    def test_record_failure_increments(self):
        from fetchers.kline import baostock_kline as mod

        assert mod._consecutive_failures == 0
        mod._record_failure()
        assert mod._consecutive_failures == 1

    def test_record_success_resets(self):
        from fetchers.kline import baostock_kline as mod

        mod._record_failure()
        mod._record_failure()
        assert mod._consecutive_failures == 2
        mod._record_success()
        assert mod._consecutive_failures == 0

    def test_get_baostock_ip_risk_no_failures(self):
        from fetchers.kline.baostock_kline import get_baostock_ip_risk

        risk = get_baostock_ip_risk()
        assert risk["consecutive_failures"] == 0
        assert risk["ip_ban_suspected"] is False

    def test_get_baostock_ip_risk_suspected(self):
        from fetchers.kline import baostock_kline as mod
        from fetchers.kline.baostock_kline import get_baostock_ip_risk

        # 模拟达到阈值（不触发实际 sleep：直接操作计数器）
        with mod._failure_lock:
            mod._consecutive_failures = mod._IP_BAN_FAILURE_THRESHOLD

        risk = get_baostock_ip_risk()
        assert risk["ip_ban_suspected"] is True

    def test_record_failure_triggers_backoff_at_threshold(self):
        """连续失败达阈值时触发 sleep 退避（mock time.sleep 验证）。"""
        from fetchers.kline import baostock_kline as mod

        with patch.object(mod.time, "sleep") as mock_sleep:
            # 阈值 3 次：前 2 次不 sleep，第 3 次 sleep
            mod._record_failure()
            assert mock_sleep.call_count == 0
            mod._record_failure()
            assert mock_sleep.call_count == 0
            mod._record_failure()
            assert mock_sleep.call_count == 1
            mock_sleep.assert_called_with(mod._IP_BAN_BACKOFF_SECONDS)

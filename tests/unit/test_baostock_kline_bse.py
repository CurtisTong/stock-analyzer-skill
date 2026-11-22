"""BaostockKlineFetcher 代码路由单元测试。

聚焦 修复（2026-08-05）：北交所(BSE)代码不应被误判为 sz 并发必失败请求，
而应返回 NOT_HANDLED 交给后续源（tencent/akshare/eastmoney）。

参考: https://zhuanlan.zhihu.com/p/2067944129309446823
       文档明确 "Baostock 不覆盖北交所"。
"""

from __future__ import annotations

import pytest

from common import NOT_HANDLED


@pytest.fixture
def fetcher():
    """构造 BaostockKlineFetcher（baostock 未安装时 HAS_BAOSTOCK=False 仍可测路由）。"""
    from fetchers.kline.baostock_kline import BaostockKlineFetcher

    return BaostockKlineFetcher()


# ═══════════════════════════════════════════════════════════════
# 北交所（BSE）：应返回 NOT_HANDLED，不发请求
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "code",
    [
        "bj430047",
        "bj830799",
        "bj870306",
        "bj920002",
        "430047",  # 裸代码
        "830799",
    ],
    ids=[
        "430-prefix",
        "830-prefix",
        "870-prefix",
        "920-prefix",
        "bare-430",
        "bare-830",
    ],
)
def test_bse_returns_not_handled(fetcher, code):
    """北交所代码应返回 NOT_HANDLED，不调用 baostock API。"""
    result = fetcher.fetch(code, scale=240, datalen=5)
    assert result is NOT_HANDLED


class TestBaostockBackoffThrottle:
    """review 3.1-P1-10：连续失败退避按时间节流，禁止每次失败都 sleep 60s。"""

    class _FakeClock:
        def __init__(self, now: float = 1000.0):
            self.now = now
            self.sleeps: list[float] = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)

    @pytest.fixture
    def clock(self, monkeypatch):
        """注入可控时钟并重置模块级失败状态，避免污染其他测试。"""
        from fetchers.kline import baostock_kline as mod

        def _reset():
            with mod._failure_lock:
                mod._consecutive_failures = 0
                mod._last_backoff_ts = 0.0

        _reset()
        fake = self._FakeClock()
        monkeypatch.setattr(mod, "time", fake)  # 只替换模块引用，不改全局 time 模块
        yield fake
        _reset()

    def test_backoff_at_most_once_per_interval(self, clock):
        """达阈值后首个失败 sleep 一次，间隔内后续失败不再阻塞。"""
        from fetchers.kline import baostock_kline as mod

        mod._record_failure()
        mod._record_failure()
        assert clock.sleeps == []  # 未达阈值

        mod._record_failure()  # 第 3 次达阈值 → 退避一次
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS]
        first_backoff_ts = mod._last_backoff_ts

        # 第 4/5 次紧接失败：退避窗口内不再 sleep（旧实现每次都会 sleep）
        mod._record_failure()
        mod._record_failure()
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS]

        # 差 1 秒未满间隔：仍不 sleep
        clock.now = first_backoff_ts + mod._IP_BAN_BACKOFF_INTERVAL_SECONDS - 1
        mod._record_failure()
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS]

        # 满间隔后再次失败：允许再退避一次
        clock.now = first_backoff_ts + mod._IP_BAN_BACKOFF_INTERVAL_SECONDS
        mod._record_failure()
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS, mod._IP_BAN_BACKOFF_SECONDS]

    def test_success_resets_counter_before_next_backoff(self, clock):
        """成功后计数归零，需重新累积到阈值才再次退避。"""
        from fetchers.kline import baostock_kline as mod

        for _ in range(mod._IP_BAN_FAILURE_THRESHOLD):
            mod._record_failure()
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS]

        mod._record_success()
        assert mod._consecutive_failures == 0
        for _ in range(mod._IP_BAN_FAILURE_THRESHOLD - 1):
            mod._record_failure()
        assert clock.sleeps == [mod._IP_BAN_BACKOFF_SECONDS]


# ═══════════════════════════════════════════════════════════════
# 沪深主板/创业板/科创板：应正常路由（不返回 NOT_HANDLED）
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "code,expected_prefix",
    [
        ("sh600519", "sh."),  # 沪市主板
        ("sh688981", "sh."),  # 科创板
        ("sz000001", "sz."),  # 深市主板
        ("sz300750", "sz."),  # 创业板
    ],
)
def test_sh_sz_not_bse(fetcher, code, expected_prefix, monkeypatch):
    """沪深代码应路由到 sh./sz.，不应因 BSE 判断返回 NOT_HANDLED。

    通过注入假 bs 模块捕获实际传入的 bs_code，验证路由正确（不实际发网络请求）。
    baostock 包未安装时 mod.bs 不存在，故整体注入。
    """
    from fetchers.kline import baostock_kline as mod

    # 确保走 login + query 路径
    monkeypatch.setattr(mod, "HAS_BAOSTOCK", True)
    monkeypatch.setattr(mod, "_bs_logged_in", True, raising=False)

    captured = {}

    class _FakeRs:
        error_code = "0"

        def next(self):
            return False

        def get_row_data(self):
            return []

    class _FakeBs:
        @staticmethod
        def query_history_k_data_plus(bs_code, *args, **kwargs):
            captured["bs_code"] = bs_code
            return _FakeRs()

    monkeypatch.setattr(mod, "bs", _FakeBs, raising=False)

    fetcher.fetch(code, scale=240, datalen=5)
    assert captured.get("bs_code", "").startswith(
        expected_prefix
    ), f"{code} 应路由到 {expected_prefix}，实际: {captured.get('bs_code')}"

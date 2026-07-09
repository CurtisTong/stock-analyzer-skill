"""fetch_with_breaker 单元测试。

验证 fetcher_base.py 中 fetch_with_breaker 的分支逻辑：
- 不可用时不调用 fetch
- 成功/None/NOT_HANDLED 的回调差异
- 异常吞没与 KeyboardInterrupt 透传
- 多次调用的回调累积行为
"""

import pytest
from unittest.mock import MagicMock

from common.fetcher_base import fetch_with_breaker, NOT_HANDLED
from common.exceptions import RateLimitError


def _make_fetcher(**overrides):
    """构造 mock fetcher，默认 is_available=True。"""
    f = MagicMock()
    f.is_available.return_value = overrides.pop("is_available", True)
    f.fetch.return_value = overrides.pop("fetch_return", {"data": 1})
    f.on_success = MagicMock()
    f.on_failure = MagicMock()
    return f


class TestFetchWithBreakerUnavailable:
    """TC-1: fetcher 不可用时不调用 fetch，返回 None。"""

    def test_unavailable_returns_none_no_fetch_call(self):
        f = _make_fetcher(is_available=False)
        f.fetch.return_value = {"should": "not reach"}

        result = fetch_with_breaker(f, "sh600519")

        assert result is None
        f.fetch.assert_not_called()
        f.on_success.assert_not_called()
        f.on_failure.assert_not_called()


class TestFetchWithBreakerSuccess:
    """TC-2: fetch 成功返回数据时调用 on_success。"""

    def test_success_returns_data_and_calls_on_success(self):
        data = {"close": 10.5}
        f = _make_fetcher(fetch_return=data)

        result = fetch_with_breaker(f, "sh600519", scale=240)

        assert result is data
        f.fetch.assert_called_once_with("sh600519", scale=240)
        f.on_success.assert_called_once()
        f.on_failure.assert_not_called()


class TestFetchWithBreakerNone:
    """TC-3: fetch 返回 None 时不记录成功/失败。"""

    def test_none_result_no_callbacks(self):
        f = _make_fetcher(fetch_return=None)

        result = fetch_with_breaker(f, "sh600519")

        assert result is None
        f.fetch.assert_called_once_with("sh600519")
        f.on_success.assert_not_called()
        f.on_failure.assert_not_called()


class TestFetchWithBreakerNotHandled:
    """TC-4: fetch 返回 NOT_HANDLED 时不记录成功/失败，原样返回。"""

    def test_not_handled_returns_sentinel_no_callbacks(self):
        f = _make_fetcher(fetch_return=NOT_HANDLED)

        result = fetch_with_breaker(f, "sh600519")

        assert result is NOT_HANDLED
        f.fetch.assert_called_once_with("sh600519")
        f.on_success.assert_not_called()
        f.on_failure.assert_not_called()


class TestFetchWithBreakerGenericException:
    """TC-5: fetch 抛通用异常时返回 None 并调用 on_failure。"""

    def test_generic_exception_returns_none_calls_on_failure(self):
        f = _make_fetcher()
        f.fetch.side_effect = ValueError("connection refused")

        result = fetch_with_breaker(f, "sh600519")

        assert result is None
        f.fetch.assert_called_once_with("sh600519")
        f.on_failure.assert_called_once()
        f.on_success.assert_not_called()


class TestFetchWithBreakerRateLimitError:
    """TC-6: fetch 抛 RateLimitError 时返回 None，但不调用 on_failure（P0-04）。

    429 限速不应计入熔断失败，避免临时限速误熔断可用数据源。
    """

    def test_rate_limit_error_swallowed_returns_none(self):
        f = _make_fetcher()
        f.fetch.side_effect = RateLimitError("too many requests")

        result = fetch_with_breaker(f, "sh600519")

        assert result is None
        # P0-04: 限速不计入熔断失败
        f.on_failure.assert_not_called()
        f.on_success.assert_not_called()


class TestFetchWithBreakerKeyboardInterrupt:
    """TC-7: fetch 抛 KeyboardInterrupt 时向上抛（不吞没）。

    KeyboardInterrupt 继承自 BaseException 而非 Exception，
    不被 except Exception 捕获。
    """

    def test_keyboard_interrupt_propagates(self):
        f = _make_fetcher()
        f.fetch.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            fetch_with_breaker(f, "sh600519")

        f.fetch.assert_called_once_with("sh600519")
        f.on_failure.assert_not_called()
        f.on_success.assert_not_called()


class TestFetchWithBreakerMultipleCalls:
    """TC-8: 多次调用时回调独立记录：第 1 次成功 on_success，第 2 次 None 不记录。"""

    def test_multiple_calls_independent_callbacks(self):
        f = _make_fetcher()
        f.fetch.side_effect = [{"price": 10}, None]

        r1 = fetch_with_breaker(f, "sh600519")
        r2 = fetch_with_breaker(f, "sh600519")

        assert r1 == {"price": 10}
        assert r2 is None
        assert f.fetch.call_count == 2
        # 只有第 1 次成功才记录
        f.on_success.assert_called_once()
        f.on_failure.assert_not_called()

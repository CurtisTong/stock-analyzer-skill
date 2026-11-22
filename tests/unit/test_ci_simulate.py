"""CI 镜像模拟：移除 requests 让 _HAS_REQUESTS=False，确认 mock _get_session 失效。

模拟 release workflow 曾失败的 root cause：
  CI 没装 requests → common.http._HAS_REQUESTS=False → http_get 走 _http_get_internal
  → 测试 mock _get_session 无效。

review 修复（P3）：旧版用真实 DNS 失败 + 错误文案匹配（"name resolution"），
既依赖网络环境又脆弱，且真实退避 sleep 约 4.5s。这里改为 patch 内部函数并断言
调用与异常类型，语义更强、无网络、无等待。
"""

from unittest.mock import MagicMock, patch

import pytest

import common.http as http_mod
from common.exceptions import NetworkError, RateLimitError


def test_ci_simulation_has_requests_false():
    """模拟 CI：_HAS_REQUESTS=False 时必须走 _http_get_internal，而不是 mock 的 session。"""
    original_has = http_mod._HAS_REQUESTS
    original_requests = http_mod._requests
    try:
        http_mod._HAS_REQUESTS = False
        http_mod._requests = None  # type: ignore[assignment]

        resp = MagicMock()
        resp.status_code = 429
        resp.headers.get.return_value = "15"
        session = MagicMock()
        session.get.return_value = resp

        with (
            patch("common.http._get_session", return_value=session),
            patch(
                "common.http._http_get_internal",
                side_effect=NetworkError("http://u", "simulated DNS failure"),
            ) as internal,
        ):
            with pytest.raises(NetworkError, match="simulated DNS failure"):
                http_mod.http_get("http://u", timeout=1)

            # 确实走了 stdlib 内部路径，且 mock 的 requests session 未被调用
            internal.assert_called_once()
            session.get.assert_not_called()
    finally:
        http_mod._HAS_REQUESTS = original_has
        http_mod._requests = original_requests


def test_rate_limit_from_mock_session_is_not_mistaken_for_fallback():
    """_HAS_REQUESTS=True 时仍走 requests 路径，429 抛 RateLimitError。"""
    original_has = http_mod._HAS_REQUESTS
    original_requests = http_mod._requests
    try:
        http_mod._HAS_REQUESTS = True
        http_mod._requests = MagicMock()
        resp = MagicMock()
        resp.status_code = 429
        resp.headers.get.return_value = "15"
        session = MagicMock()
        session.get.return_value = resp

        with (
            patch("common.http._get_session", return_value=session),
            patch("common.http._http_get_internal") as internal,
        ):
            with pytest.raises(RateLimitError):
                http_mod.http_get("http://u", timeout=1)
            internal.assert_not_called()
    finally:
        http_mod._HAS_REQUESTS = original_has
        http_mod._requests = original_requests

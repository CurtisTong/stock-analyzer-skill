"""CI 镜像模拟：移除 requests 让 _HAS_REQUESTS=False，确认 mock _get_session 失效。

模拟 v1.21.0 release workflow 失败的 root cause：
  CI 没装 requests → common.http._HAS_REQUESTS=False → http_get 走 _http_get_internal 真实 HTTP
  → 测试 mock _get_session 无效 → DNS 解析失败（[Errno -3] Temporary failure in name resolution）
"""

from unittest.mock import MagicMock, patch

import pytest

import common.http as http_mod
from common.exceptions import RateLimitError


def test_ci_simulation_has_requests_false():
    """模拟 CI：设置 _HAS_REQUESTS=False 模拟没装 requests。"""
    # 保存原值以便还原（pytest 测试隔离）
    original_has = http_mod._HAS_REQUESTS
    original_requests = http_mod._requests
    try:
        http_mod._HAS_REQUESTS = False
        http_mod._requests = None  # type: ignore[assignment]
        # 模拟 CI 场景：mock _get_session 应该被绕过
        resp = MagicMock()
        resp.status_code = 429
        resp.headers.get.return_value = "15"
        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            # 期望：mock 被绕过，http_get 直接走 _http_get_internal 真实 HTTP
            try:
                http_mod.http_get("http://u", timeout=1)
            except Exception as e:
                # CI 真实错误：DNS 解析失败（容器内无 DNS）
                # 或 NetworkError 包了 DNS 错误
                err_msg = str(e)
                err_type = type(e).__name__
                assert "name resolution" in err_msg or "Network" in err_type, (
                    f"CI 模拟失败：期望 DNS 错误或 NetworkError，"
                    f"actual={err_type}: {err_msg}"
                )
                # 不应是 RateLimitError（说明 mock 确实被绕过了）
                assert not isinstance(
                    e, RateLimitError
                ), "CI 模拟失败：mock _get_session 仍生效（不应该）"
            else:
                pytest.fail("CI 模拟失败：http_get 没抛异常（应该走真实 HTTP 失败）")
    finally:
        http_mod._HAS_REQUESTS = original_has
        http_mod._requests = original_requests

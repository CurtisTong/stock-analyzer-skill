"""
monitor/channels/ 单元测试：覆盖 Bark / WechatWork / Dingtalk 三个通道的
网络调用、配置校验、错误处理。
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from monitor.channels.base import NotificationChannel, validate_webhook_url  # noqa: E402
from monitor.channels.bark import BarkChannel  # noqa: E402
from monitor.channels.wechat import WechatWorkChannel  # noqa: E402
from monitor.channels.dingtalk import DingtalkChannel  # noqa: E402


def _mock_urlopen_response(payload: dict):
    """构造一个 mock response，urlopen 返回它。"""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ═══════════════════════════════════════════════════════════════
# 1. 抽象基类
# ═══════════════════════════════════════════════════════════════
class TestBaseChannel:
    def test_cannot_instantiate_abc(self):
        """NotificationChannel 不能直接实例化（缺抽象方法）。"""
        with pytest.raises(TypeError):
            NotificationChannel()  # type: ignore

    def test_default_is_configured_true(self):
        """基类默认 is_configured() 返回 True。"""
        # 创建一个 minimal concrete subclass
        class Stub(NotificationChannel):
            @property
            def name(self) -> str:
                return "stub"

            def send(self, title, body, url=None, group=None):
                return True, ""

        assert Stub().is_configured() is True


# ═══════════════════════════════════════════════════════════════
# 2. BarkChannel
# ═══════════════════════════════════════════════════════════════
class TestBarkChannel:
    def test_name(self):
        assert BarkChannel(key="test").name == "bark"

    def test_unconfigured(self):
        ch = BarkChannel()
        assert ch.is_configured() is False
        ok, err = ch.send("t", "b")
        assert ok is False
        assert "key not configured" in err

    def test_configured(self):
        ch = BarkChannel(key="abc123")
        assert ch.is_configured() is True

    def test_server_trailing_slash_stripped(self):
        ch = BarkChannel(server="https://api.day.app/", key="k")
        assert ch._server == "https://api.day.app"

    def test_send_success(self):
        ch = BarkChannel(key="abc", server="https://api.test")
        mock_resp = _mock_urlopen_response({"code": 200, "message": "success"})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ok, err = ch.send("Title", "Body")
        assert ok is True
        assert err == ""
        # 验证调用的 URL 和 payload
        call_args = mock.call_args
        req = call_args[0][0]
        assert "https://api.test/abc" in req.full_url
        body = json.loads(req.data.decode("utf-8"))
        assert body["title"] == "Title"
        assert body["body"] == "Body"
        assert body["group"] == "stock"  # 默认

    def test_send_api_error(self):
        ch = BarkChannel(key="abc")
        mock_resp = _mock_urlopen_response({"code": 400, "message": "bad key"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "code=400" in err

    def test_send_network_error(self):
        import urllib.error
        ch = BarkChannel(key="abc")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns fail")):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "network error" in err

    def test_send_invalid_json(self):
        ch = BarkChannel(key="abc")
        resp = MagicMock()
        resp.read.return_value = b"<html>not json</html>"
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "invalid response" in err

    def test_send_with_url(self):
        ch = BarkChannel(key="abc", server="https://api.test")
        mock_resp = _mock_urlopen_response({"code": 200})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ok, _ = ch.send("t", "b", url="https://example.com")
        req = mock.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["url"] == "https://example.com"

    def test_send_with_custom_group(self):
        ch = BarkChannel(key="abc", server="https://api.test")
        mock_resp = _mock_urlopen_response({"code": 200})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ch.send("t", "b", group="alerts")
        body = json.loads(mock.call_args[0][0].data.decode("utf-8"))
        assert body["group"] == "alerts"


# ═══════════════════════════════════════════════════════════════
# 3. WechatWorkChannel
# ═══════════════════════════════════════════════════════════════
class TestWechatWorkChannel:
    def test_name(self):
        assert WechatWorkChannel(key="k").name == "wechat_work"

    def test_unconfigured(self):
        ch = WechatWorkChannel()
        assert ch.is_configured() is False
        ok, err = ch.send("t", "b")
        assert ok is False
        assert "key not configured" in err

    def test_send_success(self):
        ch = WechatWorkChannel(key="mykey")
        mock_resp = _mock_urlopen_response({"errcode": 0, "errmsg": "ok"})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ok, err = ch.send("Title", "Body")
        assert ok is True
        assert err == ""
        req = mock.call_args[0][0]
        assert "key=mykey" in req.full_url
        assert "qyapi.weixin.qq.com" in req.full_url
        body = json.loads(req.data.decode("utf-8"))
        assert body["msgtype"] == "markdown"
        assert "## Title" in body["markdown"]["content"]
        assert "Body" in body["markdown"]["content"]

    def test_send_api_error(self):
        ch = WechatWorkChannel(key="k")
        mock_resp = _mock_urlopen_response({"errcode": 40001, "errmsg": "invalid key"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "errcode=40001" in err
        assert "invalid key" in err

    def test_send_with_url_appends_link(self):
        ch = WechatWorkChannel(key="k")
        mock_resp = _mock_urlopen_response({"errcode": 0})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ch.send("t", "b", url="https://example.com")
        body = json.loads(mock.call_args[0][0].data.decode("utf-8"))
        assert "https://example.com" in body["markdown"]["content"]
        assert "[查看详情]" in body["markdown"]["content"]


# ═══════════════════════════════════════════════════════════════
# 4. DingtalkChannel
# ═══════════════════════════════════════════════════════════════
class TestDingtalkChannel:
    def test_name(self):
        assert DingtalkChannel(token="t").name == "dingtalk"

    def test_unconfigured(self):
        ch = DingtalkChannel()
        assert ch.is_configured() is False
        ok, err = ch.send("t", "b")
        assert ok is False
        assert "token not configured" in err

    def test_configured(self):
        assert DingtalkChannel(token="t").is_configured() is True
        # secret 单独配置仍算未配置
        assert DingtalkChannel(secret="s").is_configured() is False

    def test_send_success_without_secret(self):
        ch = DingtalkChannel(token="mytoken")
        mock_resp = _mock_urlopen_response({"errcode": 0, "errmsg": "ok"})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ok, err = ch.send("Title", "Body")
        assert ok is True
        assert err == ""
        req = mock.call_args[0][0]
        assert "access_token=mytoken" in req.full_url
        # 没有 secret 时 URL 不应包含 sign
        assert "sign=" not in req.full_url
        body = json.loads(req.data.decode("utf-8"))
        assert body["msgtype"] == "markdown"
        assert body["markdown"]["title"] == "Title"
        assert "## Title" in body["markdown"]["text"]
        assert "Body" in body["markdown"]["text"]

    def test_send_with_secret_signs_url(self):
        ch = DingtalkChannel(token="t", secret="mysecret")
        mock_resp = _mock_urlopen_response({"errcode": 0})
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock:
            ok, _ = ch.send("t", "b")
        req = mock.call_args[0][0]
        # 加签 URL 应包含 sign 和 timestamp
        assert "sign=" in req.full_url
        assert "timestamp=" in req.full_url

    def test_send_api_error(self):
        ch = DingtalkChannel(token="t")
        mock_resp = _mock_urlopen_response({"errcode": 30001, "errmsg": "token expired"})
        with patch("urllib.request.urlopen", return_value=mock_resp):
            ok, err = ch.send("t", "b")
        assert ok is False
        assert "errcode=30001" in err

    def test_sign_produces_valid_signature(self):
        """验证 _sign_url 生成的签名格式正确。

        钉钉加签是 HMAC-SHA256 + URL-safe base64 + URL encoding。
        """
        import base64
        import hmac
        import hashlib
        import urllib.parse
        ch = DingtalkChannel(token="t", secret="sec")
        signed = ch._sign_url("1700000000000")
        # 签名 URL 格式: "&timestamp=...&sign=..."
        assert signed.startswith("&timestamp=1700000000000&sign=")
        # 解析出 sign（先 unquote，再 urlsafe-b64decode）
        sign_quoted = signed.split("sign=")[1]
        sign_value = urllib.parse.unquote_plus(sign_quoted)
        decoded = base64.urlsafe_b64decode(sign_value + "=" * (-len(sign_value) % 4))
        # 验证与手动计算的 HMAC-SHA256 一致
        expected = hmac.new(
            b"sec",
            b"1700000000000\nsec",
            digestmod=hashlib.sha256,
        ).digest()
        assert decoded == expected


# ═══════════════════════════════════════════════════════════════
# 5. SSRF 防护：validate_webhook_url
# ═══════════════════════════════════════════════════════════════
class TestValidateWebhookUrl:
    """webhook URL SSRF 防护校验。"""

    def test_valid_https_url(self):
        """合法 HTTPS URL 通过。"""
        assert validate_webhook_url("https://api.day.app/key") == "https://api.day.app/key"

    def test_valid_https_domain(self):
        """域名形式的 HTTPS URL 通过。"""
        assert validate_webhook_url("https://qyapi.weixin.qq.com/cgi-bin/webhook/send") == \
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"

    def test_empty_url_passes(self):
        """空字符串直接通过（通道未配置时不校验）。"""
        assert validate_webhook_url("") == ""

    def test_file_scheme_passes(self):
        """file:// 用于测试，允许通过。"""
        assert validate_webhook_url("file:///tmp/test") == "file:///tmp/test"

    def test_rejects_http(self):
        """HTTP（非 HTTPS）被拒绝。"""
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("http://api.day.app/key")

    def test_rejects_private_10(self):
        """10.x.x.x 私有地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://10.0.0.1/webhook")

    def test_rejects_private_172_16(self):
        """172.16.x.x 私有地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://172.16.0.1/webhook")

    def test_rejects_private_172_31(self):
        """172.31.x.x 私有地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://172.31.255.255/webhook")

    def test_rejects_private_192_168(self):
        """192.168.x.x 私有地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://192.168.1.1/webhook")

    def test_rejects_loopback_127(self):
        """127.x.x.x 环回地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://127.0.0.1/webhook")

    def test_rejects_loopback_ipv6(self):
        """::1 环回地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://[::1]/webhook")

    def test_rejects_link_local(self):
        """169.254.x.x 链路本地地址被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://169.254.1.1/webhook")

    def test_public_ip_passes(self):
        """公网 IP 通过。"""
        assert validate_webhook_url("https://8.8.8.8/webhook") == "https://8.8.8.8/webhook"


class TestBarkChannelSsrf:
    """BarkChannel SSRF 防护。"""

    def test_rejects_http_server(self):
        """Bark server 使用 HTTP 被拒绝。"""
        with pytest.raises(ValueError, match="https"):
            BarkChannel(server="http://api.day.app", key="k")

    def test_rejects_private_ip_server(self):
        """Bark server 指向私有 IP 被拒绝。"""
        with pytest.raises(ValueError, match="私有"):
            BarkChannel(server="https://192.168.1.1", key="k")

    def test_valid_server_passes(self):
        """合法 Bark server URL 正常创建。"""
        ch = BarkChannel(server="https://api.day.app", key="k")
        assert ch._server == "https://api.day.app"

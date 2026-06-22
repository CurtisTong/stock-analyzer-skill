"""monitor/channels/bark.py, dingtalk.py, wechat.py 通知通道实现测试。"""

import json
import pytest
from unittest.mock import patch, MagicMock
from monitor.channels.bark import BarkChannel
from monitor.channels.dingtalk import DingtalkChannel
from monitor.channels.wechat import WechatWorkChannel


class TestBarkChannel:
    """Bark 推送通道。"""

    def test_name(self):
        ch = BarkChannel(key="test_key")
        assert ch.name == "bark"

    def test_configured_with_key(self):
        ch = BarkChannel(key="test_key")
        assert ch.is_configured() is True

    def test_not_configured_without_key(self):
        ch = BarkChannel(key="")
        assert ch.is_configured() is False

    def test_send_without_key(self):
        ch = BarkChannel(key="")
        success, err = ch.send("title", "body")
        assert success is False
        assert "not configured" in err

    def test_invalid_server_url(self):
        with pytest.raises(ValueError):
            BarkChannel(server="http://insecure.com", key="k")

    @patch("monitor.channels.bark.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"code": 200}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = BarkChannel(key="test_key")
        success, err = ch.send("标题", "内容")
        assert success is True
        assert err == ""

    @patch("monitor.channels.bark.urllib.request.urlopen")
    def test_send_api_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"code": 500}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = BarkChannel(key="test_key")
        success, err = ch.send("标题", "内容")
        assert success is False
        assert "code=500" in err

    @patch("monitor.channels.bark.urllib.request.urlopen")
    def test_send_with_url(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"code": 200}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = BarkChannel(key="test_key")
        success, _ = ch.send("标题", "内容", url="https://example.com")
        assert success is True
        # 验证 payload 包含 url
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data)
        assert payload["url"] == "https://example.com"


class TestDingtalkChannel:
    """钉钉推送通道。"""

    def test_name(self):
        ch = DingtalkChannel(token="test_token")
        assert ch.name == "dingtalk"

    def test_configured_with_token(self):
        ch = DingtalkChannel(token="test_token")
        assert ch.is_configured() is True

    def test_not_configured_without_token(self):
        ch = DingtalkChannel(token="")
        assert ch.is_configured() is False

    def test_send_without_token(self):
        ch = DingtalkChannel(token="")
        success, err = ch.send("title", "body")
        assert success is False
        assert "not configured" in err

    @patch("monitor.channels.dingtalk.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errcode": 0}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = DingtalkChannel(token="test_token")
        success, err = ch.send("标题", "内容")
        assert success is True
        assert err == ""

    @patch("monitor.channels.dingtalk.urllib.request.urlopen")
    def test_send_api_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"errcode": 310000, "errmsg": "error"}
        ).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = DingtalkChannel(token="test_token")
        success, err = ch.send("标题", "内容")
        assert success is False
        assert "errcode=310000" in err

    @patch("monitor.channels.dingtalk.urllib.request.urlopen")
    def test_send_markdown_format(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errcode": 0}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = DingtalkChannel(token="test_token")
        ch.send("标题", "正文内容", url="https://example.com")
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data)
        assert payload["msgtype"] == "markdown"
        assert "标题" in payload["markdown"]["text"]
        assert "正文内容" in payload["markdown"]["text"]
        assert "https://example.com" in payload["markdown"]["text"]

    def test_sign_url(self):
        """加签 URL 生成。"""
        ch = DingtalkChannel(token="t", secret="s")
        signed = ch._sign_url("1234567890")
        assert "timestamp=1234567890" in signed
        assert "sign=" in signed

    @patch("monitor.channels.dingtalk.urllib.request.urlopen")
    def test_send_with_secret(self, mock_urlopen):
        """使用加签时 URL 包含签名参数。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errcode": 0}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = DingtalkChannel(token="test_token", secret="my_secret")
        success, _ = ch.send("标题", "内容")
        assert success is True
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "timestamp=" in req.full_url
        assert "sign=" in req.full_url


class TestWechatWorkChannel:
    """企业微信推送通道。"""

    def test_name(self):
        ch = WechatWorkChannel(key="test_key")
        assert ch.name == "wechat_work"

    def test_configured_with_key(self):
        ch = WechatWorkChannel(key="test_key")
        assert ch.is_configured() is True

    def test_not_configured_without_key(self):
        ch = WechatWorkChannel(key="")
        assert ch.is_configured() is False

    def test_send_without_key(self):
        ch = WechatWorkChannel(key="")
        success, err = ch.send("title", "body")
        assert success is False
        assert "not configured" in err

    @patch("monitor.channels.wechat.urllib.request.urlopen")
    def test_send_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errcode": 0}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WechatWorkChannel(key="test_key")
        success, err = ch.send("标题", "内容")
        assert success is True
        assert err == ""

    @patch("monitor.channels.wechat.urllib.request.urlopen")
    def test_send_api_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"errcode": 93000, "errmsg": "invalid"}
        ).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WechatWorkChannel(key="test_key")
        success, err = ch.send("标题", "内容")
        assert success is False
        assert "errcode=93000" in err

    @patch("monitor.channels.wechat.urllib.request.urlopen")
    def test_send_markdown_format(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"errcode": 0}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WechatWorkChannel(key="test_key")
        ch.send("标题", "正文", url="https://example.com")
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        payload = json.loads(req.data)
        assert payload["msgtype"] == "markdown"
        assert "标题" in payload["markdown"]["content"]
        assert "正文" in payload["markdown"]["content"]

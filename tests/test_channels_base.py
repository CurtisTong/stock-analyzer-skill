"""monitor/channels/base.py 通知通道基类与 URL 校验测试。"""

import pytest
from monitor.channels.base import validate_webhook_url, NotificationChannel


class TestValidateWebhookUrl:
    """validate_webhook_url SSRF 防护。"""

    def test_valid_https(self):
        assert (
            validate_webhook_url("https://api.example.com/webhook")
            == "https://api.example.com/webhook"
        )

    def test_empty_string(self):
        assert validate_webhook_url("") == ""

    def test_file_scheme_allowed(self):
        assert validate_webhook_url("file:///tmp/test") == "file:///tmp/test"

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("http://example.com")

    def test_ftp_rejected(self):
        with pytest.raises(ValueError, match="https"):
            validate_webhook_url("ftp://example.com")

    def test_private_ip_10_rejected(self):
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://10.0.0.1/webhook")

    def test_private_ip_192_168_rejected(self):
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://192.168.1.1/webhook")

    def test_private_ip_172_16_rejected(self):
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://172.16.0.1/webhook")

    def test_loopback_rejected(self):
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://127.0.0.1/webhook")

    def test_loopback_ipv6_rejected(self):
        with pytest.raises(ValueError, match="私有"):
            validate_webhook_url("https://[::1]/webhook")

    def test_domain_allowed(self):
        """域名（非 IP）应通过。"""
        assert (
            validate_webhook_url("https://oapi.dingtalk.com/robot/send")
            == "https://oapi.dingtalk.com/robot/send"
        )

    def test_no_hostname_rejected(self):
        with pytest.raises(ValueError, match="hostname"):
            validate_webhook_url("https://")


class TestNotificationChannel:
    """NotificationChannel 抽象基类。"""

    def test_cannot_instantiate_abstract(self):
        """不能直接实例化抽象类。"""
        with pytest.raises(TypeError):
            NotificationChannel()

    def test_concrete_subclass(self):
        """可以实例化具体子类。"""

        class Concrete(NotificationChannel):
            @property
            def name(self):
                return "test"

            def send(self, title, body, url=None, group=None):
                return True, ""

        ch = Concrete()
        assert ch.name == "test"
        assert ch.is_configured() is True
        assert ch.send("t", "b") == (True, "")

"""通知通道抽象基类。"""

import ipaddress
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional, Tuple


def validate_webhook_url(url: str) -> str:
    """校验 webhook URL，拒绝 SSRF 攻击向量。

    规则：
    - 强制 https://（允许 file:// 用于测试）
    - 拒绝私有 IP 段（10.x、172.16-31.x、192.168.x、127.x、::1、link-local）

    Returns:
        验证通过的 URL。

    Raises:
        ValueError: URL 不合法时抛出。
    """
    if not url:
        return url

    parsed = urllib.parse.urlparse(url)
    scheme = (parsed.scheme or "").lower()

    # 允许 file:// 用于测试
    if scheme == "file":
        return url

    if scheme != "https":
        raise ValueError(
            f"webhook URL 必须使用 https://，当前: {scheme}://"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("webhook URL 缺少 hostname")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        # hostname 是域名（非 IP），允许通过
        return url

    # 拒绝私有/环回/链路本地地址
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ValueError(
            f"webhook URL 不能指向私有/环回地址: {hostname}"
        )

    return url


class NotificationChannel(ABC):
    """通知通道抽象基类。

    所有通道实现必须继承此类并实现 send 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """通道名称，如 'bark', 'wechat_work'。"""

    @abstractmethod
    def send(self, title: str, body: str,
             url: Optional[str] = None,
             group: Optional[str] = None) -> Tuple[bool, str]:
        """发送通知。

        Args:
            title: 通知标题
            body: 通知内容
            url: 点击跳转 URL（可选）
            group: 消息分组（可选，用于 iOS 通知分组）

        Returns:
            (success, error_message) — 成功时 error_message 为空字符串。
        """

    def is_configured(self) -> bool:
        """检查通道是否已配置（有必要的 key/token）。"""
        return True

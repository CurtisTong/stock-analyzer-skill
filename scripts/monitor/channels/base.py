"""通知通道抽象基类。"""

import ipaddress
import time
import urllib.error
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from typing import Callable, Optional, Tuple


def send_with_retry(
    do_request: Callable[[], Tuple[bool, str]],
    max_retries: int = 2,
    backoff: float = 1.0,
) -> Tuple[bool, str]:
    """对网络错误做指数退避重试的包装器。

    P1-23: 通知通道单次 HTTP 失败即返回会漏推关键预警（如止损）。
    对网络错误（URLError/OSError）重试，API 业务错误（errcode!=0）不重试。

    Args:
        do_request: 执行单次 HTTP 请求的函数，返回 (success, error_msg)。
            若抛 URLError/OSError 视为可重试网络错误。
        max_retries: 网络错误重试次数（不含首次）。
        backoff: 退避基数（秒），第 n 次重试等待 backoff * n。

    Returns:
        最终的 (success, error_msg)。
    """
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            return do_request()
        except (urllib.error.URLError, OSError) as e:
            last_err = f"network error: {getattr(e, 'reason', e)}"
            if attempt < max_retries:
                time.sleep(backoff * (attempt + 1))
    return False, last_err


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
        raise ValueError(f"webhook URL 必须使用 https://，当前: {scheme}://")

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
        raise ValueError(f"webhook URL 不能指向私有/环回地址: {hostname}")

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
    def send(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Tuple[bool, str]:
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

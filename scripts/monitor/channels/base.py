"""通知通道抽象基类。"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple


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

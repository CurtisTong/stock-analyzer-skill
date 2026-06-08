"""盘中监控与消息推送模块。

用法:
    from monitor import NotificationManager

    nm = NotificationManager()
    nm.send("标题", "内容")
"""

from .manager import NotificationManager
from .channels.base import NotificationChannel

__all__ = ["NotificationManager", "NotificationChannel"]

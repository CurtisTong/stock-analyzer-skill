"""消息推送模块（NotificationManager + 多通道适配器）。

注：原「盘中监控」功能（compute_key_levels / scan_all / check_and_push 等）
已于 v1.20.0 移除，本模块仅保留持仓 CRUD 推送链路（Bark / 企微 / 钉钉）。

用法:
    from monitor import NotificationManager

    nm = NotificationManager()
    nm.send("标题", "内容")
"""

from .manager import NotificationManager
from .channels.base import NotificationChannel

__all__ = ["NotificationManager", "NotificationChannel"]

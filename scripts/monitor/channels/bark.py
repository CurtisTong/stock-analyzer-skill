"""Bark 推送通道（iOS）。

Bark 是一个轻量级的 iOS 推送服务，API 极简：
    GET/POST https://api.day.app/{key}/{title}/{body}

支持自托管服务器。
"""

import json
import urllib.error
import urllib.request
from typing import Optional, Tuple

from .base import NotificationChannel


class BarkChannel(NotificationChannel):
    """Bark 推送通道。"""

    def __init__(self, server: str = "https://api.day.app",
                 key: str = "", group: str = "stock"):
        self._server = server.rstrip("/")
        self._key = key
        self._group = group

    @property
    def name(self) -> str:
        return "bark"

    def is_configured(self) -> bool:
        return bool(self._key)

    def send(self, title: str, body: str,
             url: Optional[str] = None,
             group: Optional[str] = None) -> Tuple[bool, str]:
        """发送 Bark 推送。

        Returns:
            (success, error_message) — 成功时 error_message 为空字符串。
        """
        if not self._key:
            return False, "bark key not configured"

        payload = {
            "title": title,
            "body": body,
            "group": group or self._group,
            "sound": "minuet",
            "icon": "",
        }
        if url:
            payload["url"] = url

        api_url = f"{self._server}/{self._key}"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            api_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("code") == 200:
                    return True, ""
                return False, f"bark api returned code={result.get('code')}"
        except urllib.error.URLError as e:
            return False, f"network error: {e.reason}"
        except json.JSONDecodeError as e:
            return False, f"invalid response: {e}"
        except OSError as e:
            return False, f"os error: {e}"

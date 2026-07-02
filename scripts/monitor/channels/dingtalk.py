"""钉钉 webhook 推送通道。

钉钉机器人 webhook API：
    POST https://oapi.dingtalk.com/robot/send?access_token={token}

消息类型：text, markdown, link, actionCard
支持关键词、加签、IP 白名单三种安全设置。
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import urllib.parse
from typing import Optional, Tuple

from .base import NotificationChannel, send_with_retry


class DingtalkChannel(NotificationChannel):
    """钉钉 webhook 推送通道。"""

    def __init__(self, token: str = "", secret: str = ""):
        """
        Args:
            token: 钉钉机器人 access_token
            secret: 加签密钥（可选，如果使用加签安全设置）
        """
        self._token = token
        self._secret = secret

    @property
    def name(self) -> str:
        return "dingtalk"

    def is_configured(self) -> bool:
        return bool(self._token)

    def _sign_url(self, timestamp: str) -> str:
        """生成加签 URL。"""
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
        return f"&timestamp={timestamp}&sign={sign}"

    def send(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """发送钉钉 webhook 推送。

        使用 markdown 格式以支持富文本。

        Returns:
            (success, error_message) — 成功时 error_message 为空字符串。
        """
        if not self._token:
            return False, "dingtalk token not configured"

        # 构建 markdown 内容
        md_text = f"## {title}\n\n{body}"
        if url:
            md_text += f"\n\n[查看详情]({url})"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": md_text,
            },
        }

        api_url = f"https://oapi.dingtalk.com/robot/send?access_token={self._token}"

        # 如果使用加签安全设置
        if self._secret:
            timestamp = str(round(time.time() * 1000))
            api_url += self._sign_url(timestamp)

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            api_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        def _do_request():
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("errcode") == 0:
                    return True, ""
                # API 业务错误不重试
                return (
                    False,
                    f"dingtalk api returned errcode={result.get('errcode')}, errmsg={result.get('errmsg')}",
                )

        try:
            return send_with_retry(_do_request)
        except json.JSONDecodeError as e:
            return False, f"invalid response: {e}"

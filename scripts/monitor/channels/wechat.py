"""企业微信 webhook 推送通道。

企业微信机器人 webhook API：
    POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}

消息类型：text, markdown, image, news
"""

import json
import urllib.error
import urllib.request
from typing import Optional, Tuple

from .base import NotificationChannel, send_with_retry


class WechatWorkChannel(NotificationChannel):
    """企业微信 webhook 推送通道。"""

    def __init__(self, key: str = ""):
        self._key = key

    @property
    def name(self) -> str:
        return "wechat_work"

    def is_configured(self) -> bool:
        return bool(self._key)

    def send(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        group: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """发送企业微信 webhook 推送。

        使用 markdown 格式以支持富文本。

        Returns:
            (success, error_message) — 成功时 error_message 为空字符串。
        """
        if not self._key:
            return False, "wechat_work key not configured"

        # 构建 markdown 内容
        md_content = f"## {title}\n\n{body}"
        if url:
            md_content += f"\n\n[查看详情]({url})"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": md_content,
            },
        }

        api_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={self._key}"
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
                    f"wechat api returned errcode={result.get('errcode')}, errmsg={result.get('errmsg')}",
                )

        try:
            return send_with_retry(_do_request)
        except json.JSONDecodeError as e:
            return False, f"invalid response: {e}"

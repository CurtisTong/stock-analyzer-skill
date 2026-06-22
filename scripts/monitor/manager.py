"""通知管理器。

负责通道注册、消息分发、频率控制和推送日志。
"""

import re
import threading
import time
from datetime import datetime
from pathlib import Path

from dev.clock import now as _now
from typing import Optional

from config.loader import ConfigLoader

from .channels.base import NotificationChannel
from .channels.bark import BarkChannel
from .channels.wechat import WechatWorkChannel
from .channels.dingtalk import DingtalkChannel


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "notification.yaml"


def _log_path() -> Path:
    cache_dir = Path(__file__).resolve().parent.parent / "data" / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "notifications.log"


# 日志轮转配置（可从 YAML 覆盖）
_LOG_MAX_SIZE = 5 * 1024 * 1024  # 默认 5MB
_LOG_MAX_FILES = 5  # 保留最近 5 个轮转文件


def _rotate_log_if_needed(
    log_path: Path, max_size: int = _LOG_MAX_SIZE, max_files: int = _LOG_MAX_FILES
) -> None:
    """检查并执行日志轮转。

    Args:
        log_path: 日志文件路径
        max_size: 单个日志文件最大字节数
        max_files: 保留的轮转文件数量
    """
    if not log_path.exists():
        return

    # 检查文件大小
    try:
        size = log_path.stat().st_size
    except OSError:
        return

    if size < max_size:
        return

    # 执行轮转：notifications.log -> notifications.log.1 -> notifications.log.2 -> ...
    log_dir = log_path.parent
    log_name = log_path.stem
    log_ext = log_path.suffix

    # 删除最旧的轮转文件
    oldest = log_dir / f"{log_name}{log_ext}.{max_files}"
    try:
        oldest.unlink(missing_ok=True)
    except OSError:
        pass

    # 依次轮转：从 .max_files-1 到 1
    for i in range(max_files - 1, 0, -1):
        src = log_dir / f"{log_name}{log_ext}.{i}"
        dst = log_dir / f"{log_name}{log_ext}.{i + 1}"
        try:
            if src.exists():
                src.rename(dst)
        except OSError:
            pass

    # 当前日志重命名为 .1
    try:
        log_path.rename(log_dir / f"{log_name}{log_ext}.1")
    except OSError:
        pass


def _clean_old_logs(log_path: Path, keep: int = _LOG_MAX_FILES) -> int:
    """清理旧的轮转日志文件。

    Args:
        log_path: 日志文件路径
        keep: 保留最近 N 个轮转文件

    Returns:
        清理的文件数量
    """
    log_dir = log_path.parent
    log_name = log_path.stem
    log_ext = log_path.suffix

    # 匹配 notifications.log.N 格式
    escaped_ext = re.escape(log_ext)
    pattern = re.compile(rf"^{re.escape(log_name)}{escaped_ext}\.(\d+)$")
    cleaned = 0

    for f in log_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            idx = int(m.group(1))
            if idx > keep:
                try:
                    f.unlink()
                    cleaned += 1
                except OSError:
                    pass

    return cleaned


class NotificationManager:
    """通知管理器。

    用法:
        nm = NotificationManager()
        nm.send("标题", "内容")
    """

    def __init__(self, config: Optional[dict] = None):
        self._channels: list[NotificationChannel] = []
        self._config = config or self._load_config()
        self._throttle_log: dict[str, float] = {}  # key -> last_sent_ts
        self._daily_count = 0
        self._daily_date = ""
        self._lock = threading.Lock()
        self._log_write_count = 0  # 写入计数器，用于批量检查轮转
        self._setup_channels()

    def _load_config(self) -> dict:
        """加载通知配置，并更新日志轮转设置。"""
        global _LOG_MAX_SIZE, _LOG_MAX_FILES
        config = ConfigLoader.load("notification.yaml")

        # 从配置中读取日志轮转设置
        log_cfg = config.get("logging", {})
        if "max_size" in log_cfg:
            _LOG_MAX_SIZE = log_cfg["max_size"] * 1024 * 1024  # MB 转 bytes
        if "max_files" in log_cfg:
            _LOG_MAX_FILES = log_cfg["max_files"]

        return config

    def _setup_channels(self) -> None:
        """根据配置注册通道。"""
        channels_cfg = self._config.get("channels", {})

        # Bark
        bark_cfg = channels_cfg.get("bark", {})
        if bark_cfg.get("enabled", False):
            ch = BarkChannel(
                server=bark_cfg.get("server", "https://api.day.app"),
                key=bark_cfg.get("key", ""),
                group=bark_cfg.get("group", "stock"),
            )
            if ch.is_configured():
                self._channels.append(ch)

        # 企业微信
        wechat_cfg = channels_cfg.get("wechat_work", {})
        if wechat_cfg.get("enabled", False):
            ch = WechatWorkChannel(key=wechat_cfg.get("key", ""))
            if ch.is_configured():
                self._channels.append(ch)

        # 钉钉
        dingtalk_cfg = channels_cfg.get("dingtalk", {})
        if dingtalk_cfg.get("enabled", False):
            ch = DingtalkChannel(
                token=dingtalk_cfg.get("token", ""),
                secret=dingtalk_cfg.get("secret", ""),
            )
            if ch.is_configured():
                self._channels.append(ch)

    def register_channel(self, channel: NotificationChannel) -> None:
        """手动注册通知通道。"""
        if channel.is_configured():
            self._channels.append(channel)

    def get_active_channels(self) -> list[str]:
        """返回已激活的通道名称列表。"""
        return [ch.name for ch in self._channels]

    def _check_throttle(self, key: str, urgent: bool = False) -> bool:
        """检查是否被频率限制。返回 True 表示允许发送。

        Args:
            key: 去重键
            urgent: 紧急消息不受每日上限限制（但仍受去重窗口限制）
        """
        throttle_cfg = self._config.get("throttle", {})
        dedup_window = throttle_cfg.get("dedup_window", 15) * 60  # 分钟转秒
        daily_limit = throttle_cfg.get("daily_limit", 20)

        with self._lock:
            # 每日计数重置
            today = _now().strftime("%Y-%m-%d")
            if today != self._daily_date:
                self._daily_date = today
                self._daily_count = 0

            # 每日上限（紧急消息不受限）
            if not urgent and self._daily_count >= daily_limit:
                return False

            # 去重窗口（紧急消息也受去重限制，避免重复轰炸）
            now = time.time()
            last = self._throttle_log.get(key, 0)
            if now - last < dedup_window:
                return False

        return True

    def _is_quiet_hours(self) -> bool:
        """检查是否在静默时段（非交易时段）。"""
        throttle_cfg = self._config.get("throttle", {})
        quiet = throttle_cfg.get("quiet_hours", "")
        if not quiet:
            return False

        try:
            start_str, end_str = quiet.split("-")
            now = _now()
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))

            start = now.replace(hour=start_h, minute=start_m, second=0)
            end = now.replace(hour=end_h, minute=end_m, second=0)

            # 跨午夜（如 15:05-09:25）
            if start > end:
                return now >= start or now < end
            return start <= now < end
        except (ValueError, AttributeError):
            return False

    def _log_send(
        self, title: str, channel: str, success: bool, error: str = ""
    ) -> None:
        """记录推送日志（带日志轮转保护，每 10 次写入检查一次轮转）。"""
        log_path = _log_path()

        # 每 10 次写入检查一次轮转，避免高频 stat() 调用
        self._log_write_count += 1
        if self._log_write_count >= 10:
            self._log_write_count = 0
            _rotate_log_if_needed(log_path, _LOG_MAX_SIZE, _LOG_MAX_FILES)

        ts = _now().strftime("%Y-%m-%d %H:%M:%S")
        status = "OK" if success else "FAIL"
        line = f"[{ts}] [{status}] [{channel}] {title}"
        if error:
            line += f" | {error}"
        line += "\n"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    def send(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        group: Optional[str] = None,
        throttle_key: Optional[str] = None,
        urgent: bool = False,
    ) -> dict:
        """发送通知到所有已激活通道。

        Args:
            title: 通知标题
            body: 通知内容
            url: 点击跳转 URL（可选）
            group: 消息分组（可选）
            throttle_key: 去重键（可选，默认用 title）
            urgent: 紧急消息不受每日上限限制（默认 False）

        Returns:
            {"sent": int, "failed": int, "results": {channel_name: bool}, "reason": str}
        """
        key = throttle_key or title

        # 静默时段检查（紧急消息也受静默限制，避免深夜打扰）
        if self._is_quiet_hours():
            return {"sent": 0, "failed": 0, "results": {}, "reason": "quiet_hours"}

        # 频率控制
        if not self._check_throttle(key, urgent=urgent):
            return {"sent": 0, "failed": 0, "results": {}, "reason": "throttled"}

        # 无活跃通道
        if not self._channels:
            return {"sent": 0, "failed": 0, "results": {}, "reason": "no_channels"}

        results = {}
        sent = 0
        failed = 0

        for ch in self._channels:
            ok, error = ch.send(title, body, url=url, group=group)
            results[ch.name] = ok
            self._log_send(title, ch.name, ok, error=error)
            if ok:
                sent += 1
            else:
                failed += 1

        if sent > 0:
            with self._lock:
                self._throttle_log[key] = time.time()
                self._daily_count += 1

        return {"sent": sent, "failed": failed, "results": results}

    def send_alert(
        self,
        alert_type: str,
        stock_name: str,
        stock_code: str,
        message: str,
        url: Optional[str] = None,
        urgent: bool = False,
    ) -> dict:
        """发送股票预警通知（带标准化格式）。

        Args:
            alert_type: 预警类型 (price/technical/portfolio/market/risk/break)
            stock_name: 股票名称
            stock_code: 股票代码
            message: 预警详情
            url: 跳转链接
            urgent: 紧急消息不受每日上限限制

        Returns:
            同 send() 返回值。
        """
        icon_map = {
            "price": "💰",
            "technical": "📊",
            "portfolio": "📋",
            "market": "🏛️",
            "risk": "⚠️",
            "break": "🔴",
        }
        icon = icon_map.get(alert_type, "📌")
        title = f"{icon} {stock_name} {alert_type}预警"
        if stock_code:
            title += f" ({stock_code})"

        throttle_key = f"{alert_type}:{stock_code}:{message[:20]}"
        return self.send(
            title, body=message, url=url, throttle_key=throttle_key, urgent=urgent
        )

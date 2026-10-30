"""可注入时钟。

生产代码用 `from dev.clock import now` 替代 `datetime.now()`，
测试可通过 monkeypatch.setattr 替换 `_now_func` 实现时间穿越。

使用示例：
    from datetime import timedelta
    from dev.clock import now

    start = (now() - timedelta(days=30)).strftime("%Y-%m-%d")

测试示例：
    from dev import clock
    monkeypatch.setattr(clock, "_now_func", lambda: fake_dt)
"""

import datetime as _dt

# A 股固定 UTC+8（1991 年后中国大陆无夏令时）
_MARKET_TZ = _dt.timezone(_dt.timedelta(hours=8), "Asia/Shanghai")

_now_func = _dt.datetime.now


def now() -> _dt.datetime:
    """当前时间。测试时可 monkeypatch。"""
    return _now_func()


def market_now() -> _dt.datetime:
    """A 股市场当前时间（Asia/Shanghai）。

    "今天是哪个交易日"类口径必须用北京时间：CI/海外主机的本地时区
    会错日（如 UTC 16:00-24:00 对应北京次日）。取数日期默认值一律用本函数。
    """
    try:
        return _now_func(_MARKET_TZ)
    except TypeError:
        # 测试注入的无参时钟：naive 值按北京墙上钟解释
        return _now_func().replace(tzinfo=_MARKET_TZ)


def freeze(target: _dt.datetime) -> None:
    """冻结时钟至指定时间，供测试时间穿越使用。"""
    global _now_func

    def _now_func():
        return target


def unfreeze() -> None:
    """解除冻结，恢复真实时间。"""
    global _now_func
    _now_func = _dt.datetime.now

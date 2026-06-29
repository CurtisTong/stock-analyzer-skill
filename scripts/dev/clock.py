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

_now_func = _dt.datetime.now


def now() -> _dt.datetime:
    """当前时间。测试时可 monkeypatch。"""
    return _now_func()


def freeze(target: _dt.datetime) -> None:
    """冻结时钟（手动模式，调试用）。"""
    global _now_func

    def _now_func():
        return target


def unfreeze() -> None:
    """解除冻结，恢复真实时间。"""
    global _now_func
    _now_func = _dt.datetime.now

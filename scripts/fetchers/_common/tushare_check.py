"""Tushare 运行时可用性检查（quote / kline 共享）。

提取自 tushare_quote.py 和 tushare_kline.py 的逐字节重复实现。
"""

import os


def check_tushare() -> bool:
    """运行时检查 tushare 是否可用（包已安装 + token 已设置）。"""
    if not os.environ.get("TUSHARE_TOKEN"):
        return False
    try:
        import tushare  # noqa: F401

        return True
    except ImportError:
        return False

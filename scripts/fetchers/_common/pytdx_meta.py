"""通达信 pytdx 共享元数据（服务器列表 + 市场代码推断）。

提取自 pytdx_quote.py 和 pytdx_kline.py 的逐字节重复实现。
"""

from common import plain_code

# 默认服务器列表（ quote / kline 两模块原本各持一份完全相同的副本）
DEFAULT_SERVERS = [
    ("119.147.212.81", 7709),
    ("112.74.214.43", 7709),
    ("221.231.141.60", 7709),
    ("101.227.73.20", 7709),
    ("101.227.77.254", 7709),
    ("14.215.128.18", 7709),
    ("59.173.18.140", 7709),
    ("218.75.126.9", 7709),
]


def get_market(code: str) -> int:
    """按 A 股代码段推断 pytdx market 编码：0=深圳, 1=上海。"""
    plain = plain_code(code).zfill(6)
    if plain.startswith(("60", "68", "51", "56", "58")):
        return 1
    return 0

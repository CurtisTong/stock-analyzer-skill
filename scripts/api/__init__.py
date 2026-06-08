"""
API 层 - 面向用户/CLI 的统一入口。

模块:
- quote_cli: 行情查询 CLI
- kline_cli: K线查询 CLI
- screener_cli: 选股 CLI
- backtest_cli: 回测 CLI

使用方法:
    from api import quote_cli, screener_cli
    
    # 命令行调用
    python -m api.quote_cli sh600989
"""
from .quote_cli import main as quote_main
from .screener_cli import main as screener_main

__all__ = [
    "quote_main",
    "screener_main",
]

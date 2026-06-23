"""持仓管理模块。

用法:
    from portfolio import PortfolioManager, TradeLog

    pm = PortfolioManager()
    pm.add_position("sh600989", "宝丰能源", 18.50, 1000)
    positions = pm.get_positions()

    tl = TradeLog()
    history = tl.query()
"""

from .manager import PortfolioManager
from .trade_log import TradeLog

__all__ = ["PortfolioManager", "TradeLog"]

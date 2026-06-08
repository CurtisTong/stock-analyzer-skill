"""持仓管理模块。

用法:
    from portfolio import PortfolioManager

    pm = PortfolioManager()
    pm.add_position("sh600989", "宝丰能源", 18.50, 1000)
    positions = pm.get_positions()
"""

from .manager import PortfolioManager

__all__ = ["PortfolioManager"]

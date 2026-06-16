"""
题材龙头（合并徐翔+赵老哥）评分函数 v2.1.1。

v2.1.0：骨架实现
v2.1.1：调 xu_xiang + zhao_laoge 加权平均

人设：涨停板战法 + 趋势龙头，强调量价+情绪/题材。
"""
from typing import Dict


def score(stock_data: dict) -> Dict[str, float]:
    """题材龙头：徐翔 0.5 + 赵老哥 0.5 加权平均。"""
    from . import xu_xiang, zhao_laoge
    from ._merge import weighted_merge

    return weighted_merge(
        [xu_xiang.score(stock_data), zhao_laoge.score(stock_data)],
        weights=[0.5, 0.5],
    )
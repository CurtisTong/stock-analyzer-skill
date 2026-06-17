"""专家圆桌决策引擎（编排层）。

保持原有公开 API 不变，内部委托给 market_detector / vote_engine / formatter。

公开 API：
- detect_market_state(index_quote, kline_data, breadth_data) -> dict
- aggregate_votes(expert_results, market_state, horizon, calibration_factor) -> dict
- aggregate_group_votes(expert_results, group, calibration_factor) -> dict
- format_debate_output(result) -> str
- format_debate_card(result) -> str
- format_group_output(result) -> str
"""

from experts.market_detector import detect_market_state
from experts.vote_engine import aggregate_votes, aggregate_group_votes
from experts.formatter import (
    format_debate_output,
    format_debate_card,
    format_group_output,
)

__all__ = [
    "detect_market_state",
    "aggregate_votes",
    "aggregate_group_votes",
    "format_debate_output",
    "format_debate_card",
    "format_group_output",
]

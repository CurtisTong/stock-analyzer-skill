"""
astock.py 涨跌停分支测试（Sprint 14）。
"""

import pytest

from technical import astock


def _make_records(prices, base_day="2025-01-01"):
    """从价格列表构造 records（每条 {open, high, low, close, volume}）。"""
    from datetime import datetime, timedelta

    start = datetime.strptime(base_day, "%Y-%m-%d")
    records = []
    for i, p in enumerate(prices):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        records.append(
            {
                "day": day,
                "open": p,
                "high": p * 1.01,
                "low": p * 0.99,
                "close": p,
                "volume": 1000000,
            }
        )
    return records


class TestLimitAnalysisBasic:
    """基础涨跌停判定。"""

    def test_insufficient_data_returns_none(self):
        """不足 10 根 K 线返回 None。"""
        records = _make_records([10.0] * 5)
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 11, "limit_down": 9}
        )
        assert result is None

    def test_normal_trading(self):
        """正常交易（无涨跌停）。"""
        # 10 根平稳 + 最后一根 10.5
        records = _make_records([10.0] * 9 + [10.5])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 11.0, "limit_down": 9.0}
        )
        assert result["board_status"] == "正常交易"
        assert result["streak_type"] == "无连板"

    def test_sealed_up(self):
        """封涨停：last_close ≈ limit_up。"""
        records = _make_records([10.0] * 9 + [10.95])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.0}
        )
        assert result["board_status"] == "封涨停"

    def test_sealed_down(self):
        """封跌停：last_close ≈ limit_down。"""
        records = _make_records([10.0] * 9 + [9.05])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.05}
        )
        assert result["board_status"] == "封跌停"

    def test_limit_up_exploded(self):
        """炸板：触及涨停但未封住。"""
        # 最后一天 high=11 但 close=10.8（未封住）
        records = _make_records([10.0] * 9 + [10.8])
        records[-1]["high"] = 10.99
        records[-1]["close"] = 10.8
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.0}
        )
        assert "炸板" in result["board_status"]


class TestStreakDetection:
    """连板检测测试。"""

    def test_first_streak(self):
        """首板：1 连板。"""
        # 9 平稳 + 1 涨停（10.0 → 10.95，+9.5%）
        records = _make_records([10.0] * 9 + [10.95])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.0}
        )
        assert result["streak_type"] == "首板"
        assert result["limit_streak"] == 1

    def test_second_streak(self):
        """二板：2 连板。"""
        # 8 平稳 + 2 连续涨停（10.0→10.95→12.0）
        records = _make_records([10.0] * 8 + [10.95, 12.0])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 12.0, "limit_down": 9.0}
        )
        assert "二板" in result["streak_type"]
        assert result["limit_streak"] == 2

    def test_monster_streak(self):
        """妖股：5+ 连板。"""
        # 5 平稳 + 5 连续涨停（每天 +9.5%）
        prices = [10.0] * 5 + [10.95, 12.0, 13.14, 14.39, 15.78]
        records = _make_records(prices)
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 15.78, "limit_down": 9.0}
        )
        assert "妖股" in result["streak_type"]
        assert result["limit_streak"] == 5


class TestStreakVolume:
    """连板量能分析测试。"""

    def test_shrinking_volume_streak(self):
        """缩量加速：连板期间成交量递减。"""
        prices = [10.0] * 5 + [10.95, 12.0, 13.14, 14.39, 15.78]
        records = _make_records(prices)
        # 设置最后 5 根成交量递减（vols[0]=5000, vols[-1]=1000）
        streak_vols = [5000, 4000, 3000, 2000, 1000]
        for i, v in enumerate(streak_vols):
            records[5 + i]["volume"] = v
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 15.78, "limit_down": 9.0}
        )
        assert "缩量加速" in result["streak_volume"]

    def test_expanding_volume_streak(self):
        """放量分歧：最后根成交量 1.5× 第一根。"""
        prices = [10.0] * 5 + [10.95, 12.0, 13.14, 14.39, 15.78]
        records = _make_records(prices)
        # 设置最后 5 根成交量递增（vols[0]=1000, vols[-1]=5000，5x>1.5x）
        streak_vols = [1000, 1100, 1200, 1300, 5000]
        for i, v in enumerate(streak_vols):
            records[5 + i]["volume"] = v
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 15.78, "limit_down": 9.0}
        )
        assert "放量分歧" in result["streak_volume"]


class TestTRisk:
    """T+1 风险提示测试。"""

    def test_t1_risk_on_sealed_up(self):
        """封涨停 + 有连板 → T+1 风险。"""
        records = _make_records([10.0] * 9 + [10.95])
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.0}
        )
        assert "T+1" in result["t1_risk"]

    def test_no_t1_risk_on_normal(self):
        """正常交易 → 无 T+1 风险。"""
        records = _make_records([10.0] * 10)
        result = astock.limit_analysis(
            records, "主板", {"limit_up": 10.95, "limit_down": 9.0}
        )
        assert result["t1_risk"] is None

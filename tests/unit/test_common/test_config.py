"""
配置加载器测试。
"""
import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from config import ConfigLoader, get_scoring_config, get_limit_config, get_industry_threshold


class TestConfigLoader:
    """配置加载器测试。"""

    def test_load_scoring_config(self):
        """测试加载评分配置。"""
        config = ConfigLoader.load("scoring.yaml")
        assert "alignment_scores" in config
        assert "market_weights" in config

    def test_load_limits_config(self):
        """测试加载限制配置。"""
        config = ConfigLoader.load("limits.yaml")
        assert "board_limits" in config
        assert "min_total_cap" in config

    def test_load_nonexistent_config(self):
        """测试加载不存在的配置。"""
        config = ConfigLoader.load("nonexistent.yaml")
        assert config == {}

    def test_get_nested_key(self):
        """测试获取嵌套键。"""
        value = ConfigLoader.get("scoring.yaml", "alignment_scores.多头排列")
        assert value == 20

    def test_get_nested_key_default(self):
        """测试获取嵌套键默认值。"""
        value = ConfigLoader.get("scoring.yaml", "nonexistent.key", "default")
        assert value == "default"

    def test_reload(self):
        """测试重新加载。"""
        # 首次加载
        config1 = ConfigLoader.load("limits.yaml")
        # 重新加载
        ConfigLoader.reload("limits.yaml")
        config2 = ConfigLoader.load("limits.yaml")
        # 应该相同（配置未改变）
        assert config1 == config2


class TestGetScoringConfig:
    """评分配置获取测试。"""

    def test_get_alignment_scores(self):
        """测试获取均线排列评分。"""
        scores = get_scoring_config("alignment_scores")
        assert scores["多头排列"] == 20
        assert scores["空头排列"] == 3

    def test_get_market_weights(self):
        """测试获取市场权重。"""
        weights = get_scoring_config("market_weights.牛市")
        assert weights["bullish_bias"] == 1.3
        assert weights["trend_following"] == 1.4

    def test_get_stock_type_weights(self):
        """测试获取个股类型权重。"""
        weights = get_scoring_config("stock_type_weights.蓝筹股")
        assert weights["ma"] == 1.3
        assert weights["macd"] == 1.1


class TestGetLimitConfig:
    """限制配置获取测试。"""

    def test_get_board_limits(self):
        """测试获取涨跌停限制。"""
        limit = get_limit_config("board_limits.主板")
        assert limit == 9.5

        limit = get_limit_config("board_limits.创业板")
        assert limit == 19.5

    def test_get_min_cap(self):
        """测试获取最低市值。"""
        cap = get_limit_config("min_total_cap.主板")
        assert cap == 40


class TestGetIndustryThreshold:
    """行业阈值获取测试。"""

    def test_get_industry_threshold_existing(self):
        """测试获取现有行业阈值。"""
        # 银行有特定阈值
        pe = get_industry_threshold("银行", "pe_undervalued", 15)
        assert pe == 8

    def test_get_industry_threshold_default(self):
        """测试获取默认行业阈值。"""
        # 不存在的行业使用默认值
        pe = get_industry_threshold("不存在的行业", "pe_undervalued", 15)
        assert pe == 15

    def test_get_industry_threshold_科技(self):
        """测试科技行业阈值。"""
        pe = get_industry_threshold("科技", "pe_undervalued", 15)
        assert pe == 30

"""(#11) chip 批量并行预取测试。

覆盖：
- chip_score_dynamic_batch 批量评分
- northbound 模块级缓存
- 并行获取 margin/top_holders
- 空输入处理
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import strategies.factors.chip as chip_factor  # noqa: E402
from data.types import MarginData, TopHolderRecord, HolderData  # noqa: E402


class TestChipDynamicBatch:
    """chip_score_dynamic_batch 批量评分。"""

    def test_empty_input_returns_empty(self):
        assert chip_factor.chip_score_dynamic_batch([]) == {}

    def test_batch_returns_scores_for_all_codes(self):
        """批量评分返回所有 code 的分数。"""
        codes = ["sh600519", "sh600989"]

        holders = [
            HolderData(end_date="", holder_num_change=-10, avg_amount=0),
            HolderData(end_date="", holder_num_change=0, avg_amount=0),
        ]
        margin = [MarginData(rzjme=100) for _ in range(5)]
        top = [TopHolderRecord(is_institution=True, change_type="增持")]

        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=holders),
            patch.object(chip_factor, "_get_margin_data", return_value=margin),
            patch.object(chip_factor, "_get_top_holders", return_value=top),
            patch("data.flow.get_northbound_flow", return_value=[]),
        ):
            # mock parallel_fetch_dict 返回预取数据
            with patch("common.parallel_fetch_dict") as mock_parallel:
                mock_parallel.side_effect = [
                    {c: margin for c in codes},  # margin_data
                    {c: top for c in codes},  # top_holders_data
                ]
                result = chip_factor.chip_score_dynamic_batch(codes)

        assert len(result) == 2
        assert "sh600519" in result
        assert "sh600989" in result
        for score in result.values():
            assert 0 <= score <= 100

    def test_batch_uses_parallel_fetch(self):
        """批量评分使用 parallel_fetch_dict 并行获取。"""
        codes = ["sh600519"]
        holders = [
            HolderData(end_date="", holder_num_change=-10, avg_amount=0),
            HolderData(end_date="", holder_num_change=0, avg_amount=0),
        ]

        with (
            patch.object(chip_factor, "_get_cached_holders", return_value=holders),
            patch("data.flow.get_northbound_flow", return_value=[]),
            patch("common.parallel_fetch_dict") as mock_parallel,
        ):
            mock_parallel.side_effect = [{}, {}]  # margin + top_holders 空
            chip_factor.chip_score_dynamic_batch(codes)

        # parallel_fetch_dict 被调用 2 次（margin + top_holders）
        assert mock_parallel.call_count == 2


class TestNorthboundCache:
    """northbound 模块级缓存。"""

    def setup_method(self):
        """每个测试前清除缓存。"""
        chip_factor._NORTHBOUND_CACHE.clear()
        chip_factor._NORTHBOUND_CACHE_TS = 0.0

    def test_cache_avoids_repeated_requests(self):
        """相同 code + days 的请求只发一次网络请求。"""
        call_count = 0
        original_flow = [{"net_buy": 100}, {"net_buy": 200}, {"net_buy": 300}]

        def mock_get_flow(code, days=20):
            nonlocal call_count
            call_count += 1
            return original_flow

        with patch("data.flow.get_northbound_flow", side_effect=mock_get_flow):
            # 第一次调用 -> 发起网络请求
            flow1 = chip_factor._get_northbound_flow_cached("sh600519", days=20)
            assert call_count == 1
            assert len(flow1) == 3

            # 第二次调用 -> 命中缓存，不发起网络请求
            flow2 = chip_factor._get_northbound_flow_cached("sh600519", days=20)
            assert call_count == 1  # 仍然只调用 1 次
            assert flow2 == flow1

    def test_cache_different_codes_separate(self):
        """不同 code 的缓存独立。"""
        call_count = 0

        def mock_get_flow(code, days=20):
            nonlocal call_count
            call_count += 1
            return [{"net_buy": 100}]

        with patch("data.flow.get_northbound_flow", side_effect=mock_get_flow):
            chip_factor._get_northbound_flow_cached("sh600519", days=20)
            chip_factor._get_northbound_flow_cached("sh600989", days=20)
            assert call_count == 2  # 两个不同 code 各请求一次

    def test_cache_failure_returns_empty(self):
        """网络失败时返回空列表。"""
        with patch("data.flow.get_northbound_flow", side_effect=Exception("net")):
            flow = chip_factor._get_northbound_flow_cached("sh600519", days=20)
        assert flow == []


class TestScoreFromData:
    """从预取数据评分（避免重复网络请求）。"""

    def test_margin_score_from_data(self):
        """从预取 margin 数据评分。"""
        margin = [MarginData(rzjme=100) for _ in range(5)]
        score = chip_factor._score_margin_trend_from_data(margin)
        assert score == 15  # 4+ 天净买入

    def test_margin_score_empty(self):
        assert chip_factor._score_margin_trend_from_data([]) == 0

    def test_institution_score_from_data(self):
        """从预取 top_holders 数据评分。"""
        top = [TopHolderRecord(is_institution=True, change_type="增持")]
        score = chip_factor._score_institution_change_from_data(top)
        assert score == 8

    def test_institution_score_empty(self):
        assert chip_factor._score_institution_change_from_data([]) == 0

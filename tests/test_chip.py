"""资金面数据模块单元测试。"""
import sys
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# 添加 scripts 目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data.types import MarginData, HolderData, TopHolderRecord


class TestMarginData:
    """融资融券数据类型测试。"""

    def test_default_values(self):
        """默认值正确。"""
        data = MarginData()
        assert data.date == ""
        assert data.code == ""
        assert data.rzye == 0.0
        assert data.rzjme == 0.0

    def test_to_dict(self):
        """to_dict 返回正确字典。"""
        data = MarginData(date="2025-06-09", code="600989", rzye=1235000000, rzjme=5234000)
        d = data.to_dict()
        assert d["date"] == "2025-06-09"
        assert d["code"] == "600989"
        assert d["rzye"] == 1235000000
        assert d["rzjme"] == 5234000


class TestHolderData:
    """股东户数数据类型测试。"""

    def test_default_values(self):
        """默认值正确。"""
        data = HolderData()
        assert data.end_date == ""
        assert data.code == ""
        assert data.holder_num == 0
        assert data.concentration == ""

    def test_to_dict(self):
        """to_dict 返回正确字典。"""
        data = HolderData(end_date="2025-03-31", code="600989", holder_num=85234, concentration="集中")
        d = data.to_dict()
        assert d["end_date"] == "2025-03-31"
        assert d["holder_num"] == 85234
        assert d["concentration"] == "集中"


class TestTopHolderRecord:
    """十大流通股东数据类型测试。"""

    def test_default_values(self):
        """默认值正确。"""
        data = TopHolderRecord()
        assert data.rank == 0
        assert data.holder_name == ""
        assert data.is_institution is False

    def test_to_dict(self):
        """to_dict 返回正确字典。"""
        data = TopHolderRecord(
            rank=1,
            holder_name="中国证券金融股份有限公司",
            holder_type="一般法人",
            hold_num=12500,
            is_institution=True,
        )
        d = data.to_dict()
        assert d["rank"] == 1
        assert d["holder_name"] == "中国证券金融股份有限公司"
        assert d["is_institution"] is True


class TestChipFetcher:
    """筹码相关 Fetcher 测试。"""

    def test_margin_fetcher_init(self):
        """MarginFetcher 初始化正确。"""
        from fetchers.eastmoney_chip import MarginFetcher
        fetcher = MarginFetcher()
        assert fetcher.name == "margin"
        assert fetcher.priority == 5

    def test_holder_fetcher_init(self):
        """HolderFetcher 初始化正确。"""
        from fetchers.eastmoney_chip import HolderFetcher
        fetcher = HolderFetcher()
        assert fetcher.name == "holder"
        assert fetcher.priority == 5

    def test_top_holder_fetcher_init(self):
        """TopHolderFetcher 初始化正确。"""
        from fetchers.eastmoney_chip import TopHolderFetcher
        fetcher = TopHolderFetcher()
        assert fetcher.name == "top_holder"
        assert fetcher.priority == 5


@pytest.mark.network
class TestChipFetcherNetwork:
    """筹码相关 Fetcher 网络测试（需要 --run-network）。"""

    def test_margin_fetch_real(self):
        """真实获取融资融券数据。"""
        from fetchers.eastmoney_chip import MarginFetcher
        fetcher = MarginFetcher()
        result = fetcher.fetch("sh600989", days=5)
        # 宝丰能源可能没有融资融券数据，所以允许 None
        if result is not None:
            assert isinstance(result, list)
            if len(result) > 0:
                assert "date" in result[0]
                assert "rzye" in result[0]

    def test_holder_fetch_real(self):
        """真实获取股东户数数据。"""
        from fetchers.eastmoney_chip import HolderFetcher
        fetcher = HolderFetcher()
        result = fetcher.fetch("sh600989", periods=2)
        # 股东户数数据应该存在
        if result is not None:
            assert isinstance(result, list)
            if len(result) > 0:
                assert "holder_num" in result[0]
                assert "concentration" in result[0]

    def test_top_holder_fetch_real(self):
        """真实获取十大流通股东数据。"""
        from fetchers.eastmoney_chip import TopHolderFetcher
        fetcher = TopHolderFetcher()
        result = fetcher.fetch("sh600989")
        # 十大流通股东数据应该存在
        if result is not None:
            assert isinstance(result, list)
            if len(result) > 0:
                assert "holder_name" in result[0]
                assert "is_institution" in result[0]


class TestChipCLI:
    """chip.py CLI 测试。"""

    def test_chip_help(self):
        """chip.py --help 正常输出。"""
        result = subprocess.run(
            ["python3", "scripts/chip.py", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "资金面分析" in result.stdout

    @pytest.mark.network
    def test_chip_json_output(self):
        """chip.py -j 输出有效 JSON。"""
        result = subprocess.run(
            ["python3", "scripts/chip.py", "sh600989", "-j"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        # 解析 JSON
        data = json.loads(result.stdout)
        assert "margin" in data or "holders" in data or "top_holders" in data

    @pytest.mark.network
    def test_chip_margin_only(self):
        """chip.py --margin 仅输出融资融券。"""
        result = subprocess.run(
            ["python3", "scripts/chip.py", "sh600989", "--margin", "-j"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "margin" in data
        assert "holders" not in data
        assert "top_holders" not in data


class TestScoringIntegration:
    """评分引擎集成测试。"""

    def test_scoring_with_chip_data(self):
        """评分引擎正确处理资金面数据。"""
        from technical.scoring import composite_score

        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "放大"},
            "kdj": {"signal": "金叉"},
            "bollinger": {"position": 0.5, "bandwidth_desc": "正常"},
            "rsi": {"rsi": 50},
            "volume": {"volume_price_signal": 1, "volume_ratio": 1.2},
            "patterns": [],
            "chip": {
                "margin": {"rzjme_5d": 1000000, "rzjme_trend": "连续增加"},
                "holders": {"concentration": "持续集中"},
            },
        }

        result = composite_score(features, stock_type="蓝筹股")
        assert "score" in result
        assert "grade" in result
        assert result["score"] > 0

    def test_scoring_without_chip_data(self):
        """评分引擎在无资金面数据时正常工作。"""
        from technical.scoring import composite_score

        features = {
            "ma_system": {"alignment": "多头排列"},
            "macd": {"signal": 1, "bar_trend": "放大"},
            "kdj": {"signal": "金叉"},
            "bollinger": {"position": 0.5, "bandwidth_desc": "正常"},
            "rsi": {"rsi": 50},
            "volume": {"volume_price_signal": 1, "volume_ratio": 1.2},
            "patterns": [],
        }

        result = composite_score(features, stock_type="普通股")
        assert "score" in result
        assert result["score"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

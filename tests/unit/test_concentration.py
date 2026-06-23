"""持仓集中度检查单元测试。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.manager import PortfolioManager


@pytest.fixture
def pm(tmp_path):
    """创建临时 PortfolioManager。"""
    import json

    path = tmp_path / "portfolio.json"
    # 创建空持仓文件，避免回退到示例文件
    path.write_text(json.dumps({"version": 2, "positions": [], "watchlist": []}))
    return PortfolioManager(path=str(path))


class TestCheckConcentration:
    def test_empty_portfolio(self, pm):
        """空持仓返回无警告。"""
        result = pm.check_concentration()
        assert result["warnings"] == []

    def test_single_stock_under_limit(self, pm):
        """多只持仓，单只未超限。"""
        pm.add_position("sh600989", "宝丰能源", 18.5, 100)  # 1850
        pm.add_position("sz000807", "云铝股份", 12.0, 100)  # 1200
        pm.add_position("sh601318", "中国平安", 50.0, 100)  # 5000
        pm.add_position("sh600519", "贵州茅台", 1500.0, 10)  # 15000
        # 设置宽松阈值，确保不触发
        result = pm.check_concentration(
            single_stock_limit=1.0,
            top3_limit=1.0,
            industry_limit=1.0,
        )
        assert result["warnings"] == []

    def test_single_stock_over_limit(self, pm):
        """单只持仓超限（20%）。"""
        # 添加多只股票，使某只占比超过 20%
        pm.add_position("sh600989", "宝丰能源", 18.5, 1000)  # 18500
        pm.add_position("sz000807", "云铝股份", 12.0, 500)  # 6000
        pm.add_position("sh601318", "中国平安", 50.0, 100)  # 5000
        # sh600989 占比 18500/29500 = 62.7% > 20%
        result = pm.check_concentration(single_stock_limit=0.20)
        assert len(result["warnings"]) > 0
        assert "集中度" in result["warnings"][0]

    def test_top3_over_limit(self, pm):
        """前 3 大持仓超限（50%）。"""
        pm.add_position("sh600989", "宝丰能源", 18.5, 1000)
        pm.add_position("sz000807", "云铝股份", 12.0, 500)
        pm.add_position("sh601318", "中国平安", 50.0, 100)
        # 前 3 大 = 100%
        result = pm.check_concentration(top3_limit=0.50)
        assert any("前3大" in w for w in result["warnings"])

    def test_details_structure(self, pm):
        """details 包含 single/top3/industry。"""
        pm.add_position("sh600989", "宝丰能源", 18.5, 1000)
        result = pm.check_concentration()
        assert "single" in result["details"]
        assert "top3" in result["details"]
        assert "industry" in result["details"]

    def test_custom_limits(self, pm):
        """自定义阈值生效。"""
        pm.add_position("sh600989", "宝丰能源", 18.5, 1000)
        # 100% 占比，但阈值设为 100% 不应触发
        result = pm.check_concentration(
            single_stock_limit=1.0, top3_limit=1.0, industry_limit=1.0
        )
        assert result["warnings"] == []

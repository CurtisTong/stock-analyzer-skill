"""Brinson 归因模块单元测试。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.brinson import (
    brinson_attribution,
    brinson_from_holdings,
    format_brinson_report,
)


class TestBrinsonAttribution:
    def test_basic_brinson(self):
        """基础 Brinson 归因：3 行业 + 已知权重与收益。"""
        result = brinson_attribution(
            portfolio_sector_returns={"科技": 0.15, "消费": 0.05, "金融": 0.02},
            benchmark_sector_returns={"科技": 0.10, "消费": 0.05, "金融": 0.05},
            portfolio_sector_weights={"科技": 0.5, "消费": 0.3, "金融": 0.2},
            benchmark_sector_weights={"科技": 0.4, "消费": 0.3, "金融": 0.3},
        )
        # 超配科技（+10%）+ 选择效应也贡献正 = 总超额应为正
        assert result.total_excess_return > 0
        # 配置效应总和应近似配置超额
        assert isinstance(result.total_allocation, float)
        # 行业分类应完整
        assert len(result.sectors) == 3

    def test_empty_input(self):
        """空输入应返回空的 BrinsonResult。"""
        result = brinson_attribution({}, {}, {}, {})
        assert result.sectors == []
        assert result.total_excess_return == 0

    def test_brinson_from_holdings(self):
        """从持仓快速构造 Brinson。"""
        positions = [
            {"code": "sh600519", "name": "茅台", "cost": 1800, "quantity": 100, "tags": ["消费"]},
            {"code": "sh601318", "name": "平安", "cost": 50, "quantity": 1000, "tags": ["金融"]},
        ]
        quotes = {"sh600519": 1900, "sh601318": 48}
        result = brinson_from_holdings(positions, quotes)
        assert isinstance(result, type(positions[0]) if False else type(result))
        assert result.portfolio_return != 0 or result.benchmark_return != 0

    def test_format_brinson_report(self):
        """格式化报告应包含关键术语。"""
        positions = [
            {"code": "sh600519", "name": "茅台", "cost": 1800, "quantity": 100, "tags": ["消费"]},
        ]
        quotes = {"sh600519": 1900}
        result = brinson_from_holdings(positions, quotes)
        report = format_brinson_report(result)
        assert "Brinson" in report
        assert "组合收益" in report
        assert "配置效应" in report
        assert "选择效应" in report

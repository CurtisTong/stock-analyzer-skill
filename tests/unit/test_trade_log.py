"""交易日志单元测试。"""

import sys
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from portfolio.trade_log import TradeLog


@pytest.fixture
def trade_log(tmp_path):
    """创建临时交易日志。"""
    path = tmp_path / "trade_log.json"
    return TradeLog(path=str(path))


class TestTradeLogRecord:
    def test_record_basic(self, trade_log):
        """基本记录功能。"""
        result = trade_log.record(
            code="sh600989",
            name="宝丰能源",
            buy_date="2025-03-15",
            cost=18.5,
            quantity=1000,
            sell_price=22.0,
        )
        assert result["code"] == "sh600989"
        assert result["name"] == "宝丰能源"
        assert result["profit"] == 3500.0
        assert result["profit_pct"] == pytest.approx(18.92, abs=0.1)

    def test_record_auto_save(self, trade_log):
        """自动保存到文件。"""
        trade_log.record(code="sh600989", cost=18.5, quantity=1000, sell_price=22.0)
        trade_log.reload()
        records = trade_log.query()
        assert len(records) == 1

    def test_record_no_save(self, trade_log):
        """不自动保存时文件为空。"""
        trade_log.record(
            code="sh600989", cost=18.5, quantity=1000, sell_price=22.0, auto_save=False
        )
        trade_log.reload()
        records = trade_log.query()
        assert len(records) == 0

    def test_record_zero_sell_price(self, trade_log):
        """卖出价为 0 时盈亏为 0。"""
        result = trade_log.record(code="sh600989", cost=18.5, quantity=1000)
        assert result["profit"] == 0.0
        assert result["profit_pct"] == 0.0


class TestTradeLogQuery:
    def test_query_by_code(self, trade_log):
        """按代码查询。"""
        trade_log.record(code="sh600989", cost=18.5, quantity=1000, sell_price=22.0)
        trade_log.record(code="sz000807", cost=12.0, quantity=500, sell_price=15.0)
        records = trade_log.query(code="sh600989")
        assert len(records) == 1
        assert records[0]["code"] == "sh600989"

    def test_query_by_date_range(self, trade_log):
        """按日期范围查询。"""
        trade_log.record(
            code="sh600989",
            cost=18.5,
            quantity=1000,
            sell_price=22.0,
            sell_date="2026-01-01",
        )
        trade_log.record(
            code="sz000807",
            cost=12.0,
            quantity=500,
            sell_price=15.0,
            sell_date="2026-06-01",
        )
        records = trade_log.query(start_date="2026-03-01")
        assert len(records) == 1
        assert records[0]["code"] == "sz000807"

    def test_query_limit(self, trade_log):
        """限制返回数量。"""
        for i in range(10):
            trade_log.record(code=f"sh60000{i}", cost=10, quantity=100, sell_price=12)
        records = trade_log.query(limit=3)
        assert len(records) == 3

    def test_query_empty(self, trade_log):
        """空日志查询返回空列表。"""
        records = trade_log.query()
        assert records == []


class TestTradeLogStats:
    def test_stats_basic(self, trade_log):
        """基本统计功能。"""
        trade_log.record(code="sh600989", cost=18.5, quantity=1000, sell_price=22.0)
        trade_log.record(code="sz000807", cost=12.0, quantity=500, sell_price=10.0)
        stats = trade_log.stats()
        assert stats["total_trades"] == 2
        assert stats["win_trades"] == 1
        assert stats["loss_trades"] == 1
        assert stats["win_rate"] == 50.0

    def test_stats_empty(self, trade_log):
        """空日志统计返回零值。"""
        stats = trade_log.stats()
        assert stats["total_trades"] == 0
        assert stats["win_rate"] == 0.0

    def test_summary_empty(self, trade_log):
        """空日志摘要。"""
        assert trade_log.summary() == "暂无交易记录"

    def test_summary_with_records(self, trade_log):
        """有记录时摘要包含关键信息。"""
        trade_log.record(code="sh600989", cost=18.5, quantity=1000, sell_price=22.0)
        summary = trade_log.summary()
        assert "交易记录" in summary
        assert "胜率" in summary

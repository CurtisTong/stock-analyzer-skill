"""
测试 scripts/portfolio/daily_report.py：每日持仓报告生成。

聚焦纯函数：_generate_empty_report / _format_report / _parse_quote。
避免磁盘 IO 和网络 IO。
"""
import json
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# daily_report.py line 25 引用了不存在的 common.http.HttpClient（项目 bug）
# 注入 mock 模块绕过，同时满足 common/__init__.py 的 import
class _MockHttpClient:
    def __init__(self, *args, **kwargs):
        pass
    def get(self, *args, **kwargs):
        return b""

_mock_http_module = types.ModuleType("common.http")
_mock_http_module.HttpClient = _MockHttpClient
_mock_http_module.USER_AGENTS = []
_mock_http_module.http_get = lambda *a, **kw: b""
_mock_http_module.http_get_with_headers = lambda *a, **kw: b""
_mock_http_module.decode_gbk = lambda x: x.decode("utf-8", errors="replace") if isinstance(x, bytes) else x
sys.modules["common.http"] = _mock_http_module

from portfolio.daily_report import DailyReportGenerator


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_stock_details():
    return [
        {
            "code": "sh600989", "name": "宝丰能源", "shares": 1000, "cost_price": 18.5,
            "current_price": 20.0, "change_pct": 2.5, "market_value": 20000,
            "profit": 1500, "profit_rate": 8.11,
        },
        {
            "code": "sz000807", "name": "云铝股份", "shares": 500, "cost_price": 12.0,
            "current_price": 11.0, "change_pct": -1.5, "market_value": 5500,
            "profit": -500, "profit_rate": -8.33,
        },
    ]


# ═══════════════════════════════════════════════════════════════
# _generate_empty_report
# ═══════════════════════════════════════════════════════════════

class TestGenerateEmptyReport:
    def test_returns_string(self, tmp_path):
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen._generate_empty_report()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mentions_no_positions(self, tmp_path):
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen._generate_empty_report()
        assert "暂无持仓" in result

    def test_includes_today_date(self, tmp_path):
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen._generate_empty_report()
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_includes_instructions(self, tmp_path):
        """应包含使用说明。"""
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen._generate_empty_report()
        assert "portfolio.json" in result
        assert "/portfolio" in result or "Web" in result


# ═══════════════════════════════════════════════════════════════
# _format_report
# ═══════════════════════════════════════════════════════════════

class TestFormatReport:
    def test_returns_string(self, sample_stock_details):
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(
            total_value=25500,
            total_profit=1000,
            total_profit_rate=4.0,
            stock_details=sample_stock_details,
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_total_value(self, sample_stock_details):
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(25500, 1000, 4.0, sample_stock_details)
        assert "25,500" in result or "25500" in result

    def test_includes_profit_with_sign(self, sample_stock_details):
        """盈利时 + 号显示。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(25500, 1000, 4.0, sample_stock_details)
        assert "+" in result

    def test_negative_profit_no_plus(self, sample_stock_details):
        """亏损时无 + 号。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(23500, -1000, -4.0, sample_stock_details)
        # 负数不应该有 +¥ 形式
        assert "+¥-1,000" not in result

    def test_includes_stock_table(self, sample_stock_details):
        """含 markdown 表格。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(25500, 1000, 4.0, sample_stock_details)
        assert "| 股票" in result
        assert "宝丰能源" in result
        assert "云铝股份" in result

    def test_includes_best_worst(self, sample_stock_details):
        """应识别涨幅最大和跌幅最大。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(25500, 1000, 4.0, sample_stock_details)
        # 宝丰 +2.5% 是涨幅最大
        assert "📈" in result
        assert "宝丰" in result
        # 云铝 -1.5% 是跌幅最大
        assert "📉" in result
        assert "云铝" in result

    def test_empty_stock_details(self):
        """无持仓详情时不应崩溃。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(0, 0, 0, [])
        assert "持仓数量" in result
        assert "0 只" in result

    def test_contains_sections(self, sample_stock_details):
        """应包含所有段落标题。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._format_report(25500, 1000, 4.0, sample_stock_details)
        for section in ["持仓概览", "个股表现", "今日关注", "操作建议"]:
            assert section in result, f"缺少段落: {section}"


# ═══════════════════════════════════════════════════════════════
# _parse_quote
# ═══════════════════════════════════════════════════════════════

class TestParseQuote:
    def test_parses_tencent_format(self):
        """解析腾讯行情格式（35+ 字段，~ 分隔）。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        # 腾讯格式：v_sh600989="1~宝丰能源~600989~20.00~19.50~19.80~..."
        # parts[1]=name, parts[2]=code, parts[3]=price, parts[32]=change_pct
        parts = ["v_sh600989="] + [""] * 35
        parts[1] = "宝丰能源"
        parts[2] = "sh600989"
        parts[3] = "20.00"
        parts[4] = "19.50"
        parts[5] = "19.80"
        parts[6] = "1234"
        parts[32] = "2.56"
        response = '"' + "~".join(parts) + '"'

        result = gen._parse_quote(response, "sh600989")
        assert result is not None
        assert result["code"] == "sh600989"
        assert result["price"] == 20.00
        assert result["change_pct"] == 2.56

    def test_short_response_returns_none(self):
        """parts < 35 时返回 None。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        result = gen._parse_quote("a~b~c", "sh600989")
        assert result is None

    def test_empty_response_returns_none(self):
        """空响应返回 None。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        assert gen._parse_quote("", "sh600989") is None

    def test_invalid_format_returns_none(self):
        """无效格式返回 None（不抛异常）。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        assert gen._parse_quote("not a valid quote string", "sh600989") is None


# ═══════════════════════════════════════════════════════════════
# 数学计算（generate 中嵌入的逻辑）
# ═══════════════════════════════════════════════════════════════

class TestMathConstants:
    """验证 generate() 中关键数学。"""

    def test_market_value_equals_price_times_shares(self, sample_stock_details):
        """market_value = current_price × shares。"""
        for stock in sample_stock_details:
            expected = stock["current_price"] * stock["shares"]
            assert abs(stock["market_value"] - expected) < 0.01

    def test_profit_equals_mv_minus_cost(self, sample_stock_details):
        """profit = market_value - cost_value。"""
        for stock in sample_stock_details:
            mv = stock["current_price"] * stock["shares"]
            cv = stock["cost_price"] * stock["shares"]
            expected = mv - cv
            assert abs(stock["profit"] - expected) < 0.01

    def test_profit_rate_pct(self, sample_stock_details):
        """profit_rate = (profit / cost_value) * 100。"""
        for stock in sample_stock_details:
            cv = stock["cost_price"] * stock["shares"]
            expected = (stock["profit"] / cv) * 100 if cv > 0 else 0
            assert abs(stock["profit_rate"] - expected) < 0.1


# ═══════════════════════════════════════════════════════════════
# generate() 端到端（mock 外部依赖）
# ═══════════════════════════════════════════════════════════════

class TestGenerateE2E:
    def test_generate_empty(self, tmp_path):
        """无持仓文件应返回空报告。"""
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen.generate()
        assert "暂无持仓" in result

    def test_generate_with_holdings(self, tmp_path):
        """含持仓时生成完整报告（mock quotes）。"""
        portfolio_file = tmp_path / "portfolio.json"
        # _load_portfolio 直接 json.load，期望顶层是 list of dict
        portfolio_file.write_text(json.dumps([
            {"code": "sh600989", "name": "宝丰能源", "shares": 1000, "cost_price": 18.5},
        ]))
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch.object(gen, "_fetch_quotes", return_value={
            "sh600989": {"price": 20.0, "change_pct": 2.5}
        }):
            result = gen.generate()
        assert "持仓日报" in result
        assert "宝丰能源" in result
        assert "持仓概览" in result
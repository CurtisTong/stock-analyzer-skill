"""stock.py 覆盖测试。

覆盖 render_text 各段、render_brief 各分支、main() 各分支
（json/brief/text 输出、with_backtest 成功/失败）。
所有业务层调用均 mock。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stock


def _full_result():
    return {
        "code": "sh600519",
        "name": "茅台",
        "price": 1800.5,
        "change_pct": 2.35,
        "data_warnings": ["财务数据部分缺失"],
        "warning": "K线数据不足",
        "profile": {"type": "蓝筹", "industry": "白酒"},
        "kline_count": 250,
        "chan": {
            "valid": True,
            "fenxing_count": 10,
            "bi_count": 5,
            "zhongshu_count": 2,
            "current_position": "中枢上方",
        },
        "technical": {
            "ma": "多头",
            "macd_signal": 1,
            "kdj": "金叉",
            "rsi": 65.3,
            "boll_position": 0.75,
            "volume_signal": 1,
            "patterns": [{"name": "老鸭头"}, {"name": "红三兵"}],
        },
        "finance": {
            "eps": 45.2,
            "roe": 30.5,
            "net_profit_yoy": 15.3,
            "revenue_yoy": 12.1,
            "gross_margin": 91.5,
            "debt_ratio": 20.3,
        },
        "score": {
            "score": 82.5,
            "grade": "A",
            "buy_signals": ["MACD金叉", "放量突破"],
            "sell_signals": [],
        },
        "data_time": "2025-01-10 15:00",
        "data_sources": ["行情", "财务"],
        "data_failed": [],
    }


class TestRenderText:
    def test_full_result(self):
        result = _full_result()
        text = stock.render_text(result)
        assert "茅台" in text
        assert "sh600519" in text
        assert "行业画像" in text
        assert "K 线" in text
        assert "缠论" in text
        assert "技术面" in text
        assert "财务" in text
        assert "综合评分" in text
        assert "买入信号" in text

    def test_chan_invalid(self):
        result = _full_result()
        result["chan"] = {"valid": False, "error": "数据不足"}
        text = stock.render_text(result)
        assert "数据不足" in text

    def test_chan_invalid_no_error(self):
        result = _full_result()
        result["chan"] = {"valid": False}
        text = stock.render_text(result)
        assert "数据不足" in text

    def test_negative_change(self):
        result = _full_result()
        result["change_pct"] = -3.5
        text = stock.render_text(result)
        assert "🔴" in text

    def test_low_score(self):
        result = _full_result()
        result["score"]["score"] = 40
        text = stock.render_text(result)
        assert "🔴" in text

    def test_medium_score(self):
        result = _full_result()
        result["score"]["score"] = 55
        text = stock.render_text(result)
        assert "🟡" in text

    def test_sell_signals(self):
        result = _full_result()
        result["score"]["sell_signals"] = ["死叉", "放量下跌"]
        text = stock.render_text(result)
        assert "卖出信号" in text

    def test_ma_cross_icon(self):
        result = _full_result()
        result["technical"]["ma"] = "交叉"
        text = stock.render_text(result)
        assert "🟡" in text

    def test_ma_empty_icon(self):
        result = _full_result()
        result["technical"]["ma"] = "unknown"
        text = stock.render_text(result)
        assert "⚪" in text

    def test_no_patterns(self):
        result = _full_result()
        result["technical"]["patterns"] = []
        text = stock.render_text(result)
        assert "形态" not in text

    def test_missing_fields(self):
        result = {"code": "sh600519", "name": "茅台", "price": 100, "change_pct": 0}
        text = stock.render_text(result)
        assert "茅台" in text
        assert "未知" not in text or "(未知)" not in text.split("\n")[1]


class TestRenderBrief:
    def test_high_score_buy(self):
        result = _full_result()
        result["score"]["score"] = 80
        text = stock.render_brief(result)
        assert "关注买入" in text
        assert "茅台" in text

    def test_medium_score_watch(self):
        result = _full_result()
        result["score"]["score"] = 60
        result["score"]["buy_signals"] = []
        result["score"]["sell_signals"] = []
        text = stock.render_brief(result)
        assert "观望" in text

    def test_low_score_avoid(self):
        result = _full_result()
        result["score"]["score"] = 40
        result["score"]["buy_signals"] = []
        result["score"]["sell_signals"] = ["死叉"]
        text = stock.render_brief(result)
        assert "谨慎回避" in text

    def test_buy_only_overrides(self):
        result = _full_result()
        result["score"]["score"] = 40
        result["score"]["buy_signals"] = ["金叉"]
        result["score"]["sell_signals"] = []
        text = stock.render_brief(result)
        assert "关注买入" in text

    def test_sell_only_overrides(self):
        result = _full_result()
        result["score"]["score"] = 80
        result["score"]["buy_signals"] = []
        result["score"]["sell_signals"] = ["死叉"]
        text = stock.render_brief(result)
        assert "谨慎回避" in text

    def test_negative_change_icon(self):
        result = _full_result()
        result["change_pct"] = -2.0
        text = stock.render_brief(result)
        assert "🔴" in text

    def test_no_technical(self):
        result = _full_result()
        del result["technical"]
        text = stock.render_brief(result)
        assert "茅台" in text

    def test_no_finance(self):
        result = _full_result()
        del result["finance"]
        text = stock.render_brief(result)
        assert "茅台" in text


class TestMain:
    def _setup(self, argv, result=None):
        if result is None:
            result = _full_result()
        return argv, result

    def test_text_output(self):
        argv, result = self._setup(["stock.py", "sh600519"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print") as m_print:
                    stock.main()
        m_print.assert_called_once()
        output = m_print.call_args[0][0]
        assert "茅台" in output

    def test_json_output(self):
        argv, result = self._setup(["stock.py", "sh600519", "-j"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print") as m_print:
                    stock.main()
        output = m_print.call_args[0][0]
        assert '"code"' in output
        assert '"sh600519"' in output

    def test_brief_output(self):
        argv, result = self._setup(["stock.py", "sh600519", "--brief"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print") as m_print:
                    stock.main()
        output = m_print.call_args[0][0]
        assert "茅台" in output

    def test_no_finance_flag(self):
        argv, result = self._setup(["stock.py", "sh600519", "--no-finance"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print"):
                    stock.main()
        # 验证 analyze 被调用时 include_finance=False
        call_kwargs = MockSvc.return_value.analyze.call_args
        assert call_kwargs.kwargs["include_finance"] is False

    def test_no_technical_flag(self):
        argv, result = self._setup(["stock.py", "sh600519", "--no-technical"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print"):
                    stock.main()
        call_kwargs = MockSvc.return_value.analyze.call_args
        assert call_kwargs.kwargs["include_technical"] is False

    def test_no_chan_flag(self):
        argv, result = self._setup(["stock.py", "sh600519", "--no-chan"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print"):
                    stock.main()
        call_kwargs = MockSvc.return_value.analyze.call_args
        assert call_kwargs.kwargs["include_chan"] is False

    def test_with_backtest_success(self):
        argv, result = self._setup(["stock.py", "sh600519", "--with-backtest", "-j"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("backtest.metrics.run_backtest", return_value={
                    "win_rate_pct": 60, "total_return_pct": 15, "sharpe_ratio": 1.5, "max_drawdown_pct": -10,
                }):
                    with patch("builtins.print") as m_print:
                        stock.main()
        output = m_print.call_args[0][0]
        assert "backtest" in output
        assert "60" in output

    def test_with_backtest_failure(self):
        argv, result = self._setup(["stock.py", "sh600519", "--with-backtest", "-j"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("backtest.metrics.run_backtest", side_effect=RuntimeError("err")):
                    with patch("builtins.print") as m_print:
                        stock.main()
        output = m_print.call_args[0][0]
        assert "backtest_error" in output

    def test_finance_periods(self):
        argv, result = self._setup(["stock.py", "sh600519", "--finance-periods", "4"])
        with patch("sys.argv", argv):
            with patch("stock.StockAnalysisService") as MockSvc:
                MockSvc.return_value.analyze.return_value = result
                with patch("builtins.print"):
                    stock.main()
        call_kwargs = MockSvc.return_value.analyze.call_args
        assert call_kwargs.kwargs["finance_periods"] == 4

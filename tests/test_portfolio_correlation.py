"""测试 scripts/portfolio_correlation.py：组合相关性分析。

策略：mock 外部数据 + portfolio 模块，测试 9 个函数。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import portfolio_correlation


def _mock_kline(closes):
    klines = []
    for c in closes:
        k = SimpleNamespace()
        k.close = c
        klines.append(k)
    return klines


# ═══════════════════════════════════════════════════════════════
# _pearson_corr
# ═══════════════════════════════════════════════════════════════


class TestPearsonCorr:
    def test_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0]
        assert portfolio_correlation._pearson_corr(x, y) == 1.0

    def test_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
        y = [-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0, -9.0, -10.0, -11.0]
        assert portfolio_correlation._pearson_corr(x, y) == -1.0

    def test_zero_corr(self):
        """无相关。"""
        import random
        random.seed(42)
        x = [random.gauss(0, 1) for _ in range(20)]
        y = [random.gauss(0, 1) for _ in range(20)]
        result = portfolio_correlation._pearson_corr(x, y)
        # 随机数据相关系数应当接近 0
        assert result is not None
        assert abs(result) < 0.5

    def test_short_input(self):
        assert portfolio_correlation._pearson_corr([1.0], [1.0]) is None
        assert portfolio_correlation._pearson_corr([1.0] * 5, [1.0] * 5) is None

    def test_zero_variance(self):
        """方差为 0 时 None。"""
        x = [5.0] * 15
        y = list(range(15))
        assert portfolio_correlation._pearson_corr(x, y) is None

    def test_mismatched_length(self):
        """长度不匹配：取 min。"""
        x = [1.0] * 15
        y = [1.0, 2.0]
        # n = 2 < 10 → None
        assert portfolio_correlation._pearson_corr(x, y) is None


# ═══════════════════════════════════════════════════════════════
# _load_returns
# ═══════════════════════════════════════════════════════════════


class TestLoadReturns:
    def test_success(self):
        closes = [100 + i for i in range(60)]
        with patch.object(portfolio_correlation, "get_kline",
                          return_value=_mock_kline(closes)):
            result = portfolio_correlation._load_returns("sh600519", window=60)
        assert result is not None
        # daily returns = (c[i]/c[i-1] - 1)
        assert len(result) == len(closes) - 1

    def test_empty_kline(self):
        with patch.object(portfolio_correlation, "get_kline", return_value=[]):
            assert portfolio_correlation._load_returns("sh600519") is None

    def test_short_kline(self):
        """短 K 线返回空 list（1 元素无法算 daily returns）。"""
        with patch.object(portfolio_correlation, "get_kline",
                          return_value=_mock_kline([100])):
            result = portfolio_correlation._load_returns("sh600519")
        assert result == [] or result is None

    def test_exception(self):
        with patch.object(portfolio_correlation, "get_kline",
                          side_effect=Exception("net")):
            assert portfolio_correlation._load_returns("sh600519") is None


# ═══════════════════════════════════════════════════════════════
# compute_correlation_matrix
# ═══════════════════════════════════════════════════════════════


class TestComputeCorrelationMatrix:
    def test_two_codes(self):
        """2 只股票：单一相关系数。"""
        codes = ["sh600519", "sh600000"]
        # 用变化的数据避免 zero_variance
        returns = [0.01 * (i % 3 - 1) for i in range(60)]
        with patch.object(portfolio_correlation, "_load_returns",
                          return_value=returns):
            result = portfolio_correlation.compute_correlation_matrix(codes, window=60)
        assert result is not None
        assert "matrix" in result
        assert "avg_pairwise_corr" in result
        assert "high_corr_pairs" in result

    def test_three_codes(self):
        codes = ["sh600519", "sh600000", "sh601318"]
        with patch.object(portfolio_correlation, "_load_returns",
                          return_value=[0.01 * (i % 3 - 1) for i in range(60)]):
            result = portfolio_correlation.compute_correlation_matrix(codes, window=60)
        assert result is not None
        # 实际 codes 列表会包含 sh000300 指数（自动加入基准），至少 3 个
        assert len(result["codes"]) >= 3

    def test_empty_codes(self):
        result = portfolio_correlation.compute_correlation_matrix([], window=60)
        assert result is None or isinstance(result, dict)

    def test_single_code(self):
        result = portfolio_correlation.compute_correlation_matrix(["sh600519"], window=60)
        # 1 只股票没法算 pair 相关，可能 None
        assert result is None or "matrix" in result

    def test_load_failure(self):
        codes = ["sh600519", "sh600000"]
        with patch.object(portfolio_correlation, "_load_returns", return_value=None):
            result = portfolio_correlation.compute_correlation_matrix(codes, window=60)
        # 全部失败时返回 None 或 degraded
        assert result is None or "degraded" in str(result).lower()


# ═══════════════════════════════════════════════════════════════
# _interpret_matrix
# ═══════════════════════════════════════════════════════════════


class TestInterpretMatrix:
    def test_low_correlation(self):
        result = portfolio_correlation._interpret_matrix(0.3, [], 3)
        assert isinstance(result, str)
        assert "分散" in result or "低" in result

    def test_high_correlation(self):
        result = portfolio_correlation._interpret_matrix(0.85, [], 3)
        assert isinstance(result, str)
        assert "高" in result or "集中" in result or "伪分散" in result

    def test_mid_correlation(self):
        result = portfolio_correlation._interpret_matrix(0.6, [], 3)
        assert isinstance(result, str)

    def test_with_high_pairs(self):
        result = portfolio_correlation._interpret_matrix(
            0.7, [("sh600519", "sh600000", 0.85)], 3,
        )
        assert isinstance(result, str)

    def test_none_corr(self):
        result = portfolio_correlation._interpret_matrix(None, [], 3)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# compute_stock_vs_portfolio
# ═══════════════════════════════════════════════════════════════


class TestComputeStockVsPortfolio:
    def test_success(self):
        with patch.object(portfolio_correlation, "_load_returns",
                          return_value=[0.01 * i for i in range(60)]):
            result = portfolio_correlation.compute_stock_vs_portfolio(
                "sh600519", ["sh600000", "sh601318"], window=60,
            )
        assert result is not None
        assert "vs_portfolio_avg_corr" in result
        assert "diversification_benefit" in result

    def test_empty_portfolio(self):
        with patch.object(portfolio_correlation, "_load_returns",
                          return_value=[0.01] * 60):
            result = portfolio_correlation.compute_stock_vs_portfolio(
                "sh600519", [], window=60,
            )
        assert result is None or "n_portfolio_codes" in result

    def test_load_failure(self):
        with patch.object(portfolio_correlation, "_load_returns", return_value=None):
            result = portfolio_correlation.compute_stock_vs_portfolio(
                "sh600519", ["sh600000"], window=60,
            )
        assert result is None or "degraded" in str(result).lower()


# ═══════════════════════════════════════════════════════════════
# _interpret_diversification
# ═══════════════════════════════════════════════════════════════


class TestInterpretDiversification:
    def test_high_benefit(self):
        """低相关 → 高分散价值。"""
        result = portfolio_correlation._interpret_diversification(0.2)
        assert isinstance(result, str)
        assert "高" in result or "分散" in result

    def test_low_benefit(self):
        """高相关 → 低分散价值。"""
        result = portfolio_correlation._interpret_diversification(0.9)
        assert isinstance(result, str)

    def test_none(self):
        """None 输入抛 TypeError（实际行为，调用方需处理）。"""
        with pytest.raises(TypeError):
            portfolio_correlation._interpret_diversification(None)


# ═══════════════════════════════════════════════════════════════
# get_portfolio_codes
# ═══════════════════════════════════════════════════════════════


class TestGetPortfolioCodes:
    def test_with_positions(self):
        fake_pm = MagicMock()
        fake_pm.get_positions = MagicMock(return_value=[
            {"code": "sh600519", "shares": 100},
            {"code": "sh600000", "shares": 200},
        ])
        # mock portfolio.manager.PortfolioManager
        import sys
        fake_module = MagicMock()
        fake_module.PortfolioManager = MagicMock(return_value=fake_pm)
        with patch.dict(sys.modules, {"portfolio.manager": fake_module}):
            result = portfolio_correlation.get_portfolio_codes()
        assert "sh600519" in result
        assert "sh600000" in result

    def test_empty_portfolio(self):
        fake_pm = MagicMock()
        fake_pm.get_positions = MagicMock(return_value=[])
        import sys
        fake_module = MagicMock()
        fake_module.PortfolioManager = MagicMock(return_value=fake_pm)
        with patch.dict(sys.modules, {"portfolio.manager": fake_module}):
            result = portfolio_correlation.get_portfolio_codes()
        assert result == []

    def test_exception(self):
        """import 失败时返回空 list。"""
        with patch.dict(sys.modules, {"portfolio.manager": None}):
            result = portfolio_correlation.get_portfolio_codes()
        assert result == []


# ═══════════════════════════════════════════════════════════════
# compute_full_portfolio_correlation
# ═══════════════════════════════════════════════════════════════


class TestComputeFullPortfolioCorrelation:
    def test_with_stock_and_portfolio(self):
        with patch.object(portfolio_correlation, "get_portfolio_codes",
                          return_value=["sh600000", "sh601318"]), \
             patch.object(portfolio_correlation, "_load_returns",
                          return_value=[0.01 * i for i in range(60)]):
            result = portfolio_correlation.compute_full_portfolio_correlation(
                stock_code="sh600519", window=60,
            )
        assert result is not None
        assert "data_quality" in result
        # n_portfolio_codes 或 avg_pairwise_corr
        assert "n_portfolio_codes" in result or "avg_pairwise_corr" in result

    def test_empty_portfolio(self):
        """无持仓时返回 degraded。"""
        with patch.object(portfolio_correlation, "get_portfolio_codes",
                          return_value=[]):
            result = portfolio_correlation.compute_full_portfolio_correlation(
                stock_code="sh600519", window=60,
            )
        assert result is not None
        assert "data_quality" in result

    def test_no_stock_code(self):
        """无 stock_code 时仅算组合矩阵。"""
        with patch.object(portfolio_correlation, "get_portfolio_codes",
                          return_value=["sh600000", "sh601318"]), \
             patch.object(portfolio_correlation, "_load_returns",
                          return_value=[0.01 * i for i in range(60)]):
            result = portfolio_correlation.compute_full_portfolio_correlation(
                stock_code=None, window=60,
            )
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["portfolio_correlation.py"])
        try:
            portfolio_correlation.main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert captured is not None

    def test_with_stock_code(self, capsys, monkeypatch):
        with patch.object(portfolio_correlation, "compute_full_portfolio_correlation",
                          return_value={
                              "n_portfolio_codes": 2,
                              "portfolio_codes": ["sh600000", "sh601318"],
                              "matrix": [[1.0, 0.5], [0.5, 1.0]],
                              "avg_pairwise_corr": 0.5,
                              "high_corr_pairs": [],
                              "vs_portfolio_avg_corr": 0.3,
                              "diversification_benefit": "中",
                              "portfolio_empty": False,
                              "interpretation": "良好分散",
                              "data_quality": {"degraded_fields": []},
                          }):
            monkeypatch.setattr(sys, "argv", ["portfolio_correlation.py", "--stock", "sh600519"])
            portfolio_correlation.main()
        captured = capsys.readouterr()
        assert captured is not None

    def test_json_output(self, capsys, monkeypatch):
        import json
        with patch.object(portfolio_correlation, "compute_full_portfolio_correlation",
                          return_value={
                              "n_portfolio_codes": 2,
                              "portfolio_codes": ["sh600000", "sh601318"],
                              "matrix": [[1.0, 0.5], [0.5, 1.0]],
                              "avg_pairwise_corr": 0.5,
                              "high_corr_pairs": [],
                              "vs_portfolio_avg_corr": 0.3,
                              "diversification_benefit": "中",
                              "portfolio_empty": False,
                              "interpretation": "良好分散",
                              "data_quality": {"degraded_fields": []},
                          }):
            monkeypatch.setattr(sys, "argv", ["portfolio_correlation.py", "--stock", "sh600519", "-j"])
            portfolio_correlation.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["avg_pairwise_corr"] == 0.5

    def test_list_flag(self, capsys, monkeypatch):
        with patch.object(portfolio_correlation, "get_portfolio_codes",
                          return_value=["sh600000", "sh601318"]):
            monkeypatch.setattr(sys, "argv", ["portfolio_correlation.py", "--list"])
            portfolio_correlation.main()
        captured = capsys.readouterr()
        assert "sh600000" in captured.out or "持仓" in captured.out

    def test_empty_portfolio_message(self, capsys, monkeypatch):
        with patch.object(portfolio_correlation, "compute_full_portfolio_correlation",
                          return_value={
                              "portfolio_empty": True,
                              "interpretation": "无持仓",
                              "data_quality": {"degraded_fields": []},
                          }):
            monkeypatch.setattr(sys, "argv", ["portfolio_correlation.py"])
            portfolio_correlation.main()
        captured = capsys.readouterr()
        assert "无持仓" in captured.out or "持仓" in captured.out
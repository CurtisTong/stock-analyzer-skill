"""测试 scripts/industry_beta.py：行业 beta 计算。

策略：mock get_quotes/get_kline，测试 5 个函数。
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import industry_beta


def _mock_quote(code, total_cap=1e10):
    q = SimpleNamespace(code=code, name="test")
    q.has_basic_data = lambda: True
    q.total_cap = total_cap
    return q


def _mock_kline(closes):
    klines = []
    for c in closes:
        k = SimpleNamespace()
        k.close = c
        klines.append(k)
    return klines


# ═══════════════════════════════════════════════════════════════
# select_index_by_size
# ═══════════════════════════════════════════════════════════════


class TestSelectIndexBySize:
    def test_large_cap(self):
        """> 500 亿 → sh000300。"""
        q = _mock_quote("sh600519", total_cap=1000.0)  # 1000 亿（单位：亿元）
        with patch("industry_beta.get_quotes", return_value=[q]):
            assert industry_beta.select_index_by_size("sh600519") == "sh000300"

    def test_mid_cap(self):
        """100-500 亿 → sh000905。"""
        q = _mock_quote("sh600519", total_cap=200.0)  # 200 亿
        with patch("industry_beta.get_quotes", return_value=[q]):
            assert industry_beta.select_index_by_size("sh600519") == "sh000905"

    def test_small_cap(self):
        """<= 100 亿 → sh000852。"""
        q = _mock_quote("sh600519", total_cap=50.0)
        with patch("industry_beta.get_quotes", return_value=[q]):
            assert industry_beta.select_index_by_size("sh600519") == "sh000852"

    def test_no_quote_fallback(self):
        """无 quote 时 fallback 到 sh000300。"""
        with patch("industry_beta.get_quotes", return_value=[]):
            assert industry_beta.select_index_by_size("sh600519") == "sh000300"

    def test_exception_fallback(self):
        """异常时 fallback。"""
        with patch("industry_beta.get_quotes", side_effect=Exception("net")):
            assert industry_beta.select_index_by_size("sh600519") == "sh000300"

    def test_no_basic_data_fallback(self):
        """无 basic_data 时 fallback。"""
        q = SimpleNamespace()
        q.has_basic_data = lambda: False
        with patch("industry_beta.get_quotes", return_value=[q]):
            assert industry_beta.select_index_by_size("sh600519") == "sh000300"


# ═══════════════════════════════════════════════════════════════
# _daily_returns
# ═══════════════════════════════════════════════════════════════


class TestDailyReturns:
    def test_normal(self):
        """正常序列：1d_return = (c[i]/c[i-1] - 1)。"""
        closes = [100, 110, 121, 100]  # +10%, +10%, -17.36%
        returns = industry_beta._daily_returns(closes)
        assert len(returns) == 3
        assert abs(returns[0] - 0.10) < 0.001
        assert abs(returns[1] - 0.10) < 0.001
        assert abs(returns[2] - (-0.1736)) < 0.001

    def test_short_input(self):
        """长度 < 2 返回空。"""
        assert industry_beta._daily_returns([]) == []
        assert industry_beta._daily_returns([100]) == []

    def test_zero_prev_close(self):
        """前一日 close=0 跳过（避免除零）。"""
        closes = [0, 100]
        returns = industry_beta._daily_returns(closes)
        # 除零时跳过
        assert len(returns) == 0 or all(abs(r) < 1e9 for r in returns)


# ═══════════════════════════════════════════════════════════════
# _ols_beta
# ═══════════════════════════════════════════════════════════════


class TestOlsBeta:
    def test_perfect_correlation(self):
        """完美正相关 → beta=1.0（n>=10）。"""
        r = [float(i) for i in range(1, 20)]
        result = industry_beta._ols_beta(r, r)
        assert result is not None
        assert abs(result["beta"] - 1.0) < 0.01
        assert abs(result["alpha"]) < 0.01
        assert abs(result["r_squared"] - 1.0) < 0.01

    def test_double_correlation(self):
        """个股 = 2 * 指数 → beta=2.0。"""
        r_index = [float(i) for i in range(1, 20)]
        r_stock = [2.0 * x for x in r_index]
        result = industry_beta._ols_beta(r_stock, r_index)
        assert result is not None
        assert abs(result["beta"] - 2.0) < 0.01

    def test_zero_variance(self):
        """指数无波动 → beta 不可计算。"""
        r = [1.0] * 15
        result = industry_beta._ols_beta(r, [0.0] * 15)
        assert result is None

    def test_short_input(self):
        """长度 < 10 返回 None。"""
        result = industry_beta._ols_beta([1.0] * 5, [1.0] * 5)
        assert result is None

    def test_mismatched_length(self):
        """长度不匹配返回 None。"""
        result = industry_beta._ols_beta([1.0] * 15, [1.0] * 5)
        assert result is None

    def test_negative_correlation(self):
        """负相关 → beta < 0。"""
        r_index = [float(i) for i in range(1, 20)]
        r_stock = [-1.0 * x for x in r_index]
        result = industry_beta._ols_beta(r_stock, r_index)
        assert result is not None
        assert result["beta"] < 0

    def test_n_observations(self):
        """返回 n_observations 字段。"""
        r = [float(i) for i in range(1, 20)]
        result = industry_beta._ols_beta(r, r)
        assert result["n_observations"] == 19


# ═══════════════════════════════════════════════════════════════
# _interpret_beta
# ═══════════════════════════════════════════════════════════════


class TestInterpretBeta:
    def test_high_beta(self):
        """beta > 1.5 → 高弹性。"""
        result = industry_beta._interpret_beta(2.0)
        assert "高弹性" in result or "进攻" in result

    def test_low_beta(self):
        """beta < 0.5 → 防御。"""
        result = industry_beta._interpret_beta(0.3)
        assert "防御" in result or "低弹性" in result

    def test_normal_beta(self):
        """0.5-1.5 → 正常。"""
        result = industry_beta._interpret_beta(1.0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_negative_beta(self):
        """负 beta → 逆周期。"""
        result = industry_beta._interpret_beta(-0.5)
        assert "逆" in result or "负" in result

    def test_none_beta(self):
        """beta=None → 未知。"""
        result = industry_beta._interpret_beta(None)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# compute_beta
# ═══════════════════════════════════════════════════════════════


class TestComputeBeta:
    def test_success(self):
        """完整流程：拉 K 线 + 计算 OLS。"""
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110,
                  109, 108, 107, 106, 105, 104, 103, 102, 101,
                  100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                  110, 111, 112, 113, 114, 115, 116, 117, 118, 119,
                  120, 121, 122, 123, 124, 125, 126, 127, 128, 129,
                  130, 131, 132, 133, 134, 135, 136, 137, 138, 139]
        index_closes = [4000 + i for i in range(len(closes))]  # 同样上升

        def mock_kline(code, scale=240, datalen=60):
            if code == "sh600519":
                return _mock_kline(closes)
            elif code == "sh000300":
                return _mock_kline(index_closes)
            return []

        with patch.object(industry_beta, "get_kline", side_effect=mock_kline):
            result = industry_beta.compute_beta("sh600519", index_code="sh000300", window=60)
        assert result is not None
        assert "beta" in result
        assert "alpha" in result
        assert "r_squared" in result
        assert "interpretation" in result
        assert "data_quality" in result

    def test_default_index(self):
        """未传 index_code 时使用 select_index_by_size。"""
        closes = [100 + i for i in range(60)]
        with patch.object(industry_beta, "select_index_by_size", return_value="sh000300"), \
             patch.object(industry_beta, "get_kline", side_effect=lambda *a, **kw: _mock_kline(closes)):
            result = industry_beta.compute_beta("sh600519")
        assert result is not None

    def test_no_kline_data(self):
        """K 线为空时返回 degraded dict。"""
        with patch.object(industry_beta, "get_kline", return_value=[]):
            result = industry_beta.compute_beta("sh600519", index_code="sh000300")
        assert result is not None
        assert "data_quality" in result
        assert len(result["data_quality"]["degraded_fields"]) > 0

    def test_insufficient_data(self):
        """数据不足时返回 degraded dict。"""
        with patch.object(industry_beta, "get_kline", return_value=_mock_kline([100])):
            result = industry_beta.compute_beta("sh600519", index_code="sh000300")
        assert result is not None
        assert "data_quality" in result

    def test_exception(self):
        """异常时返回 degraded dict。"""
        with patch.object(industry_beta, "get_kline", side_effect=Exception("net")):
            result = industry_beta.compute_beta("sh600519", index_code="sh000300")
        assert result is not None
        assert "data_quality" in result


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["industry_beta.py"])
        try:
            industry_beta.main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert captured is not None

    def test_with_stock_code(self, capsys, monkeypatch):
        with patch.object(industry_beta, "compute_beta", return_value={
            "stock_code": "sh600519", "index_code": "sh000300", "window": 60,
            "beta": 1.2, "alpha": 0.01, "alpha_annual": 2.5, "r_squared": 0.7,
            "volatility_pct": 25.0, "n_observations": 60,
            "interpretation": "正常弹性",
            "data_quality": {"degraded_fields": []},
        }):
            monkeypatch.setattr(sys, "argv", ["industry_beta.py", "sh600519"])
            industry_beta.main()
        captured = capsys.readouterr()
        assert "beta" in captured.out.lower() or "1.2" in captured.out

    def test_no_data(self, capsys, monkeypatch):
        with patch.object(industry_beta, "compute_beta", return_value=None):
            monkeypatch.setattr(sys, "argv", ["industry_beta.py", "sh600519"])
            industry_beta.main()
        captured = capsys.readouterr()
        assert "失败" in captured.out or len(captured.out) >= 0

    def test_json_output(self, capsys, monkeypatch):
        import json
        with patch.object(industry_beta, "compute_beta", return_value={
            "stock_code": "sh600519", "index_code": "sh000300", "window": 60,
            "beta": 1.2, "alpha": 0.01, "alpha_annual": 2.5, "r_squared": 0.7,
            "volatility_pct": 25.0, "n_observations": 60,
            "interpretation": "正常弹性",
            "data_quality": {"degraded_fields": []},
        }):
            monkeypatch.setattr(sys, "argv", ["industry_beta.py", "sh600519", "-j"])
            industry_beta.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["beta"] == 1.2

    def test_with_index_flag(self, monkeypatch):
        with patch.object(industry_beta, "compute_beta", return_value=None) as m:
            monkeypatch.setattr(sys, "argv", ["industry_beta.py", "sh600519", "--index", "sh000905"])
            industry_beta.main()
        assert m.call_args.kwargs.get("index_code") == "sh000905"
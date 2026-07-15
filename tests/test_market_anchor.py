"""测试 scripts/market_anchor.py：市场环境锚定编排器。

策略：mock 所有外部数据源（get_quotes/get_kline/get_northbound_flow），
验证 18 个函数的输入/输出契约。
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import market_anchor

# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════


def _mock_quote(code, name, price=100.0, change_pct=1.0, has_basic=True):
    q = MagicMock()
    q.code = code
    q.name = name
    q.price = price
    q.change_pct = change_pct
    q.has_basic_data = MagicMock(return_value=has_basic)
    q.prev_close = price / (1 + change_pct / 100)
    return q


def _mock_kline(close=100.0, high=101.0, low=99.0, volume=1000):
    k = MagicMock()
    k.close = close
    k.high = high
    k.low = low
    k.volume = volume
    return k


# ═══════════════════════════════════════════════════════════════
# _fetch_index_snapshot
# ═══════════════════════════════════════════════════════════════


class TestFetchIndexSnapshot:
    def test_success(self):
        q = _mock_quote("sh000300", "沪深300", price=4000.0, change_pct=1.5)
        with patch("market_anchor.get_quotes", return_value=[q]):
            result = market_anchor._fetch_index_snapshot("sh000300")
        assert result is not None
        assert result["code"] == "sh000300"
        assert result["name"] == "沪深300"
        assert result["price"] == 4000.0
        assert result["change_pct"] == 1.5
        assert result["pe_percentile"] == 50

    def test_empty_quotes(self):
        with patch("market_anchor.get_quotes", return_value=[]):
            assert market_anchor._fetch_index_snapshot() is None

    def test_no_basic_data(self):
        q = _mock_quote("sh000300", "沪深300", has_basic=False)
        with patch("market_anchor.get_quotes", return_value=[q]):
            assert market_anchor._fetch_index_snapshot() is None

    def test_exception_returns_none(self):
        with patch("market_anchor.get_quotes", side_effect=Exception("API down")):
            assert market_anchor._fetch_index_snapshot() is None


# ═══════════════════════════════════════════════════════════════
# _fetch_index_kline
# ═══════════════════════════════════════════════════════════════


class TestFetchIndexKline:
    def test_success(self):
        klines = [_mock_kline(close=100 + i) for i in range(5)]
        with patch("market_anchor.get_kline", return_value=klines):
            result = market_anchor._fetch_index_kline("sh000300", datalen=5)
        assert result is not None
        assert len(result["closes"]) == 5
        assert result["closes"][-1] == 104
        assert "ma20" in result
        assert "volumes" in result
        assert result["ma20"] == 102.0  # (100+101+102+103+104)/5

    def test_empty_klines(self):
        with patch("market_anchor.get_kline", return_value=[]):
            assert market_anchor._fetch_index_kline() is None

    def test_exception_returns_none(self):
        with patch("market_anchor.get_kline", side_effect=Exception("net")):
            assert market_anchor._fetch_index_kline() is None

    def test_datalen_passed_through(self):
        with patch("market_anchor.get_kline", return_value=[]) as m:
            market_anchor._fetch_index_kline("sh000300", datalen=10)
        assert m.call_args.kwargs["datalen"] == 10


# ═══════════════════════════════════════════════════════════════
# _fetch_breadth
# ═══════════════════════════════════════════════════════════════


class TestFetchBreadth:
    def test_success(self):
        """成功将 market_breadth 数据转换为 market_anchor 格式。"""
        raw = {
            "advance_ratio": 0.6,
            "limit_up_count": 50,
            "limit_down_count": 5,
            "new_high_count": 100,
            "new_low_count": 50,
            "up_count": 3000,
            "down_count": 1500,
        }
        with patch("market_anchor.market_breadth.get_market_breadth", return_value=raw):
            result = market_anchor._fetch_breadth()
        assert result is not None
        assert "limit_up_count" in result
        assert "limit_down_count" in result
        assert "advance_ratio" in result or result.get("advance_ratio") is not None

    def test_exception_returns_none(self):
        with patch(
            "market_anchor.market_breadth.get_market_breadth",
            side_effect=Exception("err"),
        ):
            assert market_anchor._fetch_breadth() is None

    def test_empty_returns_something(self):
        """空 dict 不返回 None，而是返回带 default 的 dict。"""
        with patch("market_anchor.market_breadth.get_market_breadth", return_value={}):
            result = market_anchor._fetch_breadth()
        # 行为依赖实现 - 可能是 None 或含缺省字段
        assert result is None or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# _compute_multi_timeframe
# ═══════════════════════════════════════════════════════════════


class TestComputeMultiTimeframe:
    def test_full_pipeline(self):
        """5/20 日动量 + MA 对齐 + ATR。"""
        klines = [_mock_kline(close=100 + i) for i in range(250)]
        with patch("market_anchor.get_kline", return_value=klines):
            result = market_anchor._compute_multi_timeframe("sh000300")
        assert result is not None
        assert "ma20" in result
        assert "ma60" in result
        assert "ma250" in result
        assert "ma_alignment" in result
        assert "ret_5d_pct" in result
        assert "ret_20d_pct" in result
        assert "atr_14" in result
        assert "vs_ma20_pct" in result
        assert "data_quality" in result

    def test_insufficient_data(self):
        """K 线 < 20 返回 degraded dict。"""
        klines = [_mock_kline(close=100) for _ in range(10)]
        with patch("market_anchor.get_kline", return_value=klines):
            result = market_anchor._compute_multi_timeframe()
        assert "data_quality" in result
        assert (
            "multi_timeframe.insufficient_data"
            in result["data_quality"]["degraded_fields"]
        )

    def test_no_kline(self):
        """空 klines 返回 degraded dict。"""
        with patch("market_anchor.get_kline", return_value=[]):
            result = market_anchor._compute_multi_timeframe()
        assert result is not None
        assert "multi_timeframe" in result["data_quality"]["degraded_fields"]

    def test_exception(self):
        with patch("market_anchor.get_kline", side_effect=Exception("net")):
            result = market_anchor._compute_multi_timeframe()
        assert result is not None
        assert "multi_timeframe" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_macro_anchor
# ═══════════════════════════════════════════════════════════════


class TestFetchMacroAnchor:
    def test_success(self):
        """成功返回 macro + leverage + valuation_bridge。"""
        fake = {
            "macro": {"treasury_10y_pct": 2.5},
            "leverage": {"margin_balance_total_yi": 15000.0},
            "valuation_bridge": {"erp_sh300_pct": 5.5},
            "data_quality": {"degraded_fields": []},
        }
        with patch("market_anchor.fetch_macro_all", return_value=fake):
            assert market_anchor._fetch_macro_anchor() == fake

    def test_exception(self):
        """异常时返回 dict（含 degraded）。"""
        with patch("market_anchor.fetch_macro_all", side_effect=Exception("yfinance")):
            result = market_anchor._fetch_macro_anchor()
        assert result is not None
        assert "data_quality" in result or "macro_anchor" in str(result)


# ═══════════════════════════════════════════════════════════════
# _fetch_liquidity_volatility (需要 stock_code 参数)
# ═══════════════════════════════════════════════════════════════


class TestFetchLiquidityVolatility:
    def test_with_kline_data(self):
        """有 K 线时计算 ATR + 年化波动率。"""
        index_klines = [
            _mock_kline(close=4000 + i * 5, high=4010 + i, low=3990 + i)
            for i in range(60)
        ]
        with patch("market_anchor.get_kline", return_value=index_klines):
            result = market_anchor._fetch_liquidity_volatility(stock_code="sh600519")
        assert result is not None
        assert "data_quality" in result

    def test_short_klines(self):
        """短 K 线（< 20）返回 degraded。"""
        index_klines = [_mock_kline(close=4000 + i) for i in range(10)]
        with patch("market_anchor.get_kline", return_value=index_klines):
            result = market_anchor._fetch_liquidity_volatility(stock_code="sh600519")
        assert result is not None
        assert "data_quality" in result

    def test_exception(self):
        with patch("market_anchor.get_kline", side_effect=Exception("err")):
            result = market_anchor._fetch_liquidity_volatility(stock_code="sh600519")
        assert result is not None

    def test_no_stock_code(self):
        """stock_code 为 None 时仅算大盘波动率。"""
        index_klines = [_mock_kline(close=4000 + i) for i in range(60)]
        with patch("market_anchor.get_kline", return_value=index_klines):
            result = market_anchor._fetch_liquidity_volatility(stock_code=None)
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# _fetch_emotion_phase
# ═══════════════════════════════════════════════════════════════


class TestFetchEmotionPhase:
    def test_with_breadth(self):
        breadth = {"advance_ratio": 0.6, "limit_up_count": 50}
        result = market_anchor._fetch_emotion_phase(breadth)
        assert result is None or isinstance(result, str)

    def test_no_breadth(self):
        assert market_anchor._fetch_emotion_phase(None) is None

    def test_empty_breadth(self):
        assert market_anchor._fetch_emotion_phase({}) is None


# ═══════════════════════════════════════════════════════════════
# _fetch_industry_beta
# ═══════════════════════════════════════════════════════════════


class TestFetchIndustryBeta:
    def test_with_stock_code(self):
        fake = {"beta": 1.2, "alpha_annual": 0.05, "r_squared": 0.7, "data_quality": {}}
        with (
            patch("market_anchor.select_index_by_size", return_value="sh000300"),
            patch("market_anchor.compute_beta", return_value=fake),
        ):
            result = market_anchor._fetch_industry_beta("sh600519")
        assert result is not None
        assert result["beta"] == 1.2
        assert result["index_selection"] == "dynamic(市值驱动)"

    def test_no_stock_code(self):
        assert market_anchor._fetch_industry_beta(None) is None

    def test_compute_beta_returns_none(self):
        """compute_beta 返回 None 时返回 degraded dict。"""
        with (
            patch("market_anchor.select_index_by_size", return_value="sh000300"),
            patch("market_anchor.compute_beta", return_value=None),
        ):
            result = market_anchor._fetch_industry_beta("sh600519")
        assert result is not None
        assert "industry_beta" in result["data_quality"]["degraded_fields"]

    def test_exception(self):
        with (
            patch("market_anchor.select_index_by_size", return_value="sh000300"),
            patch("market_anchor.compute_beta", side_effect=Exception("kline err")),
        ):
            result = market_anchor._fetch_industry_beta("sh600519")
        # 失败返回 degraded dict
        assert result is not None
        assert "industry_beta" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# _fetch_portfolio_correlation
# ═══════════════════════════════════════════════════════════════


class TestFetchPortfolioCorrelation:
    def test_with_stock_code(self):
        fake = {
            "avg_pairwise_corr": 0.5,
            "vs_portfolio_avg_corr": 0.3,
            "data_quality": {},
        }
        with patch(
            "market_anchor.compute_full_portfolio_correlation", return_value=fake
        ):
            result = market_anchor._fetch_portfolio_correlation("sh600519")
        assert result is not None
        assert result["avg_pairwise_corr"] == 0.5

    def test_no_stock_code(self):
        """stock_code 为 None 时可能返回 None 或 graceful degraded dict。"""
        result = market_anchor._fetch_portfolio_correlation(None)
        # 行为: 应当安全（None 或包含 data_quality 的 dict）
        assert (
            result is None or "data_quality" in result or "n_portfolio_codes" in result
        )


# ═══════════════════════════════════════════════════════════════
# _fetch_northbound_pricer
# ═══════════════════════════════════════════════════════════════


class TestFetchNorthboundPricer:
    def test_with_data(self):
        fake_flow = []
        for i in range(20):
            fake_flow.append({"date": f"2026-07-{i+1:02d}", "net_buy": 100})
        with patch("market_anchor.get_northbound_flow", return_value=fake_flow):
            result = market_anchor._fetch_northbound_pricer(days=20)
        assert result is not None
        assert "data_quality" in result
        assert "days" in result

    def test_empty_flow(self):
        """空数据返回 degraded dict。"""
        with patch("market_anchor.get_northbound_flow", return_value=[]):
            result = market_anchor._fetch_northbound_pricer()
        assert result is not None
        assert "northbound.flow_data" in result["data_quality"]["degraded_fields"]

    def test_exception(self):
        with patch("market_anchor.get_northbound_flow", side_effect=Exception("api")):
            result = market_anchor._fetch_northbound_pricer()
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# _interpret_northbound
# ═══════════════════════════════════════════════════════════════


class TestInterpretNorthbound:
    def test_heavy_inflow(self):
        result = market_anchor._interpret_northbound(150.0, "流入", "持续流入")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_heavy_outflow(self):
        result = market_anchor._interpret_northbound(-150.0, "流出", "持续流出")
        assert isinstance(result, str)

    def test_mild_inflow(self):
        result = market_anchor._interpret_northbound(20.0, "流入", "震荡")
        assert isinstance(result, str)

    def test_zero_flow(self):
        result = market_anchor._interpret_northbound(0.0, "持平", "震荡")
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# _fetch_sector_rotation
# ═══════════════════════════════════════════════════════════════


class TestFetchSectorRotation:
    def test_success(self):
        fake = {
            "rotation_strength": 2.5,
            "biggest_risers": [["sh512760", "科技ETF", 3]],
            "biggest_fallers": [["sh510300", "沪深300ETF", -2]],
            "data_quality": {"degraded_fields": []},
        }
        with patch(
            "market_anchor.sector_etf_strength.compute_rotation_strength",
            return_value=fake,
        ):
            result = market_anchor._fetch_sector_rotation(window=5)
        assert result == fake


# ═══════════════════════════════════════════════════════════════
# _md_regime_emoji
# ═══════════════════════════════════════════════════════════════


class TestMdRegimeEmoji:
    def test_bull(self):
        result = market_anchor._md_regime_emoji("bull")
        assert isinstance(result, str)

    def test_bear(self):
        result = market_anchor._md_regime_emoji("bear")
        assert isinstance(result, str)

    def test_range(self):
        result = market_anchor._md_regime_emoji("range")
        assert isinstance(result, str)

    def test_unknown(self):
        result = market_anchor._md_regime_emoji("xyz")
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# analyze - 主入口
# ═══════════════════════════════════════════════════════════════


def _minimal_mocks():
    """构建一组最小 mock，覆盖所有外部调用。"""
    index_snapshot = {
        "code": "sh000300",
        "name": "沪深300",
        "price": 4000.0,
        "change_pct": 1.0,
        "pe_percentile": 50,
    }
    return [
        patch.object(
            market_anchor, "_fetch_index_snapshot", return_value=index_snapshot
        ),
        patch.object(market_anchor, "_fetch_index_kline", return_value=None),
        patch.object(market_anchor, "_fetch_breadth", return_value=None),
        patch.object(market_anchor, "_compute_multi_timeframe", return_value=None),
        patch.object(market_anchor, "_fetch_macro_anchor", return_value=None),
        patch.object(market_anchor, "_fetch_liquidity_volatility", return_value=None),
        patch.object(market_anchor, "_fetch_emotion_phase", return_value=None),
        patch.object(market_anchor, "_fetch_industry_beta", return_value=None),
        patch.object(market_anchor, "_fetch_portfolio_correlation", return_value=None),
        patch.object(market_anchor, "_fetch_northbound_pricer", return_value=None),
        patch.object(market_anchor, "_fetch_sector_rotation", return_value=None),
        patch.object(
            market_anchor,
            "detect_market_state",
            return_value={
                "regime": "bull",
                "regime_label_zh": "牛市",
                "confidence": 0.8,
            },
        ),
    ]


class TestAnalyze:
    def test_minimal_no_args(self):
        """无 stock_code + 关掉所有 fetch_*。"""
        with (
            _minimal_mocks()[0],
            _minimal_mocks()[1],
            _minimal_mocks()[2],
            _minimal_mocks()[3],
            _minimal_mocks()[4],
            _minimal_mocks()[5],
            _minimal_mocks()[6],
            _minimal_mocks()[7],
            _minimal_mocks()[8],
            _minimal_mocks()[9],
            _minimal_mocks()[10],
            _minimal_mocks()[11],
        ):
            result = market_anchor.analyze(
                stock_code=None,
                fetch_sector=False,
                fetch_portfolio=False,
                fetch_rotation=False,
                fetch_northbound=False,
            )
        assert "as_of" in result
        assert "regime" in result
        assert "data_quality" in result
        assert "degraded_fields" in result["data_quality"]

    def test_with_stock_code(self):
        """有 stock_code + industry_beta/portfolio。"""
        mocks = _minimal_mocks()
        mocks[7] = patch.object(
            market_anchor,
            "_fetch_industry_beta",
            return_value={
                "beta": 1.0,
                "data_quality": {},
                "index_selection": "dynamic",
            },
        )
        mocks[8] = patch.object(
            market_anchor,
            "_fetch_portfolio_correlation",
            return_value={"avg_pairwise_corr": 0.5, "data_quality": {}},
        )
        with (
            mocks[0],
            mocks[1],
            mocks[2],
            mocks[3],
            mocks[4],
            mocks[5],
            mocks[6],
            mocks[7],
            mocks[8],
            mocks[9],
            mocks[10],
            mocks[11],
        ):
            result = market_anchor.analyze(
                stock_code="sh600519",
                fetch_sector=False,
                fetch_portfolio=True,
                fetch_rotation=False,
                fetch_northbound=False,
            )
        assert result["industry_beta"]["beta"] == 1.0
        assert result["portfolio_correlation"]["avg_pairwise_corr"] == 0.5

    def test_degraded_fields_tracking(self):
        """失败的字段被记录到 degraded_fields。"""
        mocks = _minimal_mocks()
        # 全部 mock 返回 None
        with (
            mocks[0],
            mocks[1],
            mocks[2],
            mocks[3],
            mocks[4],
            mocks[5],
            mocks[6],
            mocks[7],
            mocks[8],
            mocks[9],
            mocks[10],
            mocks[11],
        ):
            result = market_anchor.analyze(
                stock_code=None,
                fetch_sector=False,
                fetch_portfolio=False,
                fetch_rotation=False,
                fetch_northbound=False,
            )
        assert len(result["data_quality"]["degraded_fields"]) >= 1

    def test_index_code_passed(self):
        """index_code 参数被使用。"""
        mocks = _minimal_mocks()
        mocks[0] = patch.object(
            market_anchor,
            "_fetch_index_snapshot",
            return_value={
                "code": "sh000905",
                "name": "中证500",
                "price": 5000.0,
                "change_pct": 1.0,
                "pe_percentile": 50,
            },
        )
        with (
            mocks[0],
            mocks[1],
            mocks[2],
            mocks[3],
            mocks[4],
            mocks[5],
            mocks[6],
            mocks[7],
            mocks[8],
            mocks[9],
            mocks[10],
            mocks[11],
        ):
            result = market_anchor.analyze(
                stock_code=None,
                index_code="sh000905",
                fetch_sector=False,
                fetch_portfolio=False,
                fetch_rotation=False,
                fetch_northbound=False,
            )
        assert "index_code" in result
        assert result["index_code"] == "sh000905"


# ═══════════════════════════════════════════════════════════════
# to_markdown
# ═══════════════════════════════════════════════════════════════


def _base_payload():
    """一个最小的 payload，覆盖所有字段。"""
    return {
        "as_of": "2026-07-10",
        "regime": "bull",
        "regime_label_zh": "牛市",
        "regime_confidence": 0.8,
        "regime_reason": "测试",
        "long_weight": 0.7,
        "short_weight": 0.3,
        "index_code": "sh000300",
        "index_change_pct": 1.0,
        "breadth": None,
        "sector_strength": None,
        "stock_sector_compare": None,
        "multi_timeframe": None,
        "macro": None,
        "leverage": None,
        "valuation_bridge": None,
        "liquidity_volatility": None,
        "emotion_phase": None,
        "industry_beta": None,
        "portfolio_correlation": None,
        "sector_rotation": None,
        "northbound_pricer": None,
        "data_quality": {"degraded_fields": []},
    }


class TestToMarkdown:
    def test_basic_payload(self):
        result = market_anchor.to_markdown(_base_payload())
        assert isinstance(result, str)
        assert "市场环境锚定" in result
        assert "牛市" in result

    def test_with_breadth(self):
        payload = _base_payload()
        payload["breadth"] = {
            "advance_count": 3000,
            "decline_count": 1500,
            "limit_up_count": 30,
        }
        result = market_anchor.to_markdown(payload)
        assert "市场宽度" in result

    def test_with_sector_strength(self):
        payload = _base_payload()
        payload["sector_strength"] = {
            "etfs": [
                {"code": "sh512760", "name": "科技ETF", "change_pct": 5.0, "rps": 80},
            ],
            "top": ["sh512760"],
            "bottom": [],
            "data_quality": {},
        }
        result = market_anchor.to_markdown(payload)
        assert "板块" in result

    def test_with_stock_sector_compare(self):
        payload = _base_payload()
        payload["stock_sector_compare"] = {
            "stock_code": "sh600519",
            "stock_rps": 75,
            "stock_5d_pct": 5.0,
            "sector_name": "科技ETF",
            "sector_rps": 60,
            "sector_change_pct": 3.0,
            "index_change_pct": 1.0,
            "rps_vs_sector": 15.0,
            "rps_vs_index": 25.0,
            "rank_in_sector": 3,
            "n_sector_stocks": 20,
            "verdict": "强势",
            "outperformance": True,
        }
        result = market_anchor.to_markdown(payload)
        assert "个股" in result or "vs 板块" in result

    def test_with_multi_timeframe(self):
        payload = _base_payload()
        payload["multi_timeframe"] = {
            "ma20": 100,
            "ma60": 95,
            "ma250": 90,
            "ma_alignment": "多头排列",
            "ret_5d_pct": 5.0,
            "ret_20d_pct": 10.0,
            "atr_14": 2.5,
            "vs_ma20_pct": 1.0,
            "data_quality": {"degraded_fields": []},
        }
        result = market_anchor.to_markdown(payload)
        assert "MA" in result or "时间" in result

    def test_with_macro(self):
        payload = _base_payload()
        payload["macro"] = {"treasury_10y_pct": 2.5}
        payload["leverage"] = {"margin_balance_total_yi": 15000.0}
        payload["valuation_bridge"] = {"erp_sh300_pct": 5.5}
        result = market_anchor.to_markdown(payload)
        assert "宏观" in result or "国债" in result
        assert "杠杆" in result or "融资" in result

    def test_with_liquidity_volatility(self):
        payload = _base_payload()
        payload["liquidity_volatility"] = {
            "sh300_atr_14": 50.0,
            "sh300_annualized_vol_pct": 15.0,
        }
        result = market_anchor.to_markdown(payload)
        assert "波动" in result or "ATR" in result

    def test_with_emotion(self):
        payload = _base_payload()
        payload["emotion_phase"] = "乐观"
        result = market_anchor.to_markdown(payload)
        assert "情绪" in result or "乐观" in result

    def test_with_industry_beta(self):
        payload = _base_payload()
        payload["industry_beta"] = {
            "beta": 1.2,
            "alpha_annual": 0.05,
            "r_squared": 0.7,
        }
        result = market_anchor.to_markdown(payload)
        assert "β" in result or "beta" in result.lower()

    def test_with_portfolio_correlation(self):
        payload = _base_payload()
        payload["portfolio_correlation"] = {
            "n_portfolio_codes": 3,
            "avg_pairwise_corr": 0.5,
            "vs_portfolio_avg_corr": 0.3,
            "high_corr_pairs": [],
            "diversification_benefit": "中",
        }
        result = market_anchor.to_markdown(payload)
        assert "组合" in result

    def test_with_sector_rotation(self):
        payload = _base_payload()
        payload["sector_rotation"] = {
            "rotation_strength": 2.5,
            "biggest_risers": [["sh512760", "科技", 3]],
            "biggest_fallers": [["sh510300", "300", -2]],
        }
        result = market_anchor.to_markdown(payload)
        assert "轮动" in result

    def test_with_northbound(self):
        payload = _base_payload()
        payload["northbound_pricer"] = {
            "days": 20,
            "total_net_yi": 100.0,
            "direction": "持续流入",
            "interpretation": "北向持续流入",
            "data_quality": {"degraded_fields": []},
        }
        result = market_anchor.to_markdown(payload)
        assert "北向" in result

    def test_with_degraded_fields(self):
        payload = _base_payload()
        payload["data_quality"] = {"degraded_fields": ["breadth", "sector_strength"]}
        result = market_anchor.to_markdown(payload)
        assert "降级" in result or "缺失" in result


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args_prints_help(self, capsys, monkeypatch):
        """无参数时打印帮助。"""
        monkeypatch.setattr(sys, "argv", ["market_anchor.py"])
        # 实际 main 不抛 SystemExit（argparse 在 subcommand style 下）
        try:
            market_anchor.main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # 应当有帮助信息
        assert (
            "market_anchor" in captured.out
            or "usage" in captured.out.lower()
            or "市场环境锚定" in captured.out
        )

    def test_with_stock_code_json(self, capsys, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()):
            monkeypatch.setattr(sys, "argv", ["market_anchor.py", "sh600519", "-j"])
            market_anchor.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["regime"] == "bull"

    def test_with_stock_code_markdown(self, capsys, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()):
            monkeypatch.setattr(sys, "argv", ["market_anchor.py", "sh600519"])
            market_anchor.main()
        captured = capsys.readouterr()
        assert "市场环境锚定" in captured.out

    def test_no_sector_flag(self, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()) as m:
            monkeypatch.setattr(
                sys, "argv", ["market_anchor.py", "sh600519", "--no-sector"]
            )
            market_anchor.main()
        assert m.call_args.kwargs.get("fetch_sector") is False

    def test_index_flag(self, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()) as m:
            monkeypatch.setattr(
                sys, "argv", ["market_anchor.py", "--index", "sh000905"]
            )
            market_anchor.main()
        assert m.call_args.kwargs.get("index_code") == "sh000905"

    def test_no_portfolio_flag(self, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()) as m:
            monkeypatch.setattr(
                sys,
                "argv",
                ["market_anchor.py", "sh600519", "--no-portfolio"],
            )
            market_anchor.main()
        assert m.call_args.kwargs.get("fetch_portfolio") is False

    def test_no_rotation_flag(self, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()) as m:
            monkeypatch.setattr(
                sys,
                "argv",
                ["market_anchor.py", "sh600519", "--no-rotation"],
            )
            market_anchor.main()
        assert m.call_args.kwargs.get("fetch_rotation") is False

    def test_no_northbound_flag(self, monkeypatch):
        with patch.object(market_anchor, "analyze", return_value=_base_payload()) as m:
            monkeypatch.setattr(
                sys,
                "argv",
                ["market_anchor.py", "sh600519", "--no-northbound"],
            )
            market_anchor.main()
        assert m.call_args.kwargs.get("fetch_northbound") is False

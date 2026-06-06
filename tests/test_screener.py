"""
screener.py 单元测试：覆盖策略配置、因子评分、硬过滤、load_universe、技术指标。
"""
import argparse
import json
import math
import pytest

from screener import (
    STRATEGIES,
    hard_filter,
    latest_finance,
    load_universe,
    liquidity_score,
    momentum_score,
    quality_score,
    valuation_score,
    volume_price_features,
    daily_features,
    analyze_code,
    get_industry_threshold,
    load_industry_thresholds,
)
from classifier import infer_industry
from technical.core import ema
from technical.macd import macd_full as macd_features
from technical.rsi import rsi_features

# 为方便测试 hard_filter 构造 args 对象
def _make_args(**kwargs):
    defaults = {
        "min_amount": 5000,
        "min_cap": 40,
        "exclude_loss": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ====================================================================
# 1. STRATEGIES 配置
# ====================================================================
class TestStrategies:
    """验证 5 种策略的配置完整性。"""

    def test_all_strategies_exist(self):
        expected = {"balanced", "quality_value", "growth_momentum", "defensive", "turning_point"}
        assert set(STRATEGIES.keys()) == expected

    @pytest.mark.parametrize("name", list(STRATEGIES.keys()))
    def test_weight_sum_to_one(self, name):
        cfg = STRATEGIES[name]
        keys = ["quality", "valuation", "momentum", "liquidity"]
        total = sum(cfg[k] for k in keys)
        assert abs(total - 1.0) < 1e-9, f"{name} 权重之和 {total} != 1.0"

    @pytest.mark.parametrize("name", list(STRATEGIES.keys()))
    def test_has_label(self, name):
        assert "label" in STRATEGIES[name]
        assert isinstance(STRATEGIES[name]["label"], str)
        assert len(STRATEGIES[name]["label"]) > 0

    @pytest.mark.parametrize("name", list(STRATEGIES.keys()))
    def test_weights_are_positive(self, name):
        cfg = STRATEGIES[name]
        for k in ["quality", "valuation", "momentum", "liquidity"]:
            assert cfg[k] > 0, f"{name}.{k} 应为正数"


# ====================================================================
# 2. ema 技术指标
# ====================================================================
class TestEma:
    """EMA 计算逻辑测试。"""

    def test_short_data_returns_mean(self):
        # 数据不足 period 时返回均值
        result = ema([10, 11, 12], 5)
        assert result == pytest.approx(11.0)

    def test_empty_returns_zero(self):
        assert ema([], 10) == 0

    def test_exact_period_returns_sma(self):
        prices = [10.0, 11.0, 12.0, 13.0, 14.0]
        assert ema(prices, 5) == pytest.approx(12.0)

    def test_ema_follows_price_direction(self):
        # 上升序列 EMA 应低于最新价（滞后性）
        prices = list(range(10, 30))
        result = ema(prices, 10)
        assert result < prices[-1]
        assert result > prices[0]


# ====================================================================
# 3. macd_features
# ====================================================================
class TestMacdFeatures:
    """MACD 特征计算。"""

    def test_short_data_returns_none(self):
        assert macd_features([1.0] * 20) is None

    def test_returns_all_fields(self):
        # 构造一个足够长的序列
        closes = [10 + i * 0.1 for i in range(50)]
        result = macd_features(closes)
        assert result is not None
        assert {"dif", "dea", "macd_bar", "signal"}.issubset(set(result.keys()))

    def test_signal_is_valid(self):
        closes = [10 + i * 0.1 for i in range(50)]
        result = macd_features(closes)
        assert result["signal"] in (-1, 0, 1)


# ====================================================================
# 4. rsi_features
# ====================================================================
class TestRsiFeatures:
    """RSI 计算。"""

    def test_short_data_returns_default(self):
        result = rsi_features([50.0] * 10, period=14)
        assert result["rsi"] == 50
        assert result["signal"] == 0

    def test_all_gains_gives_100(self):
        # 全涨序列 -> RSI=100, 超买
        closes = [float(i) for i in range(30)]
        result = rsi_features(closes, period=14)
        assert result["rsi"] == pytest.approx(100.0)
        assert result["signal"] == -1  # 超买

    def test_all_losses_gives_0(self):
        # 全跌序列 -> RSI=0, 超卖
        closes = [float(30 - i) for i in range(30)]
        result = rsi_features(closes, period=14)
        assert result["rsi"] == pytest.approx(0.0)
        assert result["signal"] == 1  # 超卖

    def test_moderate_rsi_no_signal(self):
        # 交替涨跌小幅波动 -> RSI 应在 30-70 之间，无信号
        closes = [50.0]
        for i in range(30):
            closes.append(closes[-1] + (0.5 if i % 2 == 0 else -0.5))
        result = rsi_features(closes, period=14)
        assert result["signal"] == 0


# ====================================================================
# 5. volume_price_features
# ====================================================================
class TestVolumePriceFeatures:
    """量价关系分析。"""

    def test_short_data_returns_neutral(self):
        result = volume_price_features([1, 2, 3], [100, 200, 300])
        assert result["signal"] == 0
        assert "数据不足" in result["desc"]

    def test_price_up_volume_up_bullish(self):
        # 价格涨 + 放量 -> 正信号
        closes = [10.0] * 10 + [11.0] * 10
        volumes = [1000] * 10 + [2000] * 10
        result = volume_price_features(closes, volumes)
        assert result["signal"] == 1

    def test_price_down_volume_down_bullish(self):
        # 价格跌 + 缩量 -> 正信号（抛压减轻）
        closes = [11.0] * 10 + [10.0] * 10
        volumes = [2000] * 10 + [1000] * 10
        result = volume_price_features(closes, volumes)
        assert result["signal"] == 1


# ====================================================================
# 6. quality_score
# ====================================================================
class TestQualityScore:
    """质量因子评分。"""

    def test_sample_finance_score_range(self, sample_finance):
        score = quality_score(sample_finance)
        assert 0 <= score <= 100

    def test_empty_finance_low_score(self):
        # 空财务数据：只有 debt 项贡献 (70-0)/70*12=12，其余为 0
        score = quality_score({})
        assert score == pytest.approx(12.0)
        assert score < 20  # 整体仍为低分

    def test_high_quality_scores_higher(self, sample_finance):
        high = quality_score(sample_finance)
        low = quality_score({
            "ROEJQ": "2",
            "PARENTNETPROFITTZ": "-10",
            "TOTALOPERATEREVETZ": "-5",
            "XSMLL": "5",
            "ZCFZL": "90",
            "EPSJB": "0.1",
            "MGJYXJJE": "0.05",
        })
        assert high > low

    def test_cashflow_bonus(self):
        # EPS > 0 且经营现金流 > 0 时有额外加分
        with_cf = quality_score({
            "ROEJQ": "15", "PARENTNETPROFITTZ": "20", "TOTALOPERATEREVETZ": "10",
            "XSMLL": "30", "ZCFZL": "50", "EPSJB": "2.0", "MGJYXJJE": "3.0",
        })
        without_cf = quality_score({
            "ROEJQ": "15", "PARENTNETPROFITTZ": "20", "TOTALOPERATEREVETZ": "10",
            "XSMLL": "30", "ZCFZL": "50", "EPSJB": "2.0", "MGJYXJJE": "-1.0",
        })
        assert with_cf > without_cf


# ====================================================================
# 7. valuation_score
# ====================================================================
class TestValuationScore:
    """估值因子评分。"""

    def test_sample_data_score_range(self, sample_quote, sample_finance):
        score = valuation_score(sample_quote, sample_finance)
        assert 0 <= score <= 100

    def test_low_pe_beats_high_pe(self, sample_finance):
        low_pe = {"pe": "8", "pb": "2"}
        high_pe = {"pe": "80", "pb": "10"}
        assert valuation_score(low_pe, sample_finance) > valuation_score(high_pe, sample_finance)

    def test_peg_bonus(self, sample_finance):
        # 低 PEG 应得到额外加分
        q_low_peg = {"pe": "10", "pb": "2"}
        q_no_peg = {"pe": "10", "pb": "2"}
        fin_high_growth = {**sample_finance, "PARENTNETPROFITTZ": "50"}
        fin_no_growth = {**sample_finance, "PARENTNETPROFITTZ": "0"}
        assert valuation_score(q_low_peg, fin_high_growth) > valuation_score(q_no_peg, fin_no_growth)


# ====================================================================
# 8. momentum_score
# ====================================================================
class TestMomentumScore:
    """动量因子评分。"""

    def _make_features(self, **kwargs):
        defaults = {
            "trend": 1, "ret20": 5.0, "volume_ratio": 1.2,
            "macd_signal": 0, "rsi": 50, "vol_price_signal": 0,
        }
        defaults.update(kwargs)
        return defaults

    def test_sample_data_score_range(self, sample_quote):
        features = self._make_features()
        score = momentum_score(features, sample_quote)
        assert 0 <= score <= 100

    def test_uptrend_scores_higher(self, sample_quote):
        up = momentum_score(self._make_features(trend=1), sample_quote)
        down = momentum_score(self._make_features(trend=-1), sample_quote)
        assert up > down

    def test_macd_golden_cross_bonus(self, sample_quote):
        golden = momentum_score(self._make_features(macd_signal=1), sample_quote)
        neutral = momentum_score(self._make_features(macd_signal=0), sample_quote)
        death = momentum_score(self._make_features(macd_signal=-1), sample_quote)
        assert golden > neutral > death

    def test_limit_up_no_penalty_in_momentum(self, sample_quote):
        """涨跌停扣分已移至 hard_filter，momentum_score 不再重复扣分"""
        normal = momentum_score(self._make_features(), sample_quote)
        limit_up = momentum_score(self._make_features(), {**sample_quote, "change_pct": "9.8"})
        # momentum_score 不再对涨跌停扣分，两者应相等
        assert normal == limit_up

    def test_rsi_extreme_penalty(self, sample_quote):
        normal = momentum_score(self._make_features(rsi=50), sample_quote)
        overbought = momentum_score(self._make_features(rsi=85), sample_quote)
        assert normal > overbought

    def test_volume_price_divergence_penalty(self, sample_quote):
        good = momentum_score(self._make_features(vol_price_signal=1), sample_quote)
        bad = momentum_score(self._make_features(vol_price_signal=-1), sample_quote)
        assert good > bad


# ====================================================================
# 9. liquidity_score
# ====================================================================
class TestLiquidityScore:
    """流动性因子评分。"""

    def test_sample_data_score_range(self, sample_quote):
        score = liquidity_score(sample_quote)
        assert 0 <= score <= 100

    def test_higher_amount_scores_higher(self):
        high = liquidity_score({"amount": "200000", "total_cap": "500", "turnover": "2"})
        low = liquidity_score({"amount": "1000", "total_cap": "10", "turnover": "0.1"})
        assert high > low

    def test_ideal_turnover_gets_max_turnover_score(self):
        # 使用较小的 amount/cap 避免 clamp 到 100
        ideal = liquidity_score({"amount": "30000", "total_cap": "80", "turnover": "3"})
        extreme = liquidity_score({"amount": "30000", "total_cap": "80", "turnover": "20"})
        assert ideal > extreme


# ====================================================================
# 10. hard_filter
# ====================================================================
class TestHardFilter:
    """硬过滤逻辑。"""

    def test_normal_stock_passes(self, sample_quote, sample_finance):
        args = _make_args()
        reasons = hard_filter(sample_quote, sample_finance, args)
        assert reasons == []

    def test_st_stock_filtered(self, sample_finance):
        args = _make_args()
        quote = {"name": "ST某某", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("ST" in r for r in reasons)

    def test_star_st_filtered(self, sample_finance):
        args = _make_args()
        quote = {"name": "*ST退市", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("ST" in r for r in reasons)

    def test_low_amount_filtered(self, sample_finance):
        args = _make_args(min_amount=5000)
        quote = {"name": "测试", "code": "sh600001", "amount": "100", "total_cap": "100", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("成交额" in r for r in reasons)

    def test_low_cap_filtered(self, sample_finance):
        args = _make_args(min_cap=40)
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "5", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("市值" in r for r in reasons)

    def test_limit_up_filtered(self, sample_finance):
        args = _make_args()
        # 主板涨跌停 >= 9.5%
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "9.8"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("涨跌停" in r for r in reasons)

    def test_gem_limit_threshold(self, sample_finance):
        """创业板涨跌停阈值为 19.5%"""
        args = _make_args()
        # 300xxx 是创业板
        quote = {"name": "测试", "code": "sz300001", "amount": "100000", "total_cap": "100", "change_pct": "15.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert not any("涨跌停" in r for r in reasons)

        quote_limit = {"name": "测试", "code": "sz300001", "amount": "100000", "total_cap": "100", "change_pct": "20.0"}
        reasons2 = hard_filter(quote_limit, sample_finance, args)
        assert any("涨跌停" in r for r in reasons2)

    def test_exclude_loss_filters_negative_eps(self):
        args = _make_args(exclude_loss=True)
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        fin = {"EPSJB": "-0.5"}
        reasons = hard_filter(quote, fin, args)
        assert any("EPS" in r for r in reasons)

    def test_exclude_loss_passes_positive_eps(self, sample_finance):
        args = _make_args(exclude_loss=True)
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert not any("EPS" in r for r in reasons)


# ====================================================================
# 11. load_universe
# ====================================================================
class TestLoadUniverse:
    """股票池加载。"""

    def test_from_codes(self):
        result = load_universe(codes=["sh600519", "sz000858"])
        assert isinstance(result, list)
        assert len(result) == 2
        # 应该已归一化
        for c in result:
            assert c.startswith(("sh", "sz"))

    def test_codes_deduplicated(self):
        result = load_universe(codes=["600519", "sh600519"])
        assert len(result) == 1

    def test_codes_sorted(self):
        result = load_universe(codes=["sz000858", "sh600519"])
        assert result == sorted(result)

    def test_from_sector_with_mock(self, monkeypatch, tmp_path):
        """从板块文件加载，mock 文件读取。"""
        sector_data = {
            "白酒": ["sh600519", "sz000858"],
            "银行": ["sh601398", "sh600036"],
        }
        fake_file = tmp_path / "sector_stocks.json"
        fake_file.write_text(json.dumps(sector_data), encoding="utf-8")

        import screener
        monkeypatch.setattr(screener, "DATA_DIR", tmp_path)

        result = load_universe(sector="白酒")
        assert len(result) == 2

    def test_from_sector_all(self, monkeypatch, tmp_path):
        """不指定板块时加载全部。"""
        sector_data = {
            "白酒": ["sh600519", "sz000858"],
            "银行": ["sh601398", "sh600036"],
        }
        fake_file = tmp_path / "sector_stocks.json"
        fake_file.write_text(json.dumps(sector_data), encoding="utf-8")

        import screener
        monkeypatch.setattr(screener, "DATA_DIR", tmp_path)

        result = load_universe()
        assert len(result) == 4

    def test_sector_not_found_raises(self, monkeypatch, tmp_path):
        """找不到板块应抛出 SystemExit。"""
        sector_data = {"白酒": ["sh600519"]}
        fake_file = tmp_path / "sector_stocks.json"
        fake_file.write_text(json.dumps(sector_data), encoding="utf-8")

        import screener
        monkeypatch.setattr(screener, "DATA_DIR", tmp_path)
        # mock _try_fetch_from_mapping 返回空
        monkeypatch.setattr(screener, "_try_fetch_from_mapping", lambda s: [])

        with pytest.raises(SystemExit):
            load_universe(sector="不存在的板块")


# ====================================================================
# 12. daily_features（需要 mock kline.fetch）
# ====================================================================
class TestDailyFeatures:
    """日线特征提取（mock K 线数据）。"""

    def test_short_data_returns_defaults(self, monkeypatch):
        import screener
        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: [])

        result = daily_features("sh600519")
        assert result["trend"] == 0
        assert result["rsi"] == 50
        assert result["macd_signal"] == 0

    def test_with_uptrend_data(self, monkeypatch, kline_uptrend):
        import screener
        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: kline_uptrend)

        result = daily_features("sh600519")
        assert "trend" in result
        assert "ret20" in result
        assert "rsi" in result
        assert result["trend"] in (-1, 0, 1)


# ====================================================================
# 13. analyze_code（完整评分流程）
# ====================================================================
class TestAnalyzeCode:
    """综合评分逻辑，mock K 线和财务数据。"""

    def test_returns_all_fields(self, sample_quote, sample_finance, monkeypatch):
        import screener
        # mock kline 和 finance 避免网络请求
        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: [])
        monkeypatch.setattr(screener, "_fetch_finance_dicts", lambda code: [sample_finance])

        args = _make_args()
        result = analyze_code(sample_quote, "balanced", args)

        expected_keys = {
            "code", "name", "board", "score",
            "quality", "valuation", "momentum", "liquidity",
            "price", "change_pct", "pe", "pb",
            "roe", "profit_growth", "ret20", "trend",
            "rsi", "macd_signal", "vol_price", "rejected",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_score_is_weighted_combination(self, sample_quote, sample_finance, monkeypatch):
        import screener
        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: [])
        monkeypatch.setattr(screener, "_fetch_finance_dicts", lambda code: [sample_finance])

        args = _make_args()
        result = analyze_code(sample_quote, "balanced", args)

        # 总分应为各维度加权和
        w = STRATEGIES["balanced"]
        expected = (
            result["quality"] * w["quality"]
            + result["valuation"] * w["valuation"]
            + result["momentum"] * w["momentum"]
            + result["liquidity"] * w["liquidity"]
        )
        assert result["score"] == pytest.approx(expected, abs=0.2)

    def test_rejected_stock_has_reasons(self, sample_finance, monkeypatch):
        import screener
        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: [])
        monkeypatch.setattr(screener, "_fetch_finance_dicts", lambda code: [sample_finance])

        st_quote = {
            "code": "sh600001", "name": "ST测试", "price": "10",
            "change_pct": "1.0", "pe": "15", "pb": "2",
            "amount": "100000", "total_cap": "100", "turnover": "1",
        }
        args = _make_args()
        result = analyze_code(st_quote, "balanced", args)
        assert len(result["rejected"]) > 0

    def test_finance_cache_used(self, sample_quote, sample_finance, monkeypatch):
        """传入 finance_cache 时不应调用 fetch_finance。"""
        import screener
        call_count = {"n": 0}

        def _should_not_be_called(code):
            call_count["n"] += 1
            return []

        monkeypatch.setattr(screener, "_fetch_kline_dicts", lambda code, limit=240, scale=30: [])
        monkeypatch.setattr(screener, "_fetch_finance_dicts", _should_not_be_called)

        args = _make_args()
        cache = {"sh600519": [sample_finance]}
        analyze_code(sample_quote, "balanced", args, finance_cache=cache)
        assert call_count["n"] == 0


# ====================================================================
# 14. infer_industry 行业推断
# ====================================================================
class TestInferIndustry:
    """行业推断逻辑。"""

    def test_bank_industry(self):
        assert infer_industry("招商银行") == "金融"

    def test_pharma_industry(self):
        assert infer_industry("恒瑞医药") == "医药"

    def test_tech_industry(self):
        assert infer_industry("中芯国际科技") == "科技"

    def test_consumer_industry(self):
        assert infer_industry("贵州茅台白酒") == "消费"

    def test_energy_industry(self):
        assert infer_industry("中国石油能源") == "能源"

    def test_real_estate_industry(self):
        assert infer_industry("万科地产") == "地产"

    def test_cycle_industry(self):
        assert infer_industry("宝钢钢铁") == "周期"

    def test_manufacturing_industry(self):
        assert infer_industry("比亚迪汽车制造") == "制造"

    def test_unknown_defaults(self):
        assert infer_industry("某某未知公司") == "默认"


# ====================================================================
# 15. 行业差异化阈值
# ====================================================================
class TestIndustryThresholds:
    """行业阈值配置。"""

    def test_thresholds_load(self):
        thresholds = load_industry_thresholds()
        assert isinstance(thresholds, dict)
        assert "金融" in thresholds
        assert "默认" in thresholds

    def test_finance_has_lower_roe(self):
        finance_roe = get_industry_threshold("金融", "roe_min", 12)
        default_roe = get_industry_threshold("默认", "roe_min", 12)
        assert finance_roe < default_roe

    def test_tech_has_higher_pe(self):
        tech_pe = get_industry_threshold("科技", "pe_reasonable", 25)
        default_pe = get_industry_threshold("默认", "pe_reasonable", 25)
        assert tech_pe > default_pe

    def test_quality_score_uses_industry(self, sample_finance):
        # 金融行业 ROE 阈值较低，相同 ROE 应得更高分
        score_default = quality_score(sample_finance, "默认")
        score_finance = quality_score(sample_finance, "金融")
        # 金融行业的 roe_excellent 更低，相同 ROE 得分更高
        assert score_finance >= score_default

    def test_valuation_score_uses_industry(self, sample_quote, sample_finance):
        # 科技行业 PE 阈值较高，相同 PE 应得更高分
        score_default = valuation_score(sample_quote, sample_finance, "默认")
        score_tech = valuation_score(sample_quote, sample_finance, "科技")
        # sample_quote PE=25.6，科技行业 pe_reasonable=40，得分更高
        assert score_tech >= score_default


# ====================================================================
# 16. 流动性板块差异化
# ====================================================================
class TestLiquidityBoardDiff:
    """流动性评分板块差异化。"""

    def test_gem_scores_higher_than_main_for_same_amount(self):
        # 创业板满分阈值更低，相同成交额得分更高
        gem_quote = {"code": "sz300001", "amount": "20000", "total_cap": "50", "turnover": "3"}
        main_quote = {"code": "sh600001", "amount": "20000", "total_cap": "50", "turnover": "3"}
        gem_score = liquidity_score(gem_quote)
        main_score = liquidity_score(main_quote)
        assert gem_score >= main_score


# ====================================================================
# 17. 硬过滤新增规则
# ====================================================================
class TestHardFilterExtended:
    """硬过滤新增规则。"""

    def test_micro_cap_filtered(self, sample_finance):
        args = _make_args()
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "2", "change_pct": "1.0"}
        reasons = hard_filter(quote, sample_finance, args)
        assert any("退市风险" in r for r in reasons)

    def test_negative_eps_filtered(self):
        args = _make_args()
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        fin = {"EPSJB": "-0.5"}
        reasons = hard_filter(quote, fin, args)
        assert any("EPS<0" in r for r in reasons)

    def test_goodwill_ratio_filtered(self):
        args = _make_args()
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        fin = {"EPSJB": "1.0", "GOODWILL_RATIO": "40"}
        reasons = hard_filter(quote, fin, args)
        assert any("商誉" in r for r in reasons)

    def test_pledge_ratio_filtered(self):
        args = _make_args()
        quote = {"name": "测试", "code": "sh600001", "amount": "100000", "total_cap": "100", "change_pct": "1.0"}
        fin = {"EPSJB": "1.0", "PLEDGE_RATIO": "80"}
        reasons = hard_filter(quote, fin, args)
        assert any("质押" in r for r in reasons)

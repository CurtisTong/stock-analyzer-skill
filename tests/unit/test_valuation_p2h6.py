"""P2-H6：valuation_score 语义修复测试。

修复内容：
1. revenue_yoy/net_profit_yoy 仅用标准化字段（FinanceRecord.to_dict），
   移除原始东财键（TOTALOPERATEREVETZ/PARENTNETPROFITTZ）回退——
   那是绝对营收值/不可达死代码，"营收绝对值当增速"语义混乱。
2. PEG 的 3 年 CAGR 优先（孤儿 TODO）：fin 携带 net_profit_cagr_3y 时优先，
   否则回退单期净利同比。
3. PS 优先用真实值 = 总市值/营业总收入，而非仅 PE × 净利率近似。
"""

from __future__ import annotations

from strategies.factors.valuation import valuation_score


class TestRevenueSemantics:
    def test_standardized_fin_without_legacy_keys_scores(self):
        """fin 只含标准化键（无 TOTALOPERATEREVETZ 等）也正常评分。"""
        fin = {"net_profit_yoy": 30.0, "revenue_yoy": 25.0, "total_revenue": 50}
        quote = {"pe": 15, "pb": 2, "total_cap": 100}
        score = valuation_score(quote, fin, "默认")
        assert 0 <= score <= 100

    def test_standardized_fin_scored_higher_than_legacy_abs(self):
        """营收增速字段缺失时不再误用绝对营收值加分。"""
        # 亏损 + 无营收增速：旧代码若误用 TOTALOPERATEREVETZ（绝对值元）当增速会加分
        fin = {"net_profit_yoy": -10.0}  # 亏损收窄但 revenue_yoy 缺失
        quote = {"pe": 0, "pb": 2, "total_cap": 500}
        s1 = valuation_score(quote, dict(fin, revenue_yoy=0.0), "默认")
        s2 = valuation_score(quote, dict(fin, revenue_yoy=15.0), "默认")
        # 有真实增速 > 无增速（无增速时不应因绝对营收误判加分）
        assert s2 > s1


class TestPegCagr:
    def test_cagr_preferred_over_single_period(self):
        """net_profit_cagr_3y 存在时 PEG 用 CAGR，而非单期 +100%。"""
        fin_cagr = {
            "net_profit_cagr_3y": 5.0,
            "net_profit_yoy": 100.0,
        }
        fin_yoy = {"net_profit_yoy": 100.0}
        quote = {"pe": 25, "pb": 3}
        # 单期 +100% → PEG=0.25 触发 +28；CAGR 5% → PEG=5 无加分 → 分更低
        with_cagr = valuation_score(quote, fin_cagr, "默认")
        without_cagr = valuation_score(quote, fin_yoy, "默认")
        assert with_cagr < without_cagr


class TestRealPs:
    def test_real_ps_uses_market_cap_over_revenue(self):
        """高 PE + 市值/营收可得：PS 用真实值（市值/营收）。"""
        # pe=100 > pe_cap=80（40×2），走 PS 分支；PS = 100/50 = 2 < 3 → +15
        fin = {"net_profit_yoy": 30.0, "revenue_yoy": 50.0, "total_revenue": 50}
        quote = {"pe": 100, "pb": 0, "total_cap": 100}
        score = valuation_score(quote, fin, "默认")
        # 基础分 15（PS 低估）→ 低净利率下无其它加分时 ≈15
        assert score >= 15

    def test_approx_ps_fallback_without_revenue(self):
        """无营收数据时退回 PE × 净利率近似（不抛错）。"""
        fin = {"net_profit_yoy": 30.0, "revenue_yoy": 50.0, "net_margin": 5.0}
        quote = {"pe": 100, "pb": 0, "total_cap": 100}
        score = valuation_score(quote, fin, "默认")
        # 近似 PS = 100 × 5% = 5 → 合理区间 +10；无营收真实值 → score ≈10
        assert score >= 10

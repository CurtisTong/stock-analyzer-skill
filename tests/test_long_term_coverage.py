"""business/long_term.py 覆盖测试（纯数据 + mock 数据获取）。

覆盖 LongTermEvaluator 的各 _calc_* 分支、_calc_level、_generate_conclusion、
format_long_term_result、main。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import business.long_term as long_term_mod
from business.long_term import (
    LongTermEvaluator,
    _load_long_term_weights,
    format_long_term_result,
)


def _make_evaluator():
    return LongTermEvaluator()


class TestCalcMoat:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_high_gross_margin(self):
        score, reasoning = self.ev._calc_moat(
            {"gross_margin": 60, "net_margin": 25, "roe": 25}
        )
        assert score > 50
        assert any("毛利率" in r for r in reasoning)

    def test_medium_gross_margin(self):
        score, _ = self.ev._calc_moat({"gross_margin": 40, "net_margin": 15, "roe": 18})
        assert score > 50

    def test_low_gross_margin(self):
        score, reasoning = self.ev._calc_moat(
            {"gross_margin": 20, "net_margin": 5, "roe": 8}
        )
        assert score < 50
        assert any("定价权弱" in r for r in reasoning)

    def test_high_net_margin(self):
        score, _ = self.ev._calc_moat({"gross_margin": 60, "net_margin": 25, "roe": 25})
        assert "净利率" in "".join(_) or score > 50

    def test_low_net_margin(self):
        score, reasoning = self.ev._calc_moat(
            {"gross_margin": 60, "net_margin": 5, "roe": 25}
        )
        assert any("盈利能力弱" in r for r in reasoning)

    def test_high_roe(self):
        score, _ = self.ev._calc_moat({"gross_margin": 60, "net_margin": 25, "roe": 25})
        assert score > 60

    def test_medium_roe(self):
        score, reasoning = self.ev._calc_moat(
            {"gross_margin": 60, "net_margin": 25, "roe": 16}
        )
        assert any("资本效率良好" in r for r in reasoning)

    def test_low_roe(self):
        score, reasoning = self.ev._calc_moat(
            {"gross_margin": 60, "net_margin": 25, "roe": 8}
        )
        assert any("资本效率一般" in r for r in reasoning)

    def test_empty_finance(self):
        score, reasoning = self.ev._calc_moat({})
        assert 0 <= score <= 100


class TestCalcGrowth:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_high_revenue_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": 30, "net_profit_yoy": 25, "roe": 20}
        )
        assert any("高成长" in r for r in reasoning)

    def test_medium_revenue_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": 15, "net_profit_yoy": 15, "roe": 12}
        )
        assert any("稳定成长" in r for r in reasoning)

    def test_low_revenue_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": 5, "net_profit_yoy": 5, "roe": 12}
        )
        assert any("低增长" in r for r in reasoning)

    def test_negative_revenue_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": -5, "net_profit_yoy": -5, "roe": 12}
        )
        assert any("负增长" in r for r in reasoning)

    def test_high_profit_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": 30, "net_profit_yoy": 30, "roe": 20}
        )
        assert any("利润增长" in r for r in reasoning)

    def test_negative_profit_growth(self):
        score, reasoning = self.ev._calc_growth(
            {"revenue_yoy": 30, "net_profit_yoy": -10, "roe": 20}
        )
        assert any("利润增长" in r for r in reasoning)


class TestCalcStability:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_low_debt_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 2, "eps": 1, "dividend_yield": 4}
        )
        assert any("财务稳健" in r for r in reasoning)

    def test_medium_debt_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 40, "ocf_per_share": 2, "eps": 1, "dividend_yield": 2}
        )
        assert any("财务正常" in r for r in reasoning)

    def test_high_debt_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 60, "ocf_per_share": 2, "eps": 1, "dividend_yield": 0.5}
        )
        assert any("负债偏高" in r for r in reasoning)

    def test_very_high_debt_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 80, "ocf_per_share": 2, "eps": 1, "dividend_yield": 0.5}
        )
        assert any("财务风险高" in r for r in reasoning)

    def test_good_cash_flow_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 2, "eps": 1, "dividend_yield": 4}
        )
        assert any("现金流充足" in r for r in reasoning)

    def test_medium_cash_flow_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 0.6, "eps": 1, "dividend_yield": 4}
        )
        assert any("现金流一般" in r for r in reasoning)

    def test_low_cash_flow_ratio(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 0.3, "eps": 1, "dividend_yield": 4}
        )
        assert any("现金流不足" in r for r in reasoning)

    def test_loss_but_positive_ocf(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 0.5, "eps": -1, "dividend_yield": 4}
        )
        assert any("造血能力" in r for r in reasoning)

    def test_negative_ocf(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": -0.5, "eps": 1, "dividend_yield": 4}
        )
        assert any("资金链风险" in r for r in reasoning)

    def test_missing_cash_flow(self):
        # eps=0, ocf=0: 走 elif ocf <= 0 分支 -> 资金链风险
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 0, "eps": 0, "dividend_yield": 4}
        )
        assert any("资金链风险" in r for r in reasoning)

    def test_high_dividend(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 2, "eps": 1, "dividend_yield": 4}
        )
        assert any("分红慷慨" in r for r in reasoning)

    def test_medium_dividend(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 2, "eps": 1, "dividend_yield": 2}
        )
        assert any("分红一般" in r for r in reasoning)

    def test_low_dividend(self):
        score, reasoning = self.ev._calc_stability(
            {"debt_ratio": 20, "ocf_per_share": 2, "eps": 1, "dividend_yield": 0.5}
        )
        assert any("分红较少" in r for r in reasoning)


class TestCalcValuation:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_low_pe(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 10, "pe_percentile": 20, "pb": 0.8}, {}
        )
        assert any("低估" in r for r in reasoning)

    def test_medium_pe(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 50, "pb": 2}, {}
        )
        assert any("合理估值" in r for r in reasoning)

    def test_high_pe(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 30, "pe_percentile": 50, "pb": 2}, {}
        )
        assert any("偏高" in r for r in reasoning)

    def test_very_high_pe(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 50, "pe_percentile": 50, "pb": 2}, {}
        )
        assert any("高估" in r for r in reasoning)

    def test_low_pe_percentile(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 10, "pb": 2}, {}
        )
        assert any("历史低位" in r for r in reasoning)

    def test_high_pe_percentile(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 80, "pb": 2}, {}
        )
        assert any("历史高位" in r for r in reasoning)

    def test_mid_pe_percentile(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 50, "pb": 2}, {}
        )
        assert any("历史中位" in r for r in reasoning)

    def test_low_pb(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 50, "pb": 0.5}, {}
        )
        assert any("低估" in r for r in reasoning)

    def test_high_pb(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 20, "pe_percentile": 50, "pb": 5}, {}
        )
        assert any("高估" in r for r in reasoning)

    def test_no_pe(self):
        score, reasoning = self.ev._calc_valuation(
            {"pe": 0, "pe_percentile": -1, "pb": 0}, {}
        )
        assert 0 <= score <= 100


class TestCalcLevel:
    def setup_method(self):
        self.ev = _make_evaluator()

    @pytest.mark.parametrize(
        "score,expected",
        [
            (85, "非常适合"),
            (70, "适合"),
            (55, "一般"),
            (40, "不太适合"),
            (20, "不适合"),
        ],
    )
    def test_levels(self, score, expected):
        assert self.ev._calc_level(score) == expected


class TestGenerateConclusion:
    def setup_method(self):
        self.ev = _make_evaluator()

    def test_excellent_score(self):
        conclusion = self.ev._generate_conclusion(80, "非常适合", 75, 75, 75, 75)
        assert "非常适合长期持有" in conclusion
        assert "护城河宽" in conclusion

    def test_good_score(self):
        conclusion = self.ev._generate_conclusion(65, "适合", 50, 50, 50, 50)
        assert "整体质量较好" in conclusion

    def test_average_score(self):
        conclusion = self.ev._generate_conclusion(50, "一般", 30, 30, 30, 30)
        assert "质量一般" in conclusion
        assert "护城河窄" in conclusion
        assert "成长性差" in conclusion
        assert "财务风险高" in conclusion
        assert "估值偏高" in conclusion

    def test_poor_score(self):
        conclusion = self.ev._generate_conclusion(30, "不适合", 30, 30, 30, 30)
        assert "不建议长期持有" in conclusion

    def test_high_growth_highlight(self):
        conclusion = self.ev._generate_conclusion(70, "适合", 50, 75, 50, 50)
        assert "成长性好" in conclusion

    def test_high_stability_highlight(self):
        conclusion = self.ev._generate_conclusion(70, "适合", 50, 50, 75, 50)
        assert "财务稳健" in conclusion

    def test_high_valuation_highlight(self):
        conclusion = self.ev._generate_conclusion(70, "适合", 50, 50, 50, 75)
        assert "估值合理" in conclusion


class TestEvaluate:
    def test_no_quote_returns_error(self):
        ev = _make_evaluator()
        with patch.object(ev, "_get_quote", return_value=None):
            result = ev.evaluate("sh600519")
        assert result == {"code": "sh600519", "error": "无法获取行情数据"}

    def test_full_evaluation(self):
        ev = _make_evaluator()
        with (
            patch.object(
                ev, "_get_quote", return_value={"name": "茅台", "pe": 20, "pb": 2}
            ),
            patch.object(
                ev,
                "_get_finance",
                return_value={
                    "gross_margin": 60,
                    "net_margin": 25,
                    "roe": 25,
                    "revenue_yoy": 30,
                    "net_profit_yoy": 25,
                    "debt_ratio": 20,
                    "ocf_per_share": 2,
                    "eps": 1,
                    "dividend_yield": 4,
                },
            ),
        ):
            result = ev.evaluate("sh600519")
        assert result["code"] == "sh600519"
        assert result["name"] == "茅台"
        assert "total_score" in result
        assert "level" in result
        assert "dimensions" in result
        assert "reasoning" in result
        assert "conclusion" in result


class TestFormatLongTermResult:
    def test_error_result(self):
        result = {"code": "sh600519", "error": "无法获取行情数据"}
        output = format_long_term_result(result)
        assert "评估失败" in output

    def test_full_result(self):
        result = {
            "code": "sh600519",
            "name": "茅台",
            "total_score": 75,
            "level": "适合",
            "dimensions": {
                "moat": {"score": 75, "weight": 0.30},
                "growth": {"score": 70, "weight": 0.25},
                "stability": {"score": 80, "weight": 0.25},
                "valuation": {"score": 60, "weight": 0.20},
            },
            "reasoning": ["✅ 毛利率高", "✅ ROE 高"],
            "conclusion": "综合评分 75 分（适合），整体质量较好。",
        }
        output = format_long_term_result(result)
        assert "茅台" in output
        assert "综合评分" in output
        assert "评分明细" in output
        assert "护城河" in output
        assert "推理过程" in output
        assert "结论" in output

    def test_all_levels_icons(self):
        for level in ["非常适合", "适合", "一般", "不太适合", "不适合", "未知"]:
            result = {
                "code": "sh000001",
                "name": "X",
                "total_score": 50,
                "level": level,
                "dimensions": {"moat": {"score": 50, "weight": 0.3}},
                "reasoning": [],
                "conclusion": "test",
            }
            output = format_long_term_result(result)
            assert "综合评分" in output


class TestLoadLongTermWeights:
    def test_default_weights_when_config_missing(self):
        weights = _load_long_term_weights()
        assert "moat" in weights
        assert "growth" in weights
        assert "stability" in weights
        assert "valuation" in weights

    def test_invalid_weight_falls_back(self):
        with patch(
            "config.loader.get_scoring_config", return_value={"moat": "invalid"}
        ):
            weights = _load_long_term_weights()
        assert weights["moat"] == 0.30  # 回退默认


class TestMain:
    def test_main_json_output(self, capsys):
        with (
            patch(
                "business.long_term.LongTermEvaluator.evaluate",
                return_value={"code": "sh600519", "total_score": 70},
            ),
            patch("sys.argv", ["long_term.py", "sh600519", "--json"]),
        ):
            long_term_mod.main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["code"] == "sh600519"

    def test_main_text_output(self, capsys):
        with (
            patch(
                "business.long_term.LongTermEvaluator.evaluate",
                return_value={
                    "code": "sh600519",
                    "name": "茅台",
                    "total_score": 70,
                    "level": "适合",
                    "dimensions": {"moat": {"score": 70, "weight": 0.3}},
                    "reasoning": [],
                    "conclusion": "test",
                },
            ),
            patch("sys.argv", ["long_term.py", "sh600519"]),
        ):
            long_term_mod.main()
        captured = capsys.readouterr()
        assert "长期持有评估" in captured.out

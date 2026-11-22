"""[review P1-22 + P3] 筛选警告阈值文案与财务时效 code 透传回归测试。

P1-22：硬过滤文案把实际值当阈值显示（goodwill=45 写 ">45%"，真实阈值 30）。
P3：check_finance_freshness 未传 code，按板块差异化 deadline 失效。
"""

from __future__ import annotations

from business import finance_freshness
from business.screening_service import AnalyzeContext, ScreeningService

SERVICE = ScreeningService()
QUOTE = {
    "code": "sh600000",
    "name": "测试股",
    "total_cap": 100,
    "amount": 1e8,
    "change_pct": 0,
}


class TestWarningThresholdText:
    def test_stale_warnings_show_threshold_not_actual(self, monkeypatch):
        """[review P1-22] 过期降级警告必须显示阈值 30%/70%。"""
        monkeypatch.setattr(
            finance_freshness,
            "check_finance_freshness",
            lambda fin, **kwargs: (True, "财报已过期"),
        )
        fin = {"eps": 1, "roe": 10, "goodwill_ratio": 45, "pledge_ratio": 80}
        _reasons, warnings = SERVICE._hard_filter(QUOTE, fin, {"pledge_warning": True})

        assert any("商誉/总资产>30%" in w for w in warnings), warnings
        assert any("质押率>70%" in w for w in warnings), warnings
        assert not any(">45%" in w or ">80%" in w for w in warnings), warnings

    def test_reject_reasons_show_threshold_not_actual(self, monkeypatch):
        """[review P1-22] 硬拒绝文案同样显示阈值。"""
        monkeypatch.setattr(
            finance_freshness,
            "check_finance_freshness",
            lambda fin, **kwargs: (False, ""),
        )
        fin = {"eps": 1, "roe": 10, "goodwill_ratio": 45, "pledge_ratio": 80}
        reasons, _warnings = SERVICE._hard_filter(QUOTE, fin, {})
        assert any("商誉/总资产>30%" in r for r in reasons), reasons
        assert any("质押率>70%" in r for r in reasons), reasons
        assert not any(">45%" in r or ">80%" in r for r in reasons), reasons


class TestFreshnessCodePassing:
    def test_hard_filter_passes_code_to_freshness(self, monkeypatch):
        """[review P3] 上下文 code 必须传到 check_finance_freshness。"""
        seen = {}

        def spy(fin, **kwargs):
            seen.update(kwargs)
            return (False, "")

        monkeypatch.setattr(finance_freshness, "check_finance_freshness", spy)
        # quote 故意不带 code，验证 code 来自显式参数而非行情 dict
        SERVICE._hard_filter({k: v for k, v in QUOTE.items() if k != "code"}, {"eps": 1}, {}, code="SH688001")
        assert seen.get("code") == "SH688001"

    def test_analyze_stock_passes_context_code(self, monkeypatch):
        """[review P3] _analyze_stock 把 AnalyzeContext.code 传给 _hard_filter。"""
        seen = {}

        def spy_hard_filter(self, quote, fin, filters, code=""):
            seen["code"] = code
            return (["mock rejection"], [])

        monkeypatch.setattr(ScreeningService, "_hard_filter", spy_hard_filter)
        ctx = AnalyzeContext(
            code="SZ300750",
            quote=QUOTE,
            fin_records=[{"eps": 1}],
            strategy="balanced",
            filters={},
        )
        result = SERVICE._analyze_stock(ctx)
        assert seen["code"] == "SZ300750"
        assert result["code"] == "SZ300750"

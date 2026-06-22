"""common/formatters.py 输出格式化工具测试。"""

import pytest
from common.formatters import (
    format_output,
    format_conclusion,
    format_footer,
    now_str,
    collect_source_evidence,
    format_with_enhancements,
)


class TestFormatOutput:
    """format_output 统一格式输出。"""

    def test_conclusion_only(self):
        result = format_output(conclusion="看多")
        assert "🎯 看多" in result

    def test_custom_emoji(self):
        result = format_output(conclusion="风险", emoji="🔴")
        assert "🔴 风险" in result

    def test_with_body(self):
        result = format_output(conclusion="结论", body="详细分析内容")
        assert "详细分析内容" in result

    def test_with_data_time(self):
        result = format_output(conclusion="结论", data_time="2026-06-22 14:30")
        assert "2026-06-22 14:30" in result

    def test_with_sources(self):
        result = format_output(conclusion="结论", sources=["腾讯行情", "东财财务"])
        assert "腾讯行情" in result
        assert "东财财务" in result

    def test_with_failed_sources(self):
        result = format_output(conclusion="结论", failed_sources=["新浪K线"])
        assert "失败源" in result
        assert "新浪K线" in result

    def test_with_ttl(self):
        result = format_output(conclusion="结论", ttl_sec=900)
        assert "900s" in result

    def test_full_output(self):
        result = format_output(
            conclusion="可介入",
            data_time="2026-06-22",
            sources=["腾讯"],
            failed_sources=["新浪"],
            ttl_sec=600,
            body="分析正文",
        )
        assert "🎯 可介入" in result
        assert "分析正文" in result
        assert "2026-06-22" in result
        assert "─" * 40 in result


class TestFormatConclusion:
    """format_conclusion 一句话结论。"""

    def test_default_emoji(self):
        assert format_conclusion("看多") == "🎯 看多"

    def test_custom_emoji(self):
        assert format_conclusion("风险", emoji="🔴") == "🔴 风险"


class TestFormatFooter:
    """format_footer 尾行。"""

    def test_empty(self):
        assert format_footer() == ""

    def test_data_time_only(self):
        result = format_footer(data_time="2026-06-22")
        assert "2026-06-22" in result

    def test_sources_only(self):
        result = format_footer(sources=["腾讯"])
        assert "腾讯" in result

    def test_ttl_only(self):
        result = format_footer(ttl_sec=300)
        assert "300s" in result


class TestNowStr:
    """now_str 时间格式。"""

    def test_format(self):
        result = now_str()
        assert len(result) == 16  # "YYYY-MM-DD HH:MM"
        assert result[4] == "-"
        assert result[7] == "-"
        assert result[10] == " "


class TestCollectSourceEvidence:
    """collect_source_evidence 数据源证据收集。"""

    def test_all_success(self):
        results = {"腾讯": "data", "东财": "data2"}
        sources, failed = collect_source_evidence(results)
        assert set(sources) == {"腾讯", "东财"}
        assert failed == []

    def test_partial_failure(self):
        results = {"腾讯": "data", "新浪": None}
        sources, failed = collect_source_evidence(results)
        assert sources == ["腾讯"]
        assert failed == ["新浪"]

    def test_all_failed(self):
        results = {"腾讯": None, "新浪": None}
        sources, failed = collect_source_evidence(results)
        assert sources == []
        assert set(failed) == {"腾讯", "新浪"}


class TestFormatWithEnhancements:
    """format_with_enhancements 增强输出。"""

    def test_risk_disclaimer_default(self):
        result = format_with_enhancements("分析结果")
        assert "风险提示" in result

    def test_no_risk_disclaimer(self):
        result = format_with_enhancements("分析结果", risk_disclaimer=False)
        assert "风险提示" not in result

    def test_auto_glossary(self):
        result = format_with_enhancements(
            "该股 ROE 较高", auto_glossary=True, risk_disclaimer=False
        )
        assert "净资产收益率" in result

    def test_explicit_terms(self):
        result = format_with_enhancements(
            "分析结果", terms=["PE", "MACD"], risk_disclaimer=False
        )
        assert "市盈率" in result
        assert "指数平滑异同移动平均线" in result

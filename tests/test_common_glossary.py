"""common/glossary.py 金融术语库测试。"""

import pytest
from common.glossary import GLOSSARY, format_glossary, add_glossary, auto_detect_terms


class TestGlossary:
    """GLOSSARY 术语库完整性。"""

    def test_core_terms_present(self):
        """核心术语必须存在。"""
        for term in ["PE", "PB", "ROE", "PEG", "EPS", "MACD", "KDJ", "RSI", "BOLL"]:
            assert term in GLOSSARY

    def test_each_term_has_fields(self):
        """每个术语都有 name/formula/meaning/reference。"""
        for term, info in GLOSSARY.items():
            assert "name" in info, f"{term} missing 'name'"
            assert "formula" in info, f"{term} missing 'formula'"
            assert "meaning" in info, f"{term} missing 'meaning'"
            assert "reference" in info, f"{term} missing 'reference'"


class TestFormatGlossary:
    """format_glossary 术语格式化。"""

    def test_known_terms(self):
        result = format_glossary(["PE", "ROE"])
        assert "市盈率" in result
        assert "净资产收益率" in result

    def test_unknown_terms_ignored(self):
        result = format_glossary(["UNKNOWN_TERM"])
        assert result == ""

    def test_empty_list(self):
        assert format_glossary([]) == ""

    def test_output_structure(self):
        result = format_glossary(["PE"])
        assert "📖" in result
        assert "含义" in result
        assert "参考" in result


class TestAddGlossary:
    """add_glossary 添加术语解释。"""

    def test_appends_to_text(self):
        result = add_glossary("原始文本", ["PE"])
        assert "原始文本" in result
        assert "市盈率" in result

    def test_no_terms_returns_original(self):
        result = add_glossary("原始文本", ["UNKNOWN"])
        assert result == "原始文本"


class TestAutoDetectTerms:
    """auto_detect_terms 自动检测术语。"""

    def test_detect_pe(self):
        terms = auto_detect_terms("PE 偏低，值得买入")
        assert "PE" in terms

    def test_detect_roe(self):
        terms = auto_detect_terms("ROE 连续 5 年 > 20%")
        assert "ROE" in terms

    def test_detect_multiple(self):
        terms = auto_detect_terms("PE 15，ROE 20%，MACD 金叉")
        assert "PE" in terms
        assert "ROE" in terms
        assert "MACD" in terms

    def test_no_false_positive(self):
        """不误报子串匹配（如 'TYPE' 中的 'PE'）。"""
        terms = auto_detect_terms("This is a TYPE test")
        # 'PE' 不应出现在检测结果中（被字母包围）
        assert "PE" not in terms

    def test_empty_text(self):
        assert auto_detect_terms("") == []

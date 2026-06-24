"""性能压测模块测试（纯函数，无网络调用）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from perf_bench import _parse_codes


class TestParseCodes:
    """_parse_codes 函数测试。"""

    def test_single_code(self):
        """单个代码。"""
        result = _parse_codes("sh600519")
        assert result == ["sh600519"]

    def test_multiple_codes(self):
        """多个代码逗号分隔。"""
        result = _parse_codes("sh600519,sh600989,sh600000")
        assert result == ["sh600519", "sh600989", "sh600000"]

    def test_code_normalization(self):
        """代码自动补前缀。"""
        result = _parse_codes("600519,000858")
        assert result == ["sh600519", "sz000858"]

    def test_mixed_format(self):
        """混合格式代码。"""
        result = _parse_codes("sh600519,000858,sz000001")
        assert result == ["sh600519", "sz000858", "sz000001"]

    def test_empty_string(self):
        """空字符串返回包含空元素的列表（split 行为）。"""
        result = _parse_codes("")
        assert len(result) == 1  # "".split(",") 得到 [""]

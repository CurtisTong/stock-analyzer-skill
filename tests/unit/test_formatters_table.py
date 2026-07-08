"""formatters.markdown_table / numbered_table 单元测试。"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from common.formatters import markdown_table, numbered_table


class TestMarkdownTable:
    def test_basic_table(self):
        """基本表格：表头 + 分隔行 + 数据行。"""
        result = markdown_table(["代码", "名称", "评分"], [("sh600519", "茅台", 78)])
        lines = result.split("\n")
        assert len(lines) == 3
        assert lines[0] == "| 代码 | 名称 | 评分 |"
        assert lines[1] == "|:------|:------|:------|"
        assert lines[2] == "| sh600519 | 茅台 | 78 |"

    def test_multiple_rows(self):
        """多行数据。"""
        rows = [("sh600519", "茅台", 78), ("sz000858", "五粮液", 72)]
        result = markdown_table(["代码", "名称", "评分"], rows)
        assert result.count("\n") == 3  # 表头 + 分隔 + 2 行
        assert "茅台" in result
        assert "五粮液" in result

    def test_right_align(self):
        """右对齐分隔符。"""
        result = markdown_table(["A"], [(1,)], align="right")
        assert "|------:|" in result

    def test_center_align(self):
        """居中对齐分隔符。"""
        result = markdown_table(["A"], [(1,)], align="center")
        assert "|:------:|" in result

    def test_empty_headers(self):
        """空表头返回空字符串。"""
        assert markdown_table([], [("a",)]) == ""

    def test_empty_rows(self):
        """空行数据返回空字符串。"""
        assert markdown_table(["A"], []) == ""

    def test_non_string_values(self):
        """非字符串值自动转 str。"""
        result = markdown_table(["值"], [(3.14, True, None)])
        assert "3.14" in result
        assert "True" in result
        assert "None" in result

    def test_doctest_example(self):
        """对齐 docstring 中的 example。"""
        result = markdown_table(["代码", "名称", "评分"], [("sh600519", "茅台", 78)])
        expected = "| 代码 | 名称 | 评分 |\n|:------|:------|:------|\n| sh600519 | 茅台 | 78 |"
        assert result == expected


class TestNumberedTable:
    def test_basic_numbered(self):
        """首列为排名序号。"""
        result = numbered_table(["代码", "评分"], [("sh600519", 78), ("sz000858", 72)])
        lines = result.split("\n")
        assert lines[0] == "| 排名 | 代码 | 评分 |"
        assert "| 1 | sh600519 | 78 |" in result
        assert "| 2 | sz000858 | 72 |" in result

    def test_start_offset(self):
        """起始序号偏移。"""
        result = numbered_table(["代码"], [("sh600519",)], start=10)
        assert "| 10 | sh600519 |" in result

    def test_empty_headers(self):
        """空表头返回空字符串。"""
        assert numbered_table([], [("a",)]) == ""

    def test_empty_rows(self):
        """空行数据：headers 非空但 rows 为空 → markdown_table 返回空字符串。"""
        result = numbered_table(["代码"], [])
        assert result == ""

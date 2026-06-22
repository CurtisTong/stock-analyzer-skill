"""common/exporters.py 数据导出与风险提示测试。"""

import csv
import pytest
from pathlib import Path
from common.exporters import (
    RISK_DISCLAIMER,
    add_risk_disclaimer,
    export_to_csv,
    export_analysis_to_csv,
    _flatten_dict,
)


class TestRiskDisclaimer:
    """风险提示。"""

    def test_disclaimer_content(self):
        assert "风险提示" in RISK_DISCLAIMER
        assert "不构成投资建议" in RISK_DISCLAIMER

    def test_add_disclaimer(self):
        result = add_risk_disclaimer("分析结果")
        assert result.startswith("分析结果")
        assert "风险提示" in result


class TestExportToCsv:
    """export_to_csv CSV 导出。"""

    def test_export_basic(self, tmp_path):
        data = [{"代码": "600519", "名称": "贵州茅台", "价格": 1800}]
        path = export_to_csv(data, "test_basic", str(tmp_path))
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8-sig")
        assert "600519" in content
        assert "贵州茅台" in content

    def test_export_empty(self, tmp_path):
        path = export_to_csv([], "test_empty", str(tmp_path))
        assert Path(path).exists()
        assert Path(path).read_text(encoding="utf-8-sig") == ""

    def test_export_creates_dir(self, tmp_path):
        subdir = tmp_path / "new_dir"
        data = [{"a": 1}]
        path = export_to_csv(data, "test_dir", str(subdir))
        assert Path(path).exists()

    def test_export_multiple_rows(self, tmp_path):
        data = [{"x": i} for i in range(5)]
        path = export_to_csv(data, "test_multi", str(tmp_path))
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 5


class TestFlattenDict:
    """_flatten_dict 字典扁平化。"""

    def test_flat_dict(self):
        assert _flatten_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_nested_dict(self):
        result = _flatten_dict({"a": {"b": 1, "c": 2}})
        assert result == {"a.b": 1, "a.c": 2}

    def test_deep_nesting(self):
        result = _flatten_dict({"a": {"b": {"c": 3}}})
        assert result == {"a.b.c": 3}

    def test_list_value(self):
        result = _flatten_dict({"a": [1, 2, 3]})
        assert result == {"a": "[1, 2, 3]"}

    def test_mixed_values(self):
        result = _flatten_dict({"x": 1, "y": {"z": "hello"}})
        assert result == {"x": 1, "y.z": "hello"}


class TestExportAnalysisToCsv:
    """export_analysis_to_csv 分析结果导出。"""

    def test_flat_analysis(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        analysis = {"PE": 15.5, "ROE": 20.3}
        path = export_analysis_to_csv(analysis, "test_analysis")
        assert Path(path).exists()
        content = Path(path).read_text(encoding="utf-8-sig")
        assert "PE" in content
        assert "ROE" in content

    def test_nested_analysis(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        analysis = {"基本面": {"PE": 15, "ROE": 20}, "技术面": {"MACD": "金叉"}}
        path = export_analysis_to_csv(analysis, "test_nested")
        assert Path(path).exists()

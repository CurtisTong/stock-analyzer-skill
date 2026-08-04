"""存货数据获取单元测试。

覆盖场景：
- 方案A：_dict_to_finance 映射 CHZZL/CHZZTS（存货周转率/天数）
- 方案B：akshare_balance enrich_with_balance_sheet 合并 INVENTORY
- _normalize_symbol 代码格式归一化
- akshare 不可用时降级
"""

import pytest

from data import get_finance  # noqa: F401  确保模块可导入
from data.mappers import FINANCE_FIELD_MAP
from data.types import FinanceRecord


class TestInventoryFieldMapping:
    """方案A：存货周转率/天数字段映射。"""

    def test_field_map_has_inventory_turnover(self):
        """FINANCE_FIELD_MAP 包含 inventory_turnover 映射。"""
        assert "inventory_turnover" in FINANCE_FIELD_MAP
        assert "CHZZL" in FINANCE_FIELD_MAP["inventory_turnover"]

    def test_field_map_has_inventory_days(self):
        """FINANCE_FIELD_MAP 包含 inventory_days 映射。"""
        assert "inventory_days" in FINANCE_FIELD_MAP
        assert "CHZZTS" in FINANCE_FIELD_MAP["inventory_days"]

    def test_field_map_has_inventory(self):
        """FINANCE_FIELD_MAP 包含 inventory（存货绝对额）映射。"""
        assert "inventory" in FINANCE_FIELD_MAP
        assert "INVENTORY" in FINANCE_FIELD_MAP["inventory"]

    def test_finance_record_has_inventory_fields(self):
        """FinanceRecord 有 inventory_turnover/inventory_days/inventory 字段。"""
        r = FinanceRecord()
        assert hasattr(r, "inventory_turnover")
        assert hasattr(r, "inventory_days")
        assert hasattr(r, "inventory")
        assert r.inventory_turnover is None  # 默认 None
        assert r.inventory_days is None
        assert r.inventory is None


class TestDictToFinance:
    """_dict_to_finance 映射存货字段。"""

    def test_inventory_turnover_mapped(self):
        """CHZZL 映射到 inventory_turnover。"""
        from data import _dict_to_finance

        raw = {
            "REPORT_DATE": "2026-03-31",
            "CHZZL": 0.503819925861,
            "CHZZTS": 178.635253153585,
            "source": "eastmoney",
        }
        r = _dict_to_finance(raw)
        assert r.inventory_turnover == 0.5038
        assert r.inventory_days == 178.6

    def test_inventory_absolute_mapped(self):
        """INVENTORY（元）映射到 inventory（亿元）。"""
        from data import _dict_to_finance

        raw = {
            "REPORT_DATE": "2026-03-31",
            "INVENTORY": 9382405579.77,  # ~93.82 亿
            "source": "eastmoney",
        }
        r = _dict_to_finance(raw)
        assert r.inventory == 93.82

    def test_inventory_none_when_missing(self):
        """无存货字段时 inventory 为 None。"""
        from data import _dict_to_finance

        raw = {"REPORT_DATE": "2026-03-31", "source": "test"}
        r = _dict_to_finance(raw)
        assert r.inventory_turnover is None
        assert r.inventory_days is None
        assert r.inventory is None


class TestAkshareBalanceEnricher:
    """方案B：akshare 资产负债表增强。"""

    def test_enrich_merges_inventory(self, monkeypatch):
        """enrich_with_balance_sheet 合并 INVENTORY 到 records。"""
        from fetchers.finance import akshare_balance

        # mock akshare 返回资产负债表 DataFrame
        class MockDF:
            def __init__(self):
                self.columns = ["REPORT_DATE", "INVENTORY"]
                self._data = [
                    {"REPORT_DATE": "2026-03-31", "INVENTORY": 9382405579.77},
                    {"REPORT_DATE": "2025-12-31", "INVENTORY": 8500000000.0},
                ]

            @property
            def empty(self):
                return False

            def head(self, n):
                # 返回自身（支持链式 .iterrows()）
                return self

            def iterrows(self):
                for i, row in enumerate(self._data):
                    yield i, row

        monkeypatch.setattr(akshare_balance, "HAS_AKSHARE", True)
        monkeypatch.setattr(
            akshare_balance,
            "ak",
            type(
                "M", (), {"stock_balance_sheet_by_report_em": lambda symbol: MockDF()}
            ),
        )

        records = [
            {"REPORT_DATE": "2026-03-31", "EPSJB": 0.41, "source": "eastmoney"},
            {"REPORT_DATE": "2025-12-31", "EPSJB": 3.37, "source": "eastmoney"},
        ]
        result = akshare_balance.enrich_with_balance_sheet(
            records, "sh603501", periods=2
        )
        assert result[0]["INVENTORY"] == 9382405579.77
        assert result[1]["INVENTORY"] == 8500000000.0

    def test_enrich_no_akshare_returns_original(self, monkeypatch):
        """akshare 不可用时原样返回。"""
        from fetchers.finance import akshare_balance

        monkeypatch.setattr(akshare_balance, "HAS_AKSHARE", False)
        records = [{"REPORT_DATE": "2026-03-31"}]
        result = akshare_balance.enrich_with_balance_sheet(records, "sh603501")
        assert result is records  # 同一对象

    def test_enrich_empty_records(self, monkeypatch):
        """空 records 原样返回。"""
        from fetchers.finance import akshare_balance

        monkeypatch.setattr(akshare_balance, "HAS_AKSHARE", True)
        result = akshare_balance.enrich_with_balance_sheet([], "sh603501")
        assert result == []

    def test_enrich_failure_returns_original(self, monkeypatch):
        """akshare 报错时原样返回（降级不阻断）。"""
        from fetchers.finance import akshare_balance

        monkeypatch.setattr(akshare_balance, "HAS_AKSHARE", True)
        monkeypatch.setattr(
            akshare_balance,
            "ak",
            type(
                "M",
                (),
                {
                    "stock_balance_sheet_by_report_em": lambda symbol: (
                        _ for _ in ()
                    ).throw(RuntimeError("网络错误"))
                },
            ),
        )

        records = [{"REPORT_DATE": "2026-03-31"}]
        result = akshare_balance.enrich_with_balance_sheet(records, "sh603501")
        assert result is records  # 原样返回


class TestNormalizeSymbol:
    """_normalize_symbol 代码格式归一化。"""

    def test_lowercase_prefix(self):
        """小写前缀转大写。"""
        from fetchers.finance.akshare_balance import _normalize_symbol

        assert _normalize_symbol("sh603501") == "SH603501"
        assert _normalize_symbol("sz300476") == "SZ300476"

    def test_plain_code_infer(self):
        """裸代码推断前缀。"""
        from fetchers.finance.akshare_balance import _normalize_symbol

        assert _normalize_symbol("603501") == "SH603501"  # 60 开头 -> SH
        assert _normalize_symbol("300476") == "SZ300476"  # 30 开头 -> SZ

    def test_already_uppercase(self):
        """已大写保持不变。"""
        from fetchers.finance.akshare_balance import _normalize_symbol

        assert _normalize_symbol("SH603501") == "SH603501"

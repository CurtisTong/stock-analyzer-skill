"""[review P1-18] classifier 财务 schema 契约回归测试。

修复前：classifier 读取旧 schema ROEJQ/PARENTNETPROFITTZ/XSMLL/ZCFZL，
但 classifier.py CLI 与 technical/analyzer.py 两条调用路径传入的都是
FinanceRecord.to_dict()（标准字段 roe/net_profit_yoy/gross_margin/debt_ratio），
四特征恒 0，分类恒落"普通股"。本测试同时覆盖两条调用路径。
"""

from __future__ import annotations

import json
import runpy
import sys
import types
from pathlib import Path

import classifier
from data.types import FinanceRecord

PKG_ROOT = Path(__file__).resolve().parent.parent.parent

QUOTE = {"code": "sh600519", "name": "测试股", "circulating_cap": 300, "turnover": 2, "pe": 20}


def _standard_fin(**overrides):
    rec = FinanceRecord(
        report_date="2026-03-31",
        roe=22.0,
        net_profit_yoy=45.0,
        gross_margin=60.0,
        debt_ratio=30.0,
        eps=1.0,
    )
    data = rec.to_dict()
    data.update(overrides)
    return data


class TestStandardSchema:
    def test_finance_record_exposes_standard_keys(self):
        """[review P1-18] 调用方实际传入的标准字段名必须先存在。"""
        data = FinanceRecord().to_dict()
        for key in ("roe", "net_profit_yoy", "gross_margin", "debt_ratio"):
            assert key in data
        for legacy in ("ROEJQ", "PARENTNETPROFITTZ", "XSMLL", "ZCFZL"):
            assert legacy not in data

    def test_standard_fields_drive_classification(self):
        """[review P1-18] 标准字段不再是恒 0：应识别出强成长股。"""
        result = classifier.classify_stock(_standard_fin(), QUOTE, [])
        assert result["type"] == "强成长股"
        assert any("净利增速45%" in r for r in result["reasons"])

    def test_none_fields_are_not_treated_as_zero(self):
        """[review P1-18] None-aware：未披露字段为 None，不得当 0 误判类型。"""
        result = classifier.classify_stock(
            _standard_fin(roe=None, net_profit_yoy=None, gross_margin=None, debt_ratio=None),
            QUOTE,
            [],
        )
        assert result["type"] == "普通股"

    def test_partial_none_does_not_trigger_defensive(self):
        """[review P1-18] 负债率未披露时不能误判为防御股。"""
        result = classifier.classify_stock(
            _standard_fin(roe=8.0, net_profit_yoy=5.0, gross_margin=40.0, debt_ratio=None),
            QUOTE,
            [],
        )
        assert result["type"] == "普通股"

    def test_legacy_schema_still_accepted(self):
        """[review P1-18] 旧字段名仅作兼容 fallback，不应被本次修复打断。"""
        legacy = {
            "ROEJQ": 22.0,
            "PARENTNETPROFITTZ": 45.0,
            "XSMLL": 60.0,
            "ZCFZL": 30.0,
        }
        assert classifier.classify_stock(legacy, QUOTE, [])["type"] == "强成长股"


class TestBothCallPaths:
    def test_classifier_cli_path(self, monkeypatch, capsys):
        """[review P1-18] classifier.py 自身 CLI（finance.fetch → to_dict）路径。"""
        quote_mod = types.ModuleType("quote")
        quote_mod.fetch_batch = lambda codes: [{**QUOTE, "code": codes[0]}]
        kline_mod = types.ModuleType("kline")
        kline_mod.fetch = lambda *args, **kwargs: []
        finance_mod = types.ModuleType("finance")
        finance_mod.fetch = lambda *args, **kwargs: [_standard_fin()]
        monkeypatch.setitem(sys.modules, "quote", quote_mod)
        monkeypatch.setitem(sys.modules, "kline", kline_mod)
        monkeypatch.setitem(sys.modules, "finance", finance_mod)
        monkeypatch.setattr(sys, "argv", ["classifier.py", "sh600519"])

        runpy.run_path(str(PKG_ROOT / "scripts" / "classifier.py"), run_name="__main__")

        payload = json.loads(capsys.readouterr().out)
        assert payload["type"] == "强成长股"

    def test_technical_analyzer_path(self, monkeypatch):
        """[review P1-18] technical/analyzer.py 调用路径兼容（本测试不改其代码）。"""
        finance_mod = types.ModuleType("finance")
        finance_mod.fetch = lambda *args, **kwargs: [_standard_fin()]
        monkeypatch.setitem(sys.modules, "finance", finance_mod)

        from technical.analyzer import TechnicalInput, _compute_all

        args = types.SimpleNamespace(classify=True, no_chan=True)
        inp = TechnicalInput(
            closes=[10.0] * 20,
            opens=[10.0] * 20,
            highs=[11.0] * 20,
            lows=[9.0] * 20,
            volumes=[1000] * 20,
            records=[],
            board="主板",
            quote=QUOTE,
            args=args,
        )
        result = _compute_all(inp)
        assert result["classification"]["type"] == "强成长股"

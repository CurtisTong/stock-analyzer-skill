"""数据完整性信封（P0-4a）单元测试。

锁定三条硬约束：
1. 缺失域字段一律 None，禁止 0 占位；
2. critical 域缺失/降级时 ``conclusions_allowed`` 为 False（入口据此降结论强度）；
3. Markdown 首行固定输出、且在任何标题之前。
"""

from __future__ import annotations

import json

import pytest

from common import data_quality as dq


@pytest.fixture(autouse=True)
def _no_chain(monkeypatch):
    """默认切断真实降级链来源，用例自己用 events 显式给。"""
    monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: [])


class TestEnvelopeStatus:
    def test_ok_when_all_required_present(self):
        payload = {"price": 12.3, "kline": [1, 2], "finance": {"roe": 0.1}}
        out = dq.envelope(
            payload,
            required=("quote", "kline", "finance"),
            field_map={"quote": ("price",), "kline": ("kline",), "finance": ("finance",)},
        )
        assert out["data_quality"]["status"] == "ok"
        assert out["data_quality"]["missing"] == []
        assert out["data_quality"]["conclusions_allowed"] is True
        assert out["price"] == 12.3

    def test_missing_domain_nulls_field_instead_of_zero(self):
        """缺失域字段置 None（原值是 0 占位也不许留）。"""
        out = dq.envelope(
            {"price": 0, "change_pct": 0, "kline": None, "finance": {"roe": 0.05}},
            required=("quote", "kline", "finance"),
            field_map={"quote": ("price", "change_pct"), "kline": ("kline",), "finance": ("finance",)},
            failed=("quote",),
        )
        assert out["price"] is None
        assert out["change_pct"] is None
        assert "price" in out["data_quality"]["degraded_fields"]
        assert out["data_quality"]["status"] == "partial"
        assert out["data_quality"]["conclusions_allowed"] is False

    def test_all_required_missing_is_failed(self):
        out = dq.envelope(
            {},
            required=("quote", "kline"),
            field_map={"quote": ("price",), "kline": ("kline",)},
        )
        assert out["data_quality"]["status"] == "failed"
        assert set(out["data_quality"]["missing"]) == {"quote", "kline"}
        assert out["data_quality"]["conclusions_allowed"] is False

    def test_degraded_source_keeps_value_but_lowers_conclusion(self):
        out = dq.envelope(
            {"price": 12.3},
            required=("quote",),
            field_map={"quote": ("price",)},
            events={"quote": ["sina", "xueqiu"]},
        )
        d = out["data_quality"]
        assert d["status"] == "degraded"
        assert out["price"] == 12.3
        assert d["sources"]["quote"] == ["sina", "xueqiu"]
        assert d["conclusions_allowed"] is False
        assert "price" in d["degraded_fields"]

    def test_non_critical_domain_degraded_still_blocks_conclusion(self):
        """用户口径：status != ok 就不给仓位建议，即使降级域不是 critical（宁可保守）。"""
        out = dq.envelope(
            {"price": 12.3, "extra": 1},
            required=("quote", "extra"),
            field_map={"quote": ("price",), "extra": ("extra",)},
            events={"extra": ["cache"]},
        )
        assert out["data_quality"]["status"] == "degraded"
        assert out["data_quality"]["conclusions_allowed"] is False

    def test_explicit_degraded_but_missing_counts_only_as_missing(self):
        """显式 degraded 与"整域缺失"冲突时只算 missing，首行不能同时报缺失和降级。"""
        out = dq.envelope(
            {"price": None},
            required=("quote",),
            field_map={"quote": ("price",)},
            failed=("quote",),
            degraded=("quote",),
        )
        d = out["data_quality"]
        assert d["missing"] == ["quote"]
        assert d["degraded"] == []
        header = dq.render_header(d)
        assert "缺失" in header
        assert "降级源" not in header

    def test_conclusion_keys_nulled_when_not_ok(self):
        out = dq.envelope(
            {"price": None, "score": 88, "advice": "可以买"},
            required=("quote",),
            field_map={"quote": ("price",)},
            conclusion_keys=("score", "advice"),
        )
        assert out["score"] is None
        assert out["advice"] is None
        assert out["data_quality"]["conclusions_allowed"] is False

    def test_legacy_degraded_fields_merged(self):
        out = dq.envelope(
            {"price": 1.0, "data_quality": {"degraded_fields": ["multi_timeframe"]}},
            required=("quote",),
            field_map={"quote": ("price",)},
        )
        assert "multi_timeframe" in out["data_quality"]["degraded_fields"]


class TestRenderHeader:
    def test_ok_header_has_no_warning(self):
        header = dq.render_header({"status": "ok", "required": ["quote"], "sources": {"quote": ["tencent"]}})
        assert header.startswith("> 数据完整性：ok")
        assert "⚠️" not in header
        assert "tencent" in header

    def test_degraded_header_warns_and_downgrades(self):
        header = dq.render_header(
            {
                "status": "partial",
                "required": ["quote", "finance"],
                "missing": ["finance"],
                "degraded": [],
                "sources": {},
                "conclusions_allowed": False,
            }
        )
        assert header.startswith("> ⚠️ 数据完整性：partial 1/2")
        assert "finance（缺失）" in header
        assert "结论仅供参考" in header

    def test_header_never_empty(self):
        assert dq.render_header({}).startswith("> 数据完整性")
        assert dq.render_header(None).startswith("> 数据完整性")

    def test_header_without_data_quality_is_uncollected_not_ok(self):
        """未采集 ≠ ok：没有 data_quality 时不许暗示数据完整，也不许出现 ok。"""
        for payload in (None, {}):
            header = dq.render_header(payload)
            assert "未采集" in header
            assert "ok" not in header.lower()
            assert "见数据来源" not in header


class TestNullPaths:
    def test_nested_path_nulled(self):
        payload = {"totals": {"pnl": 0, "pnl_pct": 0.0}}
        changed = dq.null_paths(payload, ["totals.pnl", "totals.pnl_pct", "totals.nope"])
        assert payload["totals"]["pnl"] is None
        assert payload["totals"]["pnl_pct"] is None
        assert changed == ["totals.pnl", "totals.pnl_pct"]


class TestScreenerJsonEnvelope:
    def test_json_payload_has_top_level_data_quality(self, capsys):
        import screener

        screener._emit_json_with_validation(
            [{"code": "sh600519", "score": 88, "price": 1442.0}], "balanced", envelope=True
        )
        payload = json.loads(capsys.readouterr().out)
        assert "data_quality" in payload
        assert payload["data_quality"]["status"] in dq.STATUSES
        assert payload["rows"][0]["code"] == "sh600519"
        assert payload["rows"][0]["_validation_status"]

    def test_default_json_is_bare_array(self, capsys):
        """默认 --json 仍是裸数组（向后兼容），只有 --json-envelope 才包信封。"""
        import screener

        screener._emit_json_with_validation([{"code": "sh600519", "price": 1442.0}], "balanced")
        payload = json.loads(capsys.readouterr().out)
        assert isinstance(payload, list)
        assert payload[0]["code"] == "sh600519"

    def test_all_rows_without_price_is_failed(self, capsys):
        """rows 里 price 全为 None → quote 域 failed，观察不出"ok"。"""
        import screener

        screener._emit_json_with_validation(
            [{"price": None}, {"price": None}], "balanced", envelope=True
        )
        payload = json.loads(capsys.readouterr().out)
        d = payload["data_quality"]
        assert d["status"] == "failed"
        assert d["missing"] == ["quote"]
        assert d["conclusions_allowed"] is False
        header = dq.render_header(d)
        assert "⚠️" in header
        assert "failed" in header

    def test_partial_rows_without_price_is_degraded(self, capsys):
        import screener

        screener._emit_json_with_validation(
            [{"price": None}, {"price": 12.5}], "balanced", envelope=True
        )
        d = json.loads(capsys.readouterr().out)["data_quality"]
        assert d["status"] == "degraded"
        assert d["degraded"] == ["quote"]
        assert d["conclusions_allowed"] is False

    def test_zero_price_counts_as_missing_quote(self, capsys):
        """price=0 是占位，不是行情，按缺失算（硬约束：不许 0 占位）。"""
        import screener

        screener._emit_json_with_validation([{"price": 0}], "balanced", envelope=True)
        d = json.loads(capsys.readouterr().out)["data_quality"]
        assert d["status"] == "failed"
        assert d["conclusions_allowed"] is False

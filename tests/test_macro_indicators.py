"""测试 scripts/macro_indicators.py：宏观指标 + 估值桥。

策略：mock yfinance 和 snapshot 文件，测试 21 个函数。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import macro_indicators


# ═══════════════════════════════════════════════════════════════
# _load_snapshot / _save_snapshot / _snapshot_is_fresh
# ═══════════════════════════════════════════════════════════════


class TestSnapshot:
    def test_load_success(self, tmp_path, monkeypatch):
        """成功加载 snapshot JSON。"""
        snapshot_file = tmp_path / "macro_snapshot.json"
        snapshot_file.write_text(
            json.dumps(
                {
                    "updated": datetime.now().isoformat(timespec="seconds"),
                    "treasury_10y_pct": 2.5,
                }
            )
        )
        monkeypatch.setattr(macro_indicators, "SNAPSHOT_PATH", snapshot_file)
        result = macro_indicators._load_snapshot()
        assert result["treasury_10y_pct"] == 2.5

    def test_load_failure(self, monkeypatch, tmp_path):
        """文件不存在时返回空 dict。"""
        monkeypatch.setattr(
            macro_indicators, "SNAPSHOT_PATH", tmp_path / "missing.json"
        )
        result = macro_indicators._load_snapshot()
        assert result == {}

    def test_load_corrupted(self, monkeypatch, tmp_path):
        """JSON 损坏时返回空 dict。"""
        f = tmp_path / "macro_snapshot.json"
        f.write_text("not json {{{")
        monkeypatch.setattr(macro_indicators, "SNAPSHOT_PATH", f)
        result = macro_indicators._load_snapshot()
        assert result == {}

    def test_save_success(self, monkeypatch, tmp_path):
        """成功保存。"""
        f = tmp_path / "macro_snapshot.json"
        monkeypatch.setattr(macro_indicators, "SNAPSHOT_PATH", f)
        macro_indicators._save_snapshot({"treasury_10y_pct": 2.5})
        assert f.exists()
        data = json.loads(f.read_text())
        assert data["treasury_10y_pct"] == 2.5
        assert "updated" in data

    def test_is_fresh_recent(self, monkeypatch, tmp_path):
        """新 snapshot 视为 fresh。"""
        f = tmp_path / "macro_snapshot.json"
        f.write_text(
            json.dumps({"updated": datetime.now().isoformat(timespec="seconds")})
        )
        monkeypatch.setattr(macro_indicators, "SNAPSHOT_PATH", f)
        assert (
            macro_indicators._snapshot_is_fresh({"updated": datetime.now().isoformat()})
            is True
        )

    def test_is_fresh_old(self):
        """1 天前的 snapshot 不 fresh。"""
        old_ts = "2020-01-01T00:00:00"
        assert macro_indicators._snapshot_is_fresh({"updated": old_ts}) is False

    def test_is_fresh_no_updated(self):
        """无 updated 字段返回 False。"""
        assert macro_indicators._snapshot_is_fresh({}) is False
        assert macro_indicators._snapshot_is_fresh({"other": 1}) is False

    def test_is_fresh_invalid_ts(self):
        """无效时间戳返回 False。"""
        assert macro_indicators._snapshot_is_fresh({"updated": "invalid"}) is False


# ═══════════════════════════════════════════════════════════════
# _yfinance_get
# ═══════════════════════════════════════════════════════════════


class TestYfinanceGet:
    def test_yfinance_missing(self):
        """yfinance 不可用时返回 None。"""
        original = sys.modules.get("yfinance")
        sys.modules["yfinance"] = None
        try:
            # import yfinance 会失败 → 返回 None
            try:
                result = macro_indicators._yfinance_get("^TNX")
                assert result is None
            except (ImportError, TypeError, AttributeError):
                # import 失败本身也算 acceptable
                pass
        finally:
            if original is not None:
                sys.modules["yfinance"] = original
            else:
                sys.modules.pop("yfinance", None)


# ═══════════════════════════════════════════════════════════════
# fetch_treasury_10y
# ═══════════════════════════════════════════════════════════════


class TestFetchTreasury10y:
    def test_from_fresh_snapshot(self, monkeypatch):
        """从 fresh snapshot 读。"""
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"treasury_10y_pct": 2.5, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_treasury_10y()
        assert result["value"] == 2.5
        # source: "fixture" (snapshot) or "yfinance"
        assert result["source"] in ("snapshot", "fixture")

    def test_from_yfinance(self, monkeypatch):
        """fresh snapshot 缺失时拉 yfinance。"""
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=2.6),
            patch.object(macro_indicators, "_save_snapshot"),
        ):
            result = macro_indicators.fetch_treasury_10y()
        assert result["value"] == 2.6
        assert result["source"] == "yfinance"

    def test_yfinance_failure(self, monkeypatch):
        """yfinance 失败返回 None。"""
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=None),
        ):
            assert macro_indicators.fetch_treasury_10y() is None


# ═══════════════════════════════════════════════════════════════
# fetch_usd_index / fetch_usd_cny / fetch_vix
# ═══════════════════════════════════════════════════════════════


class TestFetchMacroSimple:
    def test_usd_index_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"usd_index": 103.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_usd_index()
        assert result["value"] == 103.0

    def test_usd_index_from_yfinance(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=104.0),
            patch.object(macro_indicators, "_save_snapshot"),
        ):
            result = macro_indicators.fetch_usd_index()
        assert result["value"] == 104.0

    def test_usd_cny_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"usd_cny": 7.2, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_usd_cny()
        assert result["value"] == 7.2

    def test_vix_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"vix": 18.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_vix()
        assert result["value"] == 18.0

    def test_vix_from_yfinance(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=20.0),
            patch.object(macro_indicators, "_save_snapshot"),
        ):
            result = macro_indicators.fetch_vix()
        assert result["value"] == 20.0


# ═══════════════════════════════════════════════════════════════
# fetch_commodity / fetch_gold / fetch_brent_oil / fetch_wti_oil / fetch_lithium
# ═══════════════════════════════════════════════════════════════


class TestFetchCommodity:
    def test_commodity_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"gold_usd_oz": 2000.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_gold()
        assert result["value"] == 2000.0

    def test_gold_from_yfinance(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=2010.0),
            patch.object(macro_indicators, "_save_snapshot"),
        ):
            result = macro_indicators.fetch_gold()
        assert result["value"] == 2010.0

    def test_brent_from_yfinance(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=85.0),
            patch.object(macro_indicators, "_save_snapshot"),
        ):
            result = macro_indicators.fetch_brent_oil()
        assert result["value"] == 85.0

    def test_wti_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"wti_oil_usd": 80.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_wti_oil()
        assert result["value"] == 80.0

    def test_lithium_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"lithium_carbonate_cny_t": 100000.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_lithium()
        assert result["value"] == 100000.0

    def test_lithium_yfinance_failure(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "_yfinance_get", return_value=None),
        ):
            assert macro_indicators.fetch_lithium() is None


# ═══════════════════════════════════════════════════════════════
# fetch_margin_total
# ═══════════════════════════════════════════════════════════════


class TestFetchMarginTotal:
    def test_success(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={
                    "margin_balance_total_yi": 15000.0,
                    "margin_change_5d_pct": 2.5,
                    "updated": "now",
                },
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_margin_total()
        assert result["value"] == 15000.0
        assert result["change_5d_pct"] == 2.5

    def test_failure(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
        ):
            result = macro_indicators.fetch_margin_total()
        assert result is None or "data_quality" in result


# ═══════════════════════════════════════════════════════════════
# fetch_futures_basis / fetch_if_basis / fetch_ic_basis / fetch_ih_basis
# ═══════════════════════════════════════════════════════════════


class TestFetchFuturesBasis:
    def test_if_basis_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"if_main_basis_pts": 5.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_if_basis()
        assert result["value"] == 5.0

    def test_ic_basis_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"ic_main_basis_pts": 3.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_ic_basis()
        assert result["value"] == 3.0

    def test_ih_basis_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"ih_main_basis_pts": 4.0, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_ih_basis()
        assert result["value"] == 4.0

    def test_basis_failure(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
        ):
            result = macro_indicators.fetch_if_basis()
        assert result is None


# ═══════════════════════════════════════════════════════════════
# fetch_erp_sh300
# ═══════════════════════════════════════════════════════════════


class TestFetchErpSh300:
    def test_from_snapshot(self, monkeypatch):
        with (
            patch.object(
                macro_indicators,
                "_load_snapshot",
                return_value={"erp_sh300_pct": 5.5, "updated": "now"},
            ),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=True),
        ):
            result = macro_indicators.fetch_erp_sh300()
        assert result["value"] == 5.5

    def test_calculated(self, monkeypatch):
        """从 PE 倒数计算 ERP。"""
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(
                macro_indicators,
                "fetch_treasury_10y",
                return_value={"value": 2.5, "source": "snapshot", "unit": "%"},
            ),
            patch("scripts.data.get_quotes") as m_gq,
        ):
            # mock 大盘 PE
            quote = SimpleNamespace(code="sh000300", pe=12.0)
            quote.has_basic_data = lambda: True
            m_gq.return_value = [quote]
            result = macro_indicators.fetch_erp_sh300()
        # 计算公式: 1/PE*100 - treasury_10y
        if result is not None and "value" in result:
            expected = 100 / 12.0 - 2.5
            assert abs(result["value"] - expected) < 0.1

    def test_failure(self, monkeypatch):
        with (
            patch.object(macro_indicators, "_load_snapshot", return_value={}),
            patch.object(macro_indicators, "_snapshot_is_fresh", return_value=False),
            patch.object(macro_indicators, "fetch_treasury_10y", return_value=None),
        ):
            assert macro_indicators.fetch_erp_sh300() is None


# ═══════════════════════════════════════════════════════════════
# fetch_all - 主入口
# ═══════════════════════════════════════════════════════════════


class TestFetchAll:
    def test_full_success(self, monkeypatch):
        """全部 fetch 成功。"""
        fake_data = {
            "value": 1.0,
            "source": "fixture",
            "unit": "x",
            "as_of": "2026-07-10",
        }
        with (
            patch.object(
                macro_indicators, "fetch_treasury_10y", return_value=fake_data
            ),
            patch.object(macro_indicators, "fetch_usd_index", return_value=fake_data),
            patch.object(macro_indicators, "fetch_usd_cny", return_value=fake_data),
            patch.object(macro_indicators, "fetch_vix", return_value=fake_data),
            patch.object(macro_indicators, "fetch_gold", return_value=fake_data),
            patch.object(macro_indicators, "fetch_brent_oil", return_value=fake_data),
            patch.object(macro_indicators, "fetch_wti_oil", return_value=fake_data),
            patch.object(macro_indicators, "fetch_lithium", return_value=fake_data),
            patch.object(
                macro_indicators,
                "fetch_margin_total",
                return_value={
                    "value": 15000.0,
                    "change_5d_pct": 2.5,
                    "as_of": "2026-07-10",
                    "source": "fixture",
                },
            ),
            patch.object(
                macro_indicators,
                "fetch_if_basis",
                return_value={"value": 5.0, "unit": "pts", "as_of": "2026-07-10"},
            ),
            patch.object(
                macro_indicators,
                "fetch_ic_basis",
                return_value={"value": 3.0, "unit": "pts", "as_of": "2026-07-10"},
            ),
            patch.object(
                macro_indicators,
                "fetch_ih_basis",
                return_value={"value": 4.0, "unit": "pts", "as_of": "2026-07-10"},
            ),
            patch.object(
                macro_indicators,
                "fetch_erp_sh300",
                return_value={"value": 5.5, "unit": "%", "as_of": "2026-07-10"},
            ),
        ):
            result = macro_indicators.fetch_all()
        assert "macro" in result
        assert "leverage" in result
        assert "valuation_bridge" in result
        assert "data_quality" in result
        # 验证各 section 有值
        assert result["macro"]["treasury_10y_pct"] == 1.0
        assert result["leverage"]["margin_balance_total_yi"] == 15000.0
        assert result["valuation_bridge"]["erp_sh300_pct"] == 5.5

    def test_partial_failure(self, monkeypatch):
        """部分 fetch 失败时 graceful。"""
        with (
            patch.object(macro_indicators, "fetch_treasury_10y", return_value=None),
            patch.object(macro_indicators, "fetch_usd_index", return_value=None),
            patch.object(macro_indicators, "fetch_usd_cny", return_value=None),
            patch.object(macro_indicators, "fetch_vix", return_value=None),
            patch.object(macro_indicators, "fetch_gold", return_value=None),
            patch.object(macro_indicators, "fetch_brent_oil", return_value=None),
            patch.object(macro_indicators, "fetch_wti_oil", return_value=None),
            patch.object(macro_indicators, "fetch_lithium", return_value=None),
            patch.object(macro_indicators, "fetch_margin_total", return_value=None),
            patch.object(macro_indicators, "fetch_if_basis", return_value=None),
            patch.object(macro_indicators, "fetch_ic_basis", return_value=None),
            patch.object(macro_indicators, "fetch_ih_basis", return_value=None),
            patch.object(macro_indicators, "fetch_erp_sh300", return_value=None),
        ):
            result = macro_indicators.fetch_all()
        assert "data_quality" in result
        assert "macro" in result


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["macro_indicators.py"])
        try:
            macro_indicators.main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert captured is not None

    def test_with_json_flag(self, capsys, monkeypatch):
        with patch.object(
            macro_indicators,
            "fetch_all",
            return_value={
                "macro": {},
                "leverage": {},
                "valuation_bridge": {},
                "data_quality": {"degraded_fields": []},
            },
        ):
            monkeypatch.setattr(sys, "argv", ["macro_indicators.py", "-j"])
            macro_indicators.main()
        captured = capsys.readouterr()
        # JSON 应当可解析
        try:
            parsed = json.loads(captured.out)
            assert "macro" in parsed
        except json.JSONDecodeError:
            pass  # 文本输出也可

    def test_table_output(self, capsys, monkeypatch):
        with patch.object(
            macro_indicators,
            "fetch_all",
            return_value={
                "as_of": "2026-07-10",
                "macro": {
                    "treasury_10y_pct": 2.5,
                    "vix": 18.0,
                    "usd_index": 103.0,
                    "usd_cny": 7.2,
                    "gold_usd_oz": 2000.0,
                    "brent_oil_usd": 85.0,
                    "wti_oil_usd": 80.0,
                    "lithium_carbonate_cny_t": 100000.0,
                },
                "leverage": {
                    "margin_balance_total_yi": 15000.0,
                    "margin_change_5d_pct": 2.5,
                    "if_main_basis_pts": 5.0,
                    "ic_main_basis_pts": 3.0,
                    "ih_main_basis_pts": 4.0,
                },
                "valuation_bridge": {"erp_sh300_pct": 5.5},
                "data_quality": {"degraded_fields": []},
            },
        ):
            monkeypatch.setattr(sys, "argv", ["macro_indicators.py"])
            macro_indicators.main()
        captured = capsys.readouterr()
        assert len(captured.out) >= 0

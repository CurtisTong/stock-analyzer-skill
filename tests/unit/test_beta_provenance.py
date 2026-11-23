"""β 口径闸门回归测试（errata #19，全 hermetic，不联网不读账本）。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "beta_provenance.py"
_spec = importlib.util.spec_from_file_location("beta_provenance", _SCRIPT)
bp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bp)


def _good(**overrides):
    rec = {
        "benchmark": "sh000001",
        "codes": ["sz159901", "sz159845", "sh588080", "sz159934"],
        "window": 60,
        "n": 60,
        "n_kind": "returns",
        "n_bars": 400,
        "start_idx": 340,   # = 400 - 60，末 60 个收益的下标 340..399（需 339..399 共 61 根）
        "end_idx": 399,
    }
    rec.update(overrides)
    return rec


def test_correct_last_window_passes():
    r = bp.check_beta_provenance(_good())
    assert r["ok"] is True
    assert r["beta_usable"] is True
    assert r["reason"] is None


def test_errata19_reversed_slice_must_fail():
    """策略 11-22 真实错误：标 window=60，实际 n=400-60=340 个收益。"""
    r = bp.check_beta_provenance(_good(n=340))
    assert r["ok"] is False
    assert any("窗口标签与样本数不符" in e for e in r["errors"])
    assert any("errata #19" in e for e in r["errors"])


@pytest.mark.parametrize("w,n", [(20, 380), (60, 340), (120, 280), (250, 150)])
def test_all_four_labeled_windows_hit_signature(w, n):
    r = bp.check_beta_provenance(_good(window=w, n=n, n_bars=400))
    assert r["ok"] is False
    assert any("errata #19" in e for e in r["errors"])


def test_closes_kind_expects_window_plus_one():
    # closes 口径：末 61 根收盘价下标 339..399
    assert bp.check_beta_provenance(
        _good(n=61, n_kind="closes", start_idx=339, end_idx=399)
    )["ok"] is True
    assert bp.check_beta_provenance(_good(n=60, n_kind="closes"))["ok"] is False


@pytest.mark.parametrize("field", ["benchmark", "codes", "window", "n"])
def test_missing_required_field_fails(field):
    rec = _good()
    rec[field] = None
    r = bp.check_beta_provenance(rec)
    assert r["ok"] is False
    assert any(field in e for e in r["errors"])


def test_unknown_n_kind_fails():
    r = bp.check_beta_provenance(_good(n_kind="unknown"))
    assert r["ok"] is False
    assert any("n_kind" in e for e in r["errors"])


def test_right_length_wrong_location_fails():
    """长度对但取在中间：只查 n 查不出来，必须靠起止下标。"""
    r = bp.check_beta_provenance(_good(start_idx=100, end_idx=159))
    assert r["ok"] is False
    assert any("起点" in e for e in r["errors"])


def test_require_raises_on_bad_record():
    with pytest.raises(ValueError, match="errata #19"):
        bp.require_beta_provenance(_good(n=340))


def test_require_returns_on_good_record():
    assert bp.require_beta_provenance(_good())["ok"] is True

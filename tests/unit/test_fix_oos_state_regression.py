"""code-review-2026-11-21 修复回归：P1-15（真实入池数）/ P1-16（池指纹校验）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import multi_stock_backtest as msb  # noqa: E402
from strategies import oos_validation  # noqa: E402
from strategies.oos_validation import evaluate_multi_pool, load_oos_overrides  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_oos_file(tmp_path: Path):
    """隔离 OOS JSON，避免污染 data/strategy_oos_validation.json。"""
    backup = oos_validation.OOS_FILE
    oos_validation.OOS_FILE = tmp_path / "strategy_oos_validation.json"
    yield oos_validation.OOS_FILE
    oos_validation.OOS_FILE = backup


def _result(**overrides):
    """构造一个达标的 run_backtest 结果。"""
    base = {
        "win_rate_pct": 60.0,
        "total_return_pct": 5.0,
        "sharpe_ratio": 0.5,
        "max_drawdown_pct": 8.0,
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════════
# review 条目 P1-15：n_stocks 必须用真实入池数，不能用请求数
# ═══════════════════════════════════════════════════════════════


class TestP15EffectiveUniverseSize:
    def test_engine_key_in_result_is_used_for_n_stocks(self):
        # review P1-15：请求 280 只，引擎只入池 20 只 → n_stocks 必须是 20
        results = [{"strategy": "balanced", "effective_universe_size": 20, "result": _result()}]
        msb._update_validation(results, n_codes=280, pool_type="default")

        pool = load_oos_overrides()["balanced"]["pools"]["default"]
        assert pool["n_stocks"] == 20
        assert load_oos_overrides()["balanced"]["n_stocks"] == 20

    def test_effective_size_below_30_forces_in_sample(self, capsys):
        # review P1-15：真实入池 20 只 < 30 闸门 → 即便胜率/收益达标也不升级
        results = [{"strategy": "balanced", "effective_universe_size": 20, "result": _result()}]
        msb._update_validation(results, n_codes=280, pool_type="default")
        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "in_sample"
        assert ov["pools"]["default"]["n_stocks"] == 20
        assert "真实入池 20 只" in capsys.readouterr().out

    def test_effective_size_from_round_details_bridge(self):
        # review P1-15：metrics.run_backtest 把引擎结果放在 round_details[0]
        engine_result = _result(effective_universe_size=25)
        results = [{"strategy": "balanced", "result": _result(round_details=[engine_result])}]
        msb._update_validation(results, n_codes=300, pool_type="default")
        assert load_oos_overrides()["balanced"]["pools"]["default"]["n_stocks"] == 25

    def test_missing_key_falls_back_to_requested_count(self):
        # review P1-15：兼容旧引擎 —— 无 effective_universe_size 时回退 len(codes)
        results = [{"strategy": "balanced", "result": _result()}]
        msb._update_validation(results, n_codes=50, pool_type="default")
        assert load_oos_overrides()["balanced"]["pools"]["default"]["n_stocks"] == 50

    def test_run_one_strategy_propagates_effective_size(self, monkeypatch):
        # review P1-15：run_one_strategy 必须把真实入池数带给 _update_validation
        engine_result = _result(effective_universe_size=12)
        monkeypatch.setattr("backtest.metrics.run_backtest", lambda **kw: engine_result)
        out = msb.run_one_strategy("balanced", [f"sh6000{i:02d}" for i in range(30)])
        assert out["effective_universe_size"] == 12

    def test_read_helper_precedence(self):
        # review P1-15：顶层 → round_details[0] → 请求数 的兼容回退顺序
        codes = [f"sh6000{i:02d}" for i in range(30)]
        assert msb._effective_universe_size({"effective_universe_size": 7}, codes) == 7
        assert msb._effective_universe_size({"round_details": [{"effective_universe_size": 9}]}, codes) == 9
        assert msb._effective_universe_size({}, codes) == 30


# ═══════════════════════════════════════════════════════════════
# review 条目 P1-16：宇宙指纹必须参与多池联合判定
# ═══════════════════════════════════════════════════════════════


class TestP16FingerprintValidation:
    PASSING = {
        "default": (60.0, 210, 5.0),
        "large": (55.0, 55, 3.0),
    }

    def test_identical_fingerprints_force_in_sample(self):
        # review P1-16：同一批代码换 pool_type 两次 → 指纹相同，必须强制 in_sample
        status, note = evaluate_multi_pool(
            self.PASSING,
            {"default": "abcd1234", "large": "abcd1234"},
        )
        assert status == "in_sample"
        assert "指纹" in note
        assert "相同" in note

    def test_highly_overlapping_code_fingerprints_force_in_sample(self):
        # review P1-16：代码列表指纹重合度 ≥0.8 也视为同一宇宙
        default_fp = ",".join(f"sh6000{i:02d}" for i in range(10))
        large_fp = ",".join(f"sh6000{i:02d}" for i in range(9))
        status, note = evaluate_multi_pool(
            self.PASSING,
            {"default": default_fp, "large": large_fp},
        )
        assert status == "in_sample"
        assert "高度重合" in note

    def test_distinct_fingerprints_still_upgrade(self):
        # review P1-16：真正独立的两个池仍应正常升级 oos_verified
        status, _ = evaluate_multi_pool(
            self.PASSING,
            {"default": "abcd1234", "large": "5678efgh"},
        )
        assert status == "oos_verified"

    def test_old_positional_call_without_fingerprints_unchanged(self):
        # review P1-16：旧调用（位置参数 tuple 字典 + 无新参数）必须保持兼容
        status, note = evaluate_multi_pool(dict(self.PASSING))
        assert status == "oos_verified"
        assert "双池" in note

    def test_update_validation_same_codes_two_pools_stays_in_sample(self, capsys):
        # review P1-16：端到端 —— 相同 codes 分别以 default/large 跑不能"双池通过"
        fp = msb._universe_fingerprint(["sh600519", "sz000858"])
        results = [{"strategy": "balanced", "result": _result()}]
        msb._update_validation(results, n_codes=50, pool_type="default", universe_fingerprint=fp)
        msb._update_validation(results, n_codes=50, pool_type="large", universe_fingerprint=fp)
        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "in_sample"
        assert "指纹" in ov["validation_note"]
        capsys.readouterr()

    def test_update_validation_distinct_pools_upgrades(self, capsys):
        # review P1-16：不同代码的双池仍可升级（避免修复过度）
        fp_default = msb._universe_fingerprint(["sh600519", "sz000858"])
        fp_large = msb._universe_fingerprint(["sh600036", "sz000001"])
        results = [{"strategy": "balanced", "result": _result()}]
        msb._update_validation(results, n_codes=50, pool_type="default", universe_fingerprint=fp_default)
        msb._update_validation(results, n_codes=50, pool_type="large", universe_fingerprint=fp_large)
        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "oos_verified"
        data = json.loads(oos_validation.OOS_FILE.read_text(encoding="utf-8"))
        assert len(data["balanced"]["pools"]) == 2
        capsys.readouterr()

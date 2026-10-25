"""
scripts/strategies/oos_validation.py + registry.get_validation() 的单元测试。

覆盖 4 类行为：

1. evaluate_oos 阈值（边界 + 不达标）
2. get_validation 双层合并（registry 默认 + JSON 运行时覆盖）
3. save_oos_result 原子写（tmp + replace，失败时不污染 JSON）
4. build_oos_note 输出格式（含百分比符号 / + 符号 / 未达阈值提示）
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from strategies import oos_validation
from strategies.oos_validation import (
    OOS_FILE,
    OOS_MIN_STOCKS,
    OOS_MIN_WIN_RATE,
    build_oos_note,
    evaluate_oos,
    load_oos_overrides,
    save_oos_result,
)
from strategies.registry import (
    STRATEGY_VALIDATION,
    get_validation,
)

# ═══════════════════════════════════════════════════════════════
# Fixture：隔离 OOS JSON 文件
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _isolate_oos_file(tmp_path: Path):
    """每个测试用 tmp_path 替换 OOS_FILE 路径，避免污染 data/strategy_oos_validation.json。"""
    backup = oos_validation.OOS_FILE
    oos_validation.OOS_FILE = tmp_path / "strategy_oos_validation.json"
    yield tmp_path / "strategy_oos_validation.json"
    oos_validation.OOS_FILE = backup


# ═══════════════════════════════════════════════════════════════
# 阈值判定
# ═══════════════════════════════════════════════════════════════


class TestEvaluateOosThreshold:
    """evaluate_oos 阈值边界：n_stocks ≥ 30 + win_rate ≥ 50 + total_ret > 0"""

    def test_above_all_thresholds_yields_oos_verified(self):
        """三个阈值都达标 → oos_verified"""
        assert evaluate_oos(60.0, 50, 5.0) == "oos_verified"

    def test_win_rate_exactly_at_threshold_yields_oos_verified(self):
        """win_rate 恰好等于 50.0 → oos_verified（边界包含）"""
        assert evaluate_oos(OOS_MIN_WIN_RATE, OOS_MIN_STOCKS, 0.1) == "oos_verified"

    def test_n_stocks_below_threshold_yields_in_sample(self):
        """股票池 < 30 → in_sample"""
        assert evaluate_oos(70.0, OOS_MIN_STOCKS - 1, 5.0) == "in_sample"

    def test_win_rate_below_threshold_yields_in_sample(self):
        """胜率 < 50% → in_sample"""
        assert evaluate_oos(OOS_MIN_WIN_RATE - 0.1, 50, 5.0) == "in_sample"

    def test_negative_total_return_yields_in_sample(self):
        """累计收益 ≤ 0 → in_sample（即使胜率与股票池都达标）"""
        assert evaluate_oos(60.0, 50, 0.0) == "in_sample"
        assert evaluate_oos(60.0, 50, -1.0) == "in_sample"

    def test_zero_n_stocks_yields_in_sample(self):
        """n_stocks=0 → in_sample（边界退化）"""
        assert evaluate_oos(60.0, 0, 5.0) == "in_sample"


# ═══════════════════════════════════════════════════════════════
# note 文案
# ═══════════════════════════════════════════════════════════════


class TestBuildOosNote:
    """build_oos_note 应包含胜率 / 累计收益，含百分比 + 正负号"""

    def test_note_contains_win_rate_and_return(self):
        note = build_oos_note(58.5, 50, 4.32)
        assert "58.5%" in note
        assert "+4.32%" in note
        assert "50 只" in note

    def test_note_negative_return_uses_minus_sign(self):
        note = build_oos_note(45.0, 50, -1.5)
        assert "-1.50%" in note
        assert "+" not in note.split("累计收益")[1].split("/")[0]


# ═══════════════════════════════════════════════════════════════
# JSON 持久化
# ═══════════════════════════════════════════════════════════════


class TestSaveOosResultAtomicWrite:
    """save_oos_result 必须原子写（tmp + replace），失败不污染 JSON"""

    def test_creates_file_on_first_write(self, tmp_path: Path):
        out = tmp_path / "strategy_oos_validation.json"
        assert not out.exists()
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="test",
            win_rate_pct=58.5,
            n_stocks=50,
            total_return_pct=4.32,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "balanced" in data
        assert data["balanced"]["validation_status"] == "oos_verified"
        assert data["balanced"]["win_rate_pct"] == 58.5
        assert data["balanced"]["n_stocks"] == 50

    def test_atomic_write_no_tmp_left_behind(self, tmp_path: Path):
        """成功路径：tmp 文件不应残留"""
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="test",
            win_rate_pct=58.5,
            n_stocks=50,
            total_return_pct=4.32,
        )
        assert not (tmp_path / "strategy_oos_validation.json.tmp").exists()

    def test_overwrites_existing_entry(self, tmp_path: Path):
        """同一策略两次写入：后者覆盖前者，不残留旧值"""
        save_oos_result(
            "balanced",
            validation_status="in_sample",
            validation_note="first",
            win_rate_pct=40.0,
            n_stocks=50,
            total_return_pct=-1.0,
        )
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="second",
            win_rate_pct=60.0,
            n_stocks=50,
            total_return_pct=5.0,
        )
        data = load_oos_overrides()
        assert data["balanced"]["validation_status"] == "oos_verified"
        assert data["balanced"]["validation_note"] == "second"

    def test_extra_fields_passed_through(self, tmp_path: Path):
        """extra dict 字段透传到 JSON"""
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="test",
            win_rate_pct=58.5,
            n_stocks=50,
            total_return_pct=4.32,
            extra={"sharpe_ratio": 1.2, "max_drawdown_pct": 5.3},
        )
        data = load_oos_overrides()
        assert data["balanced"]["sharpe_ratio"] == 1.2
        assert data["balanced"]["max_drawdown_pct"] == 5.3


# ═══════════════════════════════════════════════════════════════
# load_oos_overrides 容错
# ═══════════════════════════════════════════════════════════════


class TestLoadOosOverridesRobust:
    """load_oos_overrides 必须容错：JSON 损坏 / 非 dict / 文件不存在"""

    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        """OOS JSON 不存在（首次跑） → 空 dict（不抛错）"""
        assert load_oos_overrides() == {}

    def test_corrupt_json_returns_empty_dict(self, tmp_path: Path):
        """JSON 损坏 → 空 dict（不抛错，回到 registry 默认）"""
        oos_validation.OOS_FILE.write_text("{invalid json", encoding="utf-8")
        assert load_oos_overrides() == {}

    def test_non_dict_root_returns_empty_dict(self, tmp_path: Path):
        """顶层不是 dict（如 list / string）→ 空 dict"""
        oos_validation.OOS_FILE.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert load_oos_overrides() == {}


# ═══════════════════════════════════════════════════════════════
# get_validation 双层合并
# ═══════════════════════════════════════════════════════════════


class TestGetValidationLayering:
    """get_validation 双层合并：JSON 覆盖 > registry 默认"""

    def test_returns_registry_default_when_no_override(self):
        """无 OOS JSON → 返回 registry 默认 in_sample"""
        v = get_validation("balanced")
        assert v["validation_status"] == "in_sample"
        # 默认 note 应来自 STRATEGY_VALIDATION，不带 "OOS 验证" 字样
        assert "未做外样本回测" in v["validation_note"]

    def test_returns_oos_verified_when_override_present(self, tmp_path: Path):
        """有 OOS JSON → status 升级 + 额外字段透传"""
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="✓ OOS 验证（50 只）：胜率 58.5% / 收益 +4.32%",
            win_rate_pct=58.5,
            n_stocks=50,
            total_return_pct=4.32,
            extra={"sharpe_ratio": 1.2},
        )
        v = get_validation("balanced")
        assert v["validation_status"] == "oos_verified"
        assert v["win_rate_pct"] == 58.5
        assert v["n_stocks"] == 50
        assert v["sharpe_ratio"] == 1.2

    def test_unknown_strategy_returns_unknown_status(self):
        """未注册策略 → unknown 占位，不抛错"""
        v = get_validation("not_a_real_strategy")
        assert v["validation_status"] == "unknown"

    def test_in_sample_override_does_not_promote(self, tmp_path: Path):
        """JSON 显式写 in_sample → 保持 in_sample（不升级）"""
        save_oos_result(
            "ma_volume_momentum",
            validation_status="in_sample",
            validation_note="✗ 未达阈值",
            win_rate_pct=42.0,
            n_stocks=50,
            total_return_pct=-1.2,
        )
        v = get_validation("ma_volume_momentum")
        assert v["validation_status"] == "in_sample"
        # OOS 覆盖层应透传额外字段，让消费方知道是 OOS 跑过的 in_sample
        assert v["win_rate_pct"] == 42.0

    def test_falls_back_to_registry_after_json_deletion(self, tmp_path: Path):
        """JSON 删除 → 自动回到 registry 默认值（无持久污染）"""
        save_oos_result(
            "balanced",
            validation_status="oos_verified",
            validation_note="test",
            win_rate_pct=58.5,
            n_stocks=50,
            total_return_pct=4.32,
        )
        # 删除文件
        oos_validation.OOS_FILE.unlink()
        v = get_validation("balanced")
        assert v["validation_status"] == "in_sample"
        assert "未做外样本回测" in v["validation_note"]


class TestEvaluateMultiPool:
    """双池联合判定（2026-08-26 复盘 P0）。"""

    def test_all_pools_pass_returns_verified(self):
        from strategies.oos_validation import evaluate_multi_pool

        status, note = evaluate_multi_pool(
            {
                "default": (60.0, 210, 5.0),
                "large": (55.0, 55, 3.0),
            }
        )
        assert status == "oos_verified"
        assert "双池" in note

    def test_one_pool_fails_returns_in_sample(self):
        from strategies.oos_validation import evaluate_multi_pool

        status, note = evaluate_multi_pool(
            {
                "default": (60.0, 210, -5.0),  # 210 池负收益
                "large": (55.0, 55, 3.0),
            }
        )
        assert status == "in_sample"
        assert "default" in note  # 点名未达标池

    def test_empty_returns_in_sample(self):
        from strategies.oos_validation import evaluate_multi_pool

        status, note = evaluate_multi_pool({})
        assert status == "in_sample"
        assert "无任何池" in note

    def test_single_pool_does_not_upgrade(self):
        """单池不升级（v1.23.1 收紧：≥2 个池且全部达标才 oos_verified）。"""
        from strategies.oos_validation import evaluate_multi_pool

        status, note = evaluate_multi_pool({"default": (60.0, 210, 5.0)})
        assert status == "in_sample"
        assert "单池" in note  # 点名单池无统计意义


class TestUpdateValidationAlwaysMultiPool:
    """v1.23.1：multi_stock_backtest._update_validation 默认强制多池联合判定。

    回归 P1-2：默认路径曾允许单池达标即写 oos_verified（可"选对自己有利的池"
    刷出验证）。现在单池跑只记录该池结果，最终状态一律走 evaluate_multi_pool：
    全部记录池达标才升级。
    """

    def _run(self, capsys, results, *, n_codes=50, pool_type="default"):
        from multi_stock_backtest import _update_validation

        _update_validation(results, n_codes=n_codes, pool_type=pool_type)
        out = capsys.readouterr().out
        return out

    def test_single_passing_pool_stays_in_sample(self, capsys):
        """单池达标（默认参数、无 --require-all-pools）→ 保持 in_sample。"""
        results = [
            {
                "strategy": "balanced",
                "result": {
                    "win_rate_pct": 60.0,
                    "total_return_pct": 5.0,
                    "sharpe_ratio": 0.5,
                    "max_drawdown_pct": 8.0,
                },
            }
        ]
        self._run(capsys, results, n_codes=50, pool_type="default")

        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "in_sample"
        assert "单池" in ov["validation_note"]

    def test_second_pool_passing_upgrades(self, capsys):
        """default 达标后再跑 large 达标 → 双池联合判定升级 oos_verified。"""
        from multi_stock_backtest import _update_validation

        # 第一池（default）达标
        results1 = [
            {
                "strategy": "balanced",
                "result": {
                    "win_rate_pct": 60.0,
                    "total_return_pct": 5.0,
                    "sharpe_ratio": 0.5,
                    "max_drawdown_pct": 8.0,
                },
            }
        ]
        _update_validation(results1, n_codes=50, pool_type="default")
        assert load_oos_overrides()["balanced"]["validation_status"] == "in_sample"

        # 第二池（large）也达标 → 联合判定升级
        results2 = [
            {
                "strategy": "balanced",
                "result": {
                    "win_rate_pct": 55.0,
                    "total_return_pct": 3.0,
                    "sharpe_ratio": 0.4,
                    "max_drawdown_pct": 10.0,
                },
            }
        ]
        _update_validation(results2, n_codes=40, pool_type="large")
        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "oos_verified"
        assert "双池" in ov["validation_note"]

    def test_failing_pool_blocks_upgrade(self, capsys):
        """既有 oos_verified 后跑出失败池 → 回落到 in_sample（防刷分）。"""
        from multi_stock_backtest import _update_validation

        # 先构造双池全达标
        self._run(
            capsys,
            [
                {
                    "strategy": "balanced",
                    "result": {
                        "win_rate_pct": 60.0,
                        "total_return_pct": 5.0,
                        "sharpe_ratio": 0.5,
                        "max_drawdown_pct": 8.0,
                    },
                }
            ],
            n_codes=50,
            pool_type="default",
        )
        self._run(
            capsys,
            [
                {
                    "strategy": "balanced",
                    "result": {
                        "win_rate_pct": 55.0,
                        "total_return_pct": 3.0,
                        "sharpe_ratio": 0.4,
                        "max_drawdown_pct": 10.0,
                    },
                }
            ],
            n_codes=40,
            pool_type="large",
        )
        assert load_oos_overrides()["balanced"]["validation_status"] == "oos_verified"

        # 再次跑 default 池，收益为负 → 联合判定回落 in_sample
        self._run(
            capsys,
            [
                {
                    "strategy": "balanced",
                    "result": {
                        "win_rate_pct": 20.0,
                        "total_return_pct": -5.0,
                        "sharpe_ratio": -0.5,
                        "max_drawdown_pct": 20.0,
                    },
                }
            ],
            n_codes=55,
            pool_type="default",
        )
        ov = load_oos_overrides()["balanced"]
        assert ov["validation_status"] == "in_sample"
        assert "default" in ov["validation_note"]

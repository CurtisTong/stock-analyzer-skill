"""scripts/chip_dist.py CLI 渲染层单元测试。

覆盖：现价上方无筹码密集区（main_cluster=None）时的文本渲染、批量表对取数失败项的保留、
筛选对失败项的处理。不发起网络请求。

回归背景：main_cluster 为 None 时需反弹/墙厚随之缺失，曾因 f-string 直接对 None 做
`:+.1f`/`:>7` 格式化抛 TypeError，导致 sh601398 等 250 日新高标的文本输出与
`technical.py --chip` 报告渲染失败。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

CHIP_DIST_CLI = Path(__file__).resolve().parents[2] / "scripts" / "chip_dist.py"


@pytest.fixture(scope="module")
def chip_cli():
    """加载 scripts/chip_dist.py 顶层脚本（非包，需按路径加载）。"""
    spec = importlib.util.spec_from_file_location("chip_dist_cli", CHIP_DIST_CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _chip(**overrides) -> dict:
    """无上方密集区的筹码结果（250 日新高形态）。"""
    base = {
        "price": 8.49,
        "avg_cost": 7.2,
        "price_vs_avg_cost_pct": 17.9,
        "profit_ratio": 99.9,
        "trapped_ratio": 0.1,
        "cost_range_90": {"low": 5.1, "high": 9.0},
        "main_cluster": None,
        "rebound_to_main_pct": None,
        "nearest_overhead": None,
        "wall_value_yi": None,
        "wall_thick": False,
        "turnover_window_pct": 88.0,
        "tier": "筹码在脚下",
    }
    base.update(overrides)
    return base


def _one(code: str = "sh601398", chip: dict | None = None, error: str | None = None) -> dict:
    meta = {"code": code, "as_of": "2026-10-14 10:00", "adjust": "raw", "degraded": [], "notes": []}
    if error:
        meta["error"] = error
    return {"meta": meta, "chip": chip}


class TestNum:
    """占位符格式化。"""

    def test_none_placeholder_keeps_width(self, chip_cli):
        """None 占位符须套用宽度 spec，否则批量表列错位。"""
        assert chip_cli._num(None, ">8") == "       -"
        assert chip_cli._num(4.2, ">8") == "     4.2"
        assert chip_cli._num(None) == "-"
        assert chip_cli._num(None, "", "无") == "无"


class TestRenderSingle:
    """单股文本渲染。"""

    def test_no_overhead_cluster_does_not_crash(self, chip_cli):
        """无上方密集区时用「无」占位，不再抛 TypeError。"""
        out = chip_cli.render_single(_one(chip=_chip()))
        assert "主密集区 无" in out
        assert "需反弹" not in out
        assert "筹码在脚下" in out

    def test_with_cluster_renders_rebound(self, chip_cli):
        """有上方密集区时正常渲染区间与需反弹。"""
        chip = _chip(
            main_cluster={"peak": 9.5, "band": [9.0, 10.0], "mass_pct": 30.0, "contains_price": False},
            rebound_to_main_pct=11.9,
            wall_thick=True,
        )
        out = chip_cli.render_single(_one(chip=chip))
        assert "9.0 - 10.0" in out
        assert "+11.9%" in out

    def test_failed_chip_reports_error(self, chip_cli):
        """chip 为 None 时输出计算失败原因。"""
        out = chip_cli.render_single(_one(chip=None, error="无 K 线数据"))
        assert "计算失败: 无 K 线数据" in out


class TestRenderBatch:
    """批量表渲染。"""

    def test_null_columns_do_not_crash(self, chip_cli):
        """需反弹/墙厚为 None 的列渲染为占位符。"""
        out = chip_cli.render_batch([chip_cli._flat(_one(chip=_chip()))])
        assert "sh601398" in out
        assert "筹码在脚下" in out

    def test_failed_row_is_kept_and_summarized(self, chip_cli):
        """取数失败项保留为行，并在表尾汇总数量。"""
        rows = [
            chip_cli._flat(_one("sh600989", chip=_chip())),
            chip_cli._flat(_one("sh999999", chip=None, error="无 K 线数据")),
        ]
        out = chip_cli.render_batch(rows)
        assert "取数失败" in out
        assert "1 只取数失败" in out


class TestApplyFilters:
    """筛选行为。"""

    def test_failed_item_survives_tier_filter(self, chip_cli):
        """失败项不被静默丢弃，命中/未命中档位的正常项仍按规则过滤。"""
        args = SimpleNamespace(tier="深度套牢", min_profit=None, max_rebound=None)
        rows = [
            chip_cli._flat(_one("sh600989", chip=_chip(tier="深度套牢"))),
            chip_cli._flat(_one("sh601398", chip=_chip())),
            chip_cli._flat(_one("sh999999", chip=None, error="无 K 线数据")),
        ]
        codes = [r["code"] for r in chip_cli._apply_filters(rows, args)]
        assert "sh600989" in codes
        assert "sh999999" in codes
        assert "sh601398" not in codes

    def test_no_filter_keeps_all(self, chip_cli):
        """无筛选条件时全部保留。"""
        args = SimpleNamespace(tier=None, min_profit=None, max_rebound=None)
        rows = [
            chip_cli._flat(_one("sh600989", chip=_chip())),
            chip_cli._flat(_one("sh999999", chip=None, error="无 K 线数据")),
        ]
        assert len(chip_cli._apply_filters(rows, args)) == 2

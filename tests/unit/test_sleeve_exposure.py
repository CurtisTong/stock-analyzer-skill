"""sleeve 敞口闸 E₀ 单测（全 hermetic：纯内存持仓 + 注入 β，不联网不读账本）。

回归基准锁 2026-11-24 清仓科创50 后两腿 sleeve 的 E₀=0.4379（中证1000+黄金，
β 2.2157/0.6810，末根与价格日同为 11-24；操盘/研判独立复算一致）。
旧三腿基准 0.7621（含科创50 β 2.7289、11-23 口径）已作废——清仓后 sleeve
少一腿，若测试仍锁 0.7621 就是"绿着锁过期值"。下次混用 11-23/11-24 口径
或改错 β，测试直接红，不再靠人肉对账。

不变量（Chief 11-23 定案）：
1. E₀ 由函数算、带四字段元数据（持仓清单/基准代码/末根日期/价格日期）
2. 末根日期 ≠ 价格日期 → date_aligned=False、reason 写明禁止启用
3. sleeve 任一标的缺 qty/px/beta 或总资产缺失 → e0=None、不填 0
4. 个股（广合等）不在 sleeve；自定义 sleeve 可扩展但口径须显式
"""
from __future__ import annotations

import pytest

from dev.sleeve_exposure import DEFAULT_SLEEVE, compute_exposure

TA = 709527.92
HOLDINGS = {
    "sz159845": {"qty": 50000, "px": 2.415},   # 中证1000
    "sz159934": {"qty": 8200, "px": 7.723},    # 黄金
}
BETAS = {"sz159845": 2.2157, "sz159934": 0.6810}
META = {
    "benchmark": "sh000001", "last_bar_date": "2026-11-24", "price_date": "2026-11-24",
    "beta_method": "sina_60d_sh000001",
}


def _compute(**overrides):
    kw = dict(holdings=HOLDINGS, total_assets=TA, betas=BETAS, **META)
    kw.update(overrides)
    return compute_exposure(**kw)


class TestBaselineLocked:
    def test_chief_baseline_e0(self):
        """回归基准：11-24 清仓科创50 后两腿 E₀=0.4379，逐项贡献锁定。"""
        r = _compute()
        assert r["e0"] == pytest.approx(0.4379, abs=1e-4)
        assert r["available"] is True
        assert r["date_aligned"] is True

    def test_old_three_leg_baseline_is_stale(self):
        """旧三腿基准 0.7621 含已清仓科创50，不得再用作生效值。"""
        assert 0.7621 != pytest.approx(0.4379, abs=1e-4)
        assert "sh588080" not in DEFAULT_SLEEVE  # 科创50 已清仓

    def test_per_leg_contributions(self):
        r = _compute()
        contrib = {d["code"]: d["contribution"] for d in r["detail"]}
        assert contrib["sz159845"] == pytest.approx(0.3771, abs=5e-4)
        assert contrib["sz159934"] == pytest.approx(0.0608, abs=5e-4)
        assert "sh588080" not in contrib

    def test_four_metadata_fields_present(self):
        r = _compute()
        assert r["holdings"] == ["sz159845", "sz159934"]
        assert r["benchmark"] == "sh000001"
        assert r["last_bar_date"] == "2026-11-24"
        assert r["price_date"] == "2026-11-24"
        assert r["beta_method"] == "sina_60d_sh000001"

    def test_missing_beta_method_returns_none(self):
        """Chief 11-23 补：beta_method 必填，缺了不给 E₀（不写算法名=没写口径）。"""
        r = _compute(beta_method=None)
        assert r["e0"] is None
        assert r["available"] is False
        assert "beta_method" in r["reason"]


class TestDateAlignment:
    def test_mixed_dates_disables(self):
        """末根 11-23 + 价格日 11-24（跨清仓日混口径）→ 禁止启用。"""
        r = _compute(last_bar_date="2026-11-23")
        assert r["date_aligned"] is False
        assert "禁止启用" in r["reason"]
        # E₀ 仍算出数值供对照，但 available 语义由 date_aligned 约束
        assert r["e0"] is not None

    def test_aligned_same_day(self):
        r = _compute()
        assert r["date_aligned"] is True
        assert r["reason"] is None


class TestMissingFieldsNull:
    @pytest.mark.parametrize("bad_field", ["total_assets", "benchmark", "last_bar_date", "price_date"])
    def test_missing_meta_returns_none(self, bad_field):
        kw = {bad_field: None}
        r = _compute(**kw)
        assert r["e0"] is None
        assert r["available"] is False
        assert r["reason"]

    def test_missing_beta_returns_none_not_zero(self):
        betas = dict(BETAS)
        del betas["sz159934"]
        r = _compute(betas=betas)
        assert r["e0"] is None
        assert "缺 qty/px/beta" in r["reason"]

    def test_missing_holding_returns_none(self):
        h = {k: v for k, v in HOLDINGS.items() if k != "sz159845"}
        r = _compute(holdings=h)
        assert r["e0"] is None
        assert "sz159845" in r["reason"]

    def test_zero_total_assets_rejected(self):
        r = _compute(total_assets=0)
        assert r["e0"] is None
        assert "总资产" in r["reason"]


class TestSleeveScope:
    def test_default_sleeve_excludes_individual_stocks(self):
        """个股（广合等）不在默认 sleeve，β 再高也不影响本闸。"""
        assert "sz001389" not in DEFAULT_SLEEVE  # 广合科技
        betas = dict(BETAS, sz001389=4.263)
        r = _compute(betas=betas)
        assert r["e0"] == pytest.approx(0.4379, abs=1e-4)  # 加个股 β 不改变结果

    def test_custom_sleeve_extends(self):
        """自定义 sleeve 显式纳入个股 → 贡献变化（将来扩全组合口径用）。"""
        h = dict(HOLDINGS, sz001389={"qty": 300, "px": 82.52})
        betas = dict(BETAS, sz001389=4.263)
        sleeve = DEFAULT_SLEEVE + ("sz001389",)
        r = _compute(holdings=h, betas=betas, sleeve=sleeve)
        assert r["e0"] > 0.4379  # 个股 β 4.263 抬高敞口
        assert r["holdings"] == list(sleeve)

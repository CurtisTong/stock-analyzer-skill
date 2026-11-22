"""event_bootstrap 单元测试（全 hermetic：纯内存数据，不连网、不读运行时缓存）。

覆盖三样能力：
- effective_n()：时间维重叠聚类、跨标的不合并、n_raw=0 时 ratio=None
- multipletests(holm)：数值对照 statsmodels 已知结果、缺失 p 不填 0、非法参数报错
- with_metadata()：benchmark/codes/window/n 四字段齐全，缺字段写 None
块自助暂未落（Chief 2026-11-22 指定范围），本文件不测。
"""
from __future__ import annotations

import pytest

from dev.event_bootstrap import effective_n, multipletests, with_metadata


class TestEffectiveN:
    def test_no_overlap(self):
        # 17 事件，Δ=509 ≥ W=250，各自成簇
        out = effective_n([("S", i * 509) for i in range(17)], 250)
        assert out["n_raw"] == 17
        assert out["n_eff"] == 17
        assert out["n_overlap"] == 0

    def test_boundary_strict_less_than(self):
        # Δ==W 不重叠；Δ==W-1 才重叠
        assert effective_n([("S", 0), ("S", 60)], 60)["n_eff"] == 2
        assert effective_n([("S", 0), ("S", 59)], 60)["n_eff"] == 1

    def test_overlap_clusters(self):
        # 同标的 0,10,20 间隔 10 < W=20 → 连成一簇，n_eff=1，n_overlap=2
        out = effective_n([("S", 0), ("S", 10), ("S", 20)], 20)
        assert out["n_eff"] == 1
        assert out["n_overlap"] == 2
        assert out["verdict"] == "不可用/仅案例"

    def test_cross_code_same_day_not_merged(self):
        # 跨标的同日事件不合并
        out = effective_n([("A", 100), ("B", 100)], 250)
        assert out["n_eff"] == 2

    def test_empty_ratio_is_none_not_zero(self):
        # 硬性口径：缺失字段写 None，不许 0 占位
        out = effective_n([], 20)
        assert out["n_raw"] == 0
        assert out["ratio"] is None

    def test_verdict_tiers(self):
        # n_eff=15 <30 → 降级用（即使 ratio=1.0）
        n15 = [(str(i), i * 509) for i in range(15)]
        assert effective_n(n15, 250)["verdict"] == "降级用"
        n30 = [(str(i), i * 509) for i in range(30)]
        assert effective_n(n30, 250)["verdict"] == "可用"

    def test_seventeen_events_verdict(self):
        # 与原型自检基准一致：17 事件无重叠 → n_eff=17、降级用
        out = effective_n([("S", i * 509) for i in range(17)], 250)
        assert out["n_eff"] == 17
        assert out["verdict"] == "降级用"


class TestMultipletestsHolm:
    def test_holm_step_down_values(self):
        # 手算 Holm step-down（非 statsmodels 实测，本机零依赖）：
        # p 升序 [0.0034,0.01,0.02,0.03,0.04,0.05]，m=6
        # 逐位 (m-j)*p = [0.0204,0.05,0.08,0.09,0.08,0.05]
        # 累计最大并截断 1.0 → [0.0204,0.05,0.08,0.09,0.09,0.09]
        out = multipletests([0.0034, 0.01, 0.02, 0.03, 0.04, 0.05], method="holm")
        expected = [0.0204, 0.05, 0.08, 0.09, 0.09, 0.09]
        assert out["pvals_corrected"] == pytest.approx(expected, abs=1e-9)
        assert out["reject"] == [True, False, False, False, False, False]
        assert out["n_tests"] == 6
        assert out["method"] == "holm"

    def test_single_test_unchanged(self):
        out = multipletests([0.03], method="holm")
        assert out["pvals_corrected"] == [0.03]
        assert out["reject"] == [True]  # 0.03 < alpha=0.05 → 拒绝

    def test_clips_at_one(self):
        out = multipletests([0.9, 0.8], method="holm")
        assert all(p <= 1.0 for p in out["pvals_corrected"])

    def test_missing_p_is_none_not_zero(self):
        # 缺失 p 写 None，m 只数非缺失值；None 不参与、结果位为 None（绝不填 0）
        out = multipletests([0.01, None, 0.04], method="holm")
        assert out["n_tests"] == 2
        assert out["pvals_corrected"][1] is None
        assert out["reject"][1] is None
        # m=2: 排序 0.01(index0),0.04(index2) → 2*0.01=0.02, 1*0.04=0.04
        assert out["pvals_corrected"][0] == pytest.approx(0.02, abs=1e-9)
        assert out["pvals_corrected"][2] == pytest.approx(0.04, abs=1e-9)

    def test_all_missing(self):
        out = multipletests([None, None], method="holm")
        assert out["n_tests"] == 0
        assert out["pvals_corrected"] == [None, None]

    def test_rejects_unsupported_method(self):
        with pytest.raises(ValueError, match="不支持"):
            multipletests([0.01], method="fdr_bh")

    def test_rejects_bad_alpha(self):
        with pytest.raises(ValueError, match="alpha"):
            multipletests([0.01], method="holm", alpha=1.5)


class TestWithMetadata:
    def test_four_fields_present(self):
        out = with_metadata({"n_eff": 17}, benchmark="sh000001", codes=["sz159901"], window=60, n=17)
        assert out["benchmark"] == "sh000001"
        assert out["codes"] == ["sz159901"]
        assert out["window"] == 60
        assert out["n"] == 17
        assert out["n_eff"] == 17  # 原结果保留

    def test_missing_fields_are_none_not_zero(self):
        out = with_metadata({}, benchmark=None, codes=None, window=None, n=None)
        for k in ("benchmark", "codes", "window", "n"):
            assert out[k] is None

    def test_explicit_metadata_overwrites_same_key(self):
        out = with_metadata({"benchmark": "stale"}, benchmark="sh000300", codes=None, window=None, n=None)
        assert out["benchmark"] == "sh000300"

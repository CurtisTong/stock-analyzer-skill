"""扣非净利同比字段口径测试（累计 vs 单季）。

背景（2026-10-30 国泰海通三季报分析复盘）：
东财 ZYZBAjaxNew 同时返回两个扣非同比字段，口径不同：

- KCFJCXSYJLRTZ      = 扣非净利**累计**同比（年初至报告期末），财报语义
- DJD_DEDUCTDPNP_YOY = 扣非净利**单季**同比（DJD = 单季度）

原 FIELD_MAP 把单季口径排在候选列表首位，而 _find() 取首个命中值，
导致 deducted_np_yoy 长期返回单季同比冒充累计同比。

实测偏差（2026 三季报）：

    中信证券  累计 +34.47%  vs  单季 -20.69%
    华泰证券  累计 +19.00%  vs  单季 -35.59%
    国泰海通  累计 +46.87%  vs  单季 -50.84%

影响：拿单季同比当累计同比做同业对比，会得出"扣非大幅下滑"的错误结论
（2025 三季报国泰海通扣非 YoY 显示 246.15%，实为 Q2 单季值，累计值是 168.02%）。

本测试验证：
- deducted_np_yoy 取累计口径（KCFJCXSYJLRTZ 优先）
- 单季口径单独落到 deducted_np_q_yoy，不丢失信息
- 只有单季字段时，累计字段为 None 而非错误回填
- 与公告原文交叉验证的锚点值（中信/华泰 2026 三季报）
"""

import pytest

from data import _dict_to_finance


def _em_record(report_date, report_type, **extra):
    """东财主要指标原始 dict 模板。"""
    base = {
        "REPORT_DATE": report_date,
        "REPORT_TYPE": report_type,
        "source": "eastmoney",
    }
    base.update(extra)
    return base


class TestDeductedNpYoyCaliber:
    """deducted_np_yoy 必须返回累计口径。"""

    def test_cumulative_takes_precedence_over_single_quarter(self):
        """两个字段同时存在时，累计口径优先（修复前的 bug 场景）。"""
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            KCFJCXSYJLRTZ="46.874142102896",
            DJD_DEDUCTDPNP_YOY="-50.838895557036",
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == 46.87
        assert r.deducted_np_q_yoy == -50.84

    def test_single_quarter_field_preserved_separately(self):
        """单季口径不丢失，落到 deducted_np_q_yoy。"""
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            KCFJCXSYJLRTZ="34.467233245261",
            DJD_DEDUCTDPNP_YOY="-20.691327954857",
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == 34.47
        assert r.deducted_np_q_yoy == -20.69

    def test_only_single_quarter_field_leaves_cumulative_none(self):
        """只有单季字段时，累计字段为 None，不得用单季值冒充。"""
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            DJD_DEDUCTDPNP_YOY="-50.838895557036",
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy is None
        assert r.deducted_np_q_yoy == -50.84

    def test_only_cumulative_field(self):
        """只有累计字段时，单季字段为 None。"""
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            KCFJCXSYJLRTZ="46.874142102896",
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == 46.87
        assert r.deducted_np_q_yoy is None

    def test_standardized_field_name_still_supported(self):
        """标准化字段名 deducted_np_yoy 仍然可用（akshare 等其他源的兼容路径）。"""
        d = _em_record("2026-09-30 00:00:00", "三季报", deducted_np_yoy="12.5")
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == 12.5

    def test_missing_both_fields_none(self):
        """两个字段都缺失时均为 None（数据源未披露场景）。"""
        d = _em_record("2026-09-30 00:00:00", "三季报")
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy is None
        assert r.deducted_np_q_yoy is None


class TestDeductedNpYoyAnchors:
    """与公告原文交叉验证的锚点值。

    数值取自 2026-10-30 东财 ZYZBAjaxNew 实测，并与三季报公告正文核对：
    中信 2025 前三季度扣非归母 230.00 亿（调整后）→ 2026 前三季度 312.32 亿，
    同比 +35.8%，落在东财累计口径 +34.47% 的合理误差内（追溯调整差异）。
    """

    @pytest.mark.parametrize(
        "code,expect_cum,expect_q",
        [
            ("SH600030", 34.47, -20.69),  # 中信证券
            ("SH601688", 19.0, -35.59),  # 华泰证券
            ("SH601211", 46.87, -50.84),  # 国泰海通
        ],
    )
    def test_anchor_values(self, code, expect_cum, expect_q):
        """三家券商 2026 三季报：累计为正、单季为负，口径不得混用。"""
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            KCFJCXSYJLRTZ=str(expect_cum),
            DJD_DEDUCTDPNP_YOY=str(expect_q),
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == expect_cum
        assert r.deducted_np_q_yoy == expect_q
        # 关键不变量：累计与单季方向相反时不得被混为一谈
        assert r.deducted_np_yoy != r.deducted_np_q_yoy


class TestDeductedNpYoyConsistency:
    """与其它同比字段的口径一致性。"""

    def test_revenue_and_profit_yoy_are_cumulative(self):
        """营收/归母同比均为累计口径，扣非同比必须与之对齐。

        东财 TOTALOPERATEREVETZ / PARENTNETPROFITTZ 均为年初至报告期末累计同比，
        扣非同比若取单季口径，会与同组的营收/净利同比不可比。
        """
        d = _em_record(
            "2026-09-30 00:00:00",
            "三季报",
            TOTALOPERATEREVETZ="28.511630763445",
            PARENTNETPROFITTZ="12.732951118011",
            KCFJCXSYJLRTZ="46.874142102896",
            DJD_DEDUCTDPNP_YOY="-50.838895557036",
        )
        r = _dict_to_finance(d)
        # 营收/归母同比不做舍入，用 approx 断言避免依赖舍入实现
        assert r.revenue_yoy == pytest.approx(28.5116, abs=0.01)
        assert r.net_profit_yoy == pytest.approx(12.7329, abs=0.01)
        # 扣非累计口径与营收/净利累计口径同属一组
        assert r.deducted_np_yoy == 46.87
        assert r.deducted_np_q_yoy == -50.84

    def test_first_quarter_both_calibers_equal(self):
        """一季报累计=单季，两个口径取值相同（结构自证）。"""
        d = _em_record(
            "2026-03-31 00:00:00",
            "一季报",
            KCFJCXSYJLRTZ="73.427512129824",
            DJD_DEDUCTDPNP_YOY="73.427512129824",
        )
        r = _dict_to_finance(d)
        assert r.deducted_np_yoy == r.deducted_np_q_yoy == 73.43

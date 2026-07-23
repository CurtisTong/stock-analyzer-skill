"""FinanceRecord 报告期口径（period_type）单元测试。

背景（2026-07-23 宝丰能源 PE 误算复盘）：
东财 fetcher 返回的 finance[0] 默认是最新一期，可能是单季一季报（EPS=0.50），
而非全年年报。下游若把单季 EPS 当全年做 price/eps，会把 PE 高估 4 倍（47 倍）。

本测试验证：
- _dict_to_finance 从东财 REPORT_TYPE 归一化 period_type（一季报/中报/三季报/年报）
- 缺 REPORT_TYPE 时安全降级为空串（akshare/旧数据兼容）
- expected_period_type 按 report_date 兜底推断
- compute_pe 按 period_type 选 PE 算法（单季年化 / 累计禁算 / 年报直除）
- _extract_finance_summary 标注口径 + 单季告警
"""

import pytest

from data import _dict_to_finance
from data.types import FinanceRecord
from data.helpers import compute_pe, expected_period_type


def _em_record(report_date, report_type, **extra):
    """东财原始 dict 模板（复用 test_finance_meta 风格，补 REPORT_TYPE）。

    report_date 用 '2025-03-31 00:00:00' 带时间后缀，贴近真实缓存，
    顺便覆盖 _dict_to_finance 的 [:10] 截断逻辑。
    """
    base = {
        "REPORT_DATE": report_date,
        "REPORT_TYPE": report_type,
        "EPSJB": "1.5",
        "ROEJQ": "15.0",
        "TOTALOPERATEREVETZ": "20.0",
        "PARENTNETPROFITTZ": "18.3",
        "XSMLL": "91.5",
        "XSJLL": "52.3",
        "ZCFZL": "18.7",
        "BPS": "180.00",
        "MGJYXJJE": "55.00",
        "source": "eastmoney",
    }
    base.update(extra)
    return base


class TestPeriodTypeMapping:
    """REPORT_TYPE -> period_type 归一化。"""

    @pytest.mark.parametrize(
        "rtype,expect",
        [
            ("一季报", "quarterly"),
            ("中报", "cumulative"),
            ("三季报", "cumulative"),
            ("年报", "annual"),
        ],
    )
    def test_report_type_normalized(self, rtype, expect):
        """东财四个 REPORT_TYPE 值必须正确映射到标准化枚举。"""
        r = _dict_to_finance(_em_record("2025-03-31 00:00:00", rtype))
        assert r.period_type == expect

    def test_report_date_truncated_to_10_chars(self):
        """REPORT_DATE 带时间后缀须截断为 10 位日期。"""
        r = _dict_to_finance(_em_record("2026-03-31 00:00:00", "一季报"))
        assert r.report_date == "2026-03-31"

    def test_missing_report_type_defaults_empty(self):
        """akshare/旧数据无 REPORT_TYPE 字段时降级为空串，不报错。"""
        d = _em_record("2025-03-31 00:00:00", "一季报")
        del d["REPORT_TYPE"]
        r = _dict_to_finance(d)
        assert r.period_type == ""
        # 其它字段不受影响
        assert r.report_date == "2025-03-31"
        assert r.eps == 1.5

    def test_unknown_report_type_empty(self):
        """未知 REPORT_TYPE 值降级为空串。"""
        r = _dict_to_finance(_em_record("2025-03-31 00:00:00", "未知类型"))
        assert r.period_type == ""

    def test_default_period_type_empty(self):
        """FinanceRecord 默认 period_type 为空串。"""
        assert FinanceRecord().period_type == ""

    def test_old_cache_record_has_period_type(self):
        """旧东财缓存（raw dict 带 REPORT_TYPE）读取后 period_type 非空。"""
        r = _dict_to_finance(_em_record("2025-12-31 00:00:00", "年报"))
        assert r.period_type == "annual"


class TestExpectedPeriodType:
    """report_date 末尾日期兜底推断 period_type（akshare 缺 REPORT_TYPE 时用）。"""

    @pytest.mark.parametrize(
        "date,expect",
        [
            ("2025-12-31", "annual"),
            ("2025-03-31", "quarterly"),
            ("2025-06-30", "cumulative"),
            ("2025-09-30", "cumulative"),
            ("", ""),
            ("未知", ""),
        ],
    )
    def test_date_to_type(self, date, expect):
        assert expected_period_type(date) == expect


class TestComputePe:
    """compute_pe 按 period_type 选 PE 算法。"""

    def test_annual_direct(self):
        """年报口径直接 price/eps。"""
        assert compute_pe(15.0, 1.5, "annual") == {"pe": 10.0, "method": "PE(年报)"}

    def test_quarterly_annualized(self):
        """单季口径年化×4（最乐观，标记近似）。"""
        r = compute_pe(23.64, 0.50, "quarterly")
        assert r["pe"] == round(23.64 / 2.0, 2)
        assert "近似" in r["method"]
        assert "2.00" in r["method"]

    def test_cumulative_not_direct(self):
        """累计期不可直接算 PE，返回 None 提示需 TTM。"""
        r = compute_pe(10.0, 0.78, "cumulative")
        assert r["pe"] is None
        assert "TTM" in r["method"]

    def test_none_eps(self):
        """EPS 缺失（None）不可算 PE。"""
        assert compute_pe(10.0, None, "annual")["pe"] is None

    def test_zero_eps(self):
        """EPS=0（亏损或未披露）不可算 PE。"""
        assert compute_pe(10.0, 0.0, "annual")["pe"] is None

    def test_zero_price(self):
        """股价<=0（停牌/数据异常）不可算 PE。"""
        assert compute_pe(0.0, 1.5, "annual")["pe"] is None

    def test_unknown_caliber(self):
        """口径未知（空串）跳过估值。"""
        r = compute_pe(10.0, 1.0, "")
        assert r["pe"] is None
        assert "未知" in r["method"]

    def test_baofeng_47x_error_reproduced_and_fixed(self):
        """回归：宝丰能源场景。

        错误算法（旧）：price / 单季 eps = 23.64 / 0.50 = 47.28 倍（高估 4 倍）
        正确算法（新）：compute_pe 按单季年化 = 23.64 / (0.50*4) = 11.82 倍
        """
        wrong_pe = 23.64 / 0.50  # 旧逻辑把单季当全年
        r = compute_pe(23.64, 0.50, "quarterly")
        assert r["pe"] is not None
        # 新算法约为旧算法的 1/4
        assert abs(r["pe"] - wrong_pe / 4) < 0.01
        assert r["pe"] == 11.82


class TestExtractFinanceSummary:
    """验证 _extract_finance_summary 口径标注与单季告警。"""

    def test_quarterly_emits_warning(self):
        """单季 EPS 必须有 warning 字段和年化提示。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {"eps": 0.50, "period_type": "quarterly", "report_date": "2026-03-31"}
        s = _extract_finance_summary(fin)
        assert s["eps_annualized_hint"] == 2.0
        assert "warning" in s
        assert "单季" in s["warning"]
        assert "单季" in s["eps_caliber"]
        assert "2026-03-31" in s["eps_caliber"]
        assert s["period_type"] == "quarterly"

    def test_annual_no_warning(self):
        """年报 EPS 不告警、不附年化提示。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {"eps": 1.56, "period_type": "annual", "report_date": "2025-12-31"}
        s = _extract_finance_summary(fin)
        assert "eps_annualized_hint" not in s
        assert "warning" not in s
        assert "年报" in s["eps_caliber"]
        assert "2025-12-31" in s["eps_caliber"]
        assert s["period_type"] == "annual"

    def test_cumulative_no_warning(self):
        """累计期不告警（不触发单季年化分支）。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {"eps": 0.78, "period_type": "cumulative", "report_date": "2025-06-30"}
        s = _extract_finance_summary(fin)
        assert "eps_annualized_hint" not in s
        assert "warning" not in s
        assert "累计" in s["eps_caliber"]

    def test_unknown_period_type(self):
        """period_type 为空（akshare）时 eps_caliber 标"未知"，不告警。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {"eps": 1.0, "period_type": "", "report_date": "2025-03-31"}
        s = _extract_finance_summary(fin)
        assert "未知" in s["eps_caliber"]
        assert "warning" not in s

    def test_period_type_passthrough(self):
        """period_type / report_date 必须透传到 summary。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {
            "eps": 1.5,
            "roe": 15.0,
            "period_type": "annual",
            "report_date": "2025-12-31",
        }
        s = _extract_finance_summary(fin)
        assert s["period_type"] == "annual"
        assert s["report_date"] == "2025-12-31"
        assert s["eps"] == 1.5
        assert s["roe"] == 15.0

    def test_quarterly_zero_eps_no_warning(self):
        """单季但 EPS=0（亏损/未披露）不触发年化提示，避免除零。"""
        from business.stock_analysis import _extract_finance_summary

        fin = {"eps": 0, "period_type": "quarterly", "report_date": "2026-03-31"}
        s = _extract_finance_summary(fin)
        assert "eps_annualized_hint" not in s
        assert "warning" not in s

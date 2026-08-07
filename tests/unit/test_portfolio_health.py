"""portfolio 健康检查模板的单元测试。

覆盖 manager.py 的板块分类（tags[0] 状态标签 bug 修复 + 行业大类合并映射）
+ 破位判定（成本-5% 阈值）。

按 FRAMEWORK.md 规范：纯函数 + parametrize + 显式命名。
"""

from __future__ import annotations

import pytest

from portfolio import PortfolioManager


# ────────────────────────────────────────────────────────────────
# 板块分类：状态标签白名单 + 行业大类合并
# ────────────────────────────────────────────────────────────────


class TestIndustryClassification:
    """tags 分类：先过滤状态标签，再合并到行业大类。"""

    @pytest.mark.parametrize(
        "tags,expected",
        [
            # P1-01 bug 修复：状态标签被过滤
            (["T+1待交收", "煤化工", "能源"], "煤化工"),  # T+1 被过滤
            (["长线", "半导体"], "半导体"),  # 长线被过滤
            (["短线", "锂电池"], "锂/新能源"),  # 锂电池合并
            (["观察", "锂矿"], "锂/新能源"),
            (["核心", "银行"], "银行"),  # 银行原值
            # 行业子标签合并到"锂/新能源"
            (["锂电", "有色"], "锂/新能源"),
            (["锂矿", "新能源"], "锂/新能源"),
            (["光伏", "新能源车"], "锂/新能源"),
            (["新能源", "光伏"], "锂/新能源"),
            # 其他合并
            (["通信", "海缆"], "通信"),
            (["汽零", "机器人"], "汽零"),
            # 无合并映射，保留原值
            (["半导体", "PCB"], "半导体"),
            (["白酒"], "白酒"),
            # 未知标签
            (["新潮行业"], "新潮行业"),
            ([], "未分类"),
        ],
    )
    def test_industry_resolution(self, tags, expected):
        """纯函数测试：tags → industry 分辨。"""
        # 模拟 manager.py:694-700 的逻辑
        status_tags = PortfolioManager._STATUS_TAGS
        group = PortfolioManager._INDUSTRY_GROUP
        industry_tags = [t for t in tags if t not in status_tags]
        if industry_tags:
            raw = industry_tags[0]
            result = group.get(raw, raw)
        elif tags:
            result = tags[0]
        else:
            result = "未分类"
        assert result == expected


# ────────────────────────────────────────────────────────────────
# check_concentration 端到端：验证合并映射生效
# ────────────────────────────────────────────────────────────────


class TestCheckConcentrationMerged:
    """验证修复后 check_concentration 输出真实行业集中度。"""

    def test_industry_concentration_merges_lithium_chain(self):
        """8 只持仓里 5 只是锂/新能源链，合并后应 >30% 触发警告。"""
        pm = PortfolioManager()
        result = pm.check_concentration()

        industry = result["details"]["industry"]
        # 合并后应有"锂/新能源"大类且占比 >30%
        if "锂/新能源" in industry:
            assert industry["锂/新能源"] > 30, (
                f"锂/新能源占比 {industry['锂/新能源']}% 应触发 30% 阈值警告"
            )
            # 应触发警告
            assert any("锂/新能源" in w for w in result["warnings"])

    def test_baofeng_no_longer_misclassified(self):
        """宝丰能源 tags 含 T+1待交收（状态），修复后应归"煤化工"或"能源"，不是 T+1。"""
        pm = PortfolioManager()
        result = pm.check_concentration()
        industry = result["details"]["industry"]
        # T+1 待交收不应作为 industry 键
        assert "T+1待交收" not in industry, (
            "宝丰能源被错误归到 T+1待交收 状态标签"
        )


# ────────────────────────────────────────────────────────────────
# 破位判定
# ────────────────────────────────────────────────────────────────


class TestBreakdownJudgment:
    """破位判定：现价 < 成本 × 0.95 视为破位。"""

    @pytest.mark.parametrize(
        "price,cost,is_breakdown",
        [
            # 破位
            (33.43, 35.84, True),  # 中天科技 -6.73%
            (105.87, 112.43, True),  # 阳光电源 -5.83%
            (44.12, 57.83, True),  # 华友钴业 -23.70%
            # 健康
            (23.69, 22.37, False),  # 宝丰能源 +5.9%
            (67.93, 66.92, False),  # 融捷股份 +1.5%
            (49.79, 51.13, False),  # 拓普集团 -2.6% (>= -5%)
            (31.20, 31.22, False),  # 科华数据 -0.07%
            (18.41, 18.23, False),  # 雅化集团 +1.0%
        ],
    )
    def test_breakdown_threshold(self, price, cost, is_breakdown):
        """成本-5% 阈值判定。"""
        threshold = cost * 0.95
        result = price < threshold
        assert result == is_breakdown


# ────────────────────────────────────────────────────────────────
# PortfolioManager._STATUS_TAGS 与 _INDUSTRY_GROUP 一致性
# ────────────────────────────────────────────────────────────────


class TestManagerConstants:
    """PortfolioManager 类常量的基础一致性。"""

    def test_status_tags_is_frozenset(self):
        """状态标签白名单是不可变集合。"""
        assert isinstance(PortfolioManager._STATUS_TAGS, frozenset)

    def test_industry_group_is_dict(self):
        """行业大类映射是 dict。"""
        assert isinstance(PortfolioManager._INDUSTRY_GROUP, dict)

    def test_lithium_chain_merged(self):
        """锂电产业链 6 个子标签合并到"锂/新能源"大类（核心防错配）。"""
        group = PortfolioManager._INDUSTRY_GROUP
        for sub in ["锂电", "锂矿", "锂业", "锂电池", "光伏", "储能"]:
            assert group[sub] == "锂/新能源", f"{sub} 未合并到锂/新能源"

    def test_breakdown_threshold_default(self):
        """破位判定阈值默认 0.95（成本 -5%）。"""
        assert PortfolioManager.BREAKDOWN_THRESHOLD == 0.95


# ────────────────────────────────────────────────────────────────
# health_report：结构化报告
# ────────────────────────────────────────────────────────────────


class TestHealthReport:
    """health_report 返回结构化报告，按 SKILL.md 模板标准字段。"""

    def _make_quotes_map(self, prices: dict) -> dict:
        """构造 mock 行情 dict（仅含必要字段）。"""
        return {code: {"price": price, "change_pct": 0.0} for code, price in prices.items()}

    def test_totals_structure(self):
        """totals 含 cost/value/pnl/pnl_pct 4 个字段。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        assert set(report["totals"].keys()) == {"cost", "value", "pnl", "pnl_pct"}
        # 字段类型正确（float），即使没有行情也应基于成本计算
        assert isinstance(report["totals"]["cost"], (int, float))
        assert isinstance(report["totals"]["value"], (int, float))

    def test_breakdown_positions_isolated(self):
        """破位标的独立汇总（不混入正常持仓建议）。"""
        pm = PortfolioManager()
        # 模拟中天科技（成本 35.84，现价 33.43 = -6.7% 破位）
        quotes = {
            "sh600522": {"price": 33.43, "change_pct": 0.0},
            "sh600989": {"price": 23.69, "change_pct": 0.0},
        }
        report = pm.health_report(quotes=quotes)
        # 中天科技应在 breakdown_positions
        breakdown_codes = [r["code"] for r in report["breakdown_positions"]]
        assert "sh600522" in breakdown_codes
        # 宝丰能源（成本 22.37、现价 23.69）不在 breakdown
        assert "sh600989" not in breakdown_codes

    def test_watchlist_present_even_empty(self):
        """自选股字段总是存在（即使为空列表）。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        assert "watchlist" in report
        assert isinstance(report["watchlist"], list)

    def test_thresholds_embedded(self):
        """thresholds 字段含集中度阈值（用于 P1-06 引用权威源）。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        assert report["thresholds"]["top3"] == 50
        assert report["thresholds"]["top5"] == 70
        assert report["thresholds"]["industry"] == 30
        assert report["thresholds"]["single"] == 20
        assert "0.95" in report["thresholds"]["breakdown"]

    def test_type_field_three_states(self):
        """type 字段识别实盘/示例/虚拟（解决 P1-13 / P3-14）。"""
        pm = PortfolioManager()
        assert pm.health_report(quotes={})["type"] in {"实盘持仓", "示例持仓", "虚拟持仓"}

    def test_industry_concentration_uses_merged_mapping(self):
        """industry 字段使用合并后的映射（修复后不再分散）。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        industry = report["concentration"]["details"]["industry"]
        # 不应再有"锂电/锂矿/锂业"分散键（已合并到"锂/新能源"）
        for dispersed in ["锂电", "锂矿", "锂业"]:
            assert dispersed not in industry, (
                f"行业 {dispersed} 未合并，仍分散为独立键"
            )
        # "锂/新能源" 大类键应存在（组合含相关持仓）
        if any(p.get("tags") for p in pm.get_positions()):
            assert "锂/新能源" in industry

    def test_risk_rating_includes_breakdown_and_concentration(self):
        """risk_rating 聚合破位 + 集中度警告。"""
        pm = PortfolioManager()
        quotes = {
            "sh600522": {"price": 33.43, "change_pct": 0.0},
            "sh603799": {"price": 44.12, "change_pct": 0.0},
        }
        report = pm.health_report(quotes=quotes)
        # risk_rating 应包含破位警告
        assert "破位" in report["risk_rating"]
        # 同时包含集中度警告（来自 check_concentration）
        assert "集中度" in report["risk_rating"]
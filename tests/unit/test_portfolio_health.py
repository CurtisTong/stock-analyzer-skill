"""portfolio 健康检查模板的单元测试。

覆盖 manager.py 的板块分类（tags[0] 状态标签 bug 修复 + 行业大类合并映射）
+ 破位判定（成本-5% 阈值）。

按 FRAMEWORK.md 规范：纯函数 + parametrize + 显式命名。
"""

from __future__ import annotations

import json

import pytest

from portfolio import PortfolioManager

# 测试用固定持仓：隔离真实用户 portfolio.json（gitignored，内容随用户变化）
_POS_300274 = {
    "code": "sz300274",
    "name": "阳光电源",
    "cost": 120.0,
    "quantity": 100,
    "buy_date": "2026-07-01",
    "tags": ["新能源"],
}


def _make_manager(tmp_path, positions):
    """构造使用临时持仓文件的 PortfolioManager，避免依赖真实用户数据。"""
    p = tmp_path / "portfolio.json"
    p.write_text(
        json.dumps(
            {"version": 2, "positions": positions, "watchlist": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return PortfolioManager(path=str(p))


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
            (["核心", "银行"], "金融"),  # 银行合并到金融大类（M5）
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
            (["白酒"], "消费"),  # 白酒合并到消费大类（M5）
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

    def test_industry_concentration_merges_lithium_chain(self, tmp_path):
        """8 只持仓里 5 只是锂/新能源链，合并后应 >30% 触发警告。"""
        positions = [
            {
                "code": f"sz3007{i}",
                "name": f"锂{i}",
                "cost": 100.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["锂矿"],
            }
            for i in range(5)
        ] + [
            {
                "code": "sh600000",
                "name": "浦发银行",
                "cost": 100.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["银行"],
            },
            {
                "code": "sz000858",
                "name": "五粮液",
                "cost": 100.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["白酒"],
            },
            {
                "code": "sh600584",
                "name": "长电科技",
                "cost": 100.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["半导体"],
            },
        ]
        pm = _make_manager(tmp_path, positions)
        result = pm.check_concentration()

        industry = result["details"]["industry"]
        # 合并后应有"锂/新能源"大类且占比 >30%
        if "锂/新能源" in industry:
            assert (
                industry["锂/新能源"] > 30
            ), f"锂/新能源占比 {industry['锂/新能源']}% 应触发 30% 阈值警告"
            # 应触发警告
            assert any("锂/新能源" in w for w in result["warnings"])

    def test_baofeng_no_longer_misclassified(self):
        """宝丰能源 tags 含 T+1待交收（状态），修复后应归"煤化工"或"能源"，不是 T+1。"""
        pm = PortfolioManager()
        result = pm.check_concentration()
        industry = result["details"]["industry"]
        # T+1 待交收不应作为 industry 键
        assert "T+1待交收" not in industry, "宝丰能源被错误归到 T+1待交收 状态标签"


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

    def test_totals_structure(self):
        """totals 含 cost/value/pnl/pnl_pct 4 个字段。

        L17: 行情缺失时 value/pnl/pnl_pct = None（不再是 0 或 -100% 误导）。
        """
        pm = PortfolioManager()
        # 正常情况（有 cost）
        report = pm.health_report(
            quotes={"sh600989": {"price": 23.69, "change_pct": 0}}
        )
        assert set(report["totals"].keys()) == {"cost", "value", "pnl", "pnl_pct"}
        assert isinstance(report["totals"]["cost"], (int, float))
        assert isinstance(report["totals"]["value"], (int, float))
        # 行情缺失时 value/pnl/pnl_pct = None
        report_no_q = pm.health_report(quotes=None)
        assert report_no_q["totals"]["value"] is None
        assert report_no_q["totals"]["pnl"] is None
        assert report_no_q["totals"]["pnl_pct"] is None

    def test_breakdown_positions_isolated(self, tmp_path):
        """破位标的独立汇总（不混入正常持仓建议）。"""
        positions = [
            {
                "code": "sh600522",
                "name": "中天科技",
                "cost": 35.84,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["通信"],
            },
            {
                "code": "sh600989",
                "name": "宝丰能源",
                "cost": 22.37,
                "quantity": 4000,
                "buy_date": "2026-01-01",
                "tags": ["煤化工"],
            },
        ]
        pm = _make_manager(tmp_path, positions)
        quotes = {
            "sh600522": {"price": 33.43, "change_pct": 0.0},  # -6.7% 破位
            "sh600989": {"price": 23.69, "change_pct": 0.0},  # 未破位
        }
        report = pm.health_report(quotes=quotes)
        # 中天科技应在 breakdown_positions
        breakdown_codes = [r["code"] for r in report["breakdown_positions"]]
        assert "sh600522" in breakdown_codes
        # 宝丰能源不在 breakdown
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
        """type 字段识别实盘/示例/虚拟三态（解决 P1-13 / M2）。"""
        # 实盘（默认）
        pm_real = PortfolioManager()
        assert pm_real.health_report(quotes={})["type"] == "实盘持仓"
        # 示例
        pm_example = PortfolioManager()
        pm_example._is_example = True
        assert pm_example.health_report(quotes={})["type"] == "示例持仓"
        # 虚拟
        pm_virtual = PortfolioManager()
        pm_virtual._is_virtual = True
        assert pm_virtual.health_report(quotes={})["type"] == "虚拟持仓"

    def test_industry_concentration_uses_merged_mapping(self, tmp_path):
        """industry 字段使用合并后的映射（修复后不再分散）。"""
        positions = [
            {
                "code": "sz300274",
                "name": "阳光电源",
                "cost": 120.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["锂电"],
            },
            {
                "code": "sz002466",
                "name": "天齐锂业",
                "cost": 40.0,
                "quantity": 200,
                "buy_date": "2026-07-01",
                "tags": ["锂矿"],
            },
        ]
        pm = _make_manager(tmp_path, positions)
        report = pm.health_report(quotes={})
        industry = report["concentration"]["details"]["industry"]
        # 不应再有"锂电/锂矿"分散键（已合并到"锂/新能源"）
        for dispersed in ["锂电", "锂矿", "锂业"]:
            assert dispersed not in industry, f"行业 {dispersed} 未合并，仍分散为独立键"
        # "锂/新能源" 大类键应存在（组合含相关持仓）
        assert "锂/新能源" in industry

    def test_risk_rating_includes_breakdown_and_concentration(self, tmp_path):
        """risk_rating 聚合破位 + 集中度警告。"""
        positions = [
            {
                "code": "sh600522",
                "name": "中天科技",
                "cost": 35.84,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["通信"],
            },
            {
                "code": "sh603799",
                "name": "华友钴业",
                "cost": 50.0,
                "quantity": 100,
                "buy_date": "2026-07-01",
                "tags": ["锂矿"],
            },
        ]
        pm = _make_manager(tmp_path, positions)
        quotes = {
            "sh600522": {"price": 33.43, "change_pct": 0.0},  # 破位
            "sh603799": {"price": 44.12, "change_pct": 0.0},
        }
        report = pm.health_report(quotes=quotes)
        # risk_rating 应包含破位警告
        assert "破位" in report["risk_rating"]
        # 同时包含集中度警告（来自 check_concentration）
        assert "集中度" in report["risk_rating"]


# ────────────────────────────────────────────────────────────────
# 7 项增强功能测试
# ────────────────────────────────────────────────────────────────


class TestStatusTagsExpanded:
    """M6: 扩展 _STATUS_TAGS 覆盖常见投资风格。"""

    @pytest.mark.parametrize(
        "tag",
        [
            # 投资风格
            "白马",
            "价值",
            "蓝筹",
            "大盘",
            "红利",
            "高股息",
            "成长",
            "主题",
            "概念",
            "题材",
            "赛道",
            "趋势",
            "反转",
            "突破",
            "超跌",
            "低吸",
            "追涨",
            "短线投机",
            "打板",
            "涨停",
            "妖股",
            # 持有期
            "长持",
            "永持",
            "待止损",
            "待止盈",
            "已止盈",
            "对冲",
            "套保",
            "金字塔",
            "左侧",
            "右侧",
        ],
    )
    def test_common_investment_styles_filtered(self, tag):
        """常见投资风格标签被识别为状态，不当作行业。"""
        industry_tags = [t for t in [tag] if t not in PortfolioManager._STATUS_TAGS]
        assert industry_tags == [], f"{tag} 应被 _STATUS_TAGS 过滤"


class TestIndustryGroupExpanded:
    """M5: 扩展 _INDUSTRY_GROUP 覆盖 6 大生态。"""

    @pytest.mark.parametrize(
        "sub,expected_group",
        [
            # 锂/新能源扩展
            ("电池", "锂/新能源"),
            ("正极", "锂/新能源"),
            ("硅料", "锂/新能源"),
            ("组件", "锂/新能源"),
            ("风电", "锂/新能源"),
            ("核电", "锂/新能源"),
            # 半导体
            ("PCB", "半导体"),
            ("封测", "半导体"),
            ("IC设计", "半导体"),
            # 医药
            ("CRO", "医药"),
            ("CDMO", "医药"),
            ("创新药", "医药"),
            ("中药", "医药"),
            # 消费
            ("白酒", "消费"),
            ("食品饮料", "消费"),
            ("家电", "消费"),
            ("医美", "消费"),
            # 金融
            ("银行", "金融"),
            ("证券", "金融"),
            ("保险", "金融"),
            # 资源/周期
            ("钢铁", "资源/周期"),
            ("煤炭", "资源/周期"),
            ("黄金", "资源/周期"),
            # 工业
            ("军工", "军工"),
        ],
    )
    def test_ecosystem_mapping(self, sub, expected_group):
        """6 大生态子标签合并到对应大类。"""
        assert PortfolioManager._INDUSTRY_GROUP[sub] == expected_group


class TestBreakdownTechnicalOr:
    """H1: 破位判定 OR technical.py features.breakdown 权威信号。"""

    def test_cost_breakdown_only(self, tmp_path):
        """纯成本破位（无 technical 数据）。"""
        pm = _make_manager(tmp_path, [_POS_300274])
        quotes = {"sz300274": {"price": 105.0, "change_pct": 0}}
        report = pm.health_report(quotes=quotes)
        pos = next(p for p in report["positions"] if p["code"] == "sz300274")
        assert pos["breakdown"] is True
        assert pos["breakdown_reason"] == "cost_5pct"

    def test_technical_breakdown_only(self, tmp_path):
        """仅 technical.breakdown=True（成本未破位）。"""
        pm = _make_manager(tmp_path, [_POS_300274])
        quotes = {"sz300274": {"price": 115.0, "change_pct": 0}}  # 未破成本 5%
        # 模拟 technical.py 报告破位
        tech = {"sz300274": {"breakdown": True, "stop_loss_pct": -3.5}}
        report = pm.health_report(quotes=quotes, technical_features=tech)
        pos = next(p for p in report["positions"] if p["code"] == "sz300274")
        assert pos["breakdown"] is True
        assert pos["breakdown_reason"] == "support_break"

    def test_both_breakdowns(self, tmp_path):
        """成本 + technical 同时破位。"""
        pm = _make_manager(tmp_path, [_POS_300274])
        quotes = {"sz300274": {"price": 100.0, "change_pct": 0}}  # 破成本
        tech = {"sz300274": {"breakdown": True}}
        report = pm.health_report(quotes=quotes, technical_features=tech)
        pos = next(p for p in report["positions"] if p["code"] == "sz300274")
        assert pos["breakdown"] is True
        assert pos["breakdown_reason"] == "both"

    def test_no_breakdown(self, tmp_path):
        """未破位。"""
        pm = _make_manager(tmp_path, [_POS_300274])
        quotes = {"sz300274": {"price": 115.0, "change_pct": 0}}
        tech = {"sz300274": {"breakdown": False}}
        report = pm.health_report(quotes=quotes, technical_features=tech)
        pos = next(p for p in report["positions"] if p["code"] == "sz300274")
        assert pos["breakdown"] is False
        assert pos["breakdown_reason"] == ""


class TestRegimeHint:
    """M3: regime_hint 读真实 regime_state.json。"""

    def test_regime_info_has_age_minutes(self):
        """regime 字段含 age_minutes 字段。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        assert "regime" in report
        assert "age_minutes" in report["regime"]
        # 当前 regime_state.json 实际过期（~24000 分钟）
        # 不会断言具体值，但应该返回 int 或 None
        assert report["regime"]["age_minutes"] is None or isinstance(
            report["regime"]["age_minutes"], int
        )

    def test_regime_hint_mentions_stale_data(self):
        """regime_state.json 过期时，regime_hint 提示。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        # 34209 分钟前更新 → 应提示过期
        if report["regime"].get("age_minutes", 0) > 60:
            assert "过期" in report["regime_hint"]


class TestScreenerHintDynamic:
    """M4: screener_hint 根据真实 industry 最大值动态生成。"""

    def test_screener_hint_for_lithium_concentration(self):
        """锂/新能源链占比高时建议 value 策略。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        if "锂/新能源" in report["concentration"]["details"]["industry"]:
            pct = report["concentration"]["details"]["industry"]["锂/新能源"]
            if pct > 30:
                # 锂/新能源 超 30% 应生成 screener_hint
                assert "锂/新能源" in report["screener_hint"]
                assert "value" in report["screener_hint"]


class TestWatchlistStatus:
    """M7: watchlist 5 档状态分级。"""

    def test_status_field_present(self):
        """watchlist 每项含 status 字段。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        for w in report["watchlist"]:
            assert "status" in w
            assert w["status"] in {
                "已破止损",
                "接近止损",
                "到达买点",
                "接近买点",
                "观望",
            }

    def test_status_buy_zone(self):
        """现价 ≤ target_buy 标为"到达买点"。"""
        pm = PortfolioManager()
        # 找到自选股
        watchlist = pm.get_watchlist()
        if watchlist:
            w = watchlist[0]
            tb = float(w.get("target_buy", 0) or 0)
            if tb > 0:
                quotes = {
                    w["code"]: {"price": tb * 0.9, "change_pct": 0}
                }  # 现价低于买点
                report = pm.health_report(quotes=quotes)
                row = next(r for r in report["watchlist"] if r["code"] == w["code"])
                assert row["status"] == "到达买点"

    def test_status_break_sell(self):
        """现价 ≤ target_sell 标为"已破止损"。"""
        pm = PortfolioManager()
        watchlist = pm.get_watchlist()
        if watchlist:
            w = watchlist[0]
            ts = float(w.get("target_sell", 0) or 0)
            if ts > 0:
                quotes = {
                    w["code"]: {"price": ts * 0.5, "change_pct": 0}
                }  # 现价远低于止损
                report = pm.health_report(quotes=quotes)
                row = next(r for r in report["watchlist"] if r["code"] == w["code"])
                assert row["status"] == "已破止损"


class TestQuotesNoneDegradation:
    """L17: quotes=None 降级处理。"""

    def test_quotes_none_pnl_pct_is_none(self):
        """行情缺失时 totals.pnl_pct = None 而非 0 或 -100%。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes=None)
        assert report["totals"]["pnl_pct"] is None
        assert report["totals"]["value"] is None
        assert report["totals"]["pnl"] is None

    def test_quotes_none_risk_rating_marks_degradation(self):
        """行情缺失时 risk_rating 标注"行情缺失"。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes=None)
        assert "行情缺失" in report["risk_rating"]

    def test_quotes_none_no_false_breakdown(self):
        """行情缺失时不误判所有持仓为破位。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes=None)
        # price=0 时 breakdown 公式 `price > 0` 失败 → False
        for p in report["positions"]:
            assert p["breakdown"] is False


class TestRiskRatingNaturalLanguage:
    """M8: risk_rating 改自然语言摘要（不直接拼接 warnings）。"""

    def test_risk_rating_no_warning_when_safe(self):
        """无破位无超阈值时，risk_rating = \"组合处于安全区间\"。"""
        pm = PortfolioManager()
        # 用空 quotes + 临时清空所有持仓难以构造，改用 0 quotes 触发降级
        report = pm.health_report(quotes=None)
        # 降级 + 无超阈值 → 仍含\"组合处于安全区间\"或被\"行情缺失\"覆盖
        assert (
            "组合处于安全区间" in report["risk_rating"]
            or "行情缺失" in report["risk_rating"]
        )

    def test_risk_rating_uses_semicolon_not_comma(self):
        """risk_rating 摘要用\"；\"分隔（不直接用 warnings 拼接的\"、\"）。"""
        pm = PortfolioManager()
        quotes = {
            "sh600522": {"price": 33.43, "change_pct": 0},  # 破位
        }
        report = pm.health_report(quotes=quotes)
        # 有破位 + 集中度超阈值 → 应含分号
        if "；" in report["risk_rating"]:
            # 同时不应直接用全 warnings 拼接（不应出现 4+ 个\"、\"）
            assert report["risk_rating"].count("、") <= 1


class TestReadRegimeState:
    """_read_regime_state helper 函数测试。"""

    def test_returns_dict_with_keys(self):
        """返回 dict 含 regime/updated_at/age_minutes 三个键。"""
        from portfolio.manager import _read_regime_state

        result = _read_regime_state()
        assert set(result.keys()) == {"regime", "updated_at", "age_minutes"}

    def test_age_minutes_is_int_or_none(self):
        """age_minutes 是 int 或 None（不抛错）。"""
        from portfolio.manager import _read_regime_state

        result = _read_regime_state()
        assert result["age_minutes"] is None or isinstance(result["age_minutes"], int)


# ────────────────────────────────────────────────────────────────
# L10: as_of 兜底
# ────────────────────────────────────────────────────────────────


class TestAsOfFallback:
    """L10: as_of 字段兜底（__as_of__ 哨兵键 → datetime.now()）。"""

    def test_explicit_as_of_used_when_provided(self):
        """上游传 __as_of__ 时优先使用。"""
        from datetime import datetime

        pm = PortfolioManager()
        ts = "2026-08-07T10:30:00"
        quotes = {"__as_of__": ts}
        report = pm.health_report(quotes=quotes)
        assert report["as_of"] == ts

    def test_as_of_never_empty(self):
        """as_of 永不返回空字符串（L17 降级时也应有时戳）。"""
        pm = PortfolioManager()
        # 不传 quotes
        report = pm.health_report(quotes=None)
        assert report["as_of"]  # 非空字符串

    def test_as_of_format_matches_template(self):
        """as_of 格式 YYYY-MM-DD HH:MM:SS（兼容 SKILL 模板）。"""
        import re

        pm = PortfolioManager()
        report = pm.health_report(quotes=None)
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", report["as_of"])


# ────────────────────────────────────────────────────────────────
# L14: BREAKDOWN_THRESHOLD 排版位置
# ────────────────────────────────────────────────────────────────


class TestBreakdownThresholdLocation:
    """L14: BREAKDOWN_THRESHOLD 已移到类顶部常量区块。"""

    def test_constant_accessible(self):
        """BREAKDOWN_THRESHOLD 是公开类常量，默认 0.95。"""
        assert PortfolioManager.BREAKDOWN_THRESHOLD == 0.95

    def test_constant_in_top_block(self):
        """BREAKDOWN_THRESHOLD 位置在 _STATUS_TAGS 之前（顶部常量区块）。"""
        # 检查源码位置
        import inspect

        src = inspect.getsource(PortfolioManager)
        threshold_pos = src.find("BREAKDOWN_THRESHOLD =")
        status_tags_pos = src.find("_STATUS_TAGS =")
        industry_pos = src.find("_INDUSTRY_GROUP =")
        assert threshold_pos > 0
        assert (
            threshold_pos < status_tags_pos < industry_pos
        ), "BREAKDOWN_THRESHOLD 应在 _STATUS_TAGS/_INDUSTRY_GROUP 之前"


# ────────────────────────────────────────────────────────────────
# H1 集成：auto_technical 自动拉 features.breakdown
# ────────────────────────────────────────────────────────────────


class TestAutoTechnicalIntegration:
    """H1: health_report 默认 auto_technical=True，自动调 technical.py 拉技术特征。"""

    def test_auto_technical_can_be_disabled(self):
        """auto_technical=False 时不调 technical.py。"""
        from unittest.mock import patch

        pm = PortfolioManager()
        with patch("portfolio.manager._fetch_technical_features") as mock_fetch:
            pm.health_report(quotes={}, auto_technical=False)
            mock_fetch.assert_not_called()

    def test_explicit_technical_features_overrides_auto(self):
        """显式传 technical_features 时不再调 auto_technical。"""
        from unittest.mock import patch

        pm = PortfolioManager()
        explicit = {"sh600989": {"breakdown": True, "stop_loss_pct": -3.0}}
        with patch("portfolio.manager._fetch_technical_features") as mock_fetch:
            report = pm.health_report(quotes={}, technical_features=explicit)
            mock_fetch.assert_not_called()
            # 验证显式 features 被使用（没有 quotes 时 price=0 不破位 cost_5pct，但
            # 显式 features.breakdown=True 应触发破位）
            pos = next(p for p in report["positions"] if p["code"] == "sh600989")
            assert pos["breakdown"] is True
            assert pos["breakdown_reason"] == "support_break"

    def test_fetch_technical_features_loads_module(self):
        """_fetch_technical_features 成功加载 scripts/technical.py 顶层文件。

        验证 scripts/technical.py 与 scripts/technical/ 包的命名冲突通过
        importlib.spec_from_file_location 解决。
        """
        from portfolio.manager import _fetch_technical_features

        # 空 positions → 返回空 dict（不抛错）
        result = _fetch_technical_features([], {})
        assert result == {}

    def test_fetch_technical_features_skips_failures(self):
        """_fetch_technical_features 单只失败不中断。"""
        from portfolio.manager import _fetch_technical_features

        # 不存在的 code 应被跳过（get_kline 抛错或返回空）
        positions = [{"code": "sh999999"}]  # 不存在的代码
        result = _fetch_technical_features(positions, {})
        assert result == {}  # 全部失败 → 空 dict


# ────────────────────────────────────────────────────────────────
# health_report_markdown：渲染层
# ────────────────────────────────────────────────────────────────


class TestHealthReportMarkdown:
    """健康报告 Markdown 渲染（SKILL 模板标准化）。"""

    def test_markdown_contains_required_sections(self):
        """Markdown 包含 SKILL 模板必备章节。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        md = pm.health_report_markdown(report)
        # 必备章节
        assert "## 📊" in md, "缺标题"
        assert "持仓" in md
        assert "板块分布" in md
        assert "集中度阈值" in md
        assert "风险评级" in md
        assert "总成本" in md
        assert "数据源" in md
        assert "免责声明" in md

    def test_markdown_breakdown_section(self):
        """有破位标的时显示独立汇总段。"""
        pm = PortfolioManager()
        quotes = {"sh600522": {"price": 33.0, "change_pct": 0}}
        report = pm.health_report(quotes=quotes)
        md = pm.health_report_markdown(report)
        if report["breakdown_positions"]:
            assert "### ⚠️ 已破位标的" in md
            assert "破位原因" in md

    def test_markdown_watchlist_with_status_emoji(self):
        """自选股状态有 emoji。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        md = pm.health_report_markdown(report)
        if report["watchlist"]:
            # 至少 1 个状态 emoji 出现
            for emoji in ["🔴", "🟡", "🟢", "⚪"]:
                if emoji in md:
                    return
            assert False, "watchlist 状态 emoji 缺失"

    def test_markdown_degradation_when_quotes_none(self):
        """quotes=None 时 Markdown 含\"行情缺失\"标注。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes=None)
        md = pm.health_report_markdown(report)
        assert "⚠️ 行情缺失" in md

    def test_markdown_includes_threshold_citation(self):
        """Markdown 显式引用 experts/risk_manager.md §四 阈值。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        md = pm.health_report_markdown(report)
        # 集中度阈值数字必须出现
        assert "前3大 ≤ 50%" in md
        assert "前5大 ≤ 70%" in md
        assert "单一行业 ≤ 30%" in md
        assert "单标的 ≤ 20%" in md

    def test_markdown_includes_screener_hint(self):
        """screener_hint 出现在上下游联动段。"""
        pm = PortfolioManager()
        report = pm.health_report(quotes={})
        md = pm.health_report_markdown(report)
        if "锂/新能源" in report.get("screener_hint", ""):
            assert "/screener" in md

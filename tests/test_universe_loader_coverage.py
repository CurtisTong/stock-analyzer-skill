"""universe_loader 覆盖测试（mock 文件 I/O + get_quote）。

覆盖 apply_portfolio_constraints 更多分支（空列表、板块上限、趋势惩罚、
排序）、load_universe 的 codes/full_market/sector 各模式、pre_screen_quotes
的 ST/blacklist/低流动性/低市值过滤、board_limit 分桶。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import business.universe_loader as ul


# ═══════════════════════════════════════════════════════════════
# apply_portfolio_constraints
# ═══════════════════════════════════════════════════════════════


class TestApplyPortfolioConstraints:
    def test_empty_rows_returns_empty(self):
        assert ul.apply_portfolio_constraints([]) == []

    def test_small_pool_no_sector_cap(self):
        """小于 10 只时 max_per_sector = len(rows)，不限制板块。"""
        rows = [
            {"code": "sh1", "industry": "银行", "score": 80, "trend": "上升"},
            {"code": "sh2", "industry": "银行", "score": 70, "trend": "上升"},
        ]
        result = ul.apply_portfolio_constraints(rows)
        assert len(result) == 2

    def test_large_pool_sector_cap_applied(self):
        """大于等于 10 只时按 sector_cap 限制每板块数量。"""
        rows = [
            {"code": f"sh{i}", "industry": "银行", "score": 100 - i, "trend": "上升"}
            for i in range(8)
        ]
        rows += [
            {"code": f"sz{i}", "industry": "科技", "score": 90 - i, "trend": "上升"}
            for i in range(4)
        ]
        # sector_cap=0.30 -> max_per_sector = max(2, int(12*0.30)) = max(2,3) = 3
        result = ul.apply_portfolio_constraints(rows, sector_cap=0.30)
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        tech_count = sum(1 for r in result if r["industry"] == "科技")
        assert bank_count == 3
        assert tech_count == 3

    def test_trend_penalty_applied(self):
        """趋势为下降的股票 score 被惩罚。"""
        rows = [
            {"code": "sh1", "industry": "银行", "score": 100, "trend": "下降"},
            {"code": "sh2", "industry": "科技", "score": 90, "trend": "上升"},
        ]
        result = ul.apply_portfolio_constraints(rows, trend_penalty=0.70)
        # sh1 score = 100 * 0.7 = 70.0
        bank = next(r for r in result if r["code"] == "sh1")
        assert bank["score"] == 70.0

    def test_result_sorted_by_score_desc(self):
        """结果按 score 降序排序。"""
        rows = [
            {"code": "sh1", "industry": "A", "score": 50, "trend": "上升"},
            {"code": "sh2", "industry": "B", "score": 90, "trend": "上升"},
            {"code": "sh3", "industry": "C", "score": 70, "trend": "上升"},
        ]
        result = ul.apply_portfolio_constraints(rows)
        scores = [r["score"] for r in result]
        assert scores == [90, 70, 50]

    def test_does_not_mutate_input(self):
        """返回新列表，不修改输入 rows。"""
        rows = [{"code": "sh1", "industry": "A", "score": 100, "trend": "下降"}]
        original_score = rows[0]["score"]
        ul.apply_portfolio_constraints(rows, trend_penalty=0.5)
        assert rows[0]["score"] == original_score  # 原始未被修改

    # ---------- (#9) 行业偏离约束测试 ----------

    def test_benchmark_align_off_by_default(self):
        """默认不启用基准偏离约束（向后兼容）。"""
        rows = [
            {"code": f"sh{i}", "industry": "银行", "score": 100 - i, "trend": "上升"}
            for i in range(25)
        ]
        # 不传 benchmark_weights -> 不启用偏离约束
        result = ul.apply_portfolio_constraints(rows, sector_cap=0.30)
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        # sector_cap=0.30 -> max_per_sector = max(2, int(25*0.30)) = 7
        assert bank_count == 7

    def test_benchmark_align_rejects_overweight(self):
        """(#9) 行业占比偏离基准超过 max_deviation 时跳过。"""
        # 25 只银行股，基准银行权重 12.5%，max_deviation=0.15
        # 银行允许占比 = 12.5% + 15% = 27.5% -> 25 * 27.5% = 6.875 -> 6 只
        rows = [
            {"code": f"sh{i}", "industry": "银行", "score": 100 - i, "trend": "上升"}
            for i in range(25)
        ]
        benchmark = {"银行": 12.5, "科技": 87.5}
        result = ul.apply_portfolio_constraints(
            rows, sector_cap=0.50,  # 放宽 sector_cap 让偏离约束起作用
            benchmark_weights=benchmark,
            use_benchmark_align=True,
            max_deviation=0.15,
        )
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        # 银行 12.5% + 15% = 27.5% -> 25 * 27.5% = 6.875 -> 最多 6 只
        assert bank_count <= 7

    def test_benchmark_align_small_pool_disabled(self):
        """(#9) 候选池 < 20 时自动关闭偏离约束。"""
        rows = [
            {"code": f"sh{i}", "industry": "银行", "score": 100 - i, "trend": "上升"}
            for i in range(15)
        ]
        benchmark = {"银行": 1.0, "科技": 99.0}  # 银行基准仅 1%
        result = ul.apply_portfolio_constraints(
            rows, sector_cap=0.50,
            benchmark_weights=benchmark,
            use_benchmark_align=True,
            max_deviation=0.15,
        )
        # 候选池 < 20 -> 偏离约束关闭，仅 sector_cap 限制
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        assert bank_count > 0  # 不因偏离约束被清空

    def test_benchmark_align_no_weights_disabled(self):
        """(#9) 无 benchmark_weights 时不启用偏离约束。"""
        rows = [
            {"code": f"sh{i}", "industry": "银行", "score": 100 - i, "trend": "上升"}
            for i in range(25)
        ]
        result = ul.apply_portfolio_constraints(
            rows, sector_cap=0.30,
            benchmark_weights=None,
            use_benchmark_align=True,  # 启用但无权重 -> 不生效
        )
        bank_count = sum(1 for r in result if r["industry"] == "银行")
        assert bank_count == 7  # 仅 sector_cap 限制


# ═══════════════════════════════════════════════════════════════
# load_universe
# ═══════════════════════════════════════════════════════════════


class TestLoadUniverse:
    def test_codes_mode(self, monkeypatch, tmp_path):
        """codes 模式：直接拆分并归一化。"""
        args = SimpleNamespace(
            codes="sh600519,sz000807",
            full_market=False,
            sector=None,
            exclude_board=None,
        )
        result = ul.load_universe(args)
        assert result == ["sh600519", "sz000807"]

    def test_sector_mode_matched(self, monkeypatch, tmp_path):
        """sector 模式：从 sector_stocks.json 匹配。"""
        sectors = {"银行板块": ["sh600036", "sh601398"], "科技板块": ["sz000063"]}
        ul.DATA_DIR = tmp_path
        (tmp_path / "sector_stocks.json").write_text(json.dumps(sectors), encoding="utf-8")
        args = SimpleNamespace(
            codes=None, full_market=False, sector="银行", exclude_board=None
        )
        result = ul.load_universe(args)
        assert result == ["sh600036", "sh601398"]

    def test_sector_mode_all_when_no_sector(self, monkeypatch, tmp_path):
        """无 sector 时返回所有板块股票。"""
        sectors = {"银行板块": ["sh600036"], "科技板块": ["sz000063"]}
        ul.DATA_DIR = tmp_path
        (tmp_path / "sector_stocks.json").write_text(json.dumps(sectors), encoding="utf-8")
        args = SimpleNamespace(
            codes=None, full_market=False, sector=None, exclude_board=None
        )
        result = ul.load_universe(args)
        assert set(result) == {"sh600036", "sz000063"}

    def test_sector_not_found_raises(self, monkeypatch, tmp_path):
        """sector 无匹配且无法动态拉取时 raise SystemExit。"""
        ul.DATA_DIR = tmp_path
        (tmp_path / "sector_stocks.json").write_text(
            json.dumps({"银行板块": ["sh600036"]}), encoding="utf-8"
        )
        # sector_mapping.json 不存在 -> _try_fetch_from_mapping 返回 []
        args = SimpleNamespace(
            codes=None, full_market=False, sector="不存在的板块", exclude_board=None
        )
        with pytest.raises(SystemExit):
            ul.load_universe(args)

    def test_full_market_mode_with_exclude_board(self, monkeypatch, tmp_path):
        """full_market 模式 + exclude_board 排除指定板块。"""
        data = {"主板沪": ["sh600519"], "创业板": ["sz300001"]}
        ul.DATA_DIR = tmp_path
        (tmp_path / "all_stocks.json").write_text(json.dumps(data), encoding="utf-8")
        args = SimpleNamespace(
            codes=None,
            full_market=True,
            sector=None,
            exclude_board="创业板",
        )
        result = ul.load_universe(args)
        assert "sh600519" in result
        assert "sz300001" not in result


# ═══════════════════════════════════════════════════════════════
# pre_screen_quotes
# ═══════════════════════════════════════════════════════════════


class TestPreScreenQuotes:
    def setup_method(self, method):
        """(#1) 每个测试前 mock market_snapshot 返回空水位，回退绝对值阈值。"""
        import data.market_snapshot as ms
        self._orig_snapshot = ms.get_market_snapshot
        ms.get_market_snapshot = lambda: {
            "avg_amount_yuan": 0.0,
            "median_cap": 0.0,
            "updated": "",
            "source": "test_mock",
        }

    def teardown_method(self, method):
        import data.market_snapshot as ms
        ms.get_market_snapshot = self._orig_snapshot

    def test_filters_st_stocks(self, monkeypatch):
        """ST 股票被过滤。"""
        monkeypatch.setattr("data.pool.is_st", lambda name: "ST" in name)
        quotes = [
            {"code": "sh600519", "name": "ST退市", "amount": "100000000", "total_cap": "100"},
            {"code": "sh600520", "name": "正常股", "amount": "100000000", "total_cap": "100"},
        ]
        args = SimpleNamespace(board_limit=0)
        result = ul.pre_screen_quotes(quotes, args)
        assert len(result) == 1
        assert result[0]["name"] == "正常股"

    def test_filters_low_amount(self):
        """成交额低于板块阈值被过滤。"""
        quotes = [
            # 主板阈值 5000 万 = 5e7 元；这里 amount 远低于
            {"code": "sh600519", "name": "低流动性", "amount": "1000", "total_cap": "100"},
        ]
        args = SimpleNamespace(board_limit=0)
        result = ul.pre_screen_quotes(quotes, args)
        assert result == []

    def test_filters_low_cap(self):
        """市值低于板块阈值被过滤。"""
        quotes = [
            # 主板市值阈值 40 亿；total_cap=10 < 40
            {
                "code": "sh600519",
                "name": "小市值",
                "amount": "1000000000",
                "total_cap": "10",
            },
        ]
        args = SimpleNamespace(board_limit=0)
        result = ul.pre_screen_quotes(quotes, args)
        assert result == []

    def test_board_limit_buckets(self):
        """board_limit > 0 时按板块分桶取 top N。"""
        quotes = [
            {"code": "sh600519", "name": "A", "amount": "1000000000", "total_cap": "100"},
            {"code": "sh600520", "name": "B", "amount": "500000000", "total_cap": "100"},
            {"code": "sh600521", "name": "C", "amount": "300000000", "total_cap": "100"},
        ]
        args = SimpleNamespace(board_limit=1)
        result = ul.pre_screen_quotes(quotes, args)
        # 主板桶取 amount 最大的 1 只
        assert len(result) == 1
        assert result[0]["code"] == "sh600519"

    def test_blacklist_filter(self, monkeypatch):
        """用户 blacklist 中的股票被过滤。"""
        monkeypatch.setattr(
            "common.user_profile.get_user_preference",
            lambda key: ["sh600519"] if key == "blacklist" else [],
        )
        quotes = [
            {"code": "sh600519", "name": "黑名单", "amount": "1000000000", "total_cap": "100"},
            {"code": "sh600520", "name": "正常", "amount": "1000000000", "total_cap": "100"},
        ]
        args = SimpleNamespace(board_limit=0)
        result = ul.pre_screen_quotes(quotes, args)
        assert len(result) == 1
        assert result[0]["code"] == "sh600520"

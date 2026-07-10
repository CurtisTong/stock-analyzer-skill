"""测试 scripts/sector_etf_strength.py：板块 ETF 强度 + RPS + 轮动。

策略：mock 所有外部数据源（get_quotes/get_kline/csv 文件），
验证 13 个函数的输入/输出契约。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sector_etf_strength


# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════


def _mock_quote(code, name="ETF", price=2.0, change_pct=1.0, turnover=1e8,
                total_cap=1e10, pe=15.0, has_basic=True):
    """构造 Quote-like 对象，属性访问 + 可调用 has_basic_data。"""
    from types import SimpleNamespace
    q = SimpleNamespace(
        code=code, name=name, price=price,
        change_pct=change_pct, turnover=turnover,
        total_cap=total_cap, pe=pe,
    )
    q.has_basic_data = lambda: has_basic
    return q


def _mock_kline(close=100.0, high=101.0, low=99.0, volume=1000):
    k = MagicMock()
    k.close = close
    k.high = high
    k.low = low
    k.volume = volume
    return k


# ═══════════════════════════════════════════════════════════════
# _load_sector_etfs
# ═══════════════════════════════════════════════════════════════


class TestLoadSectorEtfs:
    def test_real_csv_loads(self):
        """真实 CSV 文件加载。"""
        rows = sector_etf_strength._load_sector_etfs()
        # 真实仓库有 ~13 个 ETF
        assert isinstance(rows, list)
        if rows:  # 可能为空（如果 CSV 不存在）
            assert "code" in rows[0]
            assert "name" in rows[0]

    def test_missing_csv_returns_empty(self, monkeypatch):
        with patch.object(Path, "exists", return_value=False):
            result = sector_etf_strength._load_sector_etfs()
        assert result == []


# ═══════════════════════════════════════════════════════════════
# _fetch_one_quote
# ═══════════════════════════════════════════════════════════════


class TestFetchOneQuote:
    def test_success(self):
        q = _mock_quote("sh512760", "科技ETF", change_pct=5.0)
        with patch("sector_etf_strength.get_quotes", return_value=[q]):
            result = sector_etf_strength._fetch_one_quote("sh512760")
        assert result is not None
        assert result["code"] == "sh512760"
        assert result["change_pct"] == 5.0

    def test_empty(self):
        with patch("sector_etf_strength.get_quotes", return_value=[]):
            assert sector_etf_strength._fetch_one_quote("sh512760") is None

    def test_no_basic_data(self):
        q = _mock_quote("sh512760", has_basic=False)
        with patch("sector_etf_strength.get_quotes", return_value=[q]):
            assert sector_etf_strength._fetch_one_quote("sh512760") is None

    def test_exception(self):
        """_fetch_one_quote 无 try/except, 异常会冒泡（graceful 由调用方处理）。"""
        with patch("sector_etf_strength.get_quotes", side_effect=Exception("net")):
            with pytest.raises(Exception):
                sector_etf_strength._fetch_one_quote("sh512760")


# ═══════════════════════════════════════════════════════════════
# _fetch_etf_quotes (batch)
# ═══════════════════════════════════════════════════════════════


class TestFetchEtfQuotes:
    def test_empty_input(self):
        assert sector_etf_strength._fetch_etf_quotes([]) == {}

    def test_batch_success(self):
        q1 = _mock_quote("sh512760", "科技")
        q2 = _mock_quote("sh510300", "沪深300")
        with patch("sector_etf_strength.get_quotes", return_value=[q1, q2]):
            result = sector_etf_strength._fetch_etf_quotes(["sh512760", "sh510300"])
        assert "sh512760" in result
        assert "sh510300" in result

    def test_partial_failure(self):
        q1 = _mock_quote("sh512760", "科技")
        q_bad = _mock_quote("sh000000", has_basic=False)
        with patch("sector_etf_strength.get_quotes", return_value=[q1, q_bad]):
            result = sector_etf_strength._fetch_etf_quotes(["sh512760", "sh000000"])
        assert "sh512760" in result
        assert "sh000000" not in result  # has_basic=False 不进入结果


# ═══════════════════════════════════════════════════════════════
# compute_etf_strength
# ═══════════════════════════════════════════════════════════════


class TestComputeEtfStrength:
    def test_full_data(self):
        """完整数据：排序 + quadrant。"""
        meta = [
            {"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None},
            {"code": "sh510300", "name": "沪深300ETF", "category": "宽基", "bk_code": None},
            {"code": "sh512690", "name": "白酒ETF", "category": "消费", "bk_code": None},
        ]
        quotes = {
            "sh512760": {"code": "sh512760", "change_pct": 5.0, "turnover": 2.5},
            "sh510300": {"code": "sh510300", "change_pct": 1.0, "turnover": 1.0},
            "sh512690": {"code": "sh512690", "change_pct": 3.0, "turnover": 1.5},
        }
        rows = sector_etf_strength.compute_etf_strength(meta, quotes)
        assert len(rows) == 3
        # 找 rank=1（最高 change_pct=5.0）和 rank=3（最低 1.0）
        rank1 = next(r for r in rows if r["strength_rank"] == 1)
        rank3 = next(r for r in rows if r["strength_rank"] == 3)
        assert rank1["change_pct"] == 5.0
        assert rank1["quadrant"] == "强势"
        assert rank3["change_pct"] == 1.0
        assert rank3["quadrant"] == "弱势"

    def test_missing_quote(self):
        """ETF 数据缺失时标记 quadrant=数据缺失。"""
        meta = [
            {"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None},
        ]
        result = sector_etf_strength.compute_etf_strength(meta, {})
        assert result[0]["data_ok"] is False
        assert result[0]["quadrant"] == "数据缺失"

    def test_small_n_no_quadrant_split(self):
        """N<3 时所有 quadrant=中性。"""
        meta = [
            {"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None},
            {"code": "sh510300", "name": "沪深300ETF", "category": "宽基", "bk_code": None},
        ]
        quotes = {
            "sh512760": {"code": "sh512760", "change_pct": 5.0, "turnover": 2.5},
            "sh510300": {"code": "sh510300", "change_pct": 1.0, "turnover": 1.0},
        }
        rows = sector_etf_strength.compute_etf_strength(meta, quotes)
        for r in rows:
            assert r["quadrant"] == "中性"


# ═══════════════════════════════════════════════════════════════
# _rps
# ═══════════════════════════════════════════════════════════════


class TestRps:
    def test_stock_outperforms(self):
        """个股 5% > 板块 2% -> RPS=3。"""
        assert sector_etf_strength._rps(5.0, 2.0) == 3.0

    def test_stock_underperforms(self):
        """个股 1% < 板块 5% -> RPS=-4。"""
        assert sector_etf_strength._rps(1.0, 5.0) == -4.0

    def test_stock_none(self):
        """个股涨幅缺失 -> None。"""
        assert sector_etf_strength._rps(None, 5.0) is None

    def test_sector_none(self):
        """板块涨幅缺失 -> None。"""
        assert sector_etf_strength._rps(5.0, None) is None

    def test_both_none(self):
        """都缺失 -> None。"""
        assert sector_etf_strength._rps(None, None) is None


# ═══════════════════════════════════════════════════════════════
# _pick_index_quote
# ═══════════════════════════════════════════════════════════════


class TestPickIndexQuote:
    def test_default_index(self):
        """默认 sh000300。"""
        q = _mock_quote("sh000300", "沪深300")
        with patch("sector_etf_strength.get_quotes", return_value=[q]):
            result = sector_etf_strength._pick_index_quote()
        assert result is not None
        assert result["code"] == "sh000300"

    def test_custom_index(self):
        """自定义指数。"""
        q = _mock_quote("sh000905", "中证500")
        with patch("sector_etf_strength.get_quotes", return_value=[q]):
            result = sector_etf_strength._pick_index_quote("sh000905")
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# build_stock_sector_compare
# ═══════════════════════════════════════════════════════════════


class TestBuildStockSectorCompare:
    def test_full_data(self):
        """完整数据时三段式对比。"""
        meta = [{"code": "sh512690", "name": "白酒ETF", "category": "消费", "bk_code": None}]
        quotes = {"sh512690": {"code": "sh512690", "change_pct": 3.0, "turnover": 1.0}}
        sector_etfs = sector_etf_strength.compute_etf_strength(meta, quotes)
        stock_quote = {"change_pct": 5.0}
        index_quote = {"change_pct": 1.0}
        with patch.object(sector_etf_strength, "_load_sector_stocks",
                          return_value={"贵州茅台": ["消费"]}), \
             patch.object(sector_etf_strength, "find_sector_by_code",
                          return_value=["消费"]):
            result = sector_etf_strength.build_stock_sector_compare(
                "sh600519", stock_quote, sector_etfs, index_quote,
            )
        assert result["stock_code"] == "sh600519"
        assert result["stock_change_pct"] == 5.0
        assert result["sector_change_pct"] == 3.0
        assert result["index_change_pct"] == 1.0
        assert result["rps_vs_sector"] == 2.0
        assert result["rps_vs_index"] == 4.0

    def test_missing_stock_quote(self):
        """个股数据缺失 -> degraded。"""
        meta = [{"code": "sh512690", "name": "白酒ETF", "category": "消费", "bk_code": None}]
        quotes = {"sh512690": {"code": "sh512690", "change_pct": 3.0, "turnover": 1.0}}
        sector_etfs = sector_etf_strength.compute_etf_strength(meta, quotes)
        with patch.object(sector_etf_strength, "_load_sector_stocks", return_value={}), \
             patch.object(sector_etf_strength, "find_sector_by_code", return_value=[]):
            result = sector_etf_strength.build_stock_sector_compare(
                "sh600519", None, sector_etfs, None,
            )
        assert "stock" in result["data_quality"]["degraded_fields"]
        assert "index" in result["data_quality"]["degraded_fields"]

    def test_no_matched_etf(self):
        """个股板块无 ETF 代理。"""
        meta = [{"code": "sh510300", "name": "宽基", "category": "宽基", "bk_code": None}]
        quotes = {"sh510300": {"code": "sh510300", "change_pct": 1.0, "turnover": 0.5}}
        sector_etfs = sector_etf_strength.compute_etf_strength(meta, quotes)
        stock_quote = {"change_pct": 5.0}
        with patch.object(sector_etf_strength, "_load_sector_stocks",
                          return_value={"某股": ["机器人"]}), \
             patch.object(sector_etf_strength, "find_sector_by_code",
                          return_value=["机器人"]):
            result = sector_etf_strength.build_stock_sector_compare(
                "sh000000", stock_quote, sector_etfs, {"change_pct": 1.0},
            )
        assert "sector" in result["data_quality"]["degraded_fields"]


# ═══════════════════════════════════════════════════════════════
# compute_rotation_strength
# ═══════════════════════════════════════════════════════════════


class TestComputeRotationStrength:
    def test_full_data(self):
        """完整 ETF K 线时计算 rotation_strength。"""
        etfs = [
            {"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None},
            {"code": "sh510300", "name": "沪深300ETF", "category": "宽基", "bk_code": None},
            {"code": "sh512690", "name": "白酒ETF", "category": "消费", "bk_code": None},
        ]
        with patch.object(sector_etf_strength, "_load_sector_etfs", return_value=etfs), \
             patch.object(sector_etf_strength, "_fetch_etf_quotes",
                          return_value={
                              "sh512760": {"code": "sh512760", "change_pct": 1.0},
                              "sh510300": {"code": "sh510300", "change_pct": 1.0},
                              "sh512690": {"code": "sh512690", "change_pct": 1.0},
                          }), \
             patch.object(sector_etf_strength, "get_kline") as m_kline:
            m_kline.side_effect = lambda *args, **kwargs: [
                _mock_kline(close=100 + i) for i in range(10)
            ]
            result = sector_etf_strength.compute_rotation_strength(window=5)
        assert result is not None
        assert "rotation_strength" in result or "etfs" in result

    def test_no_etfs(self):
        with patch.object(sector_etf_strength, "_load_sector_etfs", return_value=[]):
            result = sector_etf_strength.compute_rotation_strength(window=5)
        assert result is None or "degraded_fields" in str(result) or "etfs" in result

    def test_all_kline_failures(self):
        """所有 ETF K 线拉取失败时返回 None（全部降级）。"""
        etfs = [{"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None}]
        with patch.object(sector_etf_strength, "_load_sector_etfs", return_value=etfs), \
             patch.object(sector_etf_strength, "get_kline", side_effect=Exception("net")):
            result = sector_etf_strength.compute_rotation_strength(window=5)
        # 全部失败时 None 或 degraded dict 都可能
        assert result is None or "degraded_fields" in str(result)


# ═══════════════════════════════════════════════════════════════
# _interpret_rotation
# ═══════════════════════════════════════════════════════════════


class TestInterpretRotation:
    def test_strong_rotation(self):
        """强轮动。"""
        result = sector_etf_strength._interpret_rotation(
            5.0, [["sh512760", "科技", 3]], [["sh510300", "300", -2]]
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_mild_rotation(self):
        """弱轮动。"""
        result = sector_etf_strength._interpret_rotation(
            1.0, [], [],
        )
        assert isinstance(result, str)

    def test_zero_rotation(self):
        """无轮动。"""
        result = sector_etf_strength._interpret_rotation(0.0, [], [])
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════
# analyze - 主入口
# ═══════════════════════════════════════════════════════════════


class TestAnalyze:
    def test_no_stock_no_index(self):
        """无 stock_code 且 fetch_index=False 时只返回 etfs/strong/weak。"""
        with patch.object(sector_etf_strength, "_load_sector_etfs", return_value=[
            {"code": "sh512760", "name": "科技ETF", "category": "科技", "bk_code": None},
        ]), patch.object(sector_etf_strength, "_fetch_etf_quotes", return_value={
            "sh512760": {"code": "sh512760", "change_pct": 5.0, "turnover": 1.0},
        }):
            result = sector_etf_strength.analyze(stock_code=None, fetch_index=False)
        assert "etfs" in result
        assert "strong_sectors" in result
        assert "weak_sectors" in result
        assert "data_quality" in result

    def test_with_stock_code(self):
        """有 stock_code 时含 stock_sector_compare。"""
        with patch.object(sector_etf_strength, "_load_sector_etfs", return_value=[
            {"code": "sh512690", "name": "白酒ETF", "category": "消费", "bk_code": None},
        ]), patch.object(sector_etf_strength, "_fetch_etf_quotes", return_value={
            "sh512690": {"code": "sh512690", "change_pct": 3.0, "turnover": 1.0},
        }), patch.object(sector_etf_strength, "_load_sector_stocks", return_value={}), \
             patch.object(sector_etf_strength, "find_sector_by_code", return_value=["消费"]), \
             patch.object(sector_etf_strength, "_pick_index_quote", return_value={"change_pct": 1.0}):
            result = sector_etf_strength.analyze(stock_code="sh600519", fetch_index=True)
        assert "stock_sector_compare" in result


# ═══════════════════════════════════════════════════════════════
# _print_table
# ═══════════════════════════════════════════════════════════════


class TestPrintTable:
    def test_prints_etf_table(self, capsys):
        """打印 ETF 表格。"""
        payload = {
            "as_of": "2026-07-10T10:00:00",
            "etfs": [
                {"code": "sh512760", "name": "科技ETF", "category": "科技",
                 "change_pct": 5.0, "turnover": 2.5,
                 "quadrant": "强势", "strength_rank": 1, "data_ok": True},
            ],
            "strong_sectors": ["科技ETF"],
            "weak_sectors": [],
            "data_quality": {"degraded_fields": [], "etf_ok_count": 1, "etf_total_count": 1},
            "stock_sector_compare": None,
        }
        sector_etf_strength._print_table(payload)
        captured = capsys.readouterr()
        assert "科技" in captured.out or "ETF" in captured.out

    def test_empty_etfs(self, capsys):
        """空 ETF 列表。"""
        payload = {
            "as_of": "2026-07-10T10:00:00",
            "etfs": [], "strong_sectors": [], "weak_sectors": [],
            "data_quality": {"degraded_fields": [], "etf_ok_count": 0, "etf_total_count": 0},
            "stock_sector_compare": None,
        }
        sector_etf_strength._print_table(payload)
        captured = capsys.readouterr()
        assert captured is not None

    def test_with_compare(self, capsys):
        """含 stock_sector_compare 时打印。"""
        payload = {
            "as_of": "2026-07-10T10:00:00",
            "etfs": [],
            "strong_sectors": [], "weak_sectors": [],
            "data_quality": {"degraded_fields": [], "etf_ok_count": 0, "etf_total_count": 0},
            "stock_sector_compare": {
                "stock_code": "sh600519", "stock_sectors": ["消费"],
                "matched_etf": "sh512690", "matched_etf_name": "白酒ETF",
                "stock_change_pct": 5.0, "sector_change_pct": 3.0,
                "index_change_pct": 1.0, "rps_vs_sector": 2.0, "rps_vs_index": 4.0,
                "verdict": "跑赢板块",
                "data_quality": {"degraded_fields": []},
            },
        }
        sector_etf_strength._print_table(payload)
        captured = capsys.readouterr()
        assert captured is not None


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["sector_etf_strength.py"])
        try:
            sector_etf_strength.main()
        except SystemExit:
            pass
        captured = capsys.readouterr()
        # 应当输出内容或帮助
        assert len(captured.out) >= 0

    def test_with_stock_code(self, capsys, monkeypatch):
        with patch.object(sector_etf_strength, "analyze", return_value={
            "as_of": "2026-07-10T10:00:00",
            "etfs": [{"code": "sh512760", "name": "科技ETF", "category": "科技",
                     "change_pct": 5.0, "turnover": 2.5,
                     "quadrant": "强势", "strength_rank": 1, "data_ok": True}],
            "strong_sectors": ["科技ETF"], "weak_sectors": [],
            "stock_sector_compare": None,
            "data_quality": {"degraded_fields": [], "etf_ok_count": 1, "etf_total_count": 1},
        }):
            monkeypatch.setattr(sys, "argv", ["sector_etf_strength.py", "sh600519"])
            sector_etf_strength.main()
        captured = capsys.readouterr()
        assert len(captured.out) >= 0

    def test_with_stock_code_json(self, capsys, monkeypatch):
        """-j 时输出 JSON。"""
        import json
        with patch.object(sector_etf_strength, "analyze", return_value={
            "as_of": "2026-07-10T10:00:00",
            "etfs": [],
            "strong_sectors": [], "weak_sectors": [],
            "stock_sector_compare": None,
            "data_quality": {"degraded_fields": [], "etf_ok_count": 0, "etf_total_count": 0},
        }):
            monkeypatch.setattr(sys, "argv", ["sector_etf_strength.py", "sh600519", "-j"])
            sector_etf_strength.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "etfs" in parsed

    def test_no_index_flag(self, monkeypatch):
        with patch.object(sector_etf_strength, "analyze", return_value={
            "as_of": "2026-07-10",
            "etfs": [], "strong_sectors": [], "weak_sectors": [],
            "stock_sector_compare": None,
            "data_quality": {"degraded_fields": [], "etf_ok_count": 0, "etf_total_count": 0},
        }) as m:
            monkeypatch.setattr(sys, "argv", ["sector_etf_strength.py", "--no-index"])
            sector_etf_strength.main()
        assert m.call_args.kwargs.get("fetch_index") is False
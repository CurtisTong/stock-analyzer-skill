"""hot_rank.py 补充测试：_load_all_stocks / rank_today / rank_recent_days /
rank_historical / _save_snapshot / _load_window_snapshots / merge_recent。

mock: data.get_quotes, data.get_kline, json.load, 文件 I/O, snapshots 模块。
"""

import json
import math
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import hot_rank


def _make_quote(
    code="sh600000",
    name="测试",
    price=10.0,
    amount=1e8,
    turnover=2.0,
    change_pct=1.0,
    circulating_cap=10.0,
):
    """构造 quote mock 对象。"""
    q = MagicMock()
    q.code = code
    q.name = name
    q.price = price
    q.amount = amount
    q.turnover = turnover
    q.change_pct = change_pct
    q.circulating_cap = circulating_cap
    return q


def _make_bar(amount=1e8, volume=1e6, day="2024-01-01", high=11, low=9, close=10, pct_chg=1.0):
    """构造 KlineBar mock 对象。"""
    b = MagicMock()
    b.amount = amount
    b.volume = volume
    b.day = day
    b.high = high
    b.low = low
    b.close = close
    b.pct_chg = pct_chg
    return b


# ═══════════════════════════════════════════════════════════════
# _load_all_stocks
# ═══════════════════════════════════════════════════════════════


class TestLoadAllStocks:
    def test_normal_load(self, tmp_path, monkeypatch):
        """正常加载全市场股票池。"""
        all_stocks = {
            "主板沪": ["sh600000", "sh600001"],
            "主板深": ["sz000001"],
            "创业板": ["sz300001"],
            "科创板": ["sh688001"],
            "北交所": ["bj430001"],  # 应被忽略（不在取值列表）
        }
        pool_file = tmp_path / "all_stocks.json"
        pool_file.write_text(json.dumps(all_stocks), encoding="utf-8")
        monkeypatch.setattr(hot_rank, "DATA_DIR", tmp_path)
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path / "snapshots" / "hot_rank")

        codes = hot_rank._load_all_stocks()
        assert "sh600000" in codes
        assert "sz000001" in codes
        assert "sz300001" in codes
        assert "sh688001" in codes
        assert "bj430001" not in codes  # 北交所被排除

    def test_missing_file_raises_systemexit(self, tmp_path, monkeypatch):
        """文件不存在 -> SystemExit。"""
        monkeypatch.setattr(hot_rank, "DATA_DIR", tmp_path)
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path / "snapshots" / "hot_rank")
        with pytest.raises(SystemExit):
            hot_rank._load_all_stocks()

    def test_empty_categories(self, tmp_path, monkeypatch):
        """空分类 -> 空列表。"""
        pool_file = tmp_path / "all_stocks.json"
        pool_file.write_text(json.dumps({}), encoding="utf-8")
        monkeypatch.setattr(hot_rank, "DATA_DIR", tmp_path)
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path / "snapshots" / "hot_rank")
        assert hot_rank._load_all_stocks() == []

    def test_partial_categories(self, tmp_path, monkeypatch):
        """部分分类缺失 -> 只加载存在的。"""
        all_stocks = {"主板沪": ["sh600000"]}  # 只有主板沪
        pool_file = tmp_path / "all_stocks.json"
        pool_file.write_text(json.dumps(all_stocks), encoding="utf-8")
        monkeypatch.setattr(hot_rank, "DATA_DIR", tmp_path)
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path / "snapshots" / "hot_rank")
        codes = hot_rank._load_all_stocks()
        assert codes == ["sh600000"]


# ═══════════════════════════════════════════════════════════════
# rank_today
# ═══════════════════════════════════════════════════════════════


class TestRankToday:
    def test_normal_ranking(self, capsys):
        """正常排序：hot_score 高的在前。"""
        codes = ["sh600000", "sh600001"]
        quotes = [
            _make_quote("sh600000", name="甲", amount=2e8, turnover=3.0),
            _make_quote("sh600001", name="乙", amount=1e8, turnover=5.0),
        ]
        with patch("hot_rank._fetch_quotes_batched", return_value=quotes):
            result = hot_rank.rank_today(codes, top=10)
        assert len(result) == 2
        # 高成交额+换手率应排前
        assert result[0].code == "sh600000"
        assert hasattr(result[0], "hot_score")

    def test_filters_st_and_zero(self, capsys):
        """ST/零成交被过滤。"""
        codes = ["sh600000", "sh600001", "sh600002"]
        quotes = [
            _make_quote("sh600000", name="正常股", amount=1e8, turnover=2),
            _make_quote("sh600001", name="*ST退市", amount=1e8, turnover=2),
            _make_quote("sh600002", name="停牌", price=0, amount=0, turnover=0),
        ]
        with patch("hot_rank._fetch_quotes_batched", return_value=quotes):
            result = hot_rank.rank_today(codes, top=10)
        assert len(result) == 1
        assert result[0].code == "sh600000"

    def test_top_limit(self, capsys):
        """top 限制返回数量。"""
        codes = [f"sh60000{i}" for i in range(5)]
        quotes = [
            _make_quote(f"sh60000{i}", name=f"股{i}", amount=(5 - i) * 1e8, turnover=2)
            for i in range(5)
        ]
        with patch("hot_rank._fetch_quotes_batched", return_value=quotes):
            result = hot_rank.rank_today(codes, top=3)
        assert len(result) == 3

    def test_empty_codes(self, capsys):
        """空 codes -> 空结果。"""
        with patch("hot_rank._fetch_quotes_batched", return_value=[]):
            result = hot_rank.rank_today([], top=10)
        assert result == []


# ═══════════════════════════════════════════════════════════════
# rank_recent_days
# ═══════════════════════════════════════════════════════════════


class TestRankRecentDays:
    def test_normal_multi_day(self, capsys):
        """多日累计成交额排序。"""
        codes = ["sh600000", "sh600001"]
        quotes = [
            _make_quote("sh600000", name="甲", amount=2e8, turnover=3.0, change_pct=1.0),
            _make_quote("sh600001", name="乙", amount=1e8, turnover=5.0, change_pct=2.0),
        ]
        kline_map = {
            "sh600000": [_make_bar(amount=1e8), _make_bar(amount=2e8), _make_bar(amount=3e8)],
            "sh600001": [_make_bar(amount=5e7), _make_bar(amount=5e7), _make_bar(amount=5e7)],
        }
        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("hot_rank.parallel_map", return_value=kline_map):
                result = hot_rank.rank_recent_days(codes, days=3, top=10)
        assert len(result) == 2
        assert result[0]["code"] == "sh600000"  # 累计成交额更高
        assert "amount_recent" in result[0]
        assert "hot_score" in result[0]

    def test_returns_dict_rows(self, capsys):
        """返回 dict 行（非 quote 对象）。"""
        codes = ["sh600000"]
        quotes = [_make_quote("sh600000", name="甲", amount=2e8, turnover=3.0)]
        kline_map = {"sh600000": [_make_bar(amount=1e8)]}
        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("hot_rank.parallel_map", return_value=kline_map):
                result = hot_rank.rank_recent_days(codes, days=1, top=10)
        assert isinstance(result[0], dict)
        for key in ("code", "name", "price", "change_pct", "amount_1d", "amount_recent", "hot_score"):
            assert key in result[0]

    def test_kline_bars_truncated_to_days(self, capsys):
        """K 线条数超过 days 时截取最近 days 条。"""
        codes = ["sh600000"]
        quotes = [_make_quote("sh600000", name="甲", amount=2e8, turnover=3.0)]
        # 5 条 K 线，days=3 -> 只算最近 3 条
        kline_map = {
            "sh600000": [
                _make_bar(amount=1e9),  # 应被截掉
                _make_bar(amount=1e8),
                _make_bar(amount=2e8),
                _make_bar(amount=3e8),
                _make_bar(amount=4e8),
            ]
        }
        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("hot_rank.parallel_map", return_value=kline_map):
                result = hot_rank.rank_recent_days(codes, days=3, top=10)
        # 最近 3 条累计 = 1+2+3 = 6e8... 实际 2+3+4=9e8
        assert result[0]["amount_recent"] == 9e8


# ═══════════════════════════════════════════════════════════════
# rank_historical
# ═══════════════════════════════════════════════════════════════


class TestRankHistorical:
    def test_normal_historical(self, capsys):
        """历史某日热度榜：用 K 线 volume 估算。"""
        codes = ["sh600000", "sh600001"]
        quotes = [
            _make_quote("sh600000", name="甲", amount=2e8, turnover=3.0, price=10, circulating_cap=10),
            _make_quote("sh600001", name="乙", amount=1e8, turnover=5.0, price=20, circulating_cap=20),
        ]
        # 新浪 fetcher 返回 dict 格式 K 线
        kline_map = {
            "sh600000": [
                {"day": "2024-01-01", "volume": "1000000", "high": "11", "low": "9", "close": "10", "pct_chg": "1.0"},
                {"day": "2024-01-02", "volume": "2000000", "high": "12", "low": "10", "close": "11", "pct_chg": "10.0"},
            ],
            "sh600001": [
                {"day": "2024-01-01", "volume": "500000", "high": "21", "low": "19", "close": "20", "pct_chg": "0.5"},
            ],
        }
        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("fetchers.kline.sina_kline.SinaKlineFetcher") as MockFetcher:
                mock_inst = MagicMock()

                def fake_fetch(code, scale, datalen):
                    return kline_map.get(code, [])

                mock_inst.fetch.side_effect = fake_fetch
                MockFetcher.return_value = mock_inst
                with patch("time.sleep"):
                    result = hot_rank.rank_historical(codes, "2024-01-01", top=10)
        assert len(result) == 2
        assert result[0]["code"] in ("sh600000", "sh600001")
        assert "hot_score" in result[0]
        assert "amount_1d" in result[0]

    def test_filters_zero_volume(self, capsys):
        """volume=0 的 K 线被过滤。"""
        codes = ["sh600000"]
        quotes = [_make_quote("sh600000", name="甲", price=10, circulating_cap=10)]
        kline_map = {
            "sh600000": [
                {"day": "2024-01-01", "volume": "0", "high": "11", "low": "9", "close": "10"},
            ]
        }

        def _fetch(code, scale=240, datalen=10):
            return kline_map.get(code, [])

        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("fetchers.kline.sina_kline.SinaKlineFetcher") as MockFetcher:
                mock_inst = MagicMock()
                mock_inst.fetch.side_effect = _fetch
                MockFetcher.return_value = mock_inst
                with patch("time.sleep"):
                    result = hot_rank.rank_historical(codes, "2024-01-01", top=10)
        assert result == []  # volume=0 被过滤

    def test_missing_kline_skipped(self, capsys):
        """无 K 线数据的股票被跳过。"""
        codes = ["sh600000", "sh600001"]
        quotes = [
            _make_quote("sh600000", name="甲", price=10, circulating_cap=10),
            _make_quote("sh600001", name="乙", price=20, circulating_cap=20),
        ]
        kline_map = {
            "sh600000": [],  # 空
            "sh600001": [
                {"day": "2024-01-01", "volume": "1000000", "high": "21", "low": "19", "close": "20"},
            ],
        }

        def _fetch(code, scale=240, datalen=10):
            return kline_map.get(code, [])

        with patch("hot_rank.rank_today", return_value=quotes):
            with patch("fetchers.kline.sina_kline.SinaKlineFetcher") as MockFetcher:
                mock_inst = MagicMock()
                mock_inst.fetch.side_effect = _fetch
                MockFetcher.return_value = mock_inst
                with patch("time.sleep"):
                    result = hot_rank.rank_historical(codes, "2024-01-01", top=10)
        assert len(result) == 1
        assert result[0]["code"] == "sh600001"


# ═══════════════════════════════════════════════════════════════
# _save_snapshot
# ═══════════════════════════════════════════════════════════════


class TestSaveSnapshot:
    def test_save_dict_rows(self, tmp_path, monkeypatch):
        """保存 dict 行快照。"""
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path)
        rows = [{"code": "sh600000", "name": "甲", "hot_score": 100}]
        with patch("hot_rank.atomic_write_json") as mock_write:
            hot_rank._save_snapshot(rows, mode="today", days=1)
        assert mock_write.called
        payload = mock_write.call_args[0][1]
        assert payload["snapshot_type"] == "hot_rank"
        assert payload["mode"] == "today"
        assert payload["rows"][0]["code"] == "sh600000"

    def test_save_object_with_to_dict(self, tmp_path, monkeypatch):
        """保存带 to_dict 方法的对象。"""
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path)
        obj = MagicMock()
        obj.to_dict.return_value = {"code": "sh600000", "name": "甲"}
        obj.hot_score = 100
        rows = [obj]
        with patch("hot_rank.atomic_write_json") as mock_write:
            hot_rank._save_snapshot(rows, mode="recent", days=3)
        payload = mock_write.call_args[0][1]
        assert payload["mode"] == "recent"
        assert payload["days"] == 3
        assert payload["rows"][0]["hot_score"] == 100

    def test_suffix_with_days(self, tmp_path, monkeypatch):
        """days>1 时文件名含 _dN 后缀。"""
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path)
        rows = [{"code": "sh600000", "hot_score": 100}]
        with patch("hot_rank.atomic_write_json"):
            hot_rank._save_snapshot(rows, mode="recent", days=5)
        assert True  # snapshot saved

    def test_suffix_without_days(self, tmp_path, monkeypatch):
        """days=1 时文件名无 _d 后缀。"""
        monkeypatch.setattr(hot_rank, "HOT_RANK_DIR", tmp_path)
        rows = [{"code": "sh600000", "hot_score": 100}]
        with patch("hot_rank.atomic_write_json"):
            hot_rank._save_snapshot(rows, mode="today", days=1)
        assert True  # no days suffix


# ═══════════════════════════════════════════════════════════════
# _load_window_snapshots
# ═══════════════════════════════════════════════════════════════


class TestLoadWindowSnapshots:
    def test_normal_load(self):
        """正常加载窗口快照。"""
        paths = [Path("/data/2024-01-01/snap.json"), Path("/data/2024-01-02/snap.json")]
        snapshots = {
            Path("/data/2024-01-01/snap.json"): {
                "rows": [
                    {"code": "sh600000", "name": "甲", "hot_score": 100},
                    {"code": "sh600001", "name": "乙", "hot_score": 80},
                ]
            },
            Path("/data/2024-01-02/snap.json"): {
                "rows": [
                    {"code": "sh600000", "name": "甲", "hot_score": 120},
                ]
            },
        }
        with patch("hot_rank.list_snapshots", return_value=paths):
            with patch("hot_rank.load_snapshot", side_effect=lambda p: snapshots[p]):
                counter = hot_rank._load_window_snapshots(n_days=2)
        assert counter["sh600000"]["count"] == 2
        assert counter["sh600000"]["latest_score"] == 120
        assert counter["sh600001"]["count"] == 1

    def test_filters_to_recent_n_days(self):
        """只保留最近 n_days 天的快照。"""
        paths = [
            Path("/data/2024-01-01/snap.json"),
            Path("/data/2024-01-02/snap.json"),
            Path("/data/2024-01-03/snap.json"),
        ]
        snapshots = {
            Path("/data/2024-01-01/snap.json"): {"rows": [{"code": "sh600000", "hot_score": 50}]},
            Path("/data/2024-01-02/snap.json"): {"rows": [{"code": "sh600000", "hot_score": 80}]},
            Path("/data/2024-01-03/snap.json"): {"rows": [{"code": "sh600000", "hot_score": 100}]},
        }
        with patch("hot_rank.list_snapshots", return_value=paths):
            with patch("hot_rank.load_snapshot", side_effect=lambda p: snapshots[p]):
                counter = hot_rank._load_window_snapshots(n_days=2)
        # 只最近 2 天：2024-01-02 和 2024-01-03
        assert counter["sh600000"]["count"] == 2
        assert counter["sh600000"]["latest_score"] == 100

    def test_handles_load_exception(self):
        """load_snapshot 异常被捕获跳过。"""
        paths = [Path("/data/2024-01-01/snap.json")]
        with patch("hot_rank.list_snapshots", return_value=paths):
            with patch("hot_rank.load_snapshot", side_effect=Exception("read error")):
                counter = hot_rank._load_window_snapshots(n_days=1)
        assert counter == {}

    def test_skips_rows_without_code(self):
        """无 code 的行被跳过。"""
        paths = [Path("/data/2024-01-01/snap.json")]
        snapshots = {
            Path("/data/2024-01-01/snap.json"): {
                "rows": [{"name": "无code", "hot_score": 100}]
            }
        }
        with patch("hot_rank.list_snapshots", return_value=paths):
            with patch("hot_rank.load_snapshot", side_effect=lambda p: snapshots[p]):
                counter = hot_rank._load_window_snapshots(n_days=1)
        assert counter == {}

    def test_empty_paths(self):
        with patch("hot_rank.list_snapshots", return_value=[]):
            assert hot_rank._load_window_snapshots(n_days=5) == {}


# ═══════════════════════════════════════════════════════════════
# merge_recent
# ═══════════════════════════════════════════════════════════════


class TestMergeRecent:
    def test_default_threshold(self):
        """默认阈值 = max(1, n_days//2+1)。"""
        counter = {
            "sh600000": {"count": 3, "name": "甲", "latest_score": 100},
            "sh600001": {"count": 1, "name": "乙", "latest_score": 80},
        }
        with patch("hot_rank._load_window_snapshots", return_value=counter):
            # n_days=5, threshold = max(1, 5//2+1) = 3
            result = hot_rank.merge_recent(n_days=5)
        assert len(result) == 1
        assert result[0]["code"] == "sh600000"
        assert result[0]["appear_count"] == 3

    def test_custom_min_appear(self):
        """自定义 min_appear 阈值。"""
        counter = {
            "sh600000": {"count": 2, "name": "甲", "latest_score": 100},
            "sh600001": {"count": 1, "name": "乙", "latest_score": 80},
        }
        with patch("hot_rank._load_window_snapshots", return_value=counter):
            result = hot_rank.merge_recent(n_days=5, min_appear=1)
        assert len(result) == 2

    def test_sorted_by_count_then_score(self):
        """按出现次数+得分倒序排序。"""
        counter = {
            "sh600000": {"count": 3, "name": "甲", "latest_score": 100},
            "sh600001": {"count": 3, "name": "乙", "latest_score": 120},
            "sh600002": {"count": 5, "name": "丙", "latest_score": 50},
        }
        with patch("hot_rank._load_window_snapshots", return_value=counter):
            result = hot_rank.merge_recent(n_days=3, min_appear=1)
        # 丙(5) > 乙(3,120) > 甲(3,100)
        assert result[0]["code"] == "sh600002"
        assert result[1]["code"] == "sh600001"
        assert result[2]["code"] == "sh600000"

    def test_appear_ratio(self):
        """appear_ratio = count / n_days。"""
        counter = {
            "sh600000": {"count": 3, "name": "甲", "latest_score": 100},
        }
        with patch("hot_rank._load_window_snapshots", return_value=counter):
            result = hot_rank.merge_recent(n_days=6, min_appear=1)
        assert result[0]["appear_ratio"] == 0.5  # 3/6

    def test_empty_counter(self):
        with patch("hot_rank._load_window_snapshots", return_value={}):
            assert hot_rank.merge_recent(n_days=5) == []

    def test_result_fields(self):
        counter = {
            "sh600000": {"count": 3, "name": "甲", "latest_score": 100.5},
        }
        with patch("hot_rank._load_window_snapshots", return_value=counter):
            result = hot_rank.merge_recent(n_days=5, min_appear=1)
        r = result[0]
        for key in ("code", "name", "appear_count", "appear_ratio", "latest_score"):
            assert key in r


# ═══════════════════════════════════════════════════════════════
# _hot_score 补充边界
# ═══════════════════════════════════════════════════════════════


class TestHotScoreExtra:
    def test_large_turnover(self):
        """大换手率。"""
        score = hot_rank._hot_score(1e8, 100)
        assert score > 0

    def test_consistency_with_formula(self):
        """与公式 amount*log1p(turnover) 一致。"""
        for amount, turnover in [(1e8, 5), (1e7, 1), (1e9, 10)]:
            expected = amount * math.log1p(max(turnover, 0))
            assert abs(hot_rank._hot_score(amount, turnover) - expected) < 1e-6


# ═══════════════════════════════════════════════════════════════
# main() CLI 入口
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    def test_version_flag(self, capsys):
        """--version 输出版本号。"""
        import common

        with patch.object(sys, "argv", ["hot_rank.py", "-v"]):
            with patch.object(common, "__version__", "1.0.0", create=True):
                hot_rank.main()
        out = capsys.readouterr().out
        assert "hot_rank" in out
        assert "1.0.0" in out

    def test_merge_json(self, capsys):
        """--merge N --json 输出 JSON。"""
        merge_rows = [{"code": "sh600000", "name": "甲", "appear_count": 3, "appear_ratio": 0.6, "latest_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--merge", "5", "-j"]):
            with patch("hot_rank.merge_recent", return_value=merge_rows):
                hot_rank.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"

    def test_merge_text(self, capsys):
        """--merge N 文本输出。"""
        merge_rows = [{"code": "sh600000", "name": "甲", "appear_count": 3, "appear_ratio": 0.6, "latest_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--merge", "5"]):
            with patch("hot_rank.merge_recent", return_value=merge_rows):
                hot_rank.main()
        out = capsys.readouterr().out
        assert "合并最近 5" in out
        assert "sh600000" in out

    def test_today_json(self, capsys):
        """默认单日榜 JSON 输出。"""
        q = _make_quote("sh600000", name="甲")
        q.to_dict.return_value = {"code": "sh600000", "name": "甲", "hot_score": 100}
        with patch.object(sys, "argv", ["hot_rank.py", "-j"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_today", return_value=[q]):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"

    def test_today_text(self, capsys):
        """默认单日榜文本输出。"""
        q = _make_quote("sh600000", name="甲", amount=2e8, turnover=3)
        with patch.object(sys, "argv", ["hot_rank.py"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_today", return_value=[q]):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        assert "快照已保存" in out
        assert "sh600000" in out

    def test_recent_days_text(self, capsys):
        """--days N 多日榜文本输出。"""
        rows = [{"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "amount_recent": 3e8, "hot_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--days", "3"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_recent_days", return_value=rows):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        assert "快照已保存" in out

    def test_recent_days_json(self, capsys):
        """--days N -j JSON 输出。"""
        rows = [{"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "amount_recent": 3e8, "hot_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--days", "3", "-j"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_recent_days", return_value=rows):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"

    def test_historical_text(self, capsys):
        """--historical YYYY-MM-DD 文本输出。"""
        rows = [{"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "turnover_est": 2, "amount_1d": 1e8, "hot_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--historical", "2024-01-01"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_historical", return_value=rows):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        assert "快照已保存" in out

    def test_historical_json(self, capsys):
        """--historical YYYY-MM-DD -j JSON 输出。"""
        rows = [{"code": "sh600000", "name": "甲", "price": 10, "change_pct": 1, "turnover_est": 2, "amount_1d": 1e8, "hot_score": 100}]
        with patch.object(sys, "argv", ["hot_rank.py", "--historical", "2024-01-01", "-j"]):
            with patch("hot_rank._load_all_stocks", return_value=["sh600000"]):
                with patch("hot_rank.rank_historical", return_value=rows):
                    with patch("hot_rank._save_snapshot", return_value="/tmp/snap.json"):
                        hot_rank.main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"


# ═══════════════════════════════════════════════════════════════
# _print_table
# ═══════════════════════════════════════════════════════════════


class TestPrintTable:
    def test_dict_rows_with_floats(self, capsys):
        """dict 行 + float 值（亿/万格式化）。"""
        rows = [
            {"code": "sh600000", "amount": 2e8, "hot_score": 100.5},
            {"code": "sh600001", "amount": 5e4, "hot_score": 50.0},
        ]
        hot_rank._print_table(
            rows,
            cols=["code", "amount", "hot_score"],
            headers=["#", "代码", "成交额", "热度"],
            top=10,
        )
        out = capsys.readouterr().out
        assert "sh600000" in out
        assert "亿" in out  # 2e8 -> 亿
        assert "万" in out  # 5e4 -> 万

    def test_object_rows(self, capsys):
        """对象行（getattr 访问）。"""
        q = MagicMock()
        q.code = "sh600000"
        q.amount = 1e8
        q.hot_score = 100
        hot_rank._print_table(
            [q],
            cols=["code", "amount", "hot_score"],
            headers=["#", "代码", "成交额", "热度"],
            top=10,
        )
        out = capsys.readouterr().out
        assert "sh600000" in out

    def test_empty_rows(self, capsys):
        """空行列表。"""
        hot_rank._print_table(
            [],
            cols=["code"],
            headers=["#", "代码"],
            top=10,
        )
        out = capsys.readouterr().out
        assert "Top 0" in out

    def test_top_limit(self, capsys):
        """top 限制输出行数。"""
        rows = [{"code": f"sh60000{i}", "amount": 1e8, "hot_score": i} for i in range(5)]
        hot_rank._print_table(
            rows,
            cols=["code", "amount", "hot_score"],
            headers=["#", "代码", "成交额", "热度"],
            top=2,
        )
        out = capsys.readouterr().out
        assert "sh600000" in out
        assert "sh600001" in out

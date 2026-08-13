"""data.zt_pool / data.market_snapshot 数据域单元测试。

涨停池：mock technical.sentiment 的 token 与 http 层，验证解析/缓存/一字板判定。
市场快照：mock 全市场 universe 与 quote，验证缓存命中/过期/重算。
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import technical.sentiment
import data.zt_pool as zt
import data.market_snapshot as ms


class TestZtNormalizeCode:
    """_normalize_code 东财裸代码 → 前缀代码。"""

    def test_sh(self):
        assert zt._normalize_code("600519") == "sh600519"

    def test_sz(self):
        assert zt._normalize_code("000001") == "sz000001"
        assert zt._normalize_code("300750") == "sz300750"

    def test_bj(self):
        assert zt._normalize_code("832000") == "bj832000"
        assert zt._normalize_code("430047") == "bj430047"

    def test_non_digit_passthrough(self):
        assert zt._normalize_code("sh600519") == "sh600519"

    def test_other_prefix_default(self):
        assert zt._normalize_code("200012") == "200012"


class TestZtGetPool:
    """get_zt_pool 解析/缓存/降级。"""

    @pytest.fixture(autouse=True)
    def _clear(self):
        zt.clear_cache()
        yield
        zt.clear_cache()

    def _http_payload(self):
        return {
            "data": {
                "pool": [
                    {
                        "c": "600519",
                        "lbc": 1,
                        "zbc": 0,
                        "fund": 1e8,
                        "hs": 0.5,
                        "n": "贵州茅台",
                        "zdp": 10.0,
                    },
                    {
                        "c": "000001",
                        "lbc": 2,
                        "zbc": 1,
                        "fund": 5e7,
                        "hs": 8.0,
                        "n": "平安银行",
                        "zdp": 9.9,
                    },
                    {"c": "", "lbc": 3},  # 空 code 跳过
                ]
            }
        }

    def test_token_missing_returns_empty(self, monkeypatch):
        monkeypatch.setattr(technical.sentiment, "_EASTMONEY_UT", "", raising=True)
        monkeypatch.setattr(
            technical.sentiment, "_http_get_json", lambda *a, **k: {}, raising=True
        )
        assert zt.get_zt_pool() == {}

    def test_parse_pool_and_normalize(self, monkeypatch):
        monkeypatch.setattr(technical.sentiment, "_EASTMONEY_UT", "token", raising=True)
        monkeypatch.setattr(
            technical.sentiment,
            "_http_get_json",
            lambda *a, **kw: self._http_payload(),
            raising=True,
        )
        pool = zt.get_zt_pool()
        assert pool["sh600519"]["lbc"] == 1
        assert pool["sh600519"]["zbc"] == 0
        assert pool["sh600519"]["turnover_rate"] == 0.5
        assert pool["sz000001"]["name"] == "平安银行"
        assert "sh600519" in pool

    def test_cache_hit_skips_http(self, monkeypatch):
        calls = []
        monkeypatch.setattr(technical.sentiment, "_EASTMONEY_UT", "token", raising=True)
        monkeypatch.setattr(
            technical.sentiment,
            "_http_get_json",
            lambda *a, **kw: (calls.append(kw) or self._http_payload()),
            raising=True,
        )
        zt.get_zt_pool()
        zt.get_zt_pool()
        assert len(calls) == 1  # 第二次命中缓存

    def test_exception_returns_empty(self, monkeypatch):
        monkeypatch.setattr(technical.sentiment, "_EASTMONEY_UT", "token", raising=True)
        monkeypatch.setattr(
            technical.sentiment,
            "_http_get_json",
            lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("boom")),
            raising=True,
        )
        assert zt.get_zt_pool() == {}

    def test_explicit_date_both_records_key(self, monkeypatch):
        """指定 date 时不依赖当日回落逻辑，直接走 http。"""
        monkeypatch.setattr(technical.sentiment, "_EASTMONEY_UT", "token", raising=True)
        monkeypatch.setattr(
            technical.sentiment,
            "_http_get_json",
            lambda *a, **kw: self._http_payload(),
            raising=True,
        )
        pool = zt.get_zt_pool(date="20260801")
        assert "sh600519" in pool


class TestZtOneWordLimitUp:
    """is_one_word_limit_up 一字板判定。"""

    def test_not_in_pool(self):
        assert zt.is_one_word_limit_up("sh600989", {}) is False

    def test_one_word(self):
        pool = {"sh600519": {"zbc": 0, "turnover_rate": 0.3, "fund_buy": 1e8}}
        assert zt.is_one_word_limit_up("sh600519", pool) is True

    def test_breached_not_one_word(self):
        pool = {"sh600519": {"zbc": 1, "turnover_rate": 0.3, "fund_buy": 1e8}}
        assert zt.is_one_word_limit_up("sh600519", pool) is False

    def test_high_turnover_not_one_word(self):
        pool = {"sh600519": {"zbc": 0, "turnover_rate": 2.0, "fund_buy": 1e8}}
        assert zt.is_one_word_limit_up("sh600519", pool) is False

    def test_no_fund_not_one_word(self):
        pool = {"sh600519": {"zbc": 0, "turnover_rate": 0.3, "fund_buy": 0}}
        assert zt.is_one_word_limit_up("sh600519", pool) is False

    def test_auto_fetch_when_pool_none(self, monkeypatch):
        monkeypatch.setattr(
            zt,
            "get_zt_pool",
            lambda: {"sh600519": {"zbc": 0, "turnover_rate": 0.2, "fund_buy": 1}},
        )
        assert zt.is_one_word_limit_up("sh600519") is True


class TestMarketSnapshot:
    """get_market_snapshot 缓存命中/过期/重算。"""

    @pytest.fixture(autouse=True)
    def _data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ms, "DATA_DIR", tmp_path, raising=False)
        yield tmp_path

    def _snapshot(self, updated):
        return {
            "avg_amount_yuan": 1e9,
            "median_cap": 100.0,
            "updated": updated,
            "source": "cache",
        }

    def test_cache_hit_when_fresh(self, _data_dir):
        path = _data_dir / "market_snapshot.json"
        path.write_text(
            json.dumps(self._snapshot(datetime.now().isoformat())), encoding="utf-8"
        )
        s = ms.get_market_snapshot()
        assert s["source"] == "cache"
        assert s["median_cap"] == 100.0

    def test_cache_expired_recomputes(self, _data_dir):
        stale = datetime.now() - timedelta(hours=2)
        path = _data_dir / "market_snapshot.json"
        path.write_text(json.dumps(self._snapshot(stale.isoformat())), encoding="utf-8")

        q1 = SimpleNamespace(to_dict=lambda: {"amount": 2e9, "total_cap": 200.0})
        q2 = SimpleNamespace(to_dict=lambda: {"amount": 4e9, "total_cap": 400.0})
        with (
            patch(
                "business.universe_loader.load_full_market_universe",
                return_value=["a", "b"],
            ),
            patch("data.get_quotes", return_value=[q1, q2]),
        ):
            s = ms.get_market_snapshot()
        assert s["source"] == "computed"
        assert s["avg_amount_yuan"] == 3e9  # 中位数(2e9,4e9)
        assert s["median_cap"] == 300.0
        # 重算结果应写缓存
        assert (_data_dir / "market_snapshot.json").exists()

    def test_no_universe_returns_defaults(self):
        with patch(
            "business.universe_loader.load_full_market_universe", return_value=[]
        ):
            s = ms.get_market_snapshot()
        assert s["source"] == "computed"
        assert s["avg_amount_yuan"] == 0.0

    def test_compute_exception_swallowed(self):
        with patch(
            "business.universe_loader.load_full_market_universe",
            side_effect=RuntimeError("boom"),
        ):
            s = ms.get_market_snapshot()
        assert s["source"] == "computed"


class TestMarketSnapshotInternals:
    """_is_fresh / _load_cache / _save_cache。"""

    @pytest.fixture(autouse=True)
    def _data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(ms, "DATA_DIR", tmp_path, raising=False)
        yield tmp_path

    def test_is_fresh_true(self):
        snap = {"updated": datetime.now().isoformat()}
        assert ms._is_fresh(snap, 3600) is True

    def test_is_fresh_missing_updated(self):
        assert ms._is_fresh({}, 3600) is False

    def test_is_fresh_invalid_ts(self):
        assert ms._is_fresh({"updated": "not-a-date"}, 3600) is False

    def test_is_fresh_old(self):
        snap = {"updated": (datetime.now() - timedelta(hours=2)).isoformat()}
        assert ms._is_fresh(snap, 3600) is False

    def test_load_cache_missing(self, _data_dir):
        assert ms._load_cache() is None

    def test_load_cache_corrupt(self, _data_dir):
        (_data_dir / "market_snapshot.json").write_text("{broken", encoding="utf-8")
        assert ms._load_cache() is None

    def test_load_cache_ok(self, _data_dir):
        (_data_dir / "market_snapshot.json").write_text('{"a": 1}', encoding="utf-8")
        assert ms._load_cache() == {"a": 1}

    def test_save_cache_failure_swallowed(self, monkeypatch):
        def _bad_write(*a, **k):
            raise OSError("readonly")

        # 模拟写入路径失败：patch Path.write_text 抛出 OSError，_save_cache 应吞掉
        with patch("pathlib.Path.write_text", side_effect=_bad_write):
            ms._save_cache({"a": 1})  # 不应抛异常

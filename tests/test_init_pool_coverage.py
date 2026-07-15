"""init_pool.py 覆盖测试。

mock fetch_all_market_stocks / refresh_pool / init_from_default / 文件 I/O，
覆盖 is_pool_populated、init_pool、init_full_market、main。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import init_pool as ip


class TestIsPoolPopulated:
    def test_file_not_exists(self, tmp_path):
        with patch.object(ip, "POOL_FILE", str(tmp_path / "noexist.json")):
            populated, desc = ip.is_pool_populated()
        assert populated is False
        assert "不存在" in desc

    def test_corrupt_file(self, tmp_path):
        pool_file = tmp_path / "pool.json"
        pool_file.write_text("not json{", encoding="utf-8")
        with patch.object(ip, "POOL_FILE", str(pool_file)):
            populated, desc = ip.is_pool_populated()
        assert populated is False
        assert "损坏" in desc

    def test_insufficient_sectors(self, tmp_path):
        pool_file = tmp_path / "pool.json"
        data = {"_meta": {}, "银行": ["sh600036"]}  # 仅 1 个板块
        pool_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(ip, "POOL_FILE", str(pool_file)):
            populated, desc = ip.is_pool_populated()
        assert populated is False
        assert "板块" in desc

    def test_insufficient_stocks(self, tmp_path):
        pool_file = tmp_path / "pool.json"
        # 10 个板块但每个只有 1 只股票（总 10 < 100）
        data = {f"sector_{i}": ["sh60000" + str(i)] for i in range(10)}
        pool_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(ip, "POOL_FILE", str(pool_file)):
            populated, desc = ip.is_pool_populated()
        assert populated is False
        assert "股票" in desc

    def test_populated(self, tmp_path):
        pool_file = tmp_path / "pool.json"
        data = {
            f"sector_{i}": [f"sh6000{i}{j:02d}" for j in range(20)] for i in range(10)
        }
        pool_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(ip, "POOL_FILE", str(pool_file)):
            populated, desc = ip.is_pool_populated()
        assert populated is True
        assert "10 个板块" in desc

    def test_meta_key_excluded(self, tmp_path):
        pool_file = tmp_path / "pool.json"
        data = {"_meta": {"updated": "2025-01-01"}, "_version": 2}
        for i in range(10):
            data[f"sector_{i}"] = [f"sh6000{i}{j:02d}" for j in range(20)]
        pool_file.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(ip, "POOL_FILE", str(pool_file)):
            populated, _ = ip.is_pool_populated()
        assert populated is True


class TestInitPool:
    def test_already_populated_skips(self, capsys):
        with (
            patch.object(
                ip, "is_pool_populated", return_value=(True, "20 个板块，500 只股票")
            ),
        ):
            result = ip.init_pool(force=False)
        assert result is False
        captured = capsys.readouterr()
        assert "已存在" in captured.out

    def test_force_init_with_default(self, capsys):
        with (
            patch.object(
                ip,
                "init_from_default",
                return_value={"银行": ["sh600036"], "白酒": ["sh600519"]},
            ),
            patch.dict("os.environ", {}, clear=False),
        ):
            import os

            os.environ.pop("EASTMONEY_API_TOKEN", None)
            result = ip.init_pool(top_n=20, force=True, use_default=True)
        assert result is True
        captured = capsys.readouterr()
        assert "初始化完成" in captured.out

    def test_init_via_refresh_pool(self, capsys):
        with (patch.object(ip, "refresh_pool", return_value={"银行": ["sh600036"]}),):
            import os

            os.environ.pop("EASTMONEY_API_TOKEN", None)
            result = ip.init_pool(top_n=20, force=True, use_default=False)
        assert result is True

    def test_init_returns_empty(self, capsys):
        with patch.object(ip, "refresh_pool", return_value={}):
            import os

            os.environ.pop("EASTMONEY_API_TOKEN", None)
            result = ip.init_pool(top_n=20, force=True)
        assert result is False
        captured = capsys.readouterr()
        assert "初始化失败" in captured.err

    def test_init_raises_exception(self, capsys):
        def _raise(*a, **kw):
            raise RuntimeError("network error")

        with patch.object(ip, "refresh_pool", _raise):
            import os

            os.environ.pop("EASTMONEY_API_TOKEN", None)
            result = ip.init_pool(top_n=20, force=True)
        assert result is False
        captured = capsys.readouterr()
        assert "network error" in captured.err


class TestInitFullMarket:
    def test_already_exists_skips(self, tmp_path, capsys):
        all_file = tmp_path / "all_stocks.json"
        all_file.write_text(
            json.dumps({"_meta": {"total_stocks": 5000}}), encoding="utf-8"
        )
        with patch.object(ip, "ALL_STOCKS_FILE", str(all_file)):
            result = ip.init_full_market(force=False)
        assert result is False
        captured = capsys.readouterr()
        assert "已存在" in captured.out

    def test_force_init(self, capsys):
        with (
            patch.object(
                ip,
                "fetch_all_market_stocks",
                return_value={"sh": ["sh600519"], "sz": ["sz000001"]},
            ),
            patch.object(ip, "save_all_market_stocks", lambda x: None),
        ):
            result = ip.init_full_market(force=True)
        assert result is True
        captured = capsys.readouterr()
        assert "初始化完成" in captured.out

    def test_corrupt_existing_file_reinits(self, tmp_path):
        all_file = tmp_path / "all_stocks.json"
        all_file.write_text("corrupt{", encoding="utf-8")
        with (
            patch.object(ip, "ALL_STOCKS_FILE", str(all_file)),
            patch.object(
                ip, "fetch_all_market_stocks", return_value={"sh": ["sh600519"]}
            ),
            patch.object(ip, "save_all_market_stocks", lambda x: None),
        ):
            result = ip.init_full_market(force=False)
        assert result is True

    def test_init_raises_exception(self, capsys):
        def _raise(*a, **kw):
            raise RuntimeError("net error")

        with patch.object(ip, "fetch_all_market_stocks", _raise):
            result = ip.init_full_market(force=True)
        assert result is False
        captured = capsys.readouterr()
        assert "net error" in captured.err


class TestMain:
    def test_main_default_mode(self, capsys):
        with (
            patch.object(ip, "init_pool", return_value=True),
            patch("sys.argv", ["init_pool.py"]),
        ):
            ip.main()
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_main_full_market_mode(self, capsys):
        with (
            patch.object(ip, "init_full_market", return_value=True),
            patch("sys.argv", ["init_pool.py", "--full-market"]),
        ):
            ip.main()

    def test_main_json_output(self, capsys):
        with (
            patch.object(ip, "init_pool", return_value=True),
            patch("sys.argv", ["init_pool.py", "-j", "--top", "30"]),
        ):
            ip.main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["status"] == "ok"
        assert data["args"]["top"] == 30

    def test_main_json_full_market(self, capsys):
        with (
            patch.object(ip, "init_full_market", return_value={"stocks": 5000}),
            patch("sys.argv", ["init_pool.py", "-j", "--full-market"]),
        ):
            ip.main()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["mode"] == "full_market"

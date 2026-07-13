"""
init_pool.py 单元测试：覆盖池初始化逻辑、阈值检查、fallback 行为。
"""

import json
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from init_pool import is_pool_populated, MIN_SECTORS, MIN_STOCKS


def _make_pool_data(n_sectors: int = 15, stocks_per_sector: int = 20) -> dict:
    """构造模拟股票池数据。"""
    data = {}
    for i in range(n_sectors):
        sector = f"板块{i}"
        data[sector] = [f"sh60{i:04d}" for _ in range(stocks_per_sector)]
    return data


# ═══════════════════════════════════════════════════════════════
# 0. 常量阈值合理性
# ═══════════════════════════════════════════════════════════════
class TestConstants:
    def test_min_sectors_reasonable(self):
        """板块阈值应在 3~20 之间。"""
        assert 3 <= MIN_SECTORS <= 20

    def test_min_stocks_reasonable(self):
        """股票阈值应 ≥ 50（确保池有基本覆盖）。"""
        assert MIN_STOCKS >= 50


# ═══════════════════════════════════════════════════════════════
# 1. is_pool_populated
# ═══════════════════════════════════════════════════════════════
class TestIsPoolPopulated:
    def test_no_file_returns_false(self, tmp_path, monkeypatch):
        """股票池文件不存在时返回 False。"""
        import init_pool

        monkeypatch.setattr(init_pool, "POOL_FILE", str(tmp_path / "nonexistent.json"))
        populated, desc = is_pool_populated()
        assert populated is False
        assert "不存在" in desc

    def test_corrupted_file_returns_false(self, tmp_path, monkeypatch):
        """文件损坏时返回 False。"""
        import init_pool

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json", encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(bad_file))
        populated, desc = is_pool_populated()
        assert populated is False
        assert "损坏" in desc

    def test_enough_data_returns_true(self, tmp_path, monkeypatch):
        """足够数据时返回 True。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(json.dumps(_make_pool_data()), encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, desc = is_pool_populated()
        assert populated is True
        assert "15 个板块" in desc

    def test_too_few_sectors(self, tmp_path, monkeypatch):
        """板块数不足时返回 False。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(json.dumps(_make_pool_data(n_sectors=5)), encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, desc = is_pool_populated()
        assert populated is False
        assert "5 个板块" in desc

    def test_too_few_stocks(self, tmp_path, monkeypatch):
        """股票数不足时返回 False。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(
            json.dumps(_make_pool_data(n_sectors=15, stocks_per_sector=2)),
            encoding="utf-8",
        )
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, desc = is_pool_populated()
        assert populated is False
        assert "仅 30 只股票" in desc

    def test_ignores_metadata_keys(self, tmp_path, monkeypatch):
        """下划线开头的 metadata key 不计入板块数。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        data = _make_pool_data(n_sectors=12)
        data["_updated"] = "2025-01-01"
        pool_file.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, desc = is_pool_populated()
        # 12 个板块（忽略 _updated）> 10 阈值
        assert populated is True
        assert "12 个板块" in desc

    def test_exactly_at_min_sectors(self, tmp_path, monkeypatch):
        """板块数恰好等于 MIN_SECTORS 时应返回 True（边界）。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(
            json.dumps(_make_pool_data(n_sectors=MIN_SECTORS, stocks_per_sector=20)),
            encoding="utf-8",
        )
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, _ = is_pool_populated()
        assert populated is True

    def test_exactly_at_min_stocks(self, tmp_path, monkeypatch):
        """股票数恰好等于 MIN_STOCKS 时应返回 True（边界）。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        # MIN_SECTORS 个板块，每板块 ceil(MIN_STOCKS / MIN_SECTORS) 只股票
        per_sector = max(1, -(-MIN_STOCKS // MIN_SECTORS))  # 向上取整
        pool_file.write_text(
            json.dumps(
                _make_pool_data(n_sectors=MIN_SECTORS, stocks_per_sector=per_sector)
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, _ = is_pool_populated()
        assert populated is True

    def test_one_below_min_sectors(self, tmp_path, monkeypatch):
        """板块数 = MIN_SECTORS - 1 时应返回 False（边界）。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(
            json.dumps(
                _make_pool_data(n_sectors=MIN_SECTORS - 1, stocks_per_sector=20)
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))
        populated, _ = is_pool_populated()
        assert populated is False


# ═══════════════════════════════════════════════════════════════
# 2. init_pool (mock refresh_pool/init_from_default)
# ═══════════════════════════════════════════════════════════════
class TestInitPool:
    def test_skips_when_populated(self, tmp_path, monkeypatch, capsys):
        """已初始化时跳过并打印提示。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(json.dumps(_make_pool_data()), encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))

        result = init_pool.init_pool(top_n=20)
        assert result is False
        captured = capsys.readouterr()
        assert "已存在" in captured.out
        assert "跳过" in captured.out

    def test_force_ignores_existing(self, tmp_path, monkeypatch, capsys):
        """force=True 时忽略已有数据。"""
        import init_pool

        pool_file = tmp_path / "pool.json"
        pool_file.write_text(json.dumps(_make_pool_data()), encoding="utf-8")
        monkeypatch.setattr(init_pool, "POOL_FILE", str(pool_file))

        mock_pool = _make_pool_data(n_sectors=10, stocks_per_sector=20)
        monkeypatch.setattr(init_pool, "refresh_pool", lambda **kw: mock_pool)

        result = init_pool.init_pool(top_n=20, force=True)
        assert result is True

    def test_uses_default_when_flag_set(self, tmp_path, monkeypatch, capsys):
        """use_default=True 时直接使用预置数据。"""
        import init_pool

        monkeypatch.setattr(init_pool, "POOL_FILE", str(tmp_path / "pool.json"))

        mock_pool = _make_pool_data(n_sectors=10)
        monkeypatch.setattr(
            init_pool, "init_from_default", lambda top_n, dry_run: mock_pool
        )

        result = init_pool.init_pool(top_n=20, use_default=True)
        assert result is True
        captured = capsys.readouterr()
        assert "初始化完成" in captured.out

    def test_handles_api_failure(self, tmp_path, monkeypatch, capsys):
        """API 失败时返回 False 并打印错误（stderr）。"""
        import init_pool

        monkeypatch.setattr(init_pool, "POOL_FILE", str(tmp_path / "pool.json"))
        monkeypatch.setattr(init_pool, "refresh_pool", lambda **kw: None)

        result = init_pool.init_pool(top_n=20)
        assert result is False
        captured = capsys.readouterr()
        assert "失败" in captured.err

    def test_handles_exception(self, tmp_path, monkeypatch, capsys):
        """异常时捕获并返回 False（stderr）。"""
        import init_pool

        monkeypatch.setattr(init_pool, "POOL_FILE", str(tmp_path / "pool.json"))
        monkeypatch.setattr(
            init_pool,
            "refresh_pool",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        result = init_pool.init_pool(top_n=20)
        assert result is False
        captured = capsys.readouterr()
        assert "boom" in captured.err


# ═══════════════════════════════════════════════════════════════
# init_full_market + main
# ═══════════════════════════════════════════════════════════════


class TestInitFullMarket:
    def test_already_initialized(self, tmp_path, capsys, monkeypatch):
        """全市场已初始化时跳过。"""
        import init_pool as ip
        all_path = tmp_path / "all_stocks.json"
        all_path.parent.mkdir(parents=True, exist_ok=True)
        all_path.write_text(json.dumps({"_meta": {"total_stocks": 5000}}))
        monkeypatch.setattr(ip, "ALL_STOCKS_FILE", all_path)
        result = ip.init_full_market(force=False)
        assert result is False
        captured = capsys.readouterr()
        assert "已存在" in captured.out or "跳过" in captured.out

    def test_force_refresh(self, tmp_path, capsys, monkeypatch):
        """force=True 时强制重新拉取。"""
        import init_pool as ip
        all_path = tmp_path / "all_stocks.json"
        monkeypatch.setattr(ip, "ALL_STOCKS_FILE", all_path)
        with patch("init_pool.fetch_all_market_stocks",
                   return_value={"主板": ["sh600519"], "创业板": ["sz300750"]}), \
             patch("init_pool.save_all_market_stocks", return_value=None):
            result = ip.init_full_market(force=True)
        assert result is True

    def test_init_failure(self, tmp_path, capsys, monkeypatch):
        """fetch 失败时 graceful 返回 False。"""
        import init_pool as ip
        all_path = tmp_path / "all_stocks.json"
        monkeypatch.setattr(ip, "ALL_STOCKS_FILE", all_path)
        with patch("init_pool.fetch_all_market_stocks",
                   side_effect=Exception("API down")):
            result = ip.init_full_market(force=True)
        assert result is False


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["init_pool.py"])
        with patch("init_pool.init_pool", return_value={"A": ["sh"]}):
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass

    def test_full_market_flag(self, capsys, monkeypatch):
        """--full-market 时调用 init_full_market。"""
        with patch("init_pool.init_full_market", return_value=True) as m:
            monkeypatch.setattr(sys, "argv", ["init_pool.py", "--full-market"])
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass
        m.assert_called_once()

    def test_force_flag(self, capsys, monkeypatch):
        """--force 时 force=True 传给 init_pool。"""
        with patch("init_pool.init_pool", return_value={}) as m:
            monkeypatch.setattr(sys, "argv", ["init_pool.py", "--force"])
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass
        assert m.call_args.kwargs.get("force") is True

    def test_top_flag(self, capsys, monkeypatch):
        """--top 30 时 top_n=30 传入。"""
        with patch("init_pool.init_pool", return_value={}) as m:
            monkeypatch.setattr(sys, "argv", ["init_pool.py", "--top", "30"])
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass
        assert m.call_args.kwargs.get("top_n") == 30

    def test_default_flag(self, capsys, monkeypatch):
        """--default 时 use_default=True。"""
        with patch("init_pool.init_pool", return_value={}) as m:
            monkeypatch.setattr(sys, "argv", ["init_pool.py", "--default"])
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass
        assert m.call_args.kwargs.get("use_default") is True

    def test_json_flag(self, capsys, monkeypatch):
        """-j 时输出 JSON。"""
        with patch("init_pool.init_full_market", return_value=True):
            monkeypatch.setattr(sys, "argv", ["init_pool.py", "--full-market", "-j"])
            try:
                import init_pool as ip
                ip.main()
            except SystemExit:
                pass
        captured = capsys.readouterr()
        assert "ok" in captured.out or "status" in captured.out

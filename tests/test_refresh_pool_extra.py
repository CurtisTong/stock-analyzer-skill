"""refresh_pool.py 补充测试：print_diff / main CLI 入口。

覆盖 print_diff（变更对比输出）、main() 的各子命令分支：
--full-market / --default / 普通 refresh / --diff / --json / dry-run。
所有 fetch_all_market_stocks / refresh_pool / init_from_default 均 mock。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import refresh_pool


# ═══════════════════════════════════════════════════════════════
# print_diff
# ═══════════════════════════════════════════════════════════════


class TestPrintDiff:
    def test_no_changes(self, capsys):
        current = {"消费": ["sh600519"]}
        new = {"消费": ["sh600519"]}
        refresh_pool.print_diff(current, new)
        out = capsys.readouterr().out
        assert "变更对比" in out

    def test_added_stocks(self, capsys):
        current = {"消费": ["sh600519"]}
        new = {"消费": ["sh600519", "sh600000"]}
        refresh_pool.print_diff(current, new)
        out = capsys.readouterr().out
        assert "新增" in out
        assert "sh600000" in out

    def test_removed_stocks(self, capsys):
        current = {"消费": ["sh600519", "sh600000"]}
        new = {"消费": ["sh600519"]}
        refresh_pool.print_diff(current, new)
        out = capsys.readouterr().out
        assert "移除" in out
        assert "sh600000" in out

    def test_new_sector_added(self, capsys):
        current = {"消费": ["sh600519"]}
        new = {"消费": ["sh600519"], "金融": ["sh601288"]}
        refresh_pool.print_diff(current, new)
        out = capsys.readouterr().out
        assert "金融" in out

    def test_total_summary(self, capsys):
        current = {"消费": ["sh600519", "sh600000"]}
        new = {"消费": ["sh600519"]}
        refresh_pool.print_diff(current, new)
        out = capsys.readouterr().out
        assert "总计" in out
        assert "(-1)" in out


# ═══════════════════════════════════════════════════════════════
# main() CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_main_full_market(self, capsys):
        """--full-market 拉取全市场并保存。"""
        mock_result = {"主板沪": ["sh600519"], "主板深": ["sz000001"]}
        with (
            patch("sys.argv", ["refresh_pool.py", "--full-market"]),
            patch("common.cache.cleanup_tmp_files"),
            patch("refresh_pool.fetch_all_market_stocks", return_value=mock_result),
            patch("refresh_pool.save_all_market_stocks") as mock_save,
        ):
            refresh_pool.main()
        mock_save.assert_called_once_with(mock_result)

    def test_main_full_market_dry_run(self, capsys):
        """--full-market --dry-run 不保存。"""
        mock_result = {"主板沪": ["sh600519"]}
        with (
            patch("sys.argv", ["refresh_pool.py", "--full-market", "--dry-run"]),
            patch("common.cache.cleanup_tmp_files"),
            patch("refresh_pool.fetch_all_market_stocks", return_value=mock_result),
            patch("refresh_pool.save_all_market_stocks") as mock_save,
        ):
            refresh_pool.main()
        mock_save.assert_not_called()

    def test_main_default(self, capsys):
        """--default 用预置数据初始化。"""
        with (
            patch("sys.argv", ["refresh_pool.py", "--default", "--top", "10"]),
            patch("common.cache.cleanup_tmp_files"),
            patch(
                "refresh_pool.init_from_default", return_value={"消费": ["sh600519"]}
            ) as mock_init,
        ):
            refresh_pool.main()
        mock_init.assert_called_once()
        args, kwargs = mock_init.call_args
        assert kwargs["top_n"] == 10

    def test_main_refresh(self, capsys):
        """普通 refresh 模式。"""
        with (
            patch("sys.argv", ["refresh_pool.py", "--top", "15", "--sort", "cap"]),
            patch("common.cache.cleanup_tmp_files"),
            patch(
                "refresh_pool.refresh_pool", return_value={"消费": ["sh600519"]}
            ) as mock_refresh,
        ):
            refresh_pool.main()
        args, kwargs = mock_refresh.call_args
        assert kwargs["top_n"] == 15
        assert kwargs["sort_by"] == "cap"

    def test_main_refresh_with_diff(self, capsys):
        """--diff 显示变更对比。"""
        current = {"消费": ["sh600519"]}
        new_pool = {"消费": ["sh600519", "sh600000"]}
        with (
            patch("sys.argv", ["refresh_pool.py", "--diff"]),
            patch("common.cache.cleanup_tmp_files"),
            patch("refresh_pool.load_current_pool", return_value=current),
            patch("refresh_pool.refresh_pool", return_value=new_pool),
        ):
            refresh_pool.main()
        out = capsys.readouterr().out
        assert "新增" in out
        assert "sh600000" in out

    def test_main_json_output(self, capsys):
        """-j 输出 JSON 摘要。"""
        with (
            patch("sys.argv", ["refresh_pool.py", "--full-market", "-j"]),
            patch("common.cache.cleanup_tmp_files"),
            patch(
                "refresh_pool.fetch_all_market_stocks",
                return_value={"主板沪": ["sh600519"]},
            ),
            patch("refresh_pool.save_all_market_stocks"),
        ):
            refresh_pool.main()
        out = capsys.readouterr().out
        # JSON 输出（前面可能有 logging 输出，从第一个 { 提取 JSON）
        json_start = out.index("{")
        parsed = json.loads(out[json_start:])
        assert parsed["status"] == "ok"
        assert parsed["mode"] == "full_market"

    def test_main_refresh_with_sector(self, capsys):
        """--sector 指定板块。"""
        with (
            patch("sys.argv", ["refresh_pool.py", "--sector", "消费", "金融"]),
            patch("common.cache.cleanup_tmp_files"),
            patch("refresh_pool.refresh_pool", return_value={}) as mock_refresh,
        ):
            refresh_pool.main()
        args, kwargs = mock_refresh.call_args
        assert kwargs["sectors"] == ["消费", "金融"]

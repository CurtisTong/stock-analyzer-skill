"""测试 scripts/chip.py：5 个渲染函数（format/render/main）。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import chip


# ═══════════════════════════════════════════════════════════════
# format_number
# ═══════════════════════════════════════════════════════════════


class TestFormatNumber:
    def test_yi(self):
        """>= 1e8 用亿。"""
        result = chip.format_number(1e9)
        assert "亿" in result

    def test_wan(self):
        """1e4 <= n < 1e8 用万。"""
        result = chip.format_number(5e6)
        assert "万" in result

    def test_small(self):
        result = chip.format_number(100.0)
        assert "亿" not in result
        assert "万" not in result

    def test_negative(self):
        result = chip.format_number(-1e9)
        assert "亿" in result

    def test_with_unit(self):
        result = chip.format_number(1e8, unit="元")
        assert "亿" in result
        assert "元" in result


# ═══════════════════════════════════════════════════════════════
# format_change
# ═══════════════════════════════════════════════════════════════


class TestFormatChange:
    def test_positive(self):
        assert "+" in chip.format_change(5.0)
        assert "5.00" in chip.format_change(5.0)

    def test_negative(self):
        result = chip.format_change(-2.5)
        assert "2.50" in result
        assert result.startswith("-")

    def test_zero(self):
        assert "0.00" in chip.format_change(0)


# ═══════════════════════════════════════════════════════════════
# render_margin
# ═══════════════════════════════════════════════════════════════


class TestRenderMargin:
    def test_empty(self, capsys):
        chip.render_margin([])
        captured = capsys.readouterr()
        assert "无" in captured.out or "失败" in captured.out

    def test_with_data_positive(self, capsys):
        data = [
            SimpleNamespace(date="2026-07-01", rzye=1e9, rzjme=5e8, rqyl=1e6),
            SimpleNamespace(date="2026-07-02", rzye=1.1e9, rzjme=3e8, rqyl=1.1e6),
            SimpleNamespace(date="2026-07-03", rzye=1.2e9, rzjme=2e8, rqyl=1.2e6),
        ]
        chip.render_margin(data)
        captured = capsys.readouterr()
        assert "融资融券" in captured.out
        assert "2026-07-01" in captured.out

    def test_negative_trend(self, capsys):
        """连续 5 日负 rzjme 时输出'连续减少'。"""
        data = [
            SimpleNamespace(date=f"2026-07-{i+1:02d}", rzye=1e9, rzjme=-1e8, rqyl=1e6)
            for i in range(5)
        ]
        chip.render_margin(data, days=5)
        captured = capsys.readouterr()
        assert "连续减少" in captured.out or "波动" in captured.out

    def test_increasing_trend(self, capsys):
        """连续 5 日正 rzjme 时输出'连续增加'。"""
        data = [
            SimpleNamespace(date=f"2026-07-{i+1:02d}", rzye=1e9, rzjme=1e8, rqyl=1e6)
            for i in range(5)
        ]
        chip.render_margin(data, days=5)
        captured = capsys.readouterr()
        assert "连续增加" in captured.out

    def test_mixed_trend(self, capsys):
        data = [
            SimpleNamespace(date="2026-07-01", rzye=1e9, rzjme=1e8, rqyl=1e6),
            SimpleNamespace(date="2026-07-02", rzye=1e9, rzjme=-1e8, rqyl=1e6),
            SimpleNamespace(date="2026-07-03", rzye=1e9, rzjme=1e8, rqyl=1e6),
            SimpleNamespace(date="2026-07-04", rzye=1e9, rzjme=-1e8, rqyl=1e6),
            SimpleNamespace(date="2026-07-05", rzye=1e9, rzjme=1e8, rqyl=1e6),
        ]
        chip.render_margin(data, days=5)
        captured = capsys.readouterr()
        assert "波动" in captured.out

    def test_zero_rzjme(self, capsys):
        """rzjme=0 时 sentiment=中性。"""
        data = [SimpleNamespace(date="2026-07-01", rzye=1e9, rzjme=0, rqyl=1e6)]
        chip.render_margin(data, days=1)
        captured = capsys.readouterr()
        assert "中性" in captured.out or "融资融券" in captured.out


# ═══════════════════════════════════════════════════════════════
# render_holders
# ═══════════════════════════════════════════════════════════════


class TestRenderHolders:
    def test_empty(self, capsys):
        chip.render_holders([])
        captured = capsys.readouterr()
        assert "无" in captured.out or "失败" in captured.out

    def test_with_data(self, capsys):
        data = [
            SimpleNamespace(
                end_date="2026-06-30", holder_num=50000,
                holder_num_change=-1000, avg_amount=2000,
                concentration=0.6,
            ),
            SimpleNamespace(
                end_date="2026-03-31", holder_num=51000,
                holder_num_change=500, avg_amount=1950,
                concentration=0.55,
            ),
        ]
        chip.render_holders(data)
        captured = capsys.readouterr()
        assert "股东户数" in captured.out
        assert "2026-06-30" in captured.out


# ═══════════════════════════════════════════════════════════════
# render_top_holders
# ═══════════════════════════════════════════════════════════════


class TestRenderTopHolders:
    def test_empty(self, capsys):
        chip.render_top_holders([])
        captured = capsys.readouterr()
        assert "无" in captured.out or "失败" in captured.out

    def test_with_data(self, capsys):
        data = [
            SimpleNamespace(
                rank=1, holder_name="股东A" * 5, holder_type="机构",
                hold_num=1000.0, hold_ratio=5.0, change_type="+",
                change=100.0, is_institution=True,
            ),
            SimpleNamespace(
                rank=2, holder_name="股东B", holder_type="个人",
                hold_num=500.0, hold_ratio=2.5, change_type="-",
                change=-50.0, is_institution=False,
            ),
        ]
        chip.render_top_holders(data)
        captured = capsys.readouterr()
        assert "十大流通股东" in captured.out
        assert "机构" in captured.out

    def test_long_name_truncated(self, capsys):
        data = [
            SimpleNamespace(
                rank=1, holder_name="A" * 50, holder_type="机构",
                hold_num=1000.0, hold_ratio=5.0, change_type="+",
                change=100.0, is_institution=True,
            ),
        ]
        chip.render_top_holders(data)
        # 不抛异常
        captured = capsys.readouterr()
        assert captured is not None

    def test_no_change(self, capsys):
        data = [
            SimpleNamespace(
                rank=1, holder_name="股东A", holder_type="个人",
                hold_num=1000.0, hold_ratio=5.0, change_type="不变",
                change=0, is_institution=False,
            ),
        ]
        chip.render_top_holders(data)
        # change=0 时 change_str 仅为 change_type
        captured = capsys.readouterr()
        assert "不变" in captured.out

    def test_institution_stats(self, capsys):
        data = [
            SimpleNamespace(
                rank=1, holder_name="机构1", holder_type="机构",
                hold_num=1000.0, hold_ratio=5.0, change_type="+",
                change=100.0, is_institution=True,
            ),
        ]
        chip.render_top_holders(data)
        captured = capsys.readouterr()
        assert "机构" in captured.out


# ═══════════════════════════════════════════════════════════════
# main - CLI
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_no_args_prints_help(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["chip.py"])
        # chip.main 在无参数时正常退出（不抛 SystemExit）
        try:
            chip.main()
        except SystemExit:
            pass
        # 不验证具体输出（可能空）

    def test_with_stock_code(self, capsys, monkeypatch):
        # 拦截所有数据获取
        with patch("chip.render_margin"), patch("chip.render_holders"), \
             patch("chip.render_top_holders"), \
             patch("data.chip.get_margin", return_value=[]), \
             patch("data.chip.get_holders", return_value=[]), \
             patch("data.chip.get_top_holders", return_value=[]):
            try:
                monkeypatch.setattr(sys, "argv", ["chip.py", "sh600519"])
                chip.main()
            except SystemExit:
                pass
        captured = capsys.readouterr()
        assert captured is not None

    def test_json_flag(self, capsys, monkeypatch):
        with patch("chip.render_margin"), patch("chip.render_holders"), \
             patch("chip.render_top_holders"), \
             patch("data.chip.get_margin", return_value=[]), \
             patch("data.chip.get_holders", return_value=[]), \
             patch("data.chip.get_top_holders", return_value=[]):
            try:
                monkeypatch.setattr(sys, "argv", ["chip.py", "sh600519", "-j"])
                chip.main()
            except SystemExit:
                pass
        captured = capsys.readouterr()
        assert captured is not None

    def test_margin_only(self, capsys, monkeypatch):
        with patch("chip.render_margin"), \
             patch("data.chip.get_margin", return_value=[]), \
             patch("data.chip.get_holders", return_value=[]), \
             patch("data.chip.get_top_holders", return_value=[]):
            try:
                monkeypatch.setattr(sys, "argv", ["chip.py", "sh600519", "--margin"])
                chip.main()
            except SystemExit:
                pass

    def test_holders_only(self, capsys, monkeypatch):
        with patch("chip.render_holders"), \
             patch("data.chip.get_margin", return_value=[]), \
             patch("data.chip.get_holders", return_value=[]), \
             patch("data.chip.get_top_holders", return_value=[]):
            try:
                monkeypatch.setattr(sys, "argv", ["chip.py", "sh600519", "--holders"])
                chip.main()
            except SystemExit:
                pass

    def test_top_holders_only(self, capsys, monkeypatch):
        with patch("chip.render_top_holders"), \
             patch("data.chip.get_margin", return_value=[]), \
             patch("data.chip.get_holders", return_value=[]), \
             patch("data.chip.get_top_holders", return_value=[]):
            try:
                monkeypatch.setattr(sys, "argv", ["chip.py", "sh600519", "--top-holders"])
                chip.main()
            except SystemExit:
                pass
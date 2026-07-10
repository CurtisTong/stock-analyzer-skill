"""chip.py CLI 格式化函数测试（覆盖率提升）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestFormatNumber:
    """format_number 数字格式化。"""

    def test_billions(self):
        from chip import format_number
        assert "亿" in format_number(1e8)

    def test_ten_thousands(self):
        from chip import format_number
        assert "万" in format_number(1e4)

    def test_small_number(self):
        from chip import format_number
        assert format_number(100) == "100.00"

    def test_with_unit(self):
        from chip import format_number
        result = format_number(1e8, "元")
        assert "亿" in result
        assert "元" in result

    def test_negative_billions(self):
        from chip import format_number
        assert "亿" in format_number(-1e8)


class TestFormatChange:
    """format_change 变化率格式化。"""

    def test_positive(self):
        from chip import format_change
        assert format_change(5.5) == "+5.50%"

    def test_negative(self):
        from chip import format_change
        assert format_change(-3.2) == "-3.20%"

    def test_zero(self):
        from chip import format_change
        assert format_change(0) == "0.00%"


class TestRenderMargin:
    """render_margin 融资融券渲染。"""

    def test_empty_data(self, capsys):
        from chip import render_margin
        render_margin(None)
        captured = capsys.readouterr()
        assert "无融资融券数据" in captured.out

    def test_empty_list(self, capsys):
        from chip import render_margin
        render_margin([])
        captured = capsys.readouterr()
        assert "无融资融券数据" in captured.out

    def test_with_data(self, capsys):
        from chip import render_margin
        mock_data = MagicMock()
        mock_data.days = [
            MagicMock(date="2026-01-01", rzjme=100000000, rzche=50000000,
                       rqjmg=-20000000, rzyl=1000000, rqye=500000),
        ]
        mock_data.summary = MagicMock(rzye=10000000000, rqye=500000000)
        render_margin(mock_data)
        captured = capsys.readouterr()
        assert "融资融券" in captured.out


class TestRenderHolders:
    """render_holders 股东户数渲染。"""

    def test_empty_data(self, capsys):
        from chip import render_holders
        render_holders(None)
        captured = capsys.readouterr()
        assert "无股东户数" in captured.out

    def test_empty_list(self, capsys):
        from chip import render_holders
        render_holders([])
        captured = capsys.readouterr()
        assert "无股东户数" in captured.out

    def test_with_data(self, capsys):
        from chip import render_holders
        holders = [MagicMock(end_date="2026-01-01", holder_num=10000,
                              avg_amount=1000, holder_num_change=-5.0,
                              concentration="持续集中")]
        render_holders(holders)
        captured = capsys.readouterr()
        assert "股东户数" in captured.out


class TestRenderTopHolders:
    """render_top_holders 十大股东渲染。"""

    def test_empty_data(self, capsys):
        from chip import render_top_holders
        render_top_holders(None)
        captured = capsys.readouterr()
        assert "无十大流通股东" in captured.out

    def test_empty_list(self, capsys):
        from chip import render_top_holders
        render_top_holders([])
        captured = capsys.readouterr()
        assert "无十大流通股东" in captured.out

    def test_with_data(self, capsys):
        from chip import render_top_holders
        holders = [MagicMock(rank=1, holder_name="机构A", holder_type="基金",
                              hold_num=1000000, hold_ratio=5.0,
                              change=100000, change_type="增持",
                              is_institution=True)]
        render_top_holders(holders)
        captured = capsys.readouterr()
        assert "十大流通股东" in captured.out
        assert "机构A" in captured.out

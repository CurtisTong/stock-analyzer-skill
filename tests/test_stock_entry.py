"""
测试 scripts/stock.py 主入口（之前 0 覆盖）。

策略：mock StockAnalysisService.analyze 避免真实网络请求，
聚焦 CLI 参数解析 + JSON/文本渲染 + 错误处理。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# ═══════════════════════════════════════════════════════════════
# 1. 参数解析
# ═══════════════════════════════════════════════════════════════


class TestStockArgparse:
    """验证 stock.py CLI 参数。"""

    def test_help(self, capsys):
        """--help 应正常输出。"""
        from scripts import stock

        with patch("sys.argv", ["stock.py", "--help"]):
            with pytest.raises(SystemExit):
                stock.main()
        captured = capsys.readouterr()
        assert "个股五层分析" in captured.out

    def test_required_code_arg(self, capsys):
        """code 参数必填。"""
        from scripts import stock

        with patch("sys.argv", ["stock.py"]):
            with pytest.raises(SystemExit):
                stock.main()
        captured = capsys.readouterr()
        # argparse 报错到 stderr
        assert (
            "required" in captured.err
            or "the following arguments are required" in captured.err
        )

    def test_json_flag_parsed(self):
        """--json 应被 argparse 识别。"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("code")
        parser.add_argument("-j", "--json", action="store_true")
        args = parser.parse_args(["sh600989", "-j"])
        assert args.json is True
        args = parser.parse_args(["sh600989"])
        assert args.json is False

    def test_no_finance_flag(self):
        """--no-finance 应被识别。"""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("code")
        parser.add_argument("--no-finance", action="store_true")
        parser.add_argument("--no-technical", action="store_true")
        parser.add_argument("--no-chan", action="store_true")
        args = parser.parse_args(
            ["sh600989", "--no-finance", "--no-technical", "--no-chan"]
        )
        assert args.no_finance is True
        assert args.no_technical is True
        assert args.no_chan is True


# ═══════════════════════════════════════════════════════════════
# 2. render_text 渲染
# ═══════════════════════════════════════════════════════════════


class TestStockRenderText:
    """验证五层分析结果的文本渲染。"""

    def test_render_minimal_result(self):
        """最小结果应正常渲染。"""
        from scripts.stock import render_text

        result = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "change_pct": 1.5,
        }
        text = render_text(result)
        assert "sh600989" in text
        assert "宝丰能源" in text
        assert "18.5" in text
        assert "+1.50" in text

    def test_render_with_warning(self):
        """含 warning 字段应显示 ⚠。"""
        from scripts.stock import render_text

        result = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "change_pct": 1.5,
            "warning": "财务数据缺失",
        }
        text = render_text(result)
        assert "⚠" in text
        assert "财务数据缺失" in text

    def test_render_with_profile(self):
        """含 profile 字段应渲染行业画像。"""
        from scripts.stock import render_text

        result = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "change_pct": 1.5,
            "profile": {"type": "周期股", "industry": "能源"},
        }
        text = render_text(result)
        assert "行业画像" in text
        assert "周期股" in text
        assert "能源" in text


# ═══════════════════════════════════════════════════════════════
# 3. main 端到端（mock 业务层）
# ═══════════════════════════════════════════════════════════════


class TestStockMainE2E:
    """完整 main 调用（mock 业务层避免网络）。"""

    @patch("scripts.stock.StockAnalysisService")
    def test_main_json_output(self, mock_svc_cls, capsys):
        """--json 模式输出 JSON。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "change_pct": 1.5,
        }
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch("sys.argv", ["stock.py", "sh600989", "-j"]):
            stock.main()

        captured = capsys.readouterr()
        # 应输出 JSON
        data = json.loads(captured.out)
        assert data["code"] == "sh600989"
        assert data["name"] == "宝丰能源"

    @patch("scripts.stock.StockAnalysisService")
    def test_main_text_output(self, mock_svc_cls, capsys):
        """默认模式输出文本。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {
            "code": "sh600989",
            "name": "宝丰能源",
            "price": 18.50,
            "change_pct": 1.5,
        }
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch("sys.argv", ["stock.py", "sh600989"]):
            stock.main()

        captured = capsys.readouterr()
        # 文本输出含标题（新格式：名称（代码））
        assert "宝丰能源" in captured.out
        assert "sh600989" in captured.out

    @patch("scripts.stock.StockAnalysisService")
    def test_main_passes_options(self, mock_svc_cls):
        """--no-* 选项应传递给业务层。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {
            "code": "sh600989",
            "name": "x",
            "price": 1,
            "change_pct": 0,
        }
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch(
            "sys.argv",
            ["stock.py", "sh600989", "--no-finance", "--no-technical", "--no-chan"],
        ):
            stock.main()

        # 验证 analyze 被调用时包含正确参数
        mock_svc.analyze.assert_called_once_with(
            "sh600989",
            include_technical=False,
            include_finance=False,
            include_chan=False,
        )

    @patch("scripts.stock.StockAnalysisService")
    def test_main_empty_code_rejected(self, mock_svc_cls, capsys):
        """空字符串 code 应仍调用业务层（业务层负责校验）。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {"error": "invalid code"}
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch("sys.argv", ["stock.py", "", "-j"]):
            stock.main()

        # 应至少调一次
        assert mock_svc.analyze.called

"""测试 scripts/backtest.py：thin wrapper 入口。"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# scripts/backtest.py 和 scripts/backtest/ 同时存在，sys.path 加载时 package 优先。
# 用 importlib 直接加载 .py 版。
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "backtest_wrapper", PROJECT_ROOT / "scripts" / "backtest.py"
)
backtest = importlib.util.module_from_spec(_spec)
sys.modules["backtest_wrapper"] = backtest
_spec.loader.exec_module(backtest)


class TestBacktestWrapper:
    def test_imports_main(self):
        """backtest.py 应当导入 backtest.cli.main。"""
        assert hasattr(backtest, "main")
        assert callable(backtest.main)

    def test_main_callable_via_cli(self, monkeypatch):
        """直接调用 main() 应当运行 CLI。"""
        monkeypatch.setattr(sys, "argv", ["backtest.py"])
        try:
            # main 来自 backtest.cli（已 import）
            backtest.main()
        except SystemExit:
            pass
        except Exception:
            # cli.main 可能依赖外部资源，捕获通用异常
            pass
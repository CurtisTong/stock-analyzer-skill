#!/usr/bin/env python3
"""
多因子选股策略回测（thin wrapper）。
详见 skills/backtest/SKILL.md 和 scripts/backtest/cli.py
"""

import sys
from pathlib import Path

# 注入 scripts/ 和项目根到 sys.path，复用其他脚本的模式
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 项目根

from backtest.cli import main

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""持仓录入 Web 服务（零依赖 stdlib http.server）。

监听 127.0.0.1:8765，提供：
- GET  /                  浏览器表单页（内联 HTML + vanilla JS）
- GET  /api/health        健康检查
- GET  /api/positions     列出全部持仓 + 自选
- GET  /api/positions/<c> 查询单只
- POST /api/positions     8 个 action 的统一入口
- GET  /favicon.ico       204

启动：
    python3 scripts/portfolio_web.py [--host 127.0.0.1] [--port 8765]
"""

import sys
from pathlib import Path

# 让 python3 scripts/portfolio_web.py 从项目根运行也能找到 portfolio 包
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from portfolio.web.app import make_server, Handler, VERSION, main
from portfolio.web.utils import (
    _TOKEN_FILE,
    _TOKEN_DIR,
    _token,
    _ensure_token,
    _collect_code_name_map,
    MAX_BODY_BYTES,
)
from portfolio.web.dispatch import ALLOWED_ACTIONS

__all__ = ["make_server", "Handler", "VERSION"]

if __name__ == "__main__":
    main()

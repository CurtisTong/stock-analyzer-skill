"""
持仓录入 Web 服务模块。

提供零依赖 stdlib http.server 实现的 REST API + 内联 HTML 前端。

用法：
    from portfolio.web.app import make_server, Handler, VERSION
"""
from .app import make_server, Handler, VERSION

__all__ = ["make_server", "Handler", "VERSION"]

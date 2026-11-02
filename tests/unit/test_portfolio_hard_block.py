"""保护机制硬阻止接线进 add_position 的行为测试（v1.31 补口）。

不变量：
- 熔断激活 / 同票清仓冷却期内，add_position 抛 ValueError 拒绝加仓
  （is_trading_allowed 此前面世即孤儿，熔断状态落盘却拦不住任何加仓）；
- force=True 可知情越过；
- guardrails 不可用时放行（保护层自身故障不阻塞持仓操作）。

隔离：conftest autouse 已把 guardrails 状态 / trade_log / oplog 重定向
到 tmp_path，测试构造各自的 tmp 交易日志。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from portfolio import crud
from portfolio.manager import PortfolioManager


def _make_manager(tmp_path: Path) -> PortfolioManager:
    data_file = tmp_path / "portfolio.json"
    data_file.write_text(
        json.dumps({"version": 2, "positions": [], "watchlist": []}),
        encoding="utf-8",
    )
    return PortfolioManager(str(data_file))


def _write_trade_log(tmp_path: Path, code: str, days_ago: int) -> None:
    """在（已被 autouse 重定向的）tmp 目录写入一条清仓记录。"""
    sell_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    (tmp_path / "trade_log.json").write_text(
        json.dumps(
            {
                "version": 1,
                "records": [
                    {
                        "code": code,
                        "name": "测试股",
                        "buy_date": "2026-01-01",
                        "cost": 10.0,
                        "quantity": 100,
                        "sell_date": sell_date,
                        "sell_price": 9.0,
                        "profit": -100.0,
                        "reason": "reduce_to_zero",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class TestHardBlockWiring:
    def test_cooldown_blocks_add(self, tmp_path):
        """同票清仓 10 天冷却期内：add_position 拒绝。"""
        code = "sh600989"
        _write_trade_log(tmp_path, code, days_ago=2)
        pm = _make_manager(tmp_path)

        with pytest.raises(ValueError, match="保护机制硬阻止.*冷却期"):
            crud.add_position(pm, code, "测试股", cost=10.0, quantity=100)

    def test_force_overrides_cooldown(self, tmp_path):
        """force=True 知情越过冷却期。"""
        code = "sh600989"
        _write_trade_log(tmp_path, code, days_ago=2)
        pm = _make_manager(tmp_path)

        pos = crud.add_position(pm, code, "测试股", cost=10.0, quantity=100, force=True)
        assert pos["code"] == code

    def test_active_breaker_blocks_add(self, tmp_path):
        """回撤熔断激活期间：任何代码的 add_position 都拒绝。"""
        from portfolio.guardrails import record_breaker

        record_breaker("drawdown", "回撤熔断测试", cooldown_days=5)
        pm = _make_manager(tmp_path)

        with pytest.raises(ValueError, match="保护机制硬阻止.*回撤熔断测试"):
            crud.add_position(pm, "sz300274", "阳光电源", cost=50.0, quantity=200)

    def test_stale_cooldown_does_not_block(self, tmp_path):
        """冷却期已过（>10 天）：正常加仓。"""
        code = "sh600989"
        _write_trade_log(tmp_path, code, days_ago=30)
        pm = _make_manager(tmp_path)

        pos = crud.add_position(pm, code, "测试股", cost=10.0, quantity=100)
        assert pos["code"] == code

    def test_guardrails_failure_fails_open(self, tmp_path, monkeypatch):
        """guardrails 模块异常时放行（保护层故障不阻塞业务）。"""
        import portfolio.guardrails as guardrails

        def _boom(*a, **kw):
            raise RuntimeError("状态文件损坏")

        monkeypatch.setattr(guardrails, "is_trading_allowed", _boom)
        pm = _make_manager(tmp_path)

        pos = crud.add_position(pm, "sz300274", "阳光电源", cost=50.0, quantity=200)
        assert pos["code"] == "sz300274"

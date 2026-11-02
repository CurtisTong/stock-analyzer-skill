"""stock.py --with-backtest 附加逻辑的不变量测试。

不变量：run_backtest 的文档化失败路径（返回 {"error": ...}）必须走
backtest_error 降级展示，不得把缺字段渲染成 0% 胜率——回测失败与
"没跑赢"必须可区分。

回归背景（2026-11-02 skill 审查 P1）：main() 曾把 {"error": ...} 当
成功结果取 .get("win_rate_pct")→None，render_text 的 `or 0` 链将其
渲染成"胜率 0.0% / 累计收益 +0.00%"，且 elif backtest_error 分支
永远不可达。
"""

from __future__ import annotations

import stock


class TestAttachBacktest:
    def test_error_dict_routes_to_backtest_error(self, monkeypatch):
        """失败路径：{"error": ...} → backtest_error + data_failed，无假 0 数据。"""
        import backtest.metrics as metrics

        def _fail(strategy, codes, days=60):
            return {"error": "回测失败，无有效数据"}

        monkeypatch.setattr(metrics, "run_backtest", _fail)
        result: dict = {}
        stock._attach_backtest(result, "sh600519")

        assert "backtest" not in result
        assert result["backtest_error"] == "回测失败，无有效数据"
        assert "回测胜率" in result.get("data_failed", [])

        rendered = stock.render_text({**_base_result(), **result})
        assert "⚠ 回测失败" in rendered
        assert "胜率 0.0%" not in rendered

    def test_success_dict_maps_pct_fields(self, monkeypatch):
        """成功路径：字段映射 win_rate_pct → win_rate，回测卡片正常渲染。"""
        import backtest.metrics as metrics

        def _ok(strategy, codes, days=60):
            return {
                "win_rate_pct": 57.5,
                "total_return_pct": 3.8,
                "sharpe_ratio": 0.68,
                "max_drawdown_pct": 7.85,
            }

        monkeypatch.setattr(metrics, "run_backtest", _ok)
        result: dict = {}
        stock._attach_backtest(result, "sh600519")

        assert result["backtest"] == {
            "win_rate": 57.5,
            "total_return": 3.8,
            "sharpe": 0.68,
            "max_drawdown": 7.85,
        }
        assert "backtest_error" not in result

        rendered = stock.render_text({**_base_result(), **result})
        assert "胜率 57.5%" in rendered

    def test_exception_routes_to_backtest_error(self, monkeypatch):
        """抛异常路径保持 M4 行为：backtest_error + data_failed。"""
        import backtest.metrics as metrics

        def _boom(strategy, codes, days=60):
            raise RuntimeError("网络超时")

        monkeypatch.setattr(metrics, "run_backtest", _boom)
        result: dict = {}
        stock._attach_backtest(result, "sh600519")

        assert "backtest" not in result
        assert "网络超时" in result["backtest_error"]
        assert "回测胜率" in result.get("data_failed", [])


def _base_result() -> dict:
    """render_text 所需的最小合法输入。"""
    return {
        "code": "sh600519",
        "name": "贵州茅台",
        "price": 100.0,
        "change_pct": 0.5,
        "score": {"score": 60.0, "grade": "中性"},
        "technical": {},
        "finance": {},
    }

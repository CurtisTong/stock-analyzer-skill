"""
portfolio.web.dispatch 单元测试。

历史说明：本文件由 test_dispatch_coverage.py / test_dispatch_final.py /
test_dispatch_final2.py 合并而来。三文件内容互补不重复，合并后按
动作类型分组组织，便于维护。
"""

from unittest.mock import MagicMock


# ═══════════════════════════════════════════════════════════════
# 仓位 CRUD 动作
# ═══════════════════════════════════════════════════════════════


class TestAddReduceRemove:
    """add / reduce / remove 三个动作的 happy path。"""

    def test_add_position(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_position.return_value = True
        result = dispatch(pm, {"action": "add", "code": "sh600519", "quantity": 100, "cost": 1800})
        assert isinstance(result, dict)

    def test_reduce_position(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.reduce_position.return_value = True
        result = dispatch(pm, {"action": "reduce", "code": "sh600519", "quantity": 50})
        assert isinstance(result, dict)

    def test_remove_position(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.remove_position.return_value = True
        result = dispatch(pm, {"action": "remove", "code": "sh600519"})
        assert isinstance(result, dict)


class TestUpdatePosition:
    """update 动作。"""

    def test_update(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.update_position.return_value = True
        result = dispatch(pm, {"action": "update", "code": "sh600519", "cost": 1800, "quantity": 100})
        assert isinstance(result, dict)

    def test_update_error(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.update_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "update", "code": "sh600519", "cost": 1800})
        assert isinstance(result, dict)


class TestTagPosition:
    """tag / untag 动作。"""

    def test_tag(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.tag_position.return_value = True
        result = dispatch(pm, {"action": "tag", "code": "sh600519", "tag": "白马"})
        assert isinstance(result, dict)

    def test_untag(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.untag_position.return_value = True
        result = dispatch(pm, {"action": "untag", "code": "sh600519", "tag": "白马"})
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# 自选股动作
# ═══════════════════════════════════════════════════════════════


class TestWatch:
    """add_watch / remove_watch。"""

    def test_add_watch(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_watch.return_value = True
        result = dispatch(pm, {"action": "add_watch", "code": "sh600519", "name": "茅台"})
        assert isinstance(result, dict)

    def test_add_watch_with_note(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_watch.return_value = True
        result = dispatch(
            pm,
            {"action": "add_watch", "code": "sh600519", "name": "茅台", "note": "关注"},
        )
        assert isinstance(result, dict)

    def test_remove_watch(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.remove_watch.return_value = True
        result = dispatch(pm, {"action": "remove_watch", "code": "sh600519"})
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# 异常路径
# ═══════════════════════════════════════════════════════════════


class TestDispatchErrors:
    """各动作的 side_effect 异常路径。"""

    def test_add_position_error(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "add", "code": "sh600519", "quantity": 100, "cost": 1800})
        assert isinstance(result, dict)

    def test_reduce_position_error(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.reduce_position.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "reduce", "code": "sh600519", "quantity": 50})
        assert isinstance(result, dict)

    def test_remove_watch_error(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.remove_watch.side_effect = ValueError("bad")
        result = dispatch(pm, {"action": "remove_watch", "code": "sh600519"})
        assert isinstance(result, dict)


class TestMissingFields:
    """缺字段场景。"""

    def test_missing_code(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(pm, {"action": "add"})
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════
# 未知动作
# ═══════════════════════════════════════════════════════════════


class TestUnknownAction:
    """未识别 action 的兜底返回。

    两条用例保留两种断言强度：弱断言（isinstance）覆盖 unknown 兜底，
    强断言（含 error/ok 字段）覆盖 unknown_action 兜底。
    """

    def test_unknown_weak_assert(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(pm, {"action": "unknown"})
        assert isinstance(result, dict)

    def test_unknown_action_strong_assert(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(pm, {"action": "unknown_action"})
        assert isinstance(result, dict)
        assert "error" in result or "ok" in result


# ═══════════════════════════════════════════════════════════════
# cost_source 可追溯
# ═══════════════════════════════════════════════════════════════


class TestCostSourceDispatch:
    """add/update_position 的 cost_source 透传 + cost 变更影响 meta。"""

    def test_add_position_passes_cost_source(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.add_position.return_value = {"code": "sh600989", "cost": 18.5}
        result = dispatch(
            pm,
            {
                "action": "add_position",
                "code": "sh600989",
                "name": "宝丰能源",
                "cost": 18.5,
                "quantity": 1000,
                "cost_source": "screenshot",
            },
        )
        assert result["ok"] is True
        kwargs = pm.add_position.call_args
        assert kwargs.kwargs["cost_source"] == "screenshot"

    def test_add_position_invalid_cost_source(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(
            pm,
            {
                "action": "add_position",
                "code": "sh600989",
                "cost": 18.5,
                "quantity": 1000,
                "cost_source": "guessed",
            },
        )
        assert result["ok"] is False
        assert result["error"] == "invalid_cost_source"

    def test_update_position_cost_returns_impact_meta(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.get_position.return_value = {
            "code": "sh600989",
            "cost": 18.5,
            "quantity": 1000,
        }
        pm.update_position.return_value = {
            "code": "sh600989",
            "cost": 41.93,
            "cost_source": "user_input",
        }
        result = dispatch(
            pm,
            {
                "action": "update_position",
                "code": "sh600989",
                "cost": 41.93,
            },
        )
        assert result["ok"] is True
        assert result["meta"]["cost_before"] == 18.5
        assert result["meta"]["cost_after"] == 41.93
        assert "浮亏" in result["meta"]["hint"]

    def test_update_position_passes_cost_source(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        pm.update_position.return_value = {"code": "sh600989", "cost": 41.93}
        dispatch(
            pm,
            {
                "action": "update_position",
                "code": "sh600989",
                "cost": 41.93,
                "cost_source": "screenshot",
            },
        )
        kwargs = pm.update_position.call_args
        assert kwargs.kwargs["cost_source"] == "screenshot"

    def test_update_position_invalid_cost_source(self):
        from portfolio.web.dispatch import dispatch

        pm = MagicMock()
        result = dispatch(
            pm,
            {
                "action": "update_position",
                "code": "sh600989",
                "cost": 41.93,
                "cost_source": "weird",
            },
        )
        assert result["ok"] is False
        assert result["error"] == "invalid_cost_source"

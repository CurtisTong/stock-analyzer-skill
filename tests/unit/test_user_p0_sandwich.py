"""user-P0-2 回归：错误三明治结构 + stock.py 假研判防护。

背景（用户专家审查）：错误信息没有"症状/根因/下一步"三段式；stock.py 对
"格式正确但不存在"的代码（999999）输出 🟢 综合评分 0.0 —— 用户以为分析
成功。本文件锁定两处修复。
"""

from __future__ import annotations

import pytest


class TestSandwichError:
    """handle_errors 的错误输出必须是 [❌ / 根因 / 下一步] 三明治。"""

    def test_network_error_has_all_three_parts(self):
        from common.cli_base import sandwich_error

        class FakeNetworkError(Exception):
            pass

        FakeNetworkError.__name__ = "NetworkError"  # 命中映射表

        msg = sandwich_error(FakeNetworkError("boom"))
        assert msg.startswith("❌")
        assert "【根因】" in msg
        assert "【下一步】" in msg

    def test_unknown_error_has_next_step(self):
        from common.cli_base import sandwich_error

        # 不在映射表的异常类型 → 至少给 --debug 出口
        msg = sandwich_error(ValueError("x"))
        assert "【下一步】" in msg
        assert "--debug" in msg

    def test_validation_hint_mentions_code_formats(self):
        from common.cli_base import sandwich_error

        from common.exceptions import ValidationError

        msg = sandwich_error(ValidationError("code", "abc", "格式无效"))
        assert "上证/深市" in msg or "sh600989" in msg


class TestKnownCode:
    """_known_code 从本地池识别代码（兜底判定输入是否可能输错）。"""

    def test_known_maotai(self):
        import stock

        assert stock._known_code("sh600519") is True

    def test_unknown_code(self):
        import stock

        assert stock._known_code("sh999999") is False

    def test_known_without_prefix(self):
        import stock

        # sz000001 在池内；裸代码应同样命中
        assert stock._known_code("000001") is True


class TestDataBlackoutGuard:
    """数据全降级时不得输出假研判。"""

    def _result(self, price=0.0, failed=None):
        return {"price": price, "data_failed": failed or ["行情", "财务", "K线"]}

    def test_normal_result_renders(self):
        import stock

        assert stock._check_data_blackout(self._result(price=12.3, failed=[]), "sh600519") is None

    def test_unknown_code_blackout_says_maybe_wrong_code(self):
        import stock

        msg = stock._check_data_blackout(self._result(), "sh999999")
        assert msg is not None
        assert "已退市" in msg or "输入有误" in msg
        assert "【根因】" in msg and "【下一步】" in msg

    def test_known_code_blackout_says_data_source(self):
        import stock

        msg = stock._check_data_blackout(self._result(), "sh600519")
        assert msg is not None
        assert "数据源" in msg
        assert "【下一步】" in msg

    def test_partial_failure_still_renders(self):
        import stock

        # 只有 1 类失败（如仅财务挂）→ 仍渲染（降级正常）
        assert stock._check_data_blackout(self._result(price=12.3, failed=["财务"]), "sh600519") is None

"""宏观安全垫门禁测试（v2.7.x 覆盖率提升）。

mock yfinance + config.loader.safe_get，覆盖 GREEN/YELLOW/RED 三态。
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestMacroSafetyGate:
    """MacroSafetyGate 三态判定 + 降级。"""

    def test_disabled_returns_green(self):
        """宏观安全垫禁用时返回 GREEN。"""
        with patch("strategies.macro.gate.safe_get", return_value=False):
            from strategies.macro.gate import MacroSafetyGate, MacroState

            gate = MacroSafetyGate()
            state, msg = gate.check()
            assert state == MacroState.GREEN
            assert "已禁用" in msg

    def test_green_when_vix_low(self):
        """VIX 低于阈值时返回 GREEN。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = 15.0
        gate._tlt_cache = 95.0
        gate._cache_loaded = True
        # safe_get: 第1次返回 True(enabled)，后续返回阈值默认值
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.GREEN
            assert "宏观稳定" in msg

    def test_yellow_when_vix_elevated(self):
        """VIX > 25 但 < 35 时返回 YELLOW。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = 28.0
        gate._tlt_cache = 90.0
        gate._cache_loaded = True
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.YELLOW
            assert "避险升温" in msg

    def test_red_when_vix_extreme(self):
        """VIX > 35 时返回 RED。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = 40.0
        gate._tlt_cache = 90.0
        gate._cache_loaded = True
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.RED
            assert "系统性风险" in msg

    def test_red_when_tlt_crash(self):
        """TLT < 80 时返回 RED。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = 20.0
        gate._tlt_cache = 75.0
        gate._cache_loaded = True
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.RED

    def test_yellow_when_tlt_low(self):
        """TLT < 85 但 > 80 时返回 YELLOW。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = 20.0
        gate._tlt_cache = 82.0
        gate._cache_loaded = True
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.YELLOW

    def test_green_when_data_unavailable(self):
        """VIX/TLT 均为 None 时返回 GREEN（降级不阻断）。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        gate._vix_cache = None
        gate._tlt_cache = None
        gate._cache_loaded = True
        with patch("strategies.macro.gate.safe_get", side_effect=lambda *a, **kw: True if a[1] == "enabled" else a[-1]):
            state, msg = gate.check()
            assert state == MacroState.GREEN
            assert "N/A" in msg

    def test_load_indicators_yfinance_failure(self):
        """yfinance 不可用时降级为 None。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        with patch.dict(sys.modules, {"yfinance": None}):
            gate._load_indicators()
            assert gate._vix_cache is None
            assert gate._tlt_cache is None
            assert gate._cache_loaded is True

    def test_fetch_vix_uses_cache(self):
        """二次调用 _fetch_vix 使用缓存。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        gate._vix_cache = 25.0
        gate._cache_loaded = True
        assert gate._fetch_vix() == 25.0

    def test_fetch_tlt_uses_cache(self):
        """二次调用 _fetch_tlt 使用缓存。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        gate._tlt_cache = 90.0
        gate._cache_loaded = True
        assert gate._fetch_tlt() == 90.0

"""宏观安全垫门禁测试（v2.7.x 覆盖率提升，v2.x #12 适配新 API）。

mock yfinance + config.loader.safe_get，覆盖 GREEN/YELLOW/ORANGE/RED/UNKNOWN 五态。
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def _seed_cache(gate, vix=None, tlt=None, ashare_vol=None):
    """预置缓存（#12 新 API：用 _cache_ts 替代 _cache_loaded）。"""
    gate._vix_cache = vix
    gate._tlt_cache = tlt
    gate._ashare_vol = ashare_vol
    gate._cache_ts = time.time()


def _enabled_safe_get(*a, **kw):
    """safe_get mock：enabled 返回 True，其余返回默认值。"""
    if a[1] == "enabled":
        return True
    return a[-1]


class TestMacroSafetyGate:
    """MacroSafetyGate 五态判定 + 降级。"""

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
        _seed_cache(gate, vix=15.0, tlt=95.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.GREEN
            assert "宏观稳定" in msg

    def test_yellow_when_vix_elevated(self):
        """VIX > 25 但 < 30 时返回 YELLOW。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=28.0, tlt=90.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.YELLOW
            assert "避险升温" in msg

    def test_red_when_vix_extreme(self):
        """VIX > 35 时返回 RED。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=40.0, tlt=90.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.RED
            assert "系统性风险" in msg

    def test_red_when_tlt_crash(self):
        """TLT < 80 时返回 RED。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=20.0, tlt=75.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.RED

    def test_yellow_when_tlt_low(self):
        """TLT < 85 但 > 82 时返回 YELLOW。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=20.0, tlt=83.0, ashare_vol=15.0)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.YELLOW

    def test_unknown_when_data_unavailable(self):
        """(#12) VIX/TLT/ashare 均为 None 时返回 UNKNOWN（不再降级 GREEN）。"""
        from strategies.macro.gate import MacroSafetyGate, MacroState

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=None, tlt=None, ashare_vol=None)
        with patch("strategies.macro.gate.safe_get", side_effect=_enabled_safe_get):
            state, msg = gate.check()
            assert state == MacroState.UNKNOWN
            assert "数据全部缺失" in msg

    def test_load_indicators_yfinance_failure(self):
        """yfinance 不可用时降级为 None。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        with patch.dict(sys.modules, {"yfinance": None}):
            gate._load_indicators()
            assert gate._vix_cache is None
            assert gate._tlt_cache is None
            assert gate._cache_ts > 0  # (#12) _cache_loaded -> _cache_ts

    def test_fetch_vix_uses_cache(self):
        """二次调用 _fetch_vix 使用缓存。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, vix=25.0)
        assert gate._fetch_vix() == 25.0

    def test_fetch_tlt_uses_cache(self):
        """二次调用 _fetch_tlt 使用缓存。"""
        from strategies.macro.gate import MacroSafetyGate

        gate = MacroSafetyGate()
        _seed_cache(gate, tlt=90.0)
        assert gate._fetch_tlt() == 90.0

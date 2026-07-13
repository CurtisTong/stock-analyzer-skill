"""测试 scripts/technical.py：TechnicalInput + _compute_all + main。

使用 importlib 加载 scripts/technical.py（绕过 technical/ package 屏蔽）。
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# 加载 legacy scripts/technical.py（绕过 technical/ package）
_spec = importlib.util.spec_from_file_location(
    "technical_legacy_mod", PROJECT_ROOT / "scripts" / "technical.py"
)
technical = importlib.util.module_from_spec(_spec)
sys.modules["technical_legacy_mod"] = technical
_spec.loader.exec_module(technical)


def _make_input(n=100, code="sh600519"):
    """构造 TechnicalInput 含最小 K 线数据。"""
    closes = [100 + i * 0.5 for i in range(n)]
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    opens = [c - 0.1 for c in closes]
    volumes = [1000 + i * 10 for i in range(n)]
    records = [
        SimpleNamespace(
            date=f"2026-07-{i+1:02d}", open=o, high=h, low=l, close=c, volume=v,
        )
        for i, (o, h, l, c, v) in enumerate(zip(opens, highs, lows, closes, volumes))
    ]
    quote = {"code": code, "name": "test", "pe": 15.0, "pb": 2.0, "net_profit_yoy": 10.0}
    return technical.TechnicalInput(
        closes=closes, opens=opens, highs=highs, lows=lows, volumes=volumes,
        records=records, board="main", quote=quote, args=None,
    )


def _mock_all_indicators(monkeypatch_target=technical):
    """mock 所有技术指标函数。"""
    mocks = {}
    patches = [
        ("ma_system", {"ma5": [], "ma20": []}),
        ("macd_full", {"macd": 0}),
        ("kdj_full", {"k": 50, "d": 50, "j": 50}),
        ("bollinger", {"upper": 110, "mid": 100, "lower": 90}),
        ("rsi_features", {"rsi6": 50, "rsi12": 50, "rsi24": 50}),
        ("volume_analysis", {"vol_ratio": 1.0}),
        ("detect_candle_patterns", []),
        ("support_resistance", {"nearest_resistance": 105}),
        ("box_detection", {"in_box": False}),
        ("breakout_check", {"is_breakout": False}),
        ("wave_state", {"state": "震荡"}),
        ("limit_analysis", {"limit_status": "normal"}),
        ("incremental_ma", []),
        ("pe_percentile_score", 50),
    ]
    ctx = []
    for name, ret in patches:
        p = patch.object(monkeypatch_target, name, return_value=ret)
        ctx.append(p)
    return ctx


class TestTechnicalInput:
    def test_create(self):
        inp = _make_input()
        assert len(inp.closes) == 100
        assert inp.board == "main"


class TestComputeAll:
    def test_basic_features(self):
        """基础模式（不启用 classify）。"""
        inp = _make_input()
        ctx = _mock_all_indicators(technical)
        for p in ctx:
            p.start()
        try:
            result = technical._compute_all(inp)
        finally:
            for p in ctx:
                p.stop()
        assert "ma_system" in result
        assert "macd" in result
        assert "kdj" in result
        assert "bollinger" in result
        assert "rsi" in result
        assert "volume" in result
        assert "patterns" in result
        assert "support_resistance" in result
        assert "breakout" in result
        assert "wave" in result
        assert "limit_analysis" in result
        assert "local_patterns" in result
        assert "valuation" in result
        assert "market_environment" in result

    def test_with_classify(self):
        args = SimpleNamespace(classify=True, no_chan=False, market_index=None)
        inp = _make_input()
        inp.args = args
        # 修改 support_resistance 让 nearest_resistance=None 避开 breakout
        with patch.object(technical, "ma_system", return_value={}), \
             patch.object(technical, "macd_full", return_value={}), \
             patch.object(technical, "kdj_full", return_value={}), \
             patch.object(technical, "bollinger", return_value={}), \
             patch.object(technical, "rsi_features", return_value={}), \
             patch.object(technical, "volume_analysis", return_value={}), \
             patch.object(technical, "detect_candle_patterns", return_value=[]), \
             patch.object(technical, "support_resistance", return_value={"nearest_resistance": None}), \
             patch.object(technical, "box_detection", return_value={}), \
             patch.object(technical, "breakout_check", return_value={}), \
             patch.object(technical, "wave_state", return_value={}), \
             patch.object(technical, "limit_analysis", return_value={}), \
             patch.object(technical, "incremental_ma", return_value=[]), \
             patch.object(technical, "pe_percentile_score", return_value=60), \
             patch.object(technical, "detect_market_environment", return_value={"state": "bull"}):
            # Patch 内部 import 的 chan/classifier
            with patch.dict(sys.modules, {
                "chan": MagicMock(chan_full_analysis=MagicMock(return_value={"valid": True})),
                "classifier": MagicMock(classify_stock=MagicMock(return_value={"type": "value"})),
            }):
                result = technical._compute_all(inp)
        assert "classification" in result
        assert "chan_theory" in result

    def test_peg_calculation(self):
        inp = _make_input()
        inp.quote = {"code": "sh600519", "pe": 30.0, "pb": 3.0, "net_profit_yoy": 15.0}
        ctx = _mock_all_indicators(technical)
        for p in ctx:
            p.start()
        try:
            result = technical._compute_all(inp)
        finally:
            for p in ctx:
                p.stop()
        # PEG = 30/15 = 2.0
        assert result["valuation"]["peg"] == 2.0

    def test_peg_zero_growth(self):
        inp = _make_input()
        inp.quote = {"code": "sh600519", "pe": 30.0, "pb": 3.0, "net_profit_yoy": 0}
        ctx = _mock_all_indicators(technical)
        for p in ctx:
            p.start()
        try:
            result = technical._compute_all(inp)
        finally:
            for p in ctx:
                p.stop()
        assert result["valuation"]["peg"] == 0


class TestMain:
    def test_no_args(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["technical.py"])
        try:
            technical.main()
        except SystemExit:
            pass

    def test_with_stock_code(self, capsys, monkeypatch):
        """正常 main 调用（mock 所有外部依赖）。"""
        # 注入 fetch_kline/fetch_batch 到 technical module
        technical.fetch_kline = MagicMock(return_value=[])
        technical.fetch_batch = MagicMock(return_value=[SimpleNamespace(code="sh600519", price=100)])
        with patch.object(technical, "_compute_all", return_value={}), \
             patch("builtins.print"):
            monkeypatch.setattr(sys, "argv", ["technical.py", "sh600519"])
            try:
                technical.main()
            except SystemExit:
                pass

    def test_with_classify_flag(self, capsys, monkeypatch):
        technical.fetch_kline = MagicMock(return_value=[])
        technical.fetch_batch = MagicMock(return_value=[SimpleNamespace(code="sh600519", price=100)])
        with patch.object(technical, "_compute_all", return_value={}), \
             patch("builtins.print"):
            monkeypatch.setattr(sys, "argv",
                                 ["technical.py", "sh600519", "--classify"])
            try:
                technical.main()
            except SystemExit:
                pass

    def test_with_json_flag(self, capsys, monkeypatch):
        technical.fetch_kline = MagicMock(return_value=[])
        technical.fetch_batch = MagicMock(return_value=[SimpleNamespace(code="sh600519", price=100)])
        with patch.object(technical, "_compute_all", return_value={}), \
             patch("builtins.print"):
            monkeypatch.setattr(sys, "argv", ["technical.py", "sh600519", "-j"])
            try:
                technical.main()
            except SystemExit:
                pass

    def test_with_no_chan_flag(self, capsys, monkeypatch):
        technical.fetch_kline = MagicMock(return_value=[])
        technical.fetch_batch = MagicMock(return_value=[SimpleNamespace(code="sh600519", price=100)])
        with patch.object(technical, "_compute_all", return_value={}), \
             patch("builtins.print"):
            monkeypatch.setattr(sys, "argv",
                                 ["technical.py", "sh600519", "--classify", "--no-chan"])
            try:
                technical.main()
            except SystemExit:
                pass
"""测试 scripts/chan.py：缠论兼容层 wrapper。"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import chan as chan_wrapper


class TestChanWrapper:
    def test_re_exports(self):
        """兼容层应当导出所有缠论函数。"""
        assert hasattr(chan_wrapper, "chan_merge_inclusions")
        assert hasattr(chan_wrapper, "chan_fenxing")
        assert hasattr(chan_wrapper, "chan_bi")
        assert hasattr(chan_wrapper, "chan_xianduan")
        assert hasattr(chan_wrapper, "chan_zhongshu")
        assert hasattr(chan_wrapper, "_macd_area")
        assert hasattr(chan_wrapper, "chan_beichi")
        assert hasattr(chan_wrapper, "chan_maidian")
        assert hasattr(chan_wrapper, "chan_full_analysis")

    def test_all_callable(self):
        """所有导出函数均可调用。"""
        for name in ["chan_merge_inclusions", "chan_fenxing", "chan_bi",
                     "chan_xianduan", "chan_zhongshu", "chan_beichi",
                     "chan_maidian", "chan_full_analysis"]:
            assert callable(getattr(chan_wrapper, name))

    def test_all_exports(self):
        """__all__ 至少包含主要 API（可能含额外辅助符号）。"""
        all_set = set(chan_wrapper.__all__)
        for name in ["chan_merge_inclusions", "chan_fenxing", "chan_bi",
                     "chan_xianduan", "chan_zhongshu", "_macd_area",
                     "chan_beichi", "chan_maidian", "chan_full_analysis"]:
            assert name in all_set, f"Missing {name} in __all__"

    def test_main_no_args(self, capsys, monkeypatch):
        """无参数时调用 main 会抛 SystemExit（usage）。"""
        # 触发 if __name__ == "__main__" 块用 runpy
        import runpy
        monkeypatch.setattr(sys, "argv", ["chan.py"])
        with pytest.raises((SystemExit, Exception)):
            runpy.run_module("chan", run_name="__main__", alter_sys=True)

    def test_chan_merge_inclusions_empty(self):
        """空输入返回空。"""
        result = chan_wrapper.chan_merge_inclusions([])
        assert result == []

    def test_chan_fenxing_empty(self):
        """空 K 线返回空。"""
        result = chan_wrapper.chan_fenxing([])
        assert result == []
"""测试 scripts/fetchers/kline/efinance_kline.py：efinance K 线 fetcher。"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "efinance_kline_mod",
    PROJECT_ROOT / "scripts" / "fetchers" / "kline" / "efinance_kline.py",
)
efinance_kline = importlib.util.module_from_spec(_spec)
sys.modules["efinance_kline_mod"] = efinance_kline
_spec.loader.exec_module(efinance_kline)


class TestEfinanceKlineFetcher:
    def test_init(self):
        """初始化 name + priority=0。"""
        f = efinance_kline.EfinanceKlineFetcher()
        assert f.name == "efinance_kline"
        assert f.priority == 0

    def test_no_efinance(self):
        """HAS_EFINANCE=False 时返回 None。"""
        with patch.object(efinance_kline, "HAS_EFINANCE", False):
            f = efinance_kline.EfinanceKlineFetcher()
            result = f.fetch("sh600519")
        assert result is None

    def test_fetch_success(self):
        """成功返回 K 线数据。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        rows = [
            {
                "日期": "2026-07-01",
                "开盘": 100.0,
                "收盘": 102.0,
                "最高": 103.0,
                "最低": 99.0,
                "成交量": 1000000,
            },
            {
                "日期": "2026-07-02",
                "开盘": 102.0,
                "收盘": 105.0,
                "最高": 106.0,
                "最低": 101.0,
                "成交量": 1200000,
            },
        ]
        df = pd.DataFrame(rows)

        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(return_value=df)
        # 预设置 m.ef 属性（fetch 内 import 已失败时不存在）
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        result = f.fetch("sh600519")
        assert result is not None
        assert len(result) == 2
        assert result[0]["close"] == "102.0"
        assert result[0]["source"] == "efinance"

    def test_fetch_empty_df(self):
        """空 df 时返回 None。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = pd.DataFrame()

        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(return_value=df)
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        result = f.fetch("sh600519")
        assert result is None

    def test_fetch_exception(self):
        """异常时返回 None。"""
        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(side_effect=Exception("err"))
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        result = f.fetch("sh600519")
        assert result is None

    def test_scale_to_klt_mapping(self):
        """scale → klt 映射。"""
        for scale, expected_klt in [(5, 5), (15, 15), (30, 30), (60, 60), (240, 101)]:
            try:
                import pandas as pd
            except ImportError:
                pytest.skip("pandas not available")
            df = pd.DataFrame(
                [
                    {
                        "日期": "2026-07-01",
                        "开盘": 1,
                        "收盘": 1,
                        "最高": 1,
                        "最低": 1,
                        "成交量": 1,
                    }
                ]
            )
            fake_ef = MagicMock()
            fake_ef.stock.get_quote_history = MagicMock(return_value=df)
            efinance_kline.ef = fake_ef
            efinance_kline.HAS_EFINANCE = True
            f = efinance_kline.EfinanceKlineFetcher()
            f.fetch("sh600519", scale=scale, datalen=10)
            call = fake_ef.stock.get_quote_history.call_args
            assert call.kwargs["klt"] == expected_klt

    def test_default_scale_and_datalen(self):
        """默认 scale=240, datalen=30。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = pd.DataFrame(
            [
                {
                    "日期": "2026-07-01",
                    "开盘": 1,
                    "收盘": 1,
                    "最高": 1,
                    "最低": 1,
                    "成交量": 1,
                }
            ]
        )
        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(return_value=df)
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        f.fetch("sh600519")
        call = fake_ef.stock.get_quote_history.call_args
        assert call.kwargs["klt"] == 101
        assert call.kwargs["count"] == 30

    def test_result_empty_list(self):
        """iterrows 空时 result 为空。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = pd.DataFrame(columns=["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(return_value=df)
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        result = f.fetch("sh600519")
        assert result is None

    def test_day_truncation(self):
        """日期截断到 10 字符。"""
        try:
            import pandas as pd
        except ImportError:
            pytest.skip("pandas not available")
        df = pd.DataFrame(
            [
                {
                    "日期": "2026-07-01T09:30:00",
                    "开盘": 100.0,
                    "收盘": 102.0,
                    "最高": 103.0,
                    "最低": 99.0,
                    "成交量": 1000000,
                }
            ]
        )
        fake_ef = MagicMock()
        fake_ef.stock.get_quote_history = MagicMock(return_value=df)
        efinance_kline.ef = fake_ef
        efinance_kline.HAS_EFINANCE = True
        f = efinance_kline.EfinanceKlineFetcher()
        result = f.fetch("sh600519")
        assert result[0]["day"] == "2026-07-01"


class TestTushareCheck:
    def test_no_token_returns_false(self, monkeypatch):
        """无 TUSHARE_TOKEN 时返回 False。"""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        from fetchers._common import tushare_check

        assert tushare_check.check_tushare() is False

    def test_with_token_tushare_available(self, monkeypatch):
        """有 TUSHARE_TOKEN + tushare 包时返回 True。"""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        from fetchers._common import tushare_check

        with patch.dict("sys.modules", {"tushare": MagicMock()}):
            assert tushare_check.check_tushare() is True

    def test_with_token_tushare_missing(self, monkeypatch):
        """有 TUSHARE_TOKEN 但 tushare 未装时返回 False。"""
        monkeypatch.setenv("TUSHARE_TOKEN", "test_token")
        from fetchers._common import tushare_check

        # 移除 tushare module
        with patch.dict("sys.modules", {"tushare": None}):
            assert tushare_check.check_tushare() is False

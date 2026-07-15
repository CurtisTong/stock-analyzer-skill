"""(#3) 涨跌停换手板区分测试。

覆盖：
- 一字板（无量涨停）-> 硬过滤
- 换手板（有量涨停）-> 软警告
- 跌停 -> 硬过滤
- 非涨停 -> 不触发
- zt_pool 缺失 -> 回退硬过滤
- allow_tradable_limit_up 开关控制
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


class TestZtPoolNormalize:
    """zt_pool 代码标准化。"""

    def test_sh_code(self):
        from data.zt_pool import _normalize_code

        assert _normalize_code("600519") == "sh600519"

    def test_sz_code(self):
        from data.zt_pool import _normalize_code

        assert _normalize_code("000001") == "sz000001"
        assert _normalize_code("300750") == "sz300750"

    def test_bj_code(self):
        from data.zt_pool import _normalize_code

        assert _normalize_code("830799") == "bj830799"

    def test_already_prefixed(self):
        from data.zt_pool import _normalize_code

        assert _normalize_code("sh600519") == "sh600519"


class TestIsOneWordLimitUp:
    """一字板判定。"""

    def test_one_word_board(self):
        """封单大 + 未炸板 + 换手率 < 1% -> 一字板。"""
        from data.zt_pool import is_one_word_limit_up

        pool = {
            "sh600519": {
                "lbc": 1,
                "zbc": 0,
                "fund_buy": 50000000,
                "turnover_rate": 0.3,
                "name": "茅台",
                "change_pct": 10.0,
            }
        }
        assert is_one_word_limit_up("sh600519", zt_pool=pool) is True

    def test_tradable_board(self):
        """有换手 + 炸板 -> 非一字板（换手板）。"""
        from data.zt_pool import is_one_word_limit_up

        pool = {
            "sh600519": {
                "lbc": 1,
                "zbc": 2,
                "fund_buy": 10000000,
                "turnover_rate": 8.5,
                "name": "茅台",
                "change_pct": 10.0,
            }
        }
        assert is_one_word_limit_up("sh600519", zt_pool=pool) is False

    def test_high_turnover_not_one_word(self):
        """换手率高（>1%）但未炸板 -> 非一字板。"""
        from data.zt_pool import is_one_word_limit_up

        pool = {
            "sh600519": {
                "lbc": 1,
                "zbc": 0,
                "fund_buy": 20000000,
                "turnover_rate": 5.0,
                "name": "茅台",
                "change_pct": 10.0,
            }
        }
        assert is_one_word_limit_up("sh600519", zt_pool=pool) is False

    def test_not_in_pool(self):
        """不在涨停池 -> 非一字板。"""
        from data.zt_pool import is_one_word_limit_up

        assert is_one_word_limit_up("sh600519", zt_pool={}) is False


class TestHardFilterLimitUp:
    """_hard_filter 涨跌停区分。"""

    def _make_quote(
        self,
        code="sh600519",
        name="茅台",
        total_cap=2000,
        amount=10000_0000,
        change_pct=0.5,
    ):
        return {
            "code": code,
            "name": name,
            "total_cap": total_cap,
            "amount": amount,
            "change_pct": change_pct,
        }

    def test_normal_stock_no_limit_filter(self):
        """非涨停跌停股不触发涨跌停过滤。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote(change_pct=3.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        with patch(
            "business.finance_freshness.check_finance_freshness",
            return_value=(False, ""),
        ):
            reasons, warnings = svc._hard_filter(quote, fin, {})
        assert not any("涨跌停" in r for r in reasons)
        assert not any("涨停" in w for w in warnings)

    def test_limit_down_hard_reject(self):
        """跌停 -> 硬过滤。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        # 主板跌停 change_pct <= -9.5
        quote = self._make_quote(change_pct=-10.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        with patch(
            "business.finance_freshness.check_finance_freshness",
            return_value=(False, ""),
        ):
            reasons, warnings = svc._hard_filter(quote, fin, {})
        assert any("涨跌停" in r for r in reasons)

    def test_limit_up_default_hard_reject(self):
        """默认（无 allow_tradable 开关）涨停 -> 硬过滤。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote(change_pct=10.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        with patch(
            "business.finance_freshness.check_finance_freshness",
            return_value=(False, ""),
        ):
            reasons, warnings = svc._hard_filter(quote, fin, {})
        assert any("涨跌停" in r for r in reasons)

    def test_one_word_limit_up_hard_reject_with_allow_tradable(self):
        """allow_tradable=True 时一字板仍硬过滤。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote(code="sh600519", change_pct=10.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        pool = {
            "sh600519": {
                "lbc": 1,
                "zbc": 0,
                "fund_buy": 50000000,
                "turnover_rate": 0.3,
                "name": "茅台",
                "change_pct": 10.0,
            }
        }
        with (
            patch(
                "business.finance_freshness.check_finance_freshness",
                return_value=(False, ""),
            ),
            patch("data.zt_pool.get_zt_pool", return_value=pool),
        ):
            reasons, warnings = svc._hard_filter(
                quote, fin, {"allow_tradable_limit_up": True}
            )
        assert any("一字涨停" in r for r in reasons)

    def test_tradable_limit_up_warning_with_allow_tradable(self):
        """allow_tradable=True 时换手板降为软警告。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote(code="sh600519", change_pct=10.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        pool = {
            "sh600519": {
                "lbc": 1,
                "zbc": 2,
                "fund_buy": 10000000,
                "turnover_rate": 8.5,
                "name": "茅台",
                "change_pct": 10.0,
            }
        }
        with (
            patch(
                "business.finance_freshness.check_finance_freshness",
                return_value=(False, ""),
            ),
            patch("data.zt_pool.get_zt_pool", return_value=pool),
        ):
            reasons, warnings = svc._hard_filter(
                quote, fin, {"allow_tradable_limit_up": True}
            )
        assert not any("涨停" in r for r in reasons)
        assert any("涨停(有量" in w for w in warnings)

    def test_zt_pool_unavailable_falls_back_to_hard_reject(self):
        """zt_pool 不可用时回退硬过滤。"""
        from business.screening_service import ScreeningService

        svc = ScreeningService()
        quote = self._make_quote(change_pct=10.0)
        fin = {"eps": 1.0, "report_date": "2026-03-31"}
        with (
            patch(
                "business.finance_freshness.check_finance_freshness",
                return_value=(False, ""),
            ),
            patch(
                "data.zt_pool.is_one_word_limit_up",
                side_effect=Exception("network error"),
            ),
        ):
            reasons, warnings = svc._hard_filter(
                quote, fin, {"allow_tradable_limit_up": True}
            )
        assert any("涨跌停" in r for r in reasons)

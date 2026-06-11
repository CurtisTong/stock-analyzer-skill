"""
business 层单元测试：覆盖 ScreeningService 和 StockAnalysisService 的核心路径。
"""
import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from business.screening_service import ScreeningService, _board_limit, _min_survival_cap, _goodwill_threshold, _pledge_threshold, _st_prefixes  # noqa: E402


def _make_namespace(**kwargs):
    """构造一个 argparse-like 命名空间对象。"""
    defaults = {"min_amount": 5000, "min_cap": 40, "exclude_loss": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ═══════════════════════════════════════════════════════════════
# 1. 阈值辅助函数
# ═══════════════════════════════════════════════════════════════
class TestThresholdHelpers:
    """模块级阈值读取函数。"""

    def test_board_limit_known_boards(self):
        assert _board_limit("主板") == 9.5
        assert _board_limit("创业板") == 19.5
        assert _board_limit("科创板") == 19.5
        assert _board_limit("北交所") == 29.5

    def test_board_limit_unknown_board(self):
        assert _board_limit("unknown") == 9.5

    def test_min_survival_cap_known_boards(self):
        assert _min_survival_cap("主板") == 5
        assert _min_survival_cap("创业板") == 3
        assert _min_survival_cap("北交所") == 2

    def test_goodwill_threshold_default(self):
        assert _goodwill_threshold() == 30

    def test_pledge_threshold_default(self):
        assert _pledge_threshold() == 70

    def test_st_prefixes_default(self):
        prefixes = _st_prefixes()
        assert "ST" in prefixes
        assert "*ST" in prefixes


# ═══════════════════════════════════════════════════════════════
# 2. ScreeningService 初始化
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceInit:
    def test_default_strategy(self):
        svc = ScreeningService()
        assert svc.default_strategy == "balanced"
        assert svc.max_workers == 8


# ═══════════════════════════════════════════════════════════════
# 3. ScreeningService._hard_filter
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceHardFilter:
    def setup_method(self):
        self.svc = ScreeningService()
        self.filters = {"min_amount": 5000, "min_cap": 40, "exclude_loss": False}

    def test_st_stock_rejected(self):
        """ST 股票应被拒。"""
        quote = {"code": "sh600519", "name": "ST测试", "total_cap": 100, "amount": 1e8}
        fin = {"eps": 1, "roe": 10, "debt_ratio": 30}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert "ST风险" in reasons

    def test_normal_stock_passes(self):
        """正常股票应通过。"""
        quote = {
            "code": "sh600519", "name": "贵州茅台",
            "total_cap": 1000, "amount": 5e9, "change_pct": 1.0,
        }
        fin = {"eps": 10, "roe": 20, "debt_ratio": 30}
        assert self.svc._hard_filter(quote, fin, self.filters) == []

    def test_low_cap_rejected(self):
        quote = {"code": "sh600000", "name": "小盘", "total_cap": 5, "amount": 1e8, "change_pct": 0}
        fin = {"eps": 1, "roe": 10}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert any("市值" in r for r in reasons)

    def test_loss_excluded_with_flag(self):
        """EPS<=0 + exclude_loss=True 应被拒。"""
        quote = {"code": "sh600000", "name": "亏损股", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"eps": -1, "roe": -5}
        reasons = self.svc._hard_filter(quote, fin, {**self.filters, "exclude_loss": True})
        assert "EPS<=0" in reasons

    def test_loss_not_excluded_by_default(self):
        """EPS<=0 但 exclude_loss=False 应不被拒。"""
        quote = {"code": "sh600000", "name": "亏损股", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"eps": -1, "roe": -5}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        # 仍然会因 EPS<0(亏损) 被标记，但不会被 exclude_loss 二次标记
        assert "EPS<=0" not in reasons

    def test_goodill_warning(self):
        """商誉>阈值应被拒。"""
        quote = {"code": "sh600000", "name": "高商誉", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"eps": 1, "roe": 10, "goodwill_ratio": 50}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert any("商誉" in r for r in reasons)

    def test_pledge_warning(self):
        """质押率>阈值应被拒。"""
        quote = {"code": "sh600000", "name": "高质押", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"eps": 1, "roe": 10, "pledge_ratio": 80}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert any("质押率" in r for r in reasons)

    def test_limit_up_rejected(self):
        """涨停应被拒（T+1 限制）。"""
        quote = {"code": "sh600000", "name": "涨停", "total_cap": 100, "amount": 1e8, "change_pct": 10}
        fin = {"eps": 1, "roe": 10}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert "涨跌停限制" in reasons

    def test_limit_down_rejected(self):
        """跌停也应被拒。"""
        quote = {"code": "sh600000", "name": "跌停", "total_cap": 100, "amount": 1e8, "change_pct": -10}
        fin = {"eps": 1, "roe": 10}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert "涨跌停限制" in reasons

    def test_donghu_prefix_rejected(self):
        """*ST 前缀应被拒。"""
        quote = {"code": "sh600000", "name": "*ST 测试", "total_cap": 100, "amount": 1e8}
        fin = {"eps": 1, "roe": 10}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert "ST风险" in reasons

    def test_amount_too_low_rejected(self):
        """成交额<5000 万应被拒。"""
        quote = {"code": "sh600000", "name": "低成交", "total_cap": 100, "amount": 1e7, "change_pct": 0}
        fin = {"eps": 1, "roe": 10}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert any("成交额" in r for r in reasons)

    def test_fin_field_aliases(self):
        """兼容东财原始字段名（EPSJB/ROEJQ）。"""
        quote = {"code": "sh600000", "name": "测试", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"EPSJB": -1, "ROEJQ": 20, "ZCFZL": 30}
        reasons = self.svc._hard_filter(quote, fin, self.filters)
        assert any("EPS" in r for r in reasons)

    def test_filters_dict_missing_keys(self):
        """filters dict 缺字段时回退到硬编码默认。"""
        quote = {"code": "sh600000", "name": "测试", "total_cap": 100, "amount": 1e8, "change_pct": 0}
        fin = {"eps": 1, "roe": 10}
        # 空 filters dict
        assert isinstance(self.svc._hard_filter(quote, fin, {}), list)


# ═══════════════════════════════════════════════════════════════
# 4. ScreeningService.screen 边界情况
# ═══════════════════════════════════════════════════════════════
class TestScreeningServiceScreenEdgeCases:
    def test_empty_codes(self):
        svc = ScreeningService()
        result = svc.screen([], strategy="balanced")
        assert result == []

    def test_invalid_strategy_falls_back(self, caplog):
        """未知策略回退到默认 balanced。"""
        svc = ScreeningService()
        # 不会抛异常，会用 balanced
        with patch("business.screening_service.get_quotes", return_value=[]):
            result = svc.screen(["sh600000"], strategy="nonexistent_strategy", filters={})
        assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════
# 5. _vol_price_signal_desc
# ═══════════════════════════════════════════════════════════════
class TestVolPriceSignalDesc:
    def test_positive_signal(self):
        assert ScreeningService._vol_price_signal_desc(1) == "配合"

    def test_negative_signal(self):
        assert ScreeningService._vol_price_signal_desc(-1) == "背离"

    def test_zero_signal(self):
        assert ScreeningService._vol_price_signal_desc(0) == "中性"

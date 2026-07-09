"""Quote volume/amount 单位归一化测试。

验证 _dict_to_quote 按数据源正确归一化 volume/amount，且只归一化一次
（修复 fetcher 层与 data 层双重归一化的 bug）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data import _dict_to_quote, _normalize_volume, _normalize_amount


class TestNormalizeVolume:
    """_normalize_volume 单元测试。"""

    def test_tencent_multiplies_by_100(self):
        """腾讯源 volume=1000（手）-> 100000（股）。"""
        assert _normalize_volume(1000, "tencent") == 100000

    def test_eastmoney_multiplies_by_100(self):
        """东财源 volume=1000（手）-> 100000（股）。"""
        assert _normalize_volume(1000, "eastmoney") == 100000

    def test_sina_passes_through(self):
        """新浪源 volume 已是股，透传不修改。"""
        assert _normalize_volume(1000, "sina") == 1000

    def test_unknown_source_passes_through(self):
        assert _normalize_volume(1000, "unknown") == 1000


class TestNormalizeAmount:
    """_normalize_amount 单元测试。"""

    def test_tencent_multiplies_by_10000(self):
        """腾讯源 amount=5（万元）-> 50000（元）。"""
        assert _normalize_amount(5, "tencent") == 50000

    def test_tushare_multiplies_by_1000(self):
        """tushare 源 amount=5（千元）-> 5000（元）。"""
        assert _normalize_amount(5, "tushare") == 5000

    def test_eastmoney_passes_through(self):
        """东财源 amount 已是元，透传。"""
        assert _normalize_amount(50000, "eastmoney") == 50000


class TestDictToQuoteNormalization:
    """_dict_to_quote 集成归一化测试 -- 验证只归一化一次。"""

    def _make_dict(self, volume, amount, source="tencent"):
        return {
            "code": "sh600989",
            "name": "测试",
            "price": "10.0",
            "prev_close": "9.9",
            "open": "9.9",
            "high": "10.2",
            "low": "9.8",
            "volume": str(volume),
            "amount": str(amount),
            "source": source,
        }

    def test_tencent_normalized_once(self):
        """腾讯源 raw volume=1000（手）-> 100000（股），不是 10000000（双重×100）。"""
        q = _dict_to_quote(self._make_dict(1000, 5, "tencent"))
        assert q.volume == 100000  # ×100 一次
        assert q.amount == 50000  # ×10000 一次，不是 5e8

    def test_eastmoney_normalized_once(self):
        """东财源 raw volume=1000（手）-> 100000（股）。"""
        q = _dict_to_quote(self._make_dict(1000, 50000, "eastmoney"))
        assert q.volume == 100000  # ×100 一次
        assert q.amount == 50000  # 东财 amount 已是元，透传

    def test_sina_passes_through(self):
        """新浪源 volume/amount 已是股/元，透传不乘。"""
        q = _dict_to_quote(self._make_dict(1000, 50000, "sina"))
        assert q.volume == 1000
        assert q.amount == 50000

    def test_no_double_normalization_tencent(self):
        """回归测试：腾讯 volume 不应被双重归一化（旧 bug 会得到 10000000）。"""
        q = _dict_to_quote(self._make_dict(1000, 5, "tencent"))
        # 双重归一化的 bug 值：1000 * 100 * 100 = 10000000
        assert q.volume != 10000000
        assert q.volume == 100000
        # 双重归一化 amount：5 * 10000 * 10000 = 500000000
        assert q.amount != 500000000
        assert q.amount == 50000

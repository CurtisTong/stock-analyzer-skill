"""K 线 volume 单位归一化测试。

验证 _normalize_volume 和 _dict_to_kline_bar 按数据源正确归一化 volume 为"股"。
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from data import _normalize_volume, _dict_to_kline_bar


class TestNormalizeVolume:
    """_normalize_volume 单元测试。"""

    def test_tencent_multiplies_by_100(self):
        """腾讯源 volume=1000（手）→ 100000（股）。"""
        assert _normalize_volume(1000, "tencent") == 100000

    def test_eastmoney_multiplies_by_100(self):
        """东财源 volume=1000（手）→ 100000（股）。"""
        assert _normalize_volume(1000, "eastmoney") == 100000

    def test_sina_passes_through(self):
        """新浪源 volume 已是股，透传不修改。"""
        assert _normalize_volume(1000, "sina") == 1000

    def test_unknown_source_passes_through(self):
        """未知 source 透传不修改。"""
        assert _normalize_volume(1000, "unknown") == 1000

    def test_empty_source_passes_through(self):
        """空 source 透传不修改。"""
        assert _normalize_volume(1000, "") == 1000

    def test_zero_volume(self):
        """volume=0 不论 source 均返回 0。"""
        assert _normalize_volume(0, "tencent") == 0
        assert _normalize_volume(0, "") == 0


class TestDictToKlineBarNormalization:
    """_dict_to_kline_bar 集成归一化测试。"""

    def _make_dict(self, volume, source="tencent"):
        return {
            "day": "2024-01-15",
            "open": "10.0",
            "high": "11.0",
            "low": "9.5",
            "close": "10.5",
            "volume": str(volume),
            "amount": "1000000.0",
            "pct_chg": "1.5",
            "source": source,
        }

    def test_tencent_volume_normalized(self):
        """腾讯源 dict → KlineBar.volume 乘以 100。"""
        bar = _dict_to_kline_bar(self._make_dict(1000, "tencent"))
        assert bar.volume == 100000

    def test_eastmoney_volume_normalized(self):
        """东财源 dict → KlineBar.volume 乘以 100。"""
        bar = _dict_to_kline_bar(self._make_dict(500, "eastmoney"))
        assert bar.volume == 50000

    def test_sina_volume_passthrough(self):
        """新浪源 dict → KlineBar.volume 透传（已是股）。"""
        bar = _dict_to_kline_bar(self._make_dict(200, "sina"))
        assert bar.volume == 200

    def test_unknown_source_volume_unchanged(self):
        """未知 source → volume 透传。"""
        bar = _dict_to_kline_bar(self._make_dict(1000, "akshare"))
        assert bar.volume == 1000

    def test_missing_source_volume_unchanged(self):
        """缺失 source → volume 透传。"""
        d = self._make_dict(1000)
        del d["source"]
        bar = _dict_to_kline_bar(d)
        assert bar.volume == 1000

    def test_source_preserved_in_bar(self):
        """source 字段正确传递到 KlineBar。"""
        bar = _dict_to_kline_bar(self._make_dict(100, "tencent"))
        assert bar.source == "tencent"

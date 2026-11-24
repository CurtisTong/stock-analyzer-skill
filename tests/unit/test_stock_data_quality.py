"""stock.py 数据完整性信封回归测试（kline 域字段映射）。

背景：业务层产出的 K 线字段是 ``kline_count``（有效 K 线条数），并不存在
``kline`` 键。旧实现 ``field_map={"kline": ("kline",)}`` 让 ``_present()``
恒判 K 线域缺失 → status=partial → 按设计清空 ``score`` 等结论字段，
导致 CLI 在正常取到 240 根 K 线时仍输出 ``"score": null``。

本文件锁定：正常结果评分保留；真缺 K 线时仍按规范清空结论字段。
"""

from __future__ import annotations

import pytest

from common import data_quality as dq


@pytest.fixture(autouse=True)
def _no_chain(monkeypatch):
    """切断真实降级链，避免用例依赖历史 provider 记录。"""
    monkeypatch.setattr(dq, "_chain_providers", lambda domain, code=None: [])
    monkeypatch.setattr(dq, "_winner_provider", lambda domain, code=None: None)


def _ok_payload(**overrides):
    payload = {
        "code": "sh600989",
        "name": "宝丰能源",
        "price": 19.67,
        "change_pct": -1.99,
        "kline_count": 240,
        "finance": {"roe": 27.08, "net_profit_yoy": 59.97},
        "technical": {"ma": "空头排列"},
        "score": {"score": 45.2, "grade": "中性"},
        "data_failed": [],
    }
    payload.update(overrides)
    return payload


class TestStockKlineFieldMapping:
    def test_normal_kline_count_keeps_score(self):
        """有 kline_count 即视为 K 线域有值，不得误判缺失而清空评分。"""
        import stock

        out = stock._with_data_quality(_ok_payload(), "sh600989")

        assert out["data_quality"]["status"] == "ok"
        assert out["data_quality"]["missing"] == []
        assert out["data_quality"]["conclusions_allowed"] is True
        assert out["score"]["score"] == 45.2
        assert out["kline_count"] == 240

    def test_zero_kline_count_is_present_not_missing(self):
        """_present() 语义：0 也算有值，只有 None/缺键才是缺失。"""
        import stock

        out = stock._with_data_quality(_ok_payload(kline_count=0), "sh600989")

        assert "kline" not in out["data_quality"]["missing_domains"]
        assert out["data_quality"]["conclusions_allowed"] is True

    def test_real_kline_failure_still_clears_score(self):
        """真缺 K 线时仍须置结论字段为 None（修复不能放宽这条护栏）。"""
        import stock

        out = stock._with_data_quality(
            _ok_payload(kline_count=None, data_failed=["K线"]),
            "sh600989",
        )

        assert out["data_quality"]["status"] == "partial"
        assert "kline" in out["data_quality"]["missing_domains"]
        assert out["data_quality"]["conclusions_allowed"] is False
        assert out["score"] is None
        assert "conclusion.score" in out["data_quality"]["degraded_fields"]

    def test_missing_kline_key_clears_score(self):
        """业务层 K 线不足时根本不写 kline_count 键，同样应判缺失。"""
        import stock

        payload = _ok_payload()
        payload.pop("kline_count")

        out = stock._with_data_quality(payload, "sh600989")

        assert out["data_quality"]["status"] == "partial"
        assert "kline" in out["data_quality"]["missing_domains"]
        assert out["score"] is None

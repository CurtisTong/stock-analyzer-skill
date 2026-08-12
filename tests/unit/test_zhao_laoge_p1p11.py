"""P1-11：赵老哥评分可选增强输入（龙虎榜 / 板块横截面排名）测试。"""

from __future__ import annotations

from experts.scoring.zhao_laoge import score


def _base_data(**extra):
    """构造最小 stock_data：quote/circ_cap + 20 日 K 线（多头排列）。"""
    closes = [100 + i for i in range(20)]  # 稳步上行
    data = {
        "quote": {"circulating_cap": 100},
        "kline_data": {
            "closes": closes,
            "volumes": [1000] * 20,
        },
        "kline_features": {"trend": 1},
    }
    data.update(extra)
    return data


class TestDragonTiger:
    def test_net_buy_boosts_sentiment(self):
        base = score(_base_data())
        with_dt = score(_base_data(dragon_tiger={"net_buy": 2.5, "count": 3}))
        assert with_dt["情绪/题材"] >= base["情绪/题材"]

    def test_net_sell_suppresses_sentiment(self):
        base = score(_base_data())
        with_dt = score(_base_data(dragon_tiger={"net_buy": -1.0, "count": 1}))
        assert with_dt["情绪/题材"] <= base["情绪/题材"]

    def test_missing_dragon_tiger_is_noop(self):
        a = score(_base_data())
        b = score(_base_data(dragon_tiger={}))
        assert a == b


class TestSectorRank:
    def test_top_rank_leader_scores_high(self):
        data = _base_data(sector_rank={"rank": 1, "total": 20})
        assert score(data)["风险"] == 90

    def test_tail_rank_penalizes(self):
        data = _base_data(sector_rank={"rank": 20, "total": 20})
        assert score(data)["风险"] == 20

    def test_rank_fallback_to_pullback(self):
        # 无 sector_rank：回退回撤近似。closes 稳步上行 → 站上 MA20 → risk=80
        data = _base_data()
        assert score(data)["风险"] == 80

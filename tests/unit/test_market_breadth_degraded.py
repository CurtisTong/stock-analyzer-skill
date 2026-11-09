"""market_breadth 降级语义不变量测试（v1.31.0 修复锁定）。

修复前 bug：宽度整体拉取失败（指数 API 异常）时 up_count/down_count/up_ratio
以 0 兜底，get_market_state 把"涨跌比 0"当真实数据定性为"市场普跌，宽度偏弱"，
market_anchor 再把默认 advance_ratio=0.5 喂给 regime 判定（恒判震荡）且
confidence 强制 high——而当日沪深300 实际上涨。

不变量：
1. 整体失败 -> 宽度字段为 None（不可用），state=宽度不可用，禁止"普跌/普涨"定性
2. 仅涨跌停降级（token 缺失、涨跌家数真实）-> 按涨跌比定性（既有行为）
3. 正常数据 -> 主路径回归锚点不变
4. market_anchor._fetch_breadth 整体失败 -> 返回 None（触发退化判定 + degraded 标记）
5. v1.33.1：上游涨跌家数字段失效（接口 rc=0 但 f104/f105=0）-> 与整体失败同语义，
   不得把 0/0 当真实宽度（advance_ratio 哨兵 0.5 会让 regime 恒判"震荡"且
   confidence=high，等于用默认值冒充真实宽度）
"""

import market_breadth as mb
import market_anchor


class TestDefaultResultUnavailable:
    """整体失败兜底：宽度字段必须为 None 而非 0。"""

    def test_width_fields_are_none(self):
        r = mb._default_result()
        assert r["up_count"] is None
        assert r["down_count"] is None
        assert r["up_ratio"] is None
        assert r["_degraded"] is True
        assert r["_degraded_reason"]

    def test_default_result_state_unavailable(self):
        state = mb.get_market_state(mb._default_result())
        assert state["state"] == mb.STATE_UNAVAILABLE
        assert state["confidence"] == mb.CONFIDENCE_LOW
        assert state["degraded"] is True

    def test_no_false_direction_on_total_failure(self):
        """整体失败时禁止输出方向性结论（普跌/普涨/偏强/偏弱）。"""
        signals = " ".join(mb.get_market_state(mb._default_result())["signals"])
        assert "普跌" not in signals
        assert "普涨" not in signals
        assert "偏弱" not in signals
        assert "偏强" not in signals

    def test_unavailable_state_none_up_ratio_no_crash(self):
        """up_ratio=None 直接传入 get_market_state 不得 TypeError（v1.30.0 实际崩溃路径）。"""
        state = mb.get_market_state({"up_ratio": None, "_degraded": True, "_degraded_reason": "x"})
        assert state["state"] == mb.STATE_UNAVAILABLE


class TestPartialDegradedByRatio:
    """仅涨跌停降级（token 缺失）：涨跌家数真实，按涨跌比定性（既有行为锁定）。"""

    def test_ratio_strong(self):
        state = mb.get_market_state(
            {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 4000,
                "down_count": 1000,
                "up_ratio": 4.0,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            }
        )
        assert state["state"] == mb.STATE_BIAS_STRONG

    def test_ratio_weak(self):
        state = mb.get_market_state(
            {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 1000,
                "down_count": 4000,
                "up_ratio": 0.25,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            }
        )
        assert state["state"] == mb.STATE_BIAS_WEAK
        # 半降级允许涨跌比定性（真实数据）
        assert "普跌" in " ".join(state["signals"])

    def test_ratio_neutral(self):
        state = mb.get_market_state(
            {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 2800,
                "down_count": 2200,
                "up_ratio": 1.27,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            }
        )
        assert state["state"] == mb.STATE_BIAS_NEUTRAL


class TestNormalPathRegression:
    """正常数据主路径回归锚点（v1.31.0 不得改变）。"""

    def test_rally(self):
        state = mb.get_market_state(
            {
                "limit_up_count": 65,
                "limit_down_count": 8,
                "up_count": 3500,
                "down_count": 1500,
                "up_ratio": 2.33,
                "continuous_limit_height": 6,
                "broken_limit_rate": 25,
                "total_stocks": 5300,
            }
        )
        assert state["state"] == mb.STATE_RALLY
        assert state["degraded"] is False

    def test_zero_down_count_is_not_bearish(self):
        """down=0 且 up>0（极端普涨）计算为哨兵 99.0，不得算 0 误判普跌。"""
        # 直接测 get_market_state 消费端语义：up_ratio 哨兵值判普涨
        state = mb.get_market_state(
            {
                "limit_up_count": 120,
                "limit_down_count": 0,
                "up_count": 5200,
                "down_count": 0,
                "up_ratio": 99.0,
                "continuous_limit_height": 7,
                "broken_limit_rate": 10,
                "total_stocks": 5300,
            }
        )
        assert "普涨" in " ".join(state["signals"])
        assert "普跌" not in " ".join(state["signals"])


class TestAnchorFetchBreadth:
    """market_anchor._fetch_breadth 整体失败必须返回 None。"""

    def test_total_failure_returns_none(self, monkeypatch):
        monkeypatch.setattr(market_anchor.market_breadth, "get_market_breadth", mb._default_result)
        assert market_anchor._fetch_breadth() is None

    def test_partial_degradation_still_converts(self, monkeypatch):
        """token 降级但涨跌家数真实：仍返回转换后的 dict（advance_ratio 真实）。"""
        monkeypatch.setattr(
            market_anchor.market_breadth,
            "get_market_breadth",
            lambda: {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 3000,
                "down_count": 2000,
                "up_ratio": 1.5,
                "total_stocks": 5300,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            },
        )
        b = market_anchor._fetch_breadth()
        assert b is not None
        assert b["advance_ratio"] == 0.6
        assert b["up_ratio"] == 1.5
        assert b["_degraded"] is True

    def test_emotion_phase_none_on_total_failure(self, monkeypatch):
        """整体失败时 emotion_phase 不可得（此前误输出"偏弱(宽度)"）。"""
        monkeypatch.setattr(market_anchor.market_breadth, "get_market_breadth", mb._default_result)
        assert market_anchor._fetch_emotion_phase(market_anchor._fetch_breadth()) is None


class TestSignalsConsumer:
    """下游 signals.py 对 up_ratio=None 的容错（v1.31.0 修复锁定）。"""

    def test_generate_signals_tolerates_none_up_ratio(self):
        from technical.signals import _generate_signals

        features = {
            "macd": {"signal": 0},
            "kdj": {"signal": "", "钝化": False},
            "boll": {"position": 0.5, "bandwidth_desc": ""},
        }
        # v1.30.0：up_ratio=None 时 None > 2 TypeError
        buy, sell, _structured = _generate_signals(
            features,
            market_breadth={"limit_up_count": 0, "limit_down_count": 0, "continuous_limit_height": 0, "up_ratio": None},
        )
        all_signals = buy + sell
        assert "普涨" not in "".join(all_signals)
        assert "普跌" not in "".join(all_signals)


class TestZeroZeroWidthUnavailable:
    """v1.33.1：上游涨跌家数字段失效（rc=0 但 f104/f105=0）必须按不可用处理。

    实测背景（2026-11-06）：东财 ulist.np 接口对 f104/f105/f106 恒返回 0，
    market_breadth 把 0/0 当真实宽度 -> up_ratio 哨兵 0.5 -> market_anchor
    advance_ratio=0.5 -> regime 恒判"震荡"、confidence=high、emotion_phase="震荡(宽度)"，
    而当日实为普跌（板块家数聚合上涨占比 13.8%）。
    """

    @staticmethod
    def _mock_index_api(monkeypatch, payload):
        """把 market_breadth 的指数 API 换成固定响应。"""
        monkeypatch.setattr(mb, "http_get", lambda *a, **k: payload)

    @staticmethod
    def _mock_limit_data(monkeypatch):
        monkeypatch.setattr(
            mb,
            "get_limit_data",
            lambda: {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "continuous_limit_height": 0,
                "broken_limit_rate": 0,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            },
        )

    def test_fetch_breadth_zero_zero_is_unavailable(self, monkeypatch):
        """0/0 -> 宽度字段为 None + _degraded 标记（不是 0，也不是 0.5 哨兵）。"""
        payload = '{"rc":0,"data":{"total":2,"diff":[' '{"f104":0,"f105":0,"f106":0},' '{"f104":0,"f105":0,"f106":0}]}}'
        self._mock_index_api(monkeypatch, payload)
        self._mock_limit_data(monkeypatch)

        r = mb.get_market_breadth()
        assert r["up_count"] is None
        assert r["down_count"] is None
        assert r["up_ratio"] is None
        assert r["_degraded"] is True
        assert "涨跌家数" in r["_degraded_reason"]

    def test_fetch_breadth_normal_counts_unchanged(self, monkeypatch):
        """真实涨跌家数路径不受影响（主路径回归）。"""
        payload = (
            '{"rc":0,"data":{"total":2,"diff":['
            '{"f104":3000,"f105":1800,"f106":200},'
            '{"f104":1200,"f105":800,"f106":100}]}}'
        )
        self._mock_index_api(monkeypatch, payload)
        self._mock_limit_data(monkeypatch)

        r = mb.get_market_breadth()
        assert r["up_count"] == 4200
        assert r["down_count"] == 2600
        assert r["up_ratio"] == 1.62
        assert r["total_stocks"] == 7100

    def test_state_zero_zero_not_qualitative(self):
        """0/0 + 哨兵 up_ratio=0.5 -> 宽度不可用，不得定性"震荡(宽度)"。"""
        state = mb.get_market_state(
            {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 0,
                "down_count": 0,
                "up_ratio": 0.5,
                "_degraded": True,
                "_degraded_reason": "涨跌家数字段不可用（接口返回 0/0）",
            }
        )
        assert state["state"] == mb.STATE_UNAVAILABLE
        assert state["confidence"] == mb.CONFIDENCE_LOW
        assert state["degraded"] is True
        signals = " ".join(state["signals"])
        assert "普跌" not in signals
        assert "普涨" not in signals
        assert "偏弱" not in signals
        assert "偏强" not in signals

    def test_state_ratio_survives_when_counts_real(self):
        """真实涨跌家数 + 仅涨跌停降级：仍按涨跌比定性（既有行为锁定）。"""
        state = mb.get_market_state(
            {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 800,
                "down_count": 4600,
                "up_ratio": 0.17,
                "_degraded": True,
                "_degraded_reason": "涨跌停数据降级",
            }
        )
        assert state["state"] == mb.STATE_BIAS_WEAK
        assert "普跌" in " ".join(state["signals"])

    def test_anchor_fetch_breadth_zero_zero_returns_none(self, monkeypatch):
        """anchor 侧：0/0 视为整体失败 -> 返回 None（走退化判定 + degraded 标记）。"""
        monkeypatch.setattr(
            market_anchor.market_breadth,
            "get_market_breadth",
            lambda: {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 0,
                "down_count": 0,
                "up_ratio": 0.5,
                "total_stocks": 0,
                "_degraded": True,
                "_degraded_reason": "涨跌家数字段不可用（接口返回 0/0）",
            },
        )
        assert market_anchor._fetch_breadth() is None
        assert "涨跌家数" in market_anchor._LAST_BREADTH_REASON

    def test_anchor_fetch_breadth_none_counts_returns_none(self, monkeypatch):
        """anchor 侧：None 计数（整体失败路径）同样返回 None。"""
        monkeypatch.setattr(market_anchor.market_breadth, "get_market_breadth", mb._default_result)
        assert market_anchor._fetch_breadth() is None

    def test_anchor_fetch_breadth_real_counts_unchanged(self, monkeypatch):
        """anchor 侧：真实家数时 advance_ratio 仍为真实值（主路径回归）。"""
        monkeypatch.setattr(
            market_anchor.market_breadth,
            "get_market_breadth",
            lambda: {
                "limit_up_count": 30,
                "limit_down_count": 5,
                "up_count": 800,
                "down_count": 4600,
                "up_ratio": 0.17,
                "total_stocks": 5400,
            },
        )
        b = market_anchor._fetch_breadth()
        assert b is not None
        assert b["advance_ratio"] == 0.148
        assert b["new_high_low_ratio"] == 0.174
        assert market_anchor._LAST_BREADTH_REASON is None

    def test_emotion_phase_none_when_zero_zero(self, monkeypatch):
        """0/0 时情绪周期不可得（不得输出"震荡(宽度)"这类伪宽度结论）。"""
        monkeypatch.setattr(
            market_anchor.market_breadth,
            "get_market_breadth",
            lambda: {
                "limit_up_count": 0,
                "limit_down_count": 0,
                "up_count": 0,
                "down_count": 0,
                "up_ratio": 0.5,
                "total_stocks": 0,
                "_degraded": True,
                "_degraded_reason": "涨跌家数字段不可用（接口返回 0/0）",
            },
        )
        assert market_anchor._fetch_emotion_phase(market_anchor._fetch_breadth()) is None

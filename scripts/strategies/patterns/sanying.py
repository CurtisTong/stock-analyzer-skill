"""
三阴一阳 / 三阳一阴战法。
"""

from common import to_float
from strategies.patterns.utils import _is_bearish, _is_bullish


def detect_sanying_yiyang(records, volumes, code=""):
    """
    三阴一阳（洗盘后拉升）和三阳一阴（诱多后出货）。

    优化版（v2）基于 5 只股票回测验证：
    - 放量（vol_ratio > 1.2）胜率 60-80%
    - 小幅下跌（< 3%）后反弹更可靠
    - 中等反弹比例（20-50%）为最佳区间

    放宽识别条件：不要求阴线实体递减，增加量化指标评估。
    """
    if len(records) < 4:
        return []

    results = []

    for i in range(3, len(records)):
        r0, r1, r2, r3 = records[i - 3], records[i - 2], records[i - 1], records[i]
        o0, c0, o1, c1, o2, c2, o3, c3 = [
            to_float(r.get(k)) for r in [r0, r1, r2, r3] for k in ["open", "close"]
        ]
        v0, v1, v2, v3 = [to_float(r.get("volume")) for r in [r0, r1, r2, r3]]

        # ── 三阴一阳（底部洗盘结束）──
        if all(
            _is_bearish(o, c) for o, c in [(o0, c0), (o1, c1), (o2, c2)]
        ) and _is_bullish(o3, c3):

            # 计算三阴累计跌幅（负值表示下跌）
            total_decline = (c2 - o0) / max(o0, 0.001) * 100

            # 排除非下跌序列：三阴一阳本意是"洗盘后拉升"，
            # 三阴整体是上涨的（c2 > o0，total_decline > 0）不构成本形态
            if total_decline > -1.0:
                return False

            # 计算成交量比（阳线 vs 三阴均量）
            avg_yin_vol = (v0 + v1 + v2) / 3
            vol_ratio = v3 / max(avg_yin_vol, 1)

            # 计算反弹比例（阳线实体 / 三阴总实体）
            yang_body = c3 - o3
            yin_total_body = o0 - c2
            # 避免除零：当三阴总实体太小时，反弹比例无意义
            if yin_total_body < 0.01:
                rebound_ratio = 0
            else:
                rebound_ratio = yang_body / yin_total_body * 100

            # 放宽条件：不要求阴线实体递减，只要求放量阳线收盘高于前一日
            if vol_ratio >= 1.0 and c3 > c2:
                # 多维度置信度评分
                confidence_score = 0

                # 量比评分（核心因子）
                if vol_ratio >= 1.5:
                    confidence_score += 3
                elif vol_ratio >= 1.2:
                    confidence_score += 2
                else:
                    confidence_score += 1

                # 跌幅控制评分
                if abs(total_decline) < 3:  # 小幅下跌最佳
                    confidence_score += 2
                elif abs(total_decline) < 5:
                    confidence_score += 1

                # 反弹比例评分
                if 20 <= rebound_ratio <= 50:  # 中等反弹最佳
                    confidence_score += 2
                elif rebound_ratio > 50:
                    confidence_score += 1

                # 覆盖力度
                coverage = (c3 - c0) / max(abs(c0 - o0), 0.001)
                if coverage > 0.8:
                    confidence_score += 1

                confidence = (
                    "高"
                    if confidence_score >= 5
                    else "中" if confidence_score >= 3 else "低"
                )

                results.append(
                    {
                        "name": "三阴一阳",
                        "type": "看涨",
                        "date": r3.get("day", ""),
                        "desc": f"三阴跌{total_decline:.1f}%后放量阳线反弹{rebound_ratio:.0f}%，量比{vol_ratio:.1f}x",
                        "confidence": confidence,
                        "idx": i,
                        "metrics": {
                            "total_decline": round(total_decline, 2),
                            "vol_ratio": round(vol_ratio, 2),
                            "rebound_ratio": round(rebound_ratio, 2),
                            "coverage": round(coverage, 2),
                        },
                    }
                )

        # ── 三阳一阴（高位诱多出货）──
        if all(
            _is_bullish(o, c) for o, c in [(o0, c0), (o1, c1), (o2, c2)]
        ) and _is_bearish(o3, c3):

            # 计算三阳累计涨幅
            total_rise = (c2 - o0) / max(o0, 0.001) * 100

            # 计算成交量比
            avg_yang_vol = (v0 + v1 + v2) / 3
            vol_ratio = v3 / max(avg_yang_vol, 1)

            # 放宽条件：放量阴线收盘低于前一日
            if vol_ratio >= 1.2 and c3 < c2:
                confidence = "高" if vol_ratio >= 1.5 else "中"
                results.append(
                    {
                        "name": "三阳一阴",
                        "type": "看跌",
                        "date": r3.get("day", ""),
                        "desc": f"三阳涨{total_rise:.1f}%后放量阴线吞没，量比{vol_ratio:.1f}x",
                        "confidence": confidence,
                        "idx": i,
                        "metrics": {
                            "total_rise": round(total_rise, 2),
                            "vol_ratio": round(vol_ratio, 2),
                        },
                    }
                )

    return results

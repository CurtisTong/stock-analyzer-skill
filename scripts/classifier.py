#!/usr/bin/env python3
"""
A 股个股类型分类器。
根据财务数据、行情数据和 K 线走势特征，自动判定 7 种类型。
可被 technical.py 或其他模块 import 使用。
"""
from common import to_float, clamp


# ── 类型 → 推荐指标映射 ──

TYPE_INDICATOR_MAP = {
    "题材股": {
        "priority": ["K线形态", "涨停分析", "量比", "RSI"],
        "deprioritized": ["MACD", "KDJ"],
    },
    "蓝筹股": {
        "priority": ["均线系统", "BOLL", "MACD背离", "箱体"],
        "deprioritized": ["KDJ"],
    },
    "强成长股": {
        "priority": ["MACD趋势", "BOLL上轨", "量比", "RSI"],
        "deprioritized": ["KDJ"],
    },
    "周期股": {
        "priority": ["MACD背离", "KDJ钝化", "缠论背驰", "BOLL"],
        "deprioritized": ["简单均线"],
    },
    "稳成长股": {
        "priority": ["均线排列", "MACD", "BOLL", "RSI", "老鸭头"],
        "deprioritized": ["KDJ"],
    },
    "防御股": {
        "priority": ["BOLL", "RSI", "均线粘合", "箱体"],
        "deprioritized": ["KDJ"],
    },
    "普通股": {
        "priority": ["均线", "MACD", "KDJ", "BOLL", "RSI", "量价"],
        "deprioritized": [],
    },
}


def classify_stock(fin_record=None, quote_record=None, kline_records=None):
    """
    判定 A 股个股类型。

    Args:
        fin_record: 单期财务数据 dict（finance.py 返回的 records[0]）
                   字段: ROEJQ, PARENTNETPROFITTZ, XSMLL, ZCFZL 等
        quote_record: 实时行情 dict（quote.py 返回）
                     字段: circulating_cap, total_cap, turnover, pe 等
        kline_records: K 线数据 list

    Returns:
        {
            "type": "强成长股"|...|"普通股",
            "confidence": "高"|"中"|"低",
            "reasons": [...],
            "priority_indicators": [...],
            "deprioritized": [...],
        }
    """
    reasons = []
    confidence = "高"

    # 提取行情特征
    circulating_cap = to_float(quote_record.get("circulating_cap")) if quote_record else 0
    total_cap = to_float(quote_record.get("total_cap")) if quote_record else 0
    turnover = to_float(quote_record.get("turnover")) if quote_record else 0

    # 提取财务特征
    has_finance = fin_record and isinstance(fin_record, dict)
    roe = to_float(fin_record.get("ROEJQ")) if has_finance else 0
    profit_growth = to_float(fin_record.get("PARENTNETPROFITTZ")) if has_finance else 0
    gross_margin = to_float(fin_record.get("XSMLL")) if has_finance else 0
    debt = to_float(fin_record.get("ZCFZL")) if has_finance else 0

    # 连板检测
    has_limit_streak = False
    if kline_records and len(kline_records) >= 10:
        from common import board_type as _board_type
        code = quote_record.get("code", "") if quote_record else ""
        bd = _board_type(code)
        limit_ratio = {"主板": 9.5, "创业板": 19.5, "科创板": 19.5, "北交所": 29.5}.get(bd, 9.5)
        for i in range(len(kline_records) - 1, max(len(kline_records) - 5, 0), -1):
            r = kline_records[i]
            prev = kline_records[i - 1] if i > 0 else r
            chg = (to_float(r.get("close")) - to_float(prev.get("close"))) / max(to_float(prev.get("close")), 0.01) * 100
            if chg >= limit_ratio * 0.95:
                has_limit_streak = True
                break

    # ── 规则分类（优先级从高到低） ──
    stock_type = "普通股"
    confidence = "低"

    # 1. 题材股
    if circulating_cap > 0 and circulating_cap < 100 and (has_limit_streak or turnover > 10):
        stock_type = "题材股"
        reasons.append(f"流通市值{circulating_cap:.0f}亿(小盘)")
        if has_limit_streak:
            reasons.append("近期有连板记录")
        if turnover > 10:
            reasons.append(f"换手率{turnover:.1f}%(高活跃度)")
        confidence = "高" if has_limit_streak else "中"

    # 2. 蓝筹股
    elif circulating_cap > 1000 and (not has_finance or roe > 10):
        stock_type = "蓝筹股"
        reasons.append(f"流通市值{circulating_cap:.0f}亿(大盘)")
        if roe > 10:
            reasons.append(f"ROE {roe:.1f}%")
            confidence = "高"
        else:
            confidence = "中"

    # 有财务数据时的精确分类
    elif has_finance:
        # 3. 强成长股
        if profit_growth > 30 and roe > 15 and circulating_cap < 500:
            stock_type = "强成长股"
            reasons.append(f"净利增速{profit_growth:.0f}%")
            reasons.append(f"ROE {roe:.1f}%")
            reasons.append(f"流通市值{circulating_cap:.0f}亿")
            confidence = "高"

        # 4. 周期股（增速波动大+毛利偏低）
        elif abs(profit_growth) > 50 and gross_margin > 0 and gross_margin < 25:
            stock_type = "周期股"
            reasons.append(f"净利增速波动大({profit_growth:.0f}%)")
            reasons.append(f"毛利率{gross_margin:.1f}%(偏低)")
            confidence = "中"

        # 5. 稳成长股
        elif 15 <= profit_growth <= 30 and roe > 12:
            stock_type = "稳成长股"
            reasons.append(f"净利增速{profit_growth:.0f}%")
            reasons.append(f"ROE {roe:.1f}%")
            confidence = "高"

        # 6. 防御股
        elif abs(profit_growth) < 20 and debt > 0 and debt < 50:
            stock_type = "防御股"
            reasons.append(f"增速稳定({profit_growth:.0f}%)")
            reasons.append(f"负债率{debt:.1f}%(低)")
            confidence = "中"

        else:
            stock_type = "普通股"
            reasons.append("不满足以上特定类型条件")
            confidence = "低"
    else:
        # 无财务数据，退化为市值分类
        if circulating_cap > 500:
            stock_type = "蓝筹股"
            reasons.append(f"流通市值{circulating_cap:.0f}亿(推测大盘)")
            confidence = "低"
        elif circulating_cap < 100 and turnover > 5:
            stock_type = "题材股"
            reasons.append(f"流通市值{circulating_cap:.0f}亿(小盘)+高换手")
            confidence = "低"
        else:
            stock_type = "普通股"
            reasons.append("无财务数据，无法精确分类")
            confidence = "低"

    # ── 返回指标建议 ──
    indicator_map = TYPE_INDICATOR_MAP.get(stock_type, TYPE_INDICATOR_MAP["普通股"])

    return {
        "type": stock_type,
        "confidence": confidence,
        "reasons": reasons,
        "priority_indicators": indicator_map["priority"],
        "deprioritized": indicator_map["deprioritized"],
    }


# ── 行业推断 ──

def infer_industry(name: str, code: str = "") -> str:
    """根据股票名称和代码推断行业分类。"""
    name = name.upper()
    # 金融：银行、保险、证券、信托
    if any(kw in name for kw in ["银行", "保险", "证券", "信托", "金融", "资管"]):
        return "金融"
    # 地产
    if any(kw in name for kw in ["地产", "置业", "置地", "房产", "万科", "保利", "碧桂园"]):
        return "地产"
    # 医药
    if any(kw in name for kw in ["医药", "药业", "制药", "生物", "疫苗", "医疗", "器械", "基因"]):
        return "医药"
    # 科技
    if any(kw in name for kw in ["科技", "软件", "信息", "智能", "芯片", "半导体", "电子", "通信", "计算"]):
        return "科技"
    # 消费
    if any(kw in name for kw in ["白酒", "食品", "饮料", "乳业", "调味", "啤酒", "茅台", "五粮液", "海天", "伊利"]):
        return "消费"
    # 能源
    if any(kw in name for kw in ["石油", "煤炭", "天然气", "能源", "石化", "燃气"]):
        return "能源"
    # 周期
    if any(kw in name for kw in ["钢铁", "有色", "铜", "铝", "锌", "黄金", "矿业", "化工", "化纤", "水泥"]):
        return "周期"
    # 制造
    if any(kw in name for kw in ["汽车", "机械", "制造", "装备", "新能源", "电池", "光伏", "风电", "家电"]):
        return "制造"
    return "默认"


# ── 统一画像入口 ──

def profile_stock(quote: dict, fin: dict = None, kline_records: list = None) -> dict:
    """统一个股画像：行业 + 类型 + 指标建议。

    Args:
        quote: 行情 dict（含 code, name 等）
        fin: 财务数据 dict（可选）
        kline_records: K 线数据列表（可选）

    Returns:
        {
            "industry": "金融"|...|"默认",
            "type": "蓝筹股"|...|"普通股",
            "confidence": "高"|"中"|"低",
            "reasons": [...],
            "priority_indicators": [...],
            "deprioritized": [...],
        }
    """
    name = quote.get("name", "")
    code = quote.get("code", "")

    industry = infer_industry(name, code)
    classification = classify_stock(fin, quote, kline_records)

    return {
        "industry": industry,
        **classification,
    }


# ── 命令行快速测试 ──
if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("用法: python3 classifier.py <code>")
        sys.exit(1)

    from common import normalize_quote_code, normalize_finance_code
    from quote import fetch_batch
    from kline import fetch as fetch_kline

    code = normalize_quote_code(sys.argv[1])
    quotes = fetch_batch([code])
    quote = quotes[0] if quotes else {}
    records = fetch_kline(code, 240, 100)

    # 尝试拉取财务数据
    fin_record = None
    try:
        from finance import fetch as fetch_finance
        fn_code = normalize_finance_code(code)
        fin_data = fetch_finance(fn_code)
        fin_record = fin_data[0] if fin_data else None
    except Exception:
        pass

    result = classify_stock(fin_record, quote, records)
    print(json.dumps(result, ensure_ascii=False, indent=2))

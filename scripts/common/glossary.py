"""金融术语库。"""

from __future__ import annotations
import re
from typing import List

GLOSSARY = {
    "PE": {
        "name": "市盈率",
        "formula": "股价 / 每股收益",
        "meaning": "投资者愿意为每 1 元盈利支付多少钱",
        "reference": "< 15 低估，15-25 合理，> 25 高估",
    },
    "PB": {
        "name": "市净率",
        "formula": "股价 / 每股净资产",
        "meaning": "投资者愿意为每 1 元净资产支付多少钱",
        "reference": "< 1 低估，1-3 合理，> 3 高估",
    },
    "ROE": {
        "name": "净资产收益率",
        "formula": "净利润 / 净资产",
        "meaning": "公司用股东的钱赚钱的能力",
        "reference": "> 15% 优秀，10-15% 良好，< 10% 一般",
    },
    "PEG": {
        "name": "市盈率相对盈利增长比率",
        "formula": "PE / 盈利增长率",
        "meaning": "估值是否匹配成长性",
        "reference": "< 1 低估，1 合理，> 1 高估",
    },
    "EPS": {
        "name": "每股收益",
        "formula": "净利润 / 总股本",
        "meaning": "每股赚多少钱",
        "reference": "越高越好，关注增长趋势",
    },
    "MACD": {
        "name": "指数平滑异同移动平均线",
        "formula": "DIF = EMA12 - EMA26, DEA = DIF的9日EMA",
        "meaning": "趋势跟踪指标，金叉看多，死叉看空",
        "reference": "DIF > DEA 金叉（看多），DIF < DEA 死叉（看空）",
    },
    "KDJ": {
        "name": "随机指标",
        "formula": "基于最高价、最低价、收盘价计算",
        "meaning": "超买超卖指标",
        "reference": "K > 80 超买，K < 20 超卖",
    },
    "RSI": {
        "name": "相对强弱指标",
        "formula": "上涨平均幅度 / (上涨+下跌平均幅度)",
        "meaning": "衡量多空力量对比",
        "reference": "> 70 超买，< 30 超卖",
    },
    "BOLL": {
        "name": "布林带",
        "formula": "中轨=MA20，上轨=中轨+2σ，下轨=中轨-2σ",
        "meaning": "价格波动通道",
        "reference": "触及上轨可能回调，触及下轨可能反弹",
    },
    "MA": {
        "name": "移动平均线",
        "formula": "N日收盘价平均值",
        "meaning": "趋势方向和支撑/阻力",
        "reference": "价格在MA上方为多头，下方为空头",
    },
    "MA5": {
        "name": "5日均线",
        "formula": "最近5日收盘价平均值",
        "meaning": "短期趋势",
        "reference": "短线操作参考",
    },
    "MA20": {
        "name": "20日均线",
        "formula": "最近20日收盘价平均值",
        "meaning": "中期趋势",
        "reference": "中线操作参考",
    },
    "MA60": {
        "name": "60日均线",
        "formula": "最近60日收盘价平均值",
        "meaning": "长期趋势",
        "reference": "长线操作参考",
    },
    "ROA": {
        "name": "总资产收益率",
        "formula": "净利润 / 总资产",
        "meaning": "公司用全部资产赚钱的能力",
        "reference": "> 5% 优秀",
    },
    "毛利率": {
        "name": "毛利率",
        "formula": "(营收-成本) / 营收",
        "meaning": "产品盈利能力",
        "reference": "> 40% 优秀，20-40% 良好",
    },
    "净利率": {
        "name": "净利率",
        "formula": "净利润 / 营收",
        "meaning": "最终盈利能力",
        "reference": "> 20% 优秀",
    },
    "负债率": {
        "name": "资产负债率",
        "formula": "总负债 / 总资产",
        "meaning": "财务风险",
        "reference": "< 50% 健康，> 70% 高风险",
    },
    "换手率": {
        "name": "换手率",
        "formula": "成交量 / 流通股本",
        "meaning": "交易活跃度",
        "reference": "< 3% 低迷，3-7% 正常，> 7% 活跃",
    },
    "量比": {
        "name": "量比",
        "formula": "当前成交量 / 过去5日平均成交量",
        "meaning": "成交量变化",
        "reference": "> 1.5 放量，< 0.7 缩量",
    },
}


def format_glossary(terms: List[str]) -> str:
    """格式化术语解释。"""
    explanations = []
    for term in terms:
        if term in GLOSSARY:
            g = GLOSSARY[term]
            explanations.append(
                f"📖 {term}（{g['name']}）\n"
                f"   含义：{g['meaning']}\n"
                f"   参考：{g['reference']}"
            )
    if not explanations:
        return ""
    return "\n\n## 术语解释\n\n" + "\n\n".join(explanations)


def add_glossary(text: str, terms: List[str]) -> str:
    """在输出中添加术语解释。"""
    glossary = format_glossary(terms)
    if glossary:
        return text + "\n" + glossary
    return text


def auto_detect_terms(text: str) -> List[str]:
    """自动检测文本中的术语。"""
    detected = []
    for term in GLOSSARY:
        pattern = r"(?<![A-Za-z])" + re.escape(term) + r"(?![A-Za-z])"
        if re.search(pattern, text):
            detected.append(term)
    return detected

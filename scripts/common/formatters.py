"""统一输出格式化工具。

为 12 个 skill 提供一致的输出结构：
  - 首行：一句话结论（🎯 / 🔴 / 🟢 / 🟡 emoji 前缀）
  - 尾行：数据时间戳 + 数据源 + 失败源

用法示例::

    from common.formatters import format_output
    result = format_output(
        conclusion="可分批介入，回踩 1620 加仓",
        data_time="2026-06-15 14:30",
        sources=["腾讯行情", "东方财富财务"],
        failed_sources=["新浪K线"],
        ttl_sec=900,
    )
    print(result)
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional


# ═══════════════════════════════════════════════════════════════
# 术语库
# ═══════════════════════════════════════════════════════════════

GLOSSARY = {
    # 估值指标
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

    # 技术指标
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

    # 均线
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

    # 财务指标
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

    # 市场指标
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
    """格式化术语解释。

    Args:
        terms: 术语列表，如 ["PE", "ROE", "MACD"]

    Returns:
        格式化的术语解释文本
    """
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
    """在输出中添加术语解释。

    Args:
        text: 原始输出文本
        terms: 需要解释的术语列表

    Returns:
        添加术语解释后的文本
    """
    glossary = format_glossary(terms)
    if glossary:
        return text + "\n" + glossary
    return text


def auto_detect_terms(text: str) -> List[str]:
    """自动检测文本中的术语。

    Args:
        text: 输出文本

    Returns:
        检测到的术语列表
    """
    detected = []
    for term in GLOSSARY:
        # 简单匹配：检查术语是否出现在文本中
        # 避免误匹配：检查前后字符
        import re
        pattern = r'(?<![A-Za-z])' + re.escape(term) + r'(?![A-Za-z])'
        if re.search(pattern, text):
            detected.append(term)
    return detected


# ═══════════════════════════════════════════════════════════════
# 风险提示
# ═══════════════════════════════════════════════════════════════

RISK_DISCLAIMER = """
⚠️ 风险提示
- 本分析仅供参考，不构成投资建议
- 股市有风险，投资需谨慎
- 历史表现不代表未来收益
- 请根据自身风险承受能力做出决策
"""


def add_risk_disclaimer(text: str) -> str:
    """添加风险提示。

    Args:
        text: 原始输出文本

    Returns:
        添加风险提示后的文本
    """
    return text + RISK_DISCLAIMER


def format_with_enhancements(
    text: str,
    terms: Optional[List[str]] = None,
    auto_glossary: bool = False,
    risk_disclaimer: bool = True,
) -> str:
    """为输出添加增强功能（术语解释 + 风险提示）。

    Args:
        text: 原始输出文本
        terms: 需要解释的术语列表（手动指定）
        auto_glossary: 是否自动检测术语
        risk_disclaimer: 是否添加风险提示

    Returns:
        增强后的文本
    """
    result = text

    # 自动检测术语
    if auto_glossary and not terms:
        terms = auto_detect_terms(text)

    # 添加术语解释
    if terms:
        result = add_glossary(result, terms)

    # 添加风险提示
    if risk_disclaimer:
        result = add_risk_disclaimer(result)

    return result


# ═══════════════════════════════════════════════════════════════
# 数据导出
# ═══════════════════════════════════════════════════════════════

def export_to_csv(data: List[dict], filename: str, output_dir: str = "output") -> str:
    """导出数据到 CSV 文件。

    Args:
        data: 数据列表，每项是字典
        filename: 文件名（不含扩展名）
        output_dir: 输出目录

    Returns:
        导出文件路径
    """
    import csv
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    filepath = output_path / f"{filename}.csv"

    if not data:
        # 创建空文件
        filepath.write_text("", encoding="utf-8-sig")
        return str(filepath)

    # 获取字段名
    fieldnames = list(data[0].keys())

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

    return str(filepath)


def export_analysis_to_csv(analysis: dict, filename: str) -> str:
    """导出分析结果到 CSV。

    Args:
        analysis: 分析结果字典
        filename: 文件名

    Returns:
        导出文件路径
    """
    # 扁平化嵌套字典
    flat_data = _flatten_dict(analysis)
    data = [{"指标": k, "值": v} for k, v in flat_data.items()]
    return export_to_csv(data, filename)


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """扁平化嵌套字典。

    Args:
        d: 嵌套字典
        parent_key: 父键名
        sep: 分隔符

    Returns:
        扁平化后的字典
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            # 列表转字符串
            items.append((new_key, str(v)))
        else:
            items.append((new_key, v))
    return dict(items)


def format_output(
    conclusion: str,
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
    body: Optional[str] = None,
    *,
    emoji: str = "🎯",
) -> str:
    """生成统一格式的 skill 输出。

    Args:
        conclusion: 一句话结论（必填）
        data_time: 数据时间戳，如 "2026-06-15 14:30"
        sources: 使用的数据源列表
        failed_sources: 失败的数据源列表
        ttl_sec: 数据 TTL（秒），用于提示"数据是 X 秒前的"
        body: 中间详细内容（五层分析、专家辩论等）
        emoji: 结论前缀 emoji，默认 🎯

    Returns:
        格式化的完整输出字符串
    """
    lines = []

    # ── 首行：一句话结论 ──
    lines.append(f"{emoji} {conclusion}")
    lines.append("")

    # ── 中间：详细内容 ──
    if body:
        lines.append(body.rstrip())
        lines.append("")

    # ── 尾行：数据源与时间戳 ──
    footer_parts = []

    if data_time:
        footer_parts.append(f"数据时间戳: {data_time}")

    if sources:
        footer_parts.append(f"数据源: {', '.join(sources)}")

    if failed_sources:
        footer_parts.append(f"⚠️ 失败源: {', '.join(failed_sources)}")

    if ttl_sec is not None:
        footer_parts.append(f"数据 TTL: {ttl_sec}s")

    if footer_parts:
        lines.append("─" * 40)
        lines.append("📊 " + " | ".join(footer_parts))

    return "\n".join(lines)


def format_conclusion(conclusion: str, emoji: str = "🎯") -> str:
    """仅生成一句话结论行（不带尾行）。

    适合 quick 模式等轻量输出场景。
    """
    return f"{emoji} {conclusion}"


def format_footer(
    data_time: Optional[str] = None,
    sources: Optional[List[str]] = None,
    failed_sources: Optional[List[str]] = None,
    ttl_sec: Optional[int] = None,
) -> str:
    """仅生成尾行（数据源 + 时间戳）。

    适合需要手动拼接 body 的场景。
    """
    footer_parts = []
    if data_time:
        footer_parts.append(f"数据时间戳: {data_time}")
    if sources:
        footer_parts.append(f"数据源: {', '.join(sources)}")
    if failed_sources:
        footer_parts.append(f"⚠️ 失败源: {', '.join(failed_sources)}")
    if ttl_sec is not None:
        footer_parts.append(f"数据 TTL: {ttl_sec}s")

    if not footer_parts:
        return ""
    return "─" * 40 + "\n📊 " + " | ".join(footer_parts)


def now_str() -> str:
    """返回当前时间的格式化字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def collect_source_evidence(fetcher_results: dict[str, object | None]) -> tuple[list[str], list[str]]:
    """从 fetcher 结果中收集数据源证据。

    Args:
        fetcher_results: {fetcher_name: result_or_None} 字典

    Returns:
        (成功源列表, 失败源列表)
    """
    sources = []
    failed = []
    for name, result in fetcher_results.items():
        if result is not None:
            sources.append(name)
        else:
            failed.append(name)
    return sources, failed

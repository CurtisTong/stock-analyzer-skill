"""
长期持有评估模块。

评估股票是否适合长期持有（3 年以上），从四个维度：
- 护城河（30%）：品牌、渠道、成本、转换成本
- 成长性（25%）：营收增长、利润增长、ROE 趋势
- 稳定性（25%）：负债率、现金流、分红
- 估值（20%）：PE 分位、PB 分位

用法：
    python3 scripts/technical/long_term.py sh600519
    python3 scripts/technical/long_term.py sh600519 --json
"""

import json

from common import to_float
from data.helpers import fetch_quote_dict_or_none, fetch_finance_first

# ═══════════════════════════════════════════════════════════════
# 长期持有评估
# ═══════════════════════════════════════════════════════════════


class LongTermEvaluator:
    """长期持有评估器。"""

    # 维度权重
    WEIGHTS = {
        "moat": 0.30,  # 护城河
        "growth": 0.25,  # 成长性
        "stability": 0.25,  # 稳定性
        "valuation": 0.20,  # 估值
    }

    def evaluate(self, code: str) -> dict:
        """评估股票是否适合长期持有。

        Args:
            code: 股票代码

        Returns:
            {
                "code": str,
                "name": str,
                "total_score": int,
                "level": str,
                "dimensions": {...},
                "reasoning": [...],
                "conclusion": str,
            }
        """
        # 获取数据
        quote = self._get_quote(code)
        finance = self._get_finance(code)

        if not quote:
            return {"code": code, "error": "无法获取行情数据"}

        # 计算各维度得分
        moat_score, moat_reasoning = self._calc_moat(finance)
        growth_score, growth_reasoning = self._calc_growth(finance)
        stability_score, stability_reasoning = self._calc_stability(finance)
        valuation_score, valuation_reasoning = self._calc_valuation(quote, finance)

        # 计算总分
        total_score = (
            moat_score * self.WEIGHTS["moat"]
            + growth_score * self.WEIGHTS["growth"]
            + stability_score * self.WEIGHTS["stability"]
            + valuation_score * self.WEIGHTS["valuation"]
        )
        total_score = int(total_score)

        # 计算等级
        level = self._calc_level(total_score)

        # 生成结论
        conclusion = self._generate_conclusion(
            total_score,
            level,
            moat_score,
            growth_score,
            stability_score,
            valuation_score,
        )

        # 合并推理链
        reasoning = (
            moat_reasoning
            + growth_reasoning
            + stability_reasoning
            + valuation_reasoning
        )

        return {
            "code": code,
            "name": quote.get("name", ""),
            "total_score": total_score,
            "level": level,
            "dimensions": {
                "moat": {"score": moat_score, "weight": self.WEIGHTS["moat"]},
                "growth": {"score": growth_score, "weight": self.WEIGHTS["growth"]},
                "stability": {
                    "score": stability_score,
                    "weight": self.WEIGHTS["stability"],
                },
                "valuation": {
                    "score": valuation_score,
                    "weight": self.WEIGHTS["valuation"],
                },
            },
            "reasoning": reasoning,
            "conclusion": conclusion,
        }

    def _get_quote(self, code: str) -> dict:
        """获取行情数据。"""
        try:
            return fetch_quote_dict_or_none(code)
        except Exception:
            return None

    def _get_finance(self, code: str) -> dict:
        """获取财务数据。"""
        try:
            return fetch_finance_first(code)
        except Exception:
            return {}

    def _calc_moat(self, finance: dict) -> tuple:
        """计算护城河得分。"""
        score = 50  # 默认中等
        reasoning = []

        # 毛利率（反映定价权）
        gross_margin = to_float(finance.get("gross_margin") or finance.get("MLLB") or 0)
        if gross_margin > 50:
            score += 20
            reasoning.append(f"✅ 毛利率 {gross_margin:.1f}% > 50%，定价权强")
        elif gross_margin > 30:
            score += 10
            reasoning.append(f"⚠️ 毛利率 {gross_margin:.1f}%，定价权一般")
        else:
            score -= 10
            reasoning.append(f"❌ 毛利率 {gross_margin:.1f}% < 30%，定价权弱")

        # 净利率（反映盈利能力）
        net_margin = to_float(finance.get("net_margin") or finance.get("JLL") or 0)
        if net_margin > 20:
            score += 15
            reasoning.append(f"✅ 净利率 {net_margin:.1f}% > 20%，盈利能力强")
        elif net_margin > 10:
            reasoning.append(f"⚠️ 净利率 {net_margin:.1f}%，盈利能力一般")
        else:
            score -= 10
            reasoning.append(f"❌ 净利率 {net_margin:.1f}% < 10%，盈利能力弱")

        # ROE（反映资本效率）
        roe = to_float(finance.get("ROEJQ") or finance.get("roe") or 0)
        if roe > 20:
            score += 15
            reasoning.append(f"✅ ROE {roe:.1f}% > 20%，资本效率高")
        elif roe > 15:
            score += 5
            reasoning.append(f"⚠️ ROE {roe:.1f}%，资本效率良好")
        else:
            reasoning.append(f"⚠️ ROE {roe:.1f}%，资本效率一般")

        score = max(0, min(100, score))
        return score, reasoning

    def _calc_growth(self, finance: dict) -> tuple:
        """计算成长性得分。"""
        score = 50
        reasoning = []

        # 营收增长率
        revenue_growth = to_float(
            finance.get("revenue_growth") or finance.get("YYZSRTBZZ") or 0
        )
        if revenue_growth > 20:
            score += 20
            reasoning.append(f"✅ 营收增长 {revenue_growth:.1f}% > 20%，高成长")
        elif revenue_growth > 10:
            score += 10
            reasoning.append(f"⚠️ 营收增长 {revenue_growth:.1f}%，稳定成长")
        elif revenue_growth > 0:
            reasoning.append(f"⚠️ 营收增长 {revenue_growth:.1f}%，低增长")
        else:
            score -= 15
            reasoning.append(f"❌ 营收增长 {revenue_growth:.1f}%，负增长")

        # 净利润增长率
        profit_growth = to_float(
            finance.get("profit_growth") or finance.get("JLRTBZZ") or 0
        )
        if profit_growth > 20:
            score += 20
            reasoning.append(f"✅ 利润增长 {profit_growth:.1f}% > 20%，高成长")
        elif profit_growth > 10:
            score += 10
            reasoning.append(f"⚠️ 利润增长 {profit_growth:.1f}%，稳定成长")
        elif profit_growth > 0:
            reasoning.append(f"⚠️ 利润增长 {profit_growth:.1f}%，低增长")
        else:
            score -= 15
            reasoning.append(f"❌ 利润增长 {profit_growth:.1f}%，负增长")

        # ROE 趋势（简化：当前 ROE）
        roe = to_float(finance.get("ROEJQ") or finance.get("roe") or 0)
        if roe > 15:
            score += 10
            reasoning.append(f"✅ ROE {roe:.1f}% > 15%，盈利能力优秀")
        elif roe > 10:
            reasoning.append(f"⚠️ ROE {roe:.1f}%，盈利能力良好")
        else:
            score -= 10
            reasoning.append(f"❌ ROE {roe:.1f}% < 10%，盈利能力一般")

        score = max(0, min(100, score))
        return score, reasoning

    def _calc_stability(self, finance: dict) -> tuple:
        """计算稳定性得分。"""
        score = 50
        reasoning = []

        # 负债率
        debt_ratio = to_float(finance.get("ZCFZL") or finance.get("debt_ratio") or 0)
        if debt_ratio < 30:
            score += 20
            reasoning.append(f"✅ 负债率 {debt_ratio:.1f}% < 30%，财务稳健")
        elif debt_ratio < 50:
            score += 10
            reasoning.append(f"⚠️ 负债率 {debt_ratio:.1f}%，财务正常")
        elif debt_ratio < 70:
            reasoning.append(f"⚠️ 负债率 {debt_ratio:.1f}%，负债偏高")
        else:
            score -= 20
            reasoning.append(f"❌ 负债率 {debt_ratio:.1f}% > 70%，财务风险高")

        # 现金流（每股经营现金流）
        ocf = to_float(finance.get("MGJYXJJE") or finance.get("ocf_per_share") or 0)
        eps = to_float(finance.get("EPSJB") or finance.get("eps") or 0)
        if eps > 0 and ocf > 0:
            fcf_ratio = ocf / eps
            if fcf_ratio > 0.8:
                score += 15
                reasoning.append(f"✅ 现金流充足：OCF/EPS {fcf_ratio:.1%} > 80%")
            elif fcf_ratio > 0.5:
                reasoning.append(f"⚠️ 现金流一般：OCF/EPS {fcf_ratio:.1%}")
            else:
                score -= 10
                reasoning.append(f"❌ 现金流不足：OCF/EPS {fcf_ratio:.1%} < 50%")
        elif eps <= 0 and ocf > 0:
            # 亏损但有现金流：可能是账面亏损（折旧等），实际经营有造血能力
            score += 10
            reasoning.append(
                f"✅ 虽然账面亏损(EPS={eps:.2f})，但经营现金流为正(OCF={ocf:.2f})，造血能力尚存"
            )
        elif ocf <= 0:
            score -= 10
            reasoning.append(f"❌ 经营现金流为负(OCF={ocf:.2f})，需关注资金链风险")
        else:
            reasoning.append("⚠️ 现金流数据缺失")

        # 分红率（简化：有分红即可）
        dividend = to_float(finance.get("dividend_yield") or finance.get("GXL") or 0)
        if dividend > 3:
            score += 15
            reasoning.append(f"✅ 股息率 {dividend:.1f}% > 3%，分红慷慨")
        elif dividend > 1:
            score += 5
            reasoning.append(f"⚠️ 股息率 {dividend:.1f}%，分红一般")
        else:
            reasoning.append(f"⚠️ 股息率 {dividend:.1f}%，分红较少")

        score = max(0, min(100, score))
        return score, reasoning

    def _calc_valuation(self, quote: dict, finance: dict) -> tuple:
        """计算估值得分。"""
        score = 50
        reasoning = []

        # PE 分位
        pe = to_float(quote.get("pe") or 0)
        pe_percentile = to_float(quote.get("pe_percentile") or -1)

        if pe > 0:
            if pe < 15:
                score += 20
                reasoning.append(f"✅ PE {pe:.1f} < 15，低估")
            elif pe < 25:
                score += 10
                reasoning.append(f"⚠️ PE {pe:.1f}，合理估值")
            elif pe < 40:
                reasoning.append(f"⚠️ PE {pe:.1f}，偏高")
            else:
                score -= 15
                reasoning.append(f"❌ PE {pe:.1f} > 40，高估")

        # PE 历史分位
        if 0 <= pe_percentile < 30:
            score += 15
            reasoning.append(f"✅ PE 历史分位 {pe_percentile:.0f}%，处于历史低位")
        elif pe_percentile > 70:
            score -= 15
            reasoning.append(f"❌ PE 历史分位 {pe_percentile:.0f}%，处于历史高位")
        elif pe_percentile >= 0:
            reasoning.append(f"⚠️ PE 历史分位 {pe_percentile:.0f}%，处于历史中位")

        # PB 分位
        pb = to_float(quote.get("pb") or 0)
        if pb > 0:
            if pb < 1:
                score += 10
                reasoning.append(f"✅ PB {pb:.1f} < 1，低估")
            elif pb < 3:
                reasoning.append(f"⚠️ PB {pb:.1f}，合理估值")
            else:
                score -= 10
                reasoning.append(f"❌ PB {pb:.1f} > 3，高估")

        score = max(0, min(100, score))
        return score, reasoning

    def _calc_level(self, score: int) -> str:
        """计算等级。"""
        if score >= 80:
            return "非常适合"
        elif score >= 65:
            return "适合"
        elif score >= 50:
            return "一般"
        elif score >= 35:
            return "不太适合"
        else:
            return "不适合"

    def _generate_conclusion(
        self, total_score, level, moat, growth, stability, valuation
    ) -> str:
        """生成结论。"""
        conclusions = []

        # 总体结论
        if total_score >= 75:
            conclusions.append(
                f"综合评分 {total_score} 分（{level}），护城河宽、成长性好、财务稳健、估值合理，非常适合长期持有。"
            )
        elif total_score >= 60:
            conclusions.append(
                f"综合评分 {total_score} 分（{level}），整体质量较好，可考虑长期持有。"
            )
        elif total_score >= 45:
            conclusions.append(
                f"综合评分 {total_score} 分（{level}），质量一般，需谨慎考虑。"
            )
        else:
            conclusions.append(
                f"综合评分 {total_score} 分（{level}），不建议长期持有。"
            )

        # 各维度亮点/风险
        if moat >= 70:
            conclusions.append("✅ 护城河宽，竞争优势明显")
        elif moat < 40:
            conclusions.append("⚠️ 护城河窄，竞争压力大")

        if growth >= 70:
            conclusions.append("✅ 成长性好，盈利稳定增长")
        elif growth < 40:
            conclusions.append("⚠️ 成长性差，增长乏力")

        if stability >= 70:
            conclusions.append("✅ 财务稳健，现金流充足")
        elif stability < 40:
            conclusions.append("⚠️ 财务风险高，负债偏重")

        if valuation >= 70:
            conclusions.append("✅ 估值合理，具有安全边际")
        elif valuation < 40:
            conclusions.append("⚠️ 估值偏高，安全边际不足")

        return "\n".join(conclusions)


def format_long_term_result(result: dict) -> str:
    """格式化长期持有评估结果。"""
    if "error" in result:
        return f"❌ 评估失败：{result['error']}"

    code = result["code"]
    name = result["name"]
    total_score = result["total_score"]
    level = result["level"]
    dimensions = result["dimensions"]
    reasoning = result["reasoning"]
    conclusion = result["conclusion"]

    # 生成分数条
    bar_length = 20
    filled = int(total_score / 100 * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)

    # 等级图标
    level_icon = {
        "非常适合": "🟢",
        "适合": "🟡",
        "一般": "⚪",
        "不太适合": "🟠",
        "不适合": "🔴",
    }.get(level, "⚪")

    lines = [
        f"📈 长期持有评估：{name}（{code}）",
        "",
        f"综合评分：{total_score}/100（{level_icon} {level}）",
        f"[{bar}] {total_score}%",
        "",
        "## 评分明细",
        "",
        "| 维度 | 权重 | 得分 | 评价 |",
        "|------|------|------|------|",
    ]

    dim_names = {
        "moat": "护城河",
        "growth": "成长性",
        "stability": "稳定性",
        "valuation": "估值",
    }

    dim_levels = {
        "moat": lambda s: "宽" if s >= 70 else ("一般" if s >= 40 else "窄"),
        "growth": lambda s: "好" if s >= 70 else ("一般" if s >= 40 else "差"),
        "stability": lambda s: "稳健" if s >= 70 else ("一般" if s >= 40 else "高风险"),
        "valuation": lambda s: "合理" if s >= 70 else ("一般" if s >= 40 else "偏高"),
    }

    for dim_key, dim_data in dimensions.items():
        dim_name = dim_names.get(dim_key, dim_key)
        weight = dim_data["weight"]
        score = dim_data["score"]
        level_fn = dim_levels.get(dim_key, lambda s: "")
        level_str = level_fn(score)
        lines.append(f"| {dim_name} | {weight:.0%} | {score:.0f} | {level_str} |")

    lines.append("")
    lines.append("## 推理过程")
    lines.append("")

    for r in reasoning:
        lines.append(f"- {r}")

    lines.append("")
    lines.append("## 结论")
    lines.append("")
    lines.append(conclusion)

    return "\n".join(lines)


def main():
    """主入口。"""
    import argparse

    parser = argparse.ArgumentParser(description="长期持有评估")
    parser.add_argument("code", help="股票代码")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    # 评估
    evaluator = LongTermEvaluator()
    result = evaluator.evaluate(args.code)

    # 输出
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_long_term_result(result))


if __name__ == "__main__":
    main()

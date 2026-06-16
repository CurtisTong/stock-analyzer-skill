"""
8 位专家的评分矩阵注册表。

数据来源：experts/*.md §九、评分矩阵。
每条记录的 weights 字段对应原 markdown 表格中的 5 维度权重百分比，
veto_conditions 字段对应原 markdown 中的"一票否决"列表。

如果人设文档更新，只需修改本文件；experts/*.md 是叙事/案例来源。
"""

from typing import Dict, List
from . import ExpertProfile

EXPERT_REGISTRY: Dict[str, ExpertProfile] = {}

# 合规隔离层：内部 ID → 显示名映射。
# 如果未来需要"虚构化"专家名称，只需改这张表 + display_name，
# 评分函数（_score_xu_xiang 等）和 decide.py 的 _EXPERT_PROFILES 不受影响。
LEGACY_ALIAS: Dict[str, str] = {
    "buffett": "巴菲特",
    "lynch": "彼得·林奇",
    "soros": "索罗斯",
    "duan_yongping": "段永平",
    "xu_xiang": "徐翔",
    "zhao_laoge": "赵老哥",
    "chaogu_yangjia": "炒股养家",
    "zuoshou_xinyi": "作手新一",
}


def get_display_name(expert_id: str) -> str:
    """获取专家的显示名称（走 LEGACY_ALIAS 隔离层）。"""
    return LEGACY_ALIAS.get(expert_id, expert_id)


def _register(profile: ExpertProfile) -> None:
    EXPERT_REGISTRY[profile.name] = profile


# ═══════════════════════════════════════════════════════════════
# 长线 4 人
# ═══════════════════════════════════════════════════════════════

_register(
    ExpertProfile(
        name="buffett",
        display_name="巴菲特",
        group="long_term",
        style="价值投资",
        horizon="月/季/年",
        core_signal="基本面+估值",
        weights={
            "基本面": 42.0,
            "估值": 28.0,
            "技术面": 5.0,
            "情绪": 5.0,
            "安全边际": 20.0,
        },
        veto_conditions=[
            "ROE < 10% 或负债率 > 70%（金融业除外）",
            "FCF 连续 2 年为负",
            "公司涉财务造假或管理层失信",
        ],
        md_path="experts/buffett.md",
    )
)

_register(
    ExpertProfile(
        name="lynch",
        display_name="彼得·林奇",
        group="long_term",
        style="成长投资",
        horizon="月/季/年",
        core_signal="基本面+估值",
        weights={
            "基本面": 35.0,
            "估值": 28.0,
            "技术面": 15.0,
            "情绪": 10.0,
            "风险": 12.0,
        },
        veto_conditions=[
            "PEG > 2.5（增速无法消化估值）",
            "连续两季 ROE 下行且营收增速 < 5%",
            "公司'增长故事'被证伪（如政策突变、核心技术被替代）",
        ],
        md_path="experts/lynch.md",
    )
)

_register(
    ExpertProfile(
        name="soros",
        display_name="索罗斯",
        group="long_term",
        style="宏观/趋势",
        horizon="月/季/年",
        core_signal="量价+情绪/反身性",
        weights={
            "基本面": 15.0,
            "估值": 10.0,
            "技术面": 25.0,
            "情绪/反身性": 30.0,
            "风险": 20.0,
        },
        veto_conditions=[
            "市场处于'所有人同边'状态（反身性顶点信号）",
            "流动性枯竭（两市成交额<5000亿且持续缩量）",
            "政策明确打压该板块（反身性向下强化）",
        ],
        md_path="experts/soros.md",
    )
)

_register(
    ExpertProfile(
        name="duan_yongping",
        display_name="段永平",
        group="long_term",
        style="逆向投资",
        horizon="月/季/年",
        core_signal="基本面+估值",
        weights={
            "基本面": 38.0,
            "估值": 22.0,
            "技术面": 5.0,
            "情绪": 5.0,
            "安全边际": 30.0,
        },
        veto_conditions=[
            "FCF 为负（'不赚钱的生意没人会做一辈子'）",
            "公司不熟/商业模式看不懂（'不熟不做'）",
            "管理层不诚信（'正直排第一'）",
        ],
        md_path="experts/duan_yongping.md",
    )
)


# ═══════════════════════════════════════════════════════════════
# 短线 4 人
# ═══════════════════════════════════════════════════════════════

_register(
    ExpertProfile(
        name="xu_xiang",
        display_name="徐翔",
        group="short_term",
        style="涨停板战法",
        horizon="日/周",
        core_signal="量价+情绪/题材",
        weights={
            "基本面": 5.0,
            "估值": 12.0,
            "技术面": 30.0,
            "情绪/题材": 43.0,
            "风险": 10.0,
        },
        veto_conditions=[
            "大盘处于20日均线下方且缩量",
            "全市场涨停家数 < 20（退潮期不打板）",
            "监管'特停'频繁（政策风险不可控）",
            "无涨停基因（近30日无涨停记录）",
        ],
        md_path="experts/xu_xiang.md",
    )
)

_register(
    ExpertProfile(
        name="zhao_laoge",
        display_name="赵老哥",
        group="short_term",
        style="趋势龙头",
        horizon="日/周",
        core_signal="量价+情绪/题材",
        weights={
            "基本面": 10.0,
            "估值": 12.0,
            "技术面": 31.0,
            "情绪/题材": 35.0,
            "风险": 12.0,
        },
        veto_conditions=[
            "龙头地位被替代（板块龙头切换）",
            "跌破20日均线（一票否决）",
        ],
        md_path="experts/zhao_laoge.md",
    )
)

_register(
    ExpertProfile(
        name="chaogu_yangjia",
        display_name="炒股养家",
        group="short_term",
        style="情绪流",
        horizon="日/周",
        core_signal="情绪/题材",
        weights={
            "基本面": 5.0,
            "估值": 12.0,
            "技术面": 15.0,
            "情绪": 58.0,
            "风险": 10.0,
        },
        veto_conditions=[
            "情绪周期处于退潮期（连续亏钱效应）",
            "全市场跌停家数 > 50（恐慌弥漫）",
        ],
        md_path="experts/chaogu_yangjia.md",
    )
)

_register(
    ExpertProfile(
        name="zuoshou_xinyi",
        display_name="作手新一",
        group="short_term",
        style="强势股低吸",
        horizon="日/周",
        core_signal="量价+情绪",
        weights={
            "基本面": 8.0,
            "估值": 12.0,
            "技术面": 33.0,
            "情绪": 35.0,
            "风险": 12.0,
        },
        veto_conditions=[
            "非强势股（无涨停或连板历史）",
            "调整中放量跌破前低（不是低吸是接飞刀）",
            "题材退潮或出现重大负面催化",
        ],
        md_path="experts/zuoshou_xinyi.md",
    )
)


def _ensure_loaded() -> None:
    """注册表在模块导入时已填充，此函数仅作显式触发点。"""
    if len(EXPERT_REGISTRY) != 8:
        raise RuntimeError(
            f"Expected 8 experts, found {len(EXPERT_REGISTRY)}: {list(EXPERT_REGISTRY)}"
        )

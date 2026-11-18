#!/usr/bin/env python3
"""板块归属语义校验：用腾讯行情取真实名称，按板块规则判定是否错配。

背景：`tests/contracts/test_sector_pool_integrity.py` 的结构校验能抓「重复 /
雷同 / 退市」，抓不到**归类语义错误**（东方财富挂在「资源」、济川药业挂在
「机器人」）。这类错误只能靠「代码 → 真实名称 → 行业关键词」判定，本工具就是
这层判定。

设计:
    - 名称一律现取（腾讯 `qt.gtimg.cn`，批量 50 只/次），不硬编码、不凭记忆；
    - 每个板块一条规则：关键词命中 = ok；命中「异业关键词」= mismatch（带建议）；
      都没命中 = unknown（关键词覆盖不到，交人工复核，**不算错**）；
    - 电力/光伏/新能源/资源 四个核心板块的规则写死在 `_CORE_RULES`，其余板块是
      关键词近似，报告里标 `approximate`；
    - 有 mismatch 时 exit 1，可直接进 CI（但要走网络，默认不在 `not network` 里跑）。

用法::

    python3 scripts/dev/verify_sector_names.py                 # 全量扫描，表格输出
    python3 scripts/dev/verify_sector_names.py --sectors 资源,机器人 --json
    python3 scripts/dev/verify_sector_names.py --strict        # mismatch 时 exit 1（默认）
    python3 scripts/dev/verify_sector_names.py --no-fail       # 只报告不失败

⚠️ 本脚本会发起真实网络请求（284 只 / 约 6 次批量请求），不要高频运行。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from common import decode_gbk, http_get, parse_tencent_line  # noqa: E402

_DATA_DIR = _SCRIPTS_DIR / "data"
_TENCENT_URL = "https://qt.gtimg.cn/q={codes}"
_BATCH_SIZE = 50
_LINE_PREFIX = re.compile(r"v_((?:sh|sz|bj)\d{6})=")

# ---------- 板块判定规则 ----------
# keywords: 名称里出现即视为该板块成员（正向证据）
# forbidden: (关键词, 建议归属) —— 出现即判 mismatch（反向证据，强于正向）
# 说明：核心板块规则写死（用户口径），其余为关键词近似，报告里标 approximate。

_CORE_RULES: dict[str, dict] = {
    "电力": {
        "keywords": (
            "电力", "水电", "核电", "能源", "发电", "电投", "三峡", "华能", "大唐",
            "申能", "京能", "川投", "桂冠", "韶能", "浙能", "皖能", "赣能", "豫能",
            "建投", "国电", "华电", "上海电力", "湖北能源", "内蒙华电", "长源",
        ),
        "forbidden": (
            ("锂", "新能源"), ("电池", "新能源"), ("光伏", "光伏"), ("太阳能", "光伏"),
            ("逆变", "光伏"), ("硅", "光伏"),
        ),
    },
    "光伏": {
        "keywords": (
            "光伏", "太阳能", "硅", "单晶", "组件", "逆变", "电池片", "胶膜", "玻璃",
            "隆基", "通威", "晶澳", "天合", "晶科", "中环", "大全", "帝尔", "捷佳",
            "迈为", "金辰", "亚玛顿", "中信博", "上机", "弘元", "亿晶", "京运通",
            "爱旭", "日升", "中来", "福斯特", "福莱特", "阳光电源", "特变",
        ),
        "forbidden": (
            ("锂", "新能源"), ("电池", "新能源"), ("地产", "（无对应板块）"),
            ("客车", "（无对应板块）"), ("药业", "医药"), ("医药", "医药"),
            ("银行", "金融"), ("证券", "金融"), ("农业", "（无对应板块）"),
            ("养殖", "（无对应板块）"), ("出版", "（无对应板块）"),
        ),
    },
    "新能源": {
        "keywords": (
            "锂", "电池", "宁德", "亿纬", "赣锋", "天齐", "恩捷", "当升", "璞泰来",
            "华友", "天赐", "先导", "国轩", "欣旺达", "孚能", "杉杉", "三花", "容百",
            "中伟", "德方", "科达利", "格林美", "比亚迪", "新能", "材料", "时代",
        ),
        "forbidden": (
            ("光伏", "光伏"), ("太阳能", "光伏"), ("组件", "光伏"), ("硅", "光伏"),
            ("逆变", "光伏"),
        ),
    },
    "资源": {
        "keywords": (
            "煤", "矿", "有色", "铝", "铜", "锌", "稀土", "钢", "铁", "金", "钼", "钨",
            "镍", "锡", "神华", "紫金", "洛钼", "黄金", "能源", "盐湖", "磷", "化工",
            "石油", "石化",
        ),
        "forbidden": (
            ("证券", "金融"), ("银行", "金融"), ("财富", "金融"), ("保险", "金融"),
            ("农业", "（无对应板块）"), ("农", "（无对应板块）"),
            ("牧业", "（无对应板块）"), ("养殖", "（无对应板块）"),
            ("出版", "（无对应板块）"), ("药业", "医药"), ("医药", "医药"),
            ("软件", "科技"), ("网络", "科技"),
        ),
    },
}

_APPROX_RULES: dict[str, dict] = {
    "消费": {
        "keywords": ("食品", "乳业", "酒", "饮料", "零售", "家电", "服装", "日用",
                     "超市", "餐饮", "旅游", "医药", "医疗", "生物", "制药"),
        "forbidden": (("光伏", "光伏"), ("煤", "资源"), ("证券", "金融")),
    },
    "科技": {
        "keywords": ("科技", "软件", "信息", "网络", "智能", "通信", "电子", "半导",
                     "芯片", "数据", "云", "人工智能", "传媒", "出版", "用友", "科大"),
        "forbidden": (("煤", "资源"), ("证券", "金融"), ("药业", "医药")),
    },
    "医药": {
        "keywords": ("药", "医", "生物", "医疗", "健康", "制药", "疫苗", "器械"),
        "forbidden": (("光伏", "光伏"), ("煤", "资源"), ("机器人", "机器人")),
    },
    "金融": {
        "keywords": ("银行", "证券", "保险", "信托", "期货", "财富", "金控", "金融"),
        "forbidden": (("药业", "医药"), ("光伏", "光伏")),
    },
    "石化": {
        "keywords": ("石油", "石化", "化纤", "炼化", "油服", "燃气", "化学", "化工"),
        "forbidden": (("药业", "医药"), ("证券", "金融")),
    },
    "军工": {
        "keywords": ("航空", "航天", "船舶", "兵", "军工", "电子", "雷达", "导弹",
                     "重工", "动力", "光电", "导航"),
        "forbidden": (("药业", "医药"), ("证券", "金融"), ("出版", "（无对应板块）")),
    },
    "半导体": {
        "keywords": ("半导体", "芯片", "微电", "集成", "光电", "存储", "晶", "芯",
                     "华虹", "中芯", "韦尔", "北方华创", "兆易"),
        "forbidden": (("煤", "资源"), ("证券", "金融"), ("药业", "医药")),
    },
    "机器人": {
        "keywords": ("机器人", "自动化", "数控", "机床", "减速", "伺服", "传动",
                     "智能装备", "精工", "机电", "股份"),
        "forbidden": (("出版", "（无对应板块）"), ("药业", "医药"),
                      ("软件", "科技"), ("网络", "科技"), ("银行", "金融")),
    },
    "家电": {
        "keywords": ("电器", "家电", "空调", "冰", "厨", "生活电器", "美的", "格力",
                     "海尔", "苏泊尔", "九阳"),
        "forbidden": (("煤", "资源"), ("证券", "金融")),
    },
    "通信设备": {
        "keywords": ("通信", "光缆", "光纤", "网络", "电子", "科技", "射频", "天线"),
        "forbidden": (("药业", "医药"), ("煤", "资源")),
    },
    "消费电子": {
        "keywords": ("电子", "科技", "光电", "精密", "声学", "连接器", "模组",
                     "股份", "视像", "传媒"),
        "forbidden": (("煤", "资源"), ("证券", "金融"), ("药业", "医药")),
    },
    "汽车电子": {
        "keywords": ("汽车", "车", "电子", "智能", "adas", "雷达", "传感", "零部件"),
        "forbidden": (("煤", "资源"), ("证券", "金融"), ("药业", "医药")),
    },
}

# 名称里没有任何行业词、关键词规则判不出来的公司（显式维护，随扫描结果追加）。
# 值 = {"sector": 应属板块, "reason": 理由, "added": 加入日期}；不在该板块时判 mismatch。
# 豁免清单是这类工具的腐蚀点：不带理由和日期的条目，半年后没人敢删。
_NAME_HINTS: dict[str, dict[str, str]] = {
    "温氏股份": {
        "sector": "消费",
        "reason": "养殖（猪禽）属大消费链；申万把它单列为农林牧渔一级行业，本仓库无该板块",
        "added": "2026-11-19",
    },
    "大北农": {
        "sector": "消费",
        "reason": "饲料/种业属大消费链；本仓库无农林牧渔板块",
        "added": "2026-11-19",
    },
    "牧原股份": {
        "sector": "消费",
        "reason": "生猪养殖属大消费链；本仓库无农林牧渔板块",
        "added": "2026-11-19",
    },
    "新希望": {
        "sector": "消费",
        "reason": "饲料/养殖属大消费链；本仓库无农林牧渔板块",
        "added": "2026-11-19",
    },
    # 以下为研判 2026-11-19 抽查 97 条关键词盲区后判「归属正确但名称无行业词」
    "北大荒": {
        "sector": "消费",
        "reason": "农垦种植属大消费链；本仓库无农林牧渔板块（研判抽查判对）",
        "added": "2026-11-19",
    },
    "新研股份": {
        "sector": "军工",
        "reason": "航空零部件为主业，农机为辅（研判抽查判对）",
        "added": "2026-11-19",
    },
    "中化装备": {
        "sector": "机器人",
        "reason": "化工装备，与机器人同属装备制造口径（研判抽查判对，近似）",
        "added": "2026-11-19",
    },
    "隆华科技": {
        "sector": "机器人",
        "reason": "传热/环保装备，与机器人同属装备制造口径（研判抽查判对，近似）",
        "added": "2026-11-19",
    },
    "三环集团": {
        "sector": "半导体",
        "reason": "MLCC/电子陶瓷，属半导体元器件链（研判抽查判对）",
        "added": "2026-11-19",
    },
    "新和成": {
        "sector": "医药",
        "reason": "维生素/原料药为主业（研判抽查判对）",
        "added": "2026-11-19",
    },
    "天下秀": {
        "sector": "科技",
        "reason": "红人经济/互联网营销，归科技（研判抽查判对，近似）",
        "added": "2026-11-19",
    },
}

# 关键词会误伤、但归属经确认无问题的标的（键 = (代码, 板块)）
_SECTOR_EXCEPTIONS: dict[tuple[str, str], dict[str, str]] = {
    ("sz000591", "电力"): {
        "reason": "中节能太阳能是光伏电站运营方（发电端），归电力运营，不归光伏制造",
        "added": "2026-11-19",
    },
}

# 主题板块：成员由其他板块再筛，不做行业归属判定
_THEME_SECTORS = {"高股息", "PCB/AI算力"}

_SECTOR_RULES: dict[str, dict] = {**_CORE_RULES, **_APPROX_RULES}


def load_pools(path: Path | None = None) -> dict[str, list[str]]:
    """读取板块池（排除 `_meta` 等下划线键）。"""
    path = path or (_DATA_DIR / "sector_stocks.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, list)}


def load_sector_map(path: Path | None = None) -> dict[str, str]:
    """读取「代码 → 板块」映射表。"""
    path = path or (_DATA_DIR / "stock_sector_map.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return dict(data.get("stocks") or {})


def fetch_names(codes: list[str], batch_size: int = _BATCH_SIZE) -> dict[str, str]:
    """批量取真实名称（腾讯行情）。取不到的代码不出现在返回值里。"""
    names: dict[str, str] = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        url = _TENCENT_URL.format(codes=",".join(batch))
        try:
            text = decode_gbk(http_get(url, timeout=10, max_retries=2))
        except Exception as exc:  # 网络异常不吞成空：整批跳过并在报告里体现
            print(f"⚠️ 行情请求失败（{len(batch)} 只）: {exc}", file=sys.stderr)
            continue
        for line in text.strip().split(";"):
            line = line.strip()
            if not line:
                continue
            m = _LINE_PREFIX.search(line)
            rec = parse_tencent_line(line)
            if m and rec.get("name"):
                names[m.group(1)] = rec["name"]
    return names


def _looks_delisted_or_st(name: str) -> bool:
    """ST / *ST / 退市整理期（名称带「退」）一律不可选，与 data.pool.is_st 同口径。"""
    upper = name.upper()
    return "ST" in upper or "退市" in upper or upper.endswith("退")


def classify(name: str, sector: str, code: str = "") -> tuple[str, str]:
    """判定单个「代码名称 × 板块」的归属。

    返回 (verdict, detail)：
    - ``("ok", "")``：命中本板块关键词；
    - ``("mismatch", 建议归属)``：命中异业关键词（name == "" 时无法判定，返回 unknown）；
    - ``("unknown", 原因)``：规则覆盖不到，交人工复核。
    """
    if not name:
        return "unknown", "名称缺失"
    if _looks_delisted_or_st(name):
        return "mismatch", "ST/退市（不可选标的）"
    if sector in _THEME_SECTORS:
        return "unknown", "主题板块不判归属"
    rule = _SECTOR_RULES.get(sector)
    if rule is None:
        return "unknown", "无规则"

    exception = _SECTOR_EXCEPTIONS.get((code, sector))
    if exception:
        return "ok", f"显式豁免（{exception['added']}）"
    hint = _NAME_HINTS.get(name)
    if hint is not None:
        if hint["sector"] == sector:
            return "ok", ""
        return "mismatch", hint["sector"]
    for kw, hint in rule["forbidden"]:
        if kw.lower() in name.lower():
            return "mismatch", hint
    for kw in rule["keywords"]:
        if kw.lower() in name.lower():
            return "ok", ""
    return "unknown", "关键词未覆盖"


def _mapping_conflicts(sector: str, mapped: str, pools: dict[str, list[str]]) -> bool:
    """映射表归属与板块池归属是否真的冲突。

    - 任一侧是主题板块 → 不冲突（主题板块跨行业抽取成员）；
    - 映射值是池子里没有的更细行业（化工/半导体/医药…）→ 不冲突；
    - 新能源 / 新能源车 是同一块的粗细写法 → 不冲突；
    - 其余（两个都是池内行业板块且不同）→ 冲突。
    """
    if sector in _THEME_SECTORS or mapped in _THEME_SECTORS:
        return False
    if mapped not in pools:
        return False
    aliases = {"新能源": {"新能源车"}, "新能源车": {"新能源"}}
    return mapped not in aliases.get(sector, set())


def build_report(
    pools: dict[str, list[str]],
    mapping: dict[str, str],
    names: dict[str, str],
    sectors: list[str] | None = None,
) -> dict:
    """生成扫描报告（纯函数，不触网，单测直接喂数据）。"""
    rows: list[dict] = []
    for sector, codes in sorted(pools.items()):
        if sectors and sector not in sectors:
            continue
        for code in codes:
            name = names.get(code, "")
            verdict, detail = classify(name, sector, code)
            mapped = mapping.get(code)
            row = {
                "code": code,
                "name": name,
                "sector": sector,
                "mapped": mapped,
                "verdict": verdict,
                "detail": detail,
                "approximate": sector not in _CORE_RULES,
            }
            # 映射表优先于池子：映射指向另一个「板块池里的行业板块」才算冲突。
            # 主题板块（高股息/PCB/AI算力/人工智能）与更细口径（化工/半导体/医药）
            # 本身就是映射表的设计意图，不判错。
            if mapped and mapped != sector and verdict == "ok":
                if _mapping_conflicts(sector, mapped, pools):
                    row["verdict"] = "mismatch"
                    row["detail"] = f"映射表归属为「{mapped}」"
            rows.append(row)

    mismatches = [r for r in rows if r["verdict"] == "mismatch"]
    return {
        "scanned": len(rows),
        "mismatches": mismatches,
        "unknown": [r for r in rows if r["verdict"] == "unknown"],
        "counts": _counts(rows),
        "rows": rows,
    }


def _counts(rows: list[dict]) -> dict:
    """口径必须写死：条目数（池内出现次数）与唯一代码数分开报，两者不等。

    同一只票可同时属于两个行业板块，所以「扫描 272 条」对应 232 个唯一代码；
    只报其中一个数会让「unknown 占一半」和「unknown 137 条」对不上。
    """
    unknown = [r for r in rows if r["verdict"] == "unknown"]
    theme = [r for r in unknown if r["sector"] in _THEME_SECTORS]
    mismatch = [r for r in rows if r["verdict"] == "mismatch"]
    return {
        "rows": len(rows),
        "codes": len({r["code"] for r in rows}),
        "mismatch_rows": len(mismatch),
        "mismatch_codes": len({r["code"] for r in mismatch}),
        "unknown_rows": len(unknown),
        "unknown_codes": len({r["code"] for r in unknown}),
        "unknown_theme_rows": len(theme),
        "unknown_theme_codes": len({r["code"] for r in theme}),
        "unknown_blind_rows": len(unknown) - len(theme),
        "unknown_blind_codes": len({r["code"] for r in unknown} - {r["code"] for r in theme}),
        # 与 unknown_theme_* 同值，保留用户口径的名字
        "skipped_by_design": len(theme),
    }


def format_table(report: dict) -> str:
    """把 mismatch 列表排成表格（无错配时给一句结论）。"""
    lines = []
    mism = report["mismatches"]
    c = report["counts"]
    if not mism:
        lines.append(
            f"✅ 未发现语义错配：扫描 {c['rows']} 条目 / {c['codes']} 只，"
            f"其中 unknown {c['unknown_rows']} 条目 / {c['unknown_codes']} 只待人工复核"
            f"（主题板块设计性排除 {c['unknown_theme_rows']}，关键词盲区 {c['unknown_blind_rows']}）"
        )
        lines.append("提示：「0 错配」只覆盖可判定部分，关键词盲区仍是人工复核责任。")
        return "\n".join(lines)
    lines.append(
        f"❌ 发现 {c['mismatch_rows']} 条语义错配（{c['mismatch_codes']} 只），"
        f"扫描 {c['rows']} 条目 / {c['codes']} 只"
    )
    lines.append("")
    lines.append("| 代码 | 名称 | 所在板块 | 建议归属 | 近似规则 |")
    lines.append("|---|---|---|---|---|")
    for r in mism:
        lines.append(
            f"| {r['code']} | {r['name'] or '（无名称）'} | {r['sector']} | "
            f"{r['detail']} | {'是' if r['approximate'] else '否'} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="板块归属语义校验（现取腾讯行情名称）")
    parser.add_argument("--sectors", help="只扫指定板块，逗号分隔")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-fail", action="store_true", help="有错配也 exit 0")
    parser.add_argument("--pools", help="板块池文件路径（默认 scripts/data/sector_stocks.json）")
    parser.add_argument("--map", dest="map_path", help="映射表文件路径（默认 scripts/data/stock_sector_map.json）")
    args = parser.parse_args(argv)

    pools = load_pools(Path(args.pools) if args.pools else None)
    mapping = load_sector_map(Path(args.map_path) if args.map_path else None)
    sectors = [s.strip() for s in args.sectors.split(",")] if args.sectors else None

    codes = sorted({c for sec, lst in pools.items() if not sectors or sec in sectors for c in lst})
    names = fetch_names(codes)
    missing = [c for c in codes if c not in names]
    if missing:
        print(f"⚠️ {len(missing)} 只未取到名称（不判错，列入 unknown）: {missing[:5]}",
              file=sys.stderr)

    report = build_report(pools, mapping, names, sectors)

    if args.json:
        print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                         ensure_ascii=False, indent=2))
    else:
        print(f"数据源: 腾讯行情 qt.gtimg.cn（{len(names)}/{len(codes)} 只已核名）")
        print(format_table(report))

    if report["mismatches"] and not args.no_fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

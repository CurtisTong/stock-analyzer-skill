"""`scripts/dev/verify_sector_names.py` 的离线单测。

工具本身要发网络请求（腾讯行情取名称），这里只测**判定逻辑**：
把「代码 → 名称」直接喂进去，不触网，保证 CI 的 `not network` 也能跑。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dev import verify_sector_names as vsn

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "scripts" / "data"


def _fake_tencent_line(code: str, name: str) -> str:
    """拼一行腾讯行情（`parse_tencent_line` 要求至少 50 段）。"""
    parts = ["0"] * 60
    parts[1] = name
    parts[2] = code[2:]
    return f'v_{code}="{"~".join(parts)}";'


# ---------- classify：核心板块强规则 ----------


@pytest.mark.parametrize(
    ("name", "sector", "expected"),
    [
        ("中国神华", "资源", "ok"),
        ("陕西煤业", "资源", "ok"),
        ("东方财富", "资源", "mismatch"),  # 券商挂到资源
        ("大北农", "资源", "mismatch"),  # 农业挂到资源
        ("赣锋锂业", "光伏", "mismatch"),  # 锂电挂到光伏
        ("隆基绿能", "光伏", "ok"),
        ("亿纬锂能", "电力", "mismatch"),  # 锂电挂到电力
        ("长江电力", "电力", "ok"),
        ("宁德时代", "新能源", "ok"),
        ("时代出版", "机器人", "mismatch"),  # 出版挂到机器人
        ("济川药业", "机器人", "mismatch"),  # 医药挂到机器人
    ],
)
def test_classify_core_sectors(name, sector, expected):
    verdict, _ = vsn.classify(name, sector)
    assert verdict == expected


def test_classify_missing_name_is_unknown_not_error():
    """取不到名称时只能判 unknown，不能当错配（否则网络抖动会变成假红）。"""
    verdict, detail = vsn.classify("", "电力")
    assert verdict == "unknown"
    assert "名称" in detail


def test_classify_uncovered_name_is_unknown():
    """关键词覆盖不到时判 unknown，交人工复核，不制造假阳性。"""
    verdict, _ = vsn.classify("某只没听过的公司", "资源")
    assert verdict == "unknown"


def test_theme_sector_is_never_judged():
    """主题板块（高股息 / PCB/AI算力）成员来自其他板块，不做行业归属判定。"""
    verdict, detail = vsn.classify("中国神华", "高股息")
    assert verdict == "unknown"
    assert "主题" in detail


# ---------- build_report：映射表优先 + 违规归集 ----------


def test_build_report_flags_mismatch_and_mapping_conflict():
    pools = {"资源": ["sz300059", "sh601088"], "电力": ["sh600900"], "金融": ["sh601398"]}
    mapping = {"sz300059": "资源", "sh601088": "电力"}  # 神华的映射指向池内另一行业 → 冲突
    names = {"sz300059": "东方财富", "sh601088": "中国神华", "sh600900": "长江电力",
             "sh601398": "工商银行"}

    report = vsn.build_report(pools, mapping, names)

    assert report["scanned"] == 4
    flagged = {r["code"]: r["detail"] for r in report["mismatches"]}
    assert "sz300059" in flagged  # 券商挂资源
    assert "sh601088" in flagged  # 池子说资源、映射说电力（两个池内行业板块）
    assert "sh600900" not in flagged


@pytest.mark.parametrize(
    ("mapped", "why"),
    [("化工", "映射比池子更细，不在池内"), ("高股息", "主题板块"), ("新能源车", "新能源的粗细写法")],
)
def test_mapping_conflict_exemptions(mapped, why):
    """映射表更细的口径 / 主题板块 / 新能源别名都不算冲突。"""
    assert vsn._mapping_conflicts("新能源", mapped, {"新能源": [], "光伏": []}) is (mapped == "光伏")


def test_build_report_allows_new_energy_alias():
    """「新能源」与非细分的「新能源车」是同一块的粗细写法，不算冲突。"""
    pools = {"新能源": ["sz300750"]}
    mapping = {"sz300750": "新能源车"}
    names = {"sz300750": "宁德时代"}

    report = vsn.build_report(pools, mapping, names)

    assert report["mismatches"] == []


def test_build_report_marks_approximate_sectors():
    """非核心板块标 approximate——提示结论来自关键词近似。"""
    pools = {"机器人": ["sh600588"]}
    report = vsn.build_report(pools, {}, {"sh600588": "用友网络"})

    assert report["rows"][0]["approximate"] is True
    assert report["mismatches"], "用友网络（软件 ERP）挂机器人应判错配"


def test_every_pool_sector_has_a_rule():
    """板块池里每个非主题板块都必须有判定规则，否则新增板块会静默漏检。"""
    with open(_DATA_DIR / "sector_stocks.json", encoding="utf-8") as f:
        data = json.load(f)
    sectors = {k for k in data if not k.startswith("_")}
    missing = sectors - set(vsn._SECTOR_RULES) - vsn._THEME_SECTORS
    assert not missing, f"以下板块缺判定规则: {sorted(missing)}"


# ---------- fetch_names：批量取名的代码映射 ----------


def test_fetch_names_maps_prefixed_code(monkeypatch):
    """腾讯返回的 code 段是 6 位数字，必须按 `v_shXXXXXX=` 前缀还原带市场前缀的代码。"""
    line = _fake_tencent_line("sh601857", "中国石油")

    monkeypatch.setattr(vsn, "http_get", lambda *a, **k: line.encode("gbk"))
    monkeypatch.setattr(vsn, "decode_gbk", lambda raw: raw.decode("gbk"))

    names = vsn.fetch_names(["sh601857"])

    assert names == {"sh601857": "中国石油"}


def test_fetch_names_survives_network_error(monkeypatch):
    """网络失败只丢名称，不抛异常（报告里体现为 unknown）。"""

    def _boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(vsn, "http_get", _boom)
    assert vsn.fetch_names(["sh601857"]) == {}


# ---------- 豁免清单强制带理由与日期（防腐） ----------

@pytest.mark.parametrize("name", sorted(vsn._NAME_HINTS))
def test_name_hints_have_reason_and_date(name):
    """豁免条目必须写清理由和加入日期，缺字段直接挂——这类清单最容易被悄悄腐蚀。"""
    entry = vsn._NAME_HINTS[name]
    assert entry.get("sector"), f"{name} 缺 sector"
    assert entry.get("reason"), f"{name} 缺 reason"
    assert entry.get("added"), f"{name} 缺 added"


@pytest.mark.parametrize("key", sorted(vsn._SECTOR_EXCEPTIONS))
def test_sector_exceptions_have_reason_and_date(key):
    entry = vsn._SECTOR_EXCEPTIONS[key]
    assert entry.get("reason"), f"{key} 缺 reason"
    assert entry.get("added"), f"{key} 缺 added"


def test_name_hint_counts_as_ok_in_its_sector():
    """显式豁免的标的在应属板块里判 ok，在别的板块里仍判 mismatch。"""
    assert vsn.classify("温氏股份", "消费")[0] == "ok"
    assert vsn.classify("温氏股份", "资源")[0] == "mismatch"


# ---------- 计数口径：条目 vs 唯一代码 vs 设计性排除 ----------


def test_counts_report_both_scopes():
    """同一只票可属两个板块，条目数与唯一代码数必须分开报。"""
    pools = {
        "资源": ["sh601088", "sz300059"],
        "电力": ["sh601088", "sh600900"],
        "高股息": ["sh601088"],
    }
    names = {"sh601088": "中国神华", "sz300059": "东方财富", "sh600900": "长江电力"}

    counts = vsn.build_report(pools, {}, names)["counts"]

    assert counts["rows"] == 5
    assert counts["codes"] == 3
    assert counts["skipped_by_design"] == 1  # 高股息是主题板块，设计性排除
    assert counts["unknown_theme_rows"] == 1


def test_counts_mismatch_in_both_scopes():
    pools = {"光伏": ["sz002460"], "电力": ["sz002460"]}
    names = {"sz002460": "赣锋锂业"}

    counts = vsn.build_report(pools, {}, names)["counts"]

    assert counts["mismatch_rows"] == 2  # 锂电在 光伏 与 电力 各错一次
    assert counts["mismatch_codes"] == 1


# ---------- ST / 退市：名称即证据，直接判错配 ----------


@pytest.mark.parametrize("name", ["网力退", "退市明科", "*ST闻泰", "ST人福"])
def test_classify_flags_st_and_delisted(name):
    """ST / 退市标的在任何板块都判 mismatch（与 data.pool.is_st 同口径）。"""
    verdict, detail = vsn.classify(name, "机器人")
    assert verdict == "mismatch"
    assert "ST" in detail or "退市" in detail

"""板块股票池数据完整性合约（sector_stocks*.json）。

**背景**：`scripts/data/sector_stocks.default.json` 自初版提交 `cf8ee13` 起就是坏的——
「新能源」与「光伏」两个板块的成分股列表**完全相同**（光伏块是整块复制），
光伏块里还混进地产（保利发展 sh600048）、客车（宇通客车 sh600066）、
医药（同仁堂 sh600085)等明显错配标的，「电力」块混进锂电（亿纬锂能 sz300014）
与光伏逆变器（阳光电源 sz300274），`sh600089` 在新能源/光伏两块里各出现两次。

根因不是 fetcher 逻辑，而是**手写预置数据 + 全链路零校验**：
`load_default_pool()` → `init_from_default()` → `atomic_write_json()` 全程原样拷贝，
坏数据因此被写进运行期的 `sector_stocks.json`，并进一步污染
`stock_sector_map.json`（2026-08-12 生成，`sh600085` 同仁堂被标成「光伏」）。

影响面：`--sector 电力/新能源/光伏` 的筛选结果会带错票，且错票会被下游
板块 ETF 归属、持仓相关性判断继续放大。

**本文件的定位**：结构性断言（抓未来所有同类脏数据）+ 本次回归用例（防修完又回来）。
断言只读仓库内的静态数据文件，不访问网络。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "scripts" / "data"

# 运行期池（init_pool.py 生成）与预置 fallback 池（离线兜底）都必须干净
_POOL_FILES = {
    "default": _DATA_DIR / "sector_stocks.default.json",
    "runtime": _DATA_DIR / "sector_stocks.json",
}

# 主题板块：成员由其他板块筛出或天然跨板块，允许与其他板块大面积重叠
# - 高股息：build_dividend_pool() 从其他板块里按 PE<20/ROE>8% 再筛
# - PCB/AI算力：主题成分与「科技」高度重合（历史设计如此）
_THEME_SECTORS = {"高股息", "PCB/AI算力"}

# 单个代码最多可落在几个「行业」板块里（不含主题板块）
_MAX_INDUSTRY_SECTORS = 2

_CODE_PATTERN = re.compile(r"^(sh|sz)\d{6}$")


def _load_pool(path: Path) -> dict:
    assert path.exists(), f"板块池文件缺失: {path}"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _sectors_of(data: dict) -> dict[str, list[str]]:
    """只取板块键（排除 `_meta` 等下划线键）。"""
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _pool_file_id(name: str) -> str:
    return name


@pytest.fixture(params=sorted(_POOL_FILES))
def pool(request):
    """参数化到两份池文件：default / runtime。"""
    name = request.param
    return name, _load_pool(_POOL_FILES[name])


# ---------- 结构性断言（防未来同类脏数据） ----------


def test_no_duplicate_code_within_sector(pool):
    """同一板块内不得出现重复代码。

    回归：`sh600089`（特变电工）曾在「新能源」「光伏」两块里各出现两次。
    """
    name, data = pool
    offenders = {}
    for sector, codes in _sectors_of(data).items():
        seen, dup = set(), []
        for code in codes:
            if code in seen:
                dup.append(code)
            seen.add(code)
        if dup:
            offenders[sector] = sorted(set(dup))
    assert not offenders, f"[{name}] 板块内重复代码: {offenders}"


def test_sectors_are_not_identical(pool):
    """任意两个板块的成分股列表不得完全相同。

    回归：初版起「新能源」与「光伏」完全相同（`新能源 == 光伏` 为 True），
    说明其中一块是复制粘贴而非独立数据。
    """
    name, data = pool
    sectors = _sectors_of(data)
    names = sorted(sectors)
    collisions = []
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            if sectors[left] == sectors[right]:
                collisions.append((left, right))
    assert not collisions, f"[{name}] 板块成分股列表完全相同（疑似复制粘贴）: {collisions}"


def test_code_appears_in_at_most_two_industry_sectors(pool):
    """同一代码最多出现在 2 个「行业」板块（主题板块不计）。

    回归：`sh600085` 同仁堂曾在 医药/新能源/光伏 三个板块同时挂名，
    `sz002460` 赣锋锂业、`sz002245` 在 资源/新能源/光伏 三个板块同时挂名。
    """
    name, data = pool
    membership: dict[str, set[str]] = {}
    for sector, codes in _sectors_of(data).items():
        if sector in _THEME_SECTORS:
            continue
        for code in codes:
            membership.setdefault(code, set()).add(sector)

    offenders = {
        code: sorted(secs)
        for code, secs in membership.items()
        if len(secs) > _MAX_INDUSTRY_SECTORS
    }
    assert not offenders, (
        f"[{name}] 以下代码在 >{_MAX_INDUSTRY_SECTORS} 个行业板块重复挂名: {offenders}"
    )


def test_meta_counts_match_actual(pool):
    """`_meta.total_stocks` / `total_sectors` 必须与实际内容一致。

    回归：`sector_stocks.default.json` 的 `_meta.total_stocks` 曾写 280，
    实际 285（PCB 板块被扩到 25 只 + 两处重复代码）。
    """
    name, data = pool
    expected_sectors = len(_sectors_of(data))
    expected_stocks = sum(len(v) for v in _sectors_of(data).values())

    meta = data.get("_meta")
    assert isinstance(meta, dict), f"[{name}] 缺少 _meta"

    assert meta.get("total_sectors") == expected_sectors, (
        f"[{name}] _meta.total_sectors={meta.get('total_sectors')}，实际 {expected_sectors}"
    )
    assert meta.get("total_stocks") == expected_stocks, (
        f"[{name}] _meta.total_stocks={meta.get('total_stocks')}，实际 {expected_stocks}"
    )


def test_all_codes_are_well_formed(pool):
    """所有代码必须是 `sh`/`sz` + 6 位数字。"""
    name, data = pool
    bad = [
        (sector, code)
        for sector, codes in _sectors_of(data).items()
        for code in codes
        if not _CODE_PATTERN.match(str(code))
    ]
    assert not bad, f"[{name}] 非法代码格式: {bad[:10]}"


# ---------- 本次回归用例（锁死已修复的错配） ----------


def test_power_sector_excludes_battery_and_inverter():
    """「电力」板块不得含锂电 / 光伏逆变器标的（属新能源、光伏，不属电力运营）。

    回归：`sz300014` 亿纬锂能、`sz300274` 阳光电源曾在电力池里，
    导致按 `--sector 电力` 选股时把锂电和光伏串进电力名单。
    """
    data = _load_pool(_POOL_FILES["default"])
    power = set(_sectors_of(data).get("电力", []))
    assert power, "「电力」板块不应为空"
    for code in ("sz300014", "sz300274"):
        assert code not in power, f"「电力」板块仍含错配标的 {code}"


def test_photovoltaic_sector_excludes_non_pv_industries():
    """「光伏」板块不得含地产 / 客车 / 医药 / 整车标的。

    回归：光伏块曾混入保利发展 sh600048（地产）、宇通客车 sh600066（客车）、
    同仁堂 sh600085（医药）、比亚迪 sz002594（整车制造，属新能源车）。
    """
    data = _load_pool(_POOL_FILES["default"])
    pv = set(_sectors_of(data).get("光伏", []))
    assert pv, "「光伏」板块不应为空"
    for code in ("sh600048", "sh600066", "sh600085", "sz002594"):
        assert code not in pv, f"「光伏」板块仍含非光伏标的 {code}"


def test_photovoltaic_and_new_energy_are_distinct():
    """光伏 ≠ 新能源：两者是不同 BK（BK0588 光伏概念 / BK0900 新能源车）。"""
    data = _load_pool(_POOL_FILES["default"])
    sectors = _sectors_of(data)
    assert "光伏" in sectors and "新能源" in sectors
    assert sectors["光伏"] != sectors["新能源"], "「光伏」与「新能源」成分股完全相同"


# ---------- 映射表一致性（stock_sector_map.json 优先于板块池，脏了会盖掉干净池） ----------

_SECTOR_MAP_FILE = _DATA_DIR / "stock_sector_map.json"

# 映射表是「细粒度覆盖表」：允许比板块池更细的名称（如 新能源 → 新能源车、
# 电力运营 → 高股息）。这里只对本次重建的三块断言，不限制其余板块的细粒度写法。
_REBUILT_SECTORS = ("电力", "光伏", "新能源")
_REBUILT_ALIASES = {"新能源": {"新能源车"}}


def _load_sector_map() -> dict:
    assert _SECTOR_MAP_FILE.exists(), f"映射表缺失: {_SECTOR_MAP_FILE}"
    with open(_SECTOR_MAP_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_sector_map_covers_all_pool_codes():
    """板块池里的每个代码都必须在映射表里有条目。

    映射表 `_meta.purpose` 写明「优先于 sector_stocks.json」，没有条目的代码
    会静默回退到池子推断——设计意图是全量覆盖，缺条目会让排查绕远路。
    回归：本次重建前 电力 5 只 / 光伏 16 只 / 新能源 11 只 共 32 只缺条目。
    """
    mapping = _load_sector_map()["stocks"]
    data = _load_pool(_POOL_FILES["runtime"])
    missing = {
        sector: sorted(set(codes) - set(mapping))
        for sector, codes in _sectors_of(data).items()
        if set(codes) - set(mapping)
    }
    assert not missing, f"映射表缺条目: {missing}"


def test_rebuilt_sectors_map_matches_pool():
    """重建的三块：映射表归属必须与板块池一致（允许细粒度别名与主题板块）。"""
    mapping = _load_sector_map()["stocks"]
    data = _load_pool(_POOL_FILES["runtime"])
    sectors = _sectors_of(data)
    offenders = []
    for sector in _REBUILT_SECTORS:
        allow = {sector} | _REBUILT_ALIASES.get(sector, set()) | _THEME_SECTORS
        for code in sectors.get(sector, []):
            mapped = mapping.get(code)
            if mapped is not None and mapped not in allow:
                offenders.append((sector, code, mapped))
    assert not offenders, f"映射表与板块池归属冲突: {offenders}"


def test_sector_map_does_not_label_lithium_as_pv():
    """锂电链不得在映射表里标成「光伏」。

    回归：`sz002460` 赣锋锂业、`sz002245` 蔚蓝锂芯在映射表里曾是「光伏」，
    而映射表优先于板块池——池子改对了，运行时仍会被归成光伏。
    """
    mapping = _load_sector_map()["stocks"]
    for code in ("sz002460", "sz002245"):
        assert mapping.get(code) != "光伏", f"{code} 在映射表里仍被标为「光伏」"

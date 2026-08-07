"""字段映射与解析：腾讯/新浪/东财数据格式解析。"""

import logging
import re

logger = logging.getLogger(__name__)

# ---------- 名称乱码修复（P2-26 修复：腾讯接口部分股票名 GBK 字节
# 被 decode_gbk 当 UTF-8 静默接受，输出 'ǢǢʳƷ' 形式乱码）----------

# GBK 双字节字符的典型"乱码"模式：UTF-8 视角下，GBK 字节落在 CJK 扩展
# 区后会产生带重音的拉丁字母（Ǣ ǣ ʳ Ʒ 等）。这是腾讯部分股票名称的常见乱码特征。
_GARBLED_NAME_RE = re.compile(r"[ǢǣʳƷˊˋˍ˙̛̖̗̘̙̜̝̞̟̠̣̤̥̦̩̪̫̬̭̮̯̰̱̲̳̹̺̻̼͎̀́̂̃̄̅̆̇̈̉̊̋̌̍̎̏̐̑̒̓̔̽̾̿̀́͂̂̃̄̅̆̇̈̉͊͋͌̍̕̚͏͓͔͕͖͙͚͐͑͒͗͛͘͜͟͢͝͞͠͡҉ͣͤͥͦͧͨͩͪͫͬͭͮͯ҈҉]+")

# 合法中文字符的 Unicode 范围（用于 sanity check）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _looks_garbled(name: str) -> bool:
    """检测名称是否呈现腾讯 GBK→UTF-8 静默替换的典型乱码。

    判定条件（任一满足即可）：
    1. 含 `_GARBLED_NAME_RE` 中定义的典型乱码字符。
    2. 完全不含中文，但含非 ASCII 的拉丁扩展字符（怀疑编码错位）。
    """
    if not name:
        return False
    if _GARBLED_NAME_RE.search(name):
        return True
    has_cjk = bool(_CJK_RE.search(name))
    has_non_ascii = any(ord(c) > 127 for c in name)
    if not has_cjk and has_non_ascii:
        return True
    return False


def repair_tencent_name(name: str) -> str:
    """修复腾讯行情中因编码错位产生的乱码股票名。

    现象：腾讯接口部分股票名（如 sz002557 洽洽食品）返回 GBK 字节，
    上层 decode_gbk 因 UTF-8 解码不抛异常而误判为合法 UTF-8，
    结果输出 'ǢǢʳƷ'。

    修复策略：将乱码字符串回退为 GBK 字节后再以 GBK 解码，
    验证是否包含中文；包含则采用，否则保留原值。
    """
    if not name or not _looks_garbled(name):
        return name
    try:
        # 假设字符串实际是 GBK 字节被当 UTF-8 解释的结果。
        # 反向操作：UTF-8 编码 → GBK 解码。
        fixed = name.encode("utf-8", errors="strict").decode("gbk", errors="strict")
        if _CJK_RE.search(fixed):
            logger.debug("修复乱码名称: %r → %r", name, fixed)
            return fixed
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    # 兜底：errors='replace'，至少替换乱码字符而不是静默展示
    try:
        fixed = name.encode("utf-8", errors="replace").decode("gbk", errors="replace")
        if fixed and fixed != name:
            logger.debug("部分修复乱码名称: %r → %r", name, fixed)
            return fixed
    except Exception:
        pass
    return name


# ---------- 腾讯行情字段映射 ----------

# 字段位（按 ~ 分隔，0-based 索引，已剥除 v_sh600989=" 前缀）
# 方法论文档的 1-based 编号 - 1 = 本表 0-based
TENCENT_FIELDS = {
    "market": 0,  # 市场代码
    "name": 1,  # 名称
    "code": 2,  # 股票代码
    "price": 3,  # 当前价
    "prev_close": 4,  # 昨收
    "open": 5,  # 今开
    "change_amt": 31,  # 涨跌额
    "change_pct": 32,  # 涨跌幅%
    "high": 33,  # 最高
    "low": 34,  # 最低
    "volume": 36,  # 成交量(手)
    "amount": 37,  # 成交额(万)
    "turnover": 38,  # 换手率%
    "pe": 39,  # PE(动)
    "amplitude": 43,  # 振幅%
    "total_cap": 44,  # 总市值(亿) -> parse_tencent_line 转"元"
    "circulating_cap": 45,  # 流通市值(亿) -> parse_tencent_line 转"元"
    "pb": 46,  # PB
    "limit_up": 47,  # 涨停价
    "limit_down": 48,  # 跌停价
}


def _yi_to_yuan(raw: str) -> str:
    """将腾讯行情的"亿"单位字段转换为"元"（×1e8）。

    P1-4: 统一所有 quote fetcher 返回原始"元"值，归一化收口到 data 层
    _normalize_cap。腾讯字段44/45 原单位为"亿"，此处乘以 1e8 转换。
    解析失败（空/非数值）时原样返回，避免吞异常。
    """
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return raw
    # round 到整元（×1e8 后小数位无意义），避免浮点尾部长串
    return str(round(v * 1e8))


def parse_tencent_line(line: str) -> dict[str, str]:
    """解析单行腾讯行情（v_sh600989="..." 形式）。"""
    if "=" not in line or '"' not in line:
        return {}
    payload = line.split('"', 1)[1].rstrip('";\n')
    parts = payload.split("~")
    if len(parts) < 50:
        return {}
    return {
        "code": parts[TENCENT_FIELDS["code"]],
        "name": repair_tencent_name(parts[TENCENT_FIELDS["name"]]),
        "price": parts[TENCENT_FIELDS["price"]],
        "prev_close": parts[TENCENT_FIELDS["prev_close"]],
        "open": parts[TENCENT_FIELDS["open"]],
        "change_pct": parts[TENCENT_FIELDS["change_pct"]],
        "change_amt": parts[TENCENT_FIELDS["change_amt"]],
        "high": parts[TENCENT_FIELDS["high"]],
        "low": parts[TENCENT_FIELDS["low"]],
        "volume": parts[TENCENT_FIELDS["volume"]],
        "amount": parts[TENCENT_FIELDS["amount"]],
        "turnover": parts[TENCENT_FIELDS["turnover"]],
        "pe": parts[TENCENT_FIELDS["pe"]],
        "pe_type": "dynamic",  # 字段39 为 PE(动)
        "pb": parts[TENCENT_FIELDS["pb"]],
        # 字段44/45 原单位为"亿"，P1-4 统一所有 fetcher 返回原始"元"，
        # 故 ×1e8 转换；归一化在 data 层 _normalize_cap 统一 /1e8。
        "total_cap": _yi_to_yuan(parts[TENCENT_FIELDS["total_cap"]]),
        "circulating_cap": _yi_to_yuan(parts[TENCENT_FIELDS["circulating_cap"]]),
    }


# ---------- 新浪行情字段映射 ----------

SINA_QUOTE_URL = "https://hq.sinajs.cn/list={codes}"


def parse_sina_quote_line(line: str) -> dict[str, str]:
    """解析新浪行情单行: var hq_str_sh600989="名称,今开,昨收,当前价,最高,最低,...";"""
    if '="' not in line:
        return {}
    var_part, data_part = line.split('="', 1)
    code = var_part.split("_")[-1]  # sh600989
    fields = data_part.rstrip('";\n').split(",")
    if len(fields) < 32:
        return {}
    try:
        prev = float(fields[2])
        curr = float(fields[3])
        change_pct = str(round((curr / prev - 1) * 100, 2)) if prev > 0 else "0"
        change_amt = str(round(curr - prev, 2)) if prev > 0 else "0"
    except (ValueError, IndexError):
        change_pct = "0"
        change_amt = "0"

    return {
        "code": code,
        "name": repair_tencent_name(fields[0]),
        "open": fields[1],
        "prev_close": fields[2],
        "price": fields[3],
        "high": fields[4],
        "low": fields[5],
        "volume": fields[8],  # 成交量(股)
        "amount": fields[9],  # 成交额
        "change_pct": change_pct,
        "change_amt": change_amt,
        "turnover": "",  # 新浪不直接提供换手率
        "pe": "",  # 新浪不直接提供 PE
        "pb": "",  # 新浪不直接提供 PB
        "total_cap": "",  # 新浪不直接提供总市值
        "circulating_cap": "",
    }


# ---------- 东财财务字段 ----------

EAST_MONEY_FIELDS = {
    "EPSJB": "每股收益",
    "ROEJQ": "ROE(加权)%",
    "TOTALOPERATEREVETZ": "营收同比%",
    "PARENTNETPROFITTZ": "净利同比%",
    "XSMLL": "毛利率%",
    "XSJLL": "净利率%",
    "ZCFZL": "负债率%",
    "BPS": "每股净资产",
    "MGJYXJJE": "每股经营现金流",
    "XSGJ": "销售净利率%",
    "YSHZ": "营收环比%",
    "SJLTZ": "净利润环比%",
}


__all__ = [
    "TENCENT_FIELDS",
    "parse_tencent_line",
    "SINA_QUOTE_URL",
    "parse_sina_quote_line",
    "EAST_MONEY_FIELDS",
]

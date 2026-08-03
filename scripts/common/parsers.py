"""字段映射与解析：腾讯/新浪/东财数据格式解析。"""

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
        "name": parts[TENCENT_FIELDS["name"]],
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
        "name": fields[0],
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

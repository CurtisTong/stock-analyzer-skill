#!/usr/bin/env python3
"""
公共工具：编码转换、HTTP 请求、字段映射、ETF 代码表。
被 quote.py / finance.py / kline.py / announcements.py 复用。
"""
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"

# ---------- HTTP ----------

def http_get(url: str, timeout: int = 10) -> bytes:
    """GET 请求，5xx 重试一次。"""
    req = urllib.request.Request(url, headers={"User-Agent": "stock-analyzer-skill/1.0"})
    last_err = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
    raise RuntimeError(f"GET {url} 失败: {last_err}")

# ---------- 编码 ----------

def decode_gbk(data: bytes) -> str:
    """腾讯接口 GBK → UTF-8。"""
    return data.decode("gbk", errors="replace")

# ---------- 腾讯行情字段映射 ----------

# 字段位（按 ~ 分隔，0-based 索引，已剥除 v_sh600989=" 前缀）
# 方法论文档的 1-based 编号 - 1 = 本表 0-based
TENCENT_FIELDS = {
    "market": 0,            # 市场代码
    "name": 1,              # 名称
    "code": 2,              # 股票代码
    "price": 3,             # 当前价
    "prev_close": 4,        # 昨收
    "open": 5,              # 今开
    "change_amt": 31,       # 涨跌额
    "change_pct": 32,       # 涨跌幅%
    "high": 33,             # 最高
    "low": 34,              # 最低
    "volume": 36,           # 成交量(手)
    "amount": 37,           # 成交额(万)
    "turnover": 38,         # 换手率%
    "pe": 39,               # PE(动)
    "amplitude": 43,        # 振幅%
    "total_cap": 44,        # 总市值(亿)
    "circulating_cap": 45,  # 流通市值(亿)
    "pb": 46,               # PB
    "limit_up": 47,         # 涨停价
    "limit_down": 48,       # 跌停价
}

def parse_tencent_line(line: str) -> dict:
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
        "pb": parts[TENCENT_FIELDS["pb"]],
        "total_cap": parts[TENCENT_FIELDS["total_cap"]],
        "circulating_cap": parts[TENCENT_FIELDS["circulating_cap"]],
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

# ---------- 工具 ----------

def split_codes(arg: str) -> list:
    """支持逗号分隔或文件路径（@file）。"""
    if arg.startswith("@"):
        return [line.strip() for line in Path(arg[1:]).read_text().splitlines() if line.strip()]
    return [c.strip() for c in arg.split(",") if c.strip()]

def batchify(items: list, size: int = 15):
    """将列表按 size 分批。腾讯单次 ≤15。"""
    for i in range(0, len(items), size):
        yield items[i:i + size]

def err(msg: str):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

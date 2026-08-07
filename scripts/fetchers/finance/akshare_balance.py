"""akshare 资产负债表 fetcher（存货绝对额补充数据源）。

东财主源 ZYZBAjaxNew 返回主要指标（含 CHZZL/CHZZTS 存货周转率），
但不返回存货绝对额 INVENTORY。本 fetcher 调 akshare 资产负债表接口
获取 INVENTORY 等绝对额，作为主源的补充。

设计：不作为标准 fallback（东财不返回 INVENTORY 无法 fallback），
而是作为 enricher：data 层在主源返回后调用本模块合并存货数据。

依赖: akshare (可选)
"""

import logging

logger = logging.getLogger(__name__)

try:
    import akshare as ak

    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None  # 显式置 None，便于测试 monkeypatch 模块属性


def enrich_with_balance_sheet(records, code, periods=4):
    """用 akshare 资产负债表数据增强财务记录（补充存货绝对额）。

    Args:
        records: 主源返回的 list[dict]（东财 ZYZBAjaxNew 每期记录）
        code: 股票代码（带 sh/sz 前缀）
        periods: 需要增强的期数

    Returns:
        list[dict]: 增强后的 records（每条 dict 合并了 INVENTORY 字段）。
        akshare 不可用或失败时原样返回 records（降级不阻断）。
    """
    if not HAS_AKSHARE or not records:
        return records

    try:
        # akshare 资产负债表接口需要带 SH/SZ 大写前缀
        symbol = _normalize_symbol(code)
        df = ak.stock_balance_sheet_by_report_em(symbol=symbol)
        if df is None or df.empty:
            return records

        # 构建 REPORT_DATE -> INVENTORY 映射
        inventory_map = {}
        if "REPORT_DATE" in df.columns and "INVENTORY" in df.columns:
            for _, row in df.head(periods * 2).iterrows():
                rd = str(row.get("REPORT_DATE", ""))[:10]
                inv = row.get("INVENTORY")
                if rd and inv is not None:
                    inventory_map[rd] = inv

        if not inventory_map:
            return records

        # 合并到主源 records
        for rec in records:
            rd = str(rec.get("REPORT_DATE", rec.get("report_date", "")))[:10]
            if rd in inventory_map:
                rec["INVENTORY"] = inventory_map[rd]

        return records
    except Exception as e:
        logger.warning("akshare 资产负债表增强失败 %s: %s", code, e)
        return records  # 失败原样返回，不阻断主流程


def _normalize_symbol(code):
    """归一化为 akshare 资产负债表接口所需的大写带前缀格式。

    akshare stock_balance_sheet_by_report_em 需要 'SH603501' 格式，
    不接受 'sh603501' 或裸代码 '603501'。

    00 开头数字段沪深二义（上证指数 000xxx 与深市主板 000xxx 重合），
    回退信任入参前缀，避免把 sh000001（上证指数）误判为深市。
    """
    if not code:
        return code
    code = code.strip()
    # 已带前缀 -> 大写化
    if code[:2].lower() in ("sh", "sz", "bj"):
        return code[:2].upper() + code[2:]
    # 裸代码 -> 推断前缀
    if code.startswith(("60", "68", "51", "56", "58")):
        return "SH" + code
    if code.startswith(("30", "15", "16", "18")):
        return "SZ" + code
    if code.startswith(("43", "83", "87", "88", "92")):
        return "BJ" + code
    # 00 开头二义段无前缀入参：默认深市（深市主板 000xxx 数量远多于上证指数）
    if code.startswith("00"):
        return "SZ" + code
    return code

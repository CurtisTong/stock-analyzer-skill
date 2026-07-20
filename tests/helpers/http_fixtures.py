"""HTTP 替身 fixtures（respx + 真实字节样本）。

提供 fetchers 测试需要的真实 HTTP 响应字节，避免依赖网络：
- 腾讯 qt.gtimg.cn 行情
- 东财 eastmoney 财务

注意：bytes 字面量只接受 ASCII，所有中文都通过 .decode() 拼装，避免 SyntaxError。

用法：
    def test_quote(respx_mock):
        respx_mock.get("qt.gtimg.cn").respond(
            200, content=TENCENT_QUOTE_BYTES_600519
        )
        ...
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# 腾讯 qt.gtimg.cn 行情（归一化前：volume=手、amount=万元）
# ═══════════════════════════════════════════════════════════════


def _build_tencent_quote(name: str) -> bytes:
    """构建腾讯行情返回字节（ASCII-safe 构造）。"""
    prefix = b'v_sh600519="1~'
    name_bytes = name.encode("utf-8")
    tail = (
        b"~600519~1800.00~1790.00~1795.00~12345~2234567"
        b"~1810.00~1790.00~0.56~10.00~0.15~25.6~8.2~22600~22600~2026-07-20"
        b"10:30:00~2026-07-20~0.000~0.000~0.000~0.000~1.36~0.15~~0.00~0.000"
        b'~0.000~~GP-A~0.000~~0.30~~37.00";'
    )
    return prefix + name_bytes + tail


TENCENT_QUOTE_BYTES_600519 = _build_tencent_quote("贵州茅台")


# ═══════════════════════════════════════════════════════════════
# 东财 eastmoney 财务（最小可解析样本）
# ═══════════════════════════════════════════════════════════════


EASTMONEY_FINANCE_BYTES_600519 = (
    b'{"data":{'
    b'"SECURITY_CODE":"600519",'
    b'"EPSJB":"50.00",'
    b'"ROEJQ":"30.5",'
    b'"TOTALOPERATEREVETZ":"15.2",'
    b'"PARENTNETPROFITTZ":"18.3",'
    b'"XSMLL":"91.5",'
    b'"XSJLL":"52.3",'
    b'"ZCFZL":"18.7",'
    b'"BPS":"180.00",'
    b'"MGJYXJJE":"55.00"'
    b"}}"
)

"""fetcher 内部符号转换函数的单元测试。

覆盖 scripts/fetchers/kline/yfinance_kline._to_yf_symbol 与
scripts/fetchers/finance/akshare_balance._normalize_symbol 的
"00 段二义回退信任入参前缀"修复（P0-1 第二轮修复）。

按 FRAMEWORK.md 规范：纯函数无 IO，用 parametrize + 显式命名。
"""

from __future__ import annotations

import pytest

from fetchers.finance.akshare_balance import _normalize_symbol
from fetchers.kline.yfinance_kline import _to_yf_symbol

# ═══════════════════════════════════════════════════════════════
# _to_yf_symbol：上交所指数保留 sh 前缀
# ═══════════════════════════════════════════════════════════════


class TestToYfSymbol:
    """yfinance 符号转换：sh000001 保留 .SS（不是 .SZ）。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            # 上交所指数：00 段二义回退信任入参前缀（修复核心场景）
            ("sh000001", "000001.SS"),
            ("sh000016", "000016.SS"),
            ("sh000300", "000300.SS"),
            ("sh000905", "000905.SS"),
            ("SH000001", "000001.SS"),  # 大写前缀同样回退
            # 深市主板：入参 sz 保留 .SZ
            ("sz000001", "000001.SZ"),
            ("sz300750", "300750.SZ"),
            # 沪市股票：无二义数字段直接定
            ("sh600519", "600519.SS"),
            ("600519", "600519.SS"),  # 无前缀
            ("688981", "688981.SS"),  # 科创板
            # 30 段无二义：始终深市（无信任入参逻辑）
            ("300750", "300750.SZ"),
            ("sh300750", "300750.SZ"),  # 入参 sh 但 30 段无二义，仍 SZ
            # 跨市场
            ("us:aapl", "aapl"),  # us 前缀直接提取符号
            ("us:^gspc", "^gspc"),
            ("hk:0700", "0700.HK"),  # 港股转 .HK
            ("hk:7000", "7000.HK"),
            ("hk:00700", "0700.HK"),  # 5 位去前导零补 4 位
        ],
    )
    def test_to_yf_symbol(self, code, expected):
        assert _to_yf_symbol(code) == expected


# ═══════════════════════════════════════════════════════════════
# _normalize_symbol：上交所指数保留 sh 前缀
# ═══════════════════════════════════════════════════════════════


class TestNormalizeSymbol:
    """akshare 符号转换：sh000001 保留 SH000001（不是 SZ000001）。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            # 上交所指数：00 段二义回退信任入参前缀
            ("sh000001", "SH000001"),
            ("sh000300", "SH000300"),
            ("sh000905", "SH000905"),
            ("SH000001", "SH000001"),  # 大写前缀同样回退
            # 深市主板：入参 sz 保留 SZ
            ("sz000001", "SZ000001"),
            ("sz300750", "SZ300750"),
            # 沪市股票：无二义数字段直接定
            ("sh600519", "SH600519"),
            ("600519", "SH600519"),
            # 30 段无二义：始终深市
            ("300750", "SZ300750"),
            # 00 段无前缀：默认深市（深市主板 000xxx 数量远多于上证指数）
            ("000001", "SZ000001"),
            ("000300", "SZ000300"),  # 中证500 也是 00 段
            # 已带前缀的统一大写
            ("sh600989", "SH600989"),
            ("sz600989", "SZ600989"),
            # 空值与无效
            ("", ""),
        ],
    )
    def test_normalize_symbol(self, code, expected):
        assert _normalize_symbol(code) == expected

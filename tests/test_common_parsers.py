"""common/parsers.py 字段映射与解析测试。"""

import pytest
from common.parsers import (
    TENCENT_FIELDS,
    parse_tencent_line,
    SINA_QUOTE_URL,
    parse_sina_quote_line,
    EAST_MONEY_FIELDS,
)


class TestTencentFields:
    """腾讯字段映射完整性。"""

    def test_required_fields(self):
        required = [
            "code",
            "name",
            "price",
            "prev_close",
            "open",
            "change_pct",
            "volume",
            "amount",
            "turnover",
        ]
        for f in required:
            assert f in TENCENT_FIELDS, f"Missing: {f}"

    def test_field_indices_unique(self):
        indices = list(TENCENT_FIELDS.values())
        assert len(indices) == len(set(indices))


class TestParseTencentLine:
    """parse_tencent_line 腾讯行情解析。"""

    def _make_line(self, code="600989", name="宝丰能源", price="18.50"):
        """构造腾讯行情模拟行。"""
        parts = [""] * 50
        parts[0] = "1"  # market
        parts[1] = name  # name
        parts[2] = code  # code
        parts[3] = price  # price
        parts[4] = "18.00"  # prev_close
        parts[5] = "18.20"  # open
        parts[31] = "0.50"  # change_amt
        parts[32] = "2.78"  # change_pct
        parts[33] = "18.60"  # high
        parts[34] = "18.10"  # low
        parts[36] = "100000"  # volume
        parts[37] = "1850000"  # amount
        parts[38] = "1.5"  # turnover
        parts[39] = "15.0"  # pe
        parts[43] = "2.7"  # amplitude
        parts[44] = "500"  # total_cap
        parts[45] = "400"  # circulating_cap
        parts[46] = "2.5"  # pb
        parts[47] = "20.35"  # limit_up
        parts[48] = "16.65"  # limit_down
        payload = "~".join(parts)
        return f'v_sh{code}="{payload}";'

    def test_valid_line(self):
        line = self._make_line()
        result = parse_tencent_line(line)
        assert result["code"] == "600989"
        assert result["name"] == "宝丰能源"
        assert result["price"] == "18.50"

    def test_missing_equals(self):
        assert parse_tencent_line("no equals sign") == {}

    def test_missing_quotes(self):
        assert parse_tencent_line("v_sh600989=no_quotes") == {}

    def test_too_few_fields(self):
        line = 'v_sh600989="a~b~c~d~e";'
        assert parse_tencent_line(line) == {}

    def test_price_field(self):
        line = self._make_line(price="25.80")
        result = parse_tencent_line(line)
        assert result["price"] == "25.80"


class TestParseSinaQuoteLine:
    """parse_sina_quote_line 新浪行情解析。"""

    def _make_line(
        self,
        name="宝丰能源",
        open_="18.20",
        prev="18.00",
        price="18.50",
        high="18.60",
        low="18.10",
    ):
        """构造新浪行情模拟行。"""
        fields = [name, open_, prev, price, high, low] + ["0"] * 26
        # fields[8] = volume, fields[9] = amount
        fields[8] = "1000000"
        fields[9] = "18500000"
        data = ",".join(fields)
        return f'var hq_str_sh600989="{data}";'

    def test_valid_line(self):
        line = self._make_line()
        result = parse_sina_quote_line(line)
        assert result["code"] == "sh600989"
        assert result["name"] == "宝丰能源"
        assert result["price"] == "18.50"

    def test_change_pct_calculation(self):
        line = self._make_line(prev="10.00", price="11.00")
        result = parse_sina_quote_line(line)
        assert result["change_pct"] == "10.0"

    def test_missing_equals(self):
        assert parse_sina_quote_line("no equals") == {}

    def test_too_few_fields(self):
        line = 'var hq_str_sh600989="a,b,c";'
        assert parse_sina_quote_line(line) == {}

    def test_volume_field(self):
        line = self._make_line()
        result = parse_sina_quote_line(line)
        assert result["volume"] == "1000000"


class TestEastMoneyFields:
    """东财财务字段映射。"""

    def test_core_fields(self):
        assert "EPSJB" in EAST_MONEY_FIELDS
        assert "ROEJQ" in EAST_MONEY_FIELDS
        assert "XSMLL" in EAST_MONEY_FIELDS
        assert "ZCFZL" in EAST_MONEY_FIELDS

    def test_field_names(self):
        assert EAST_MONEY_FIELDS["EPSJB"] == "每股收益"
        assert EAST_MONEY_FIELDS["ROEJQ"] == "ROE(加权)%"

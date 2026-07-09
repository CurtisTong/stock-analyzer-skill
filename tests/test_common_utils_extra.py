"""common/utils.py 工具函数补充测试（覆盖缺失场景）。"""

import json
import os
from unittest.mock import patch

import pytest
from common.utils import (
    plain_code,
    infer_exchange,
    normalize_quote_code,
    normalize_finance_code,
    to_secid,
    board_type,
    is_etf,
    batchify,
    to_float,
    to_int,
    clamp,
    compute_volume_ratio,
    compute_optimal_workers,
    normalize_volume,
    normalize_amount,
    board_limit_pct,
    atomic_write_json,
)


class TestPlainCode:
    def test_sh_prefix(self):
        assert plain_code("sh600519") == "600519"

    def test_sz_prefix(self):
        assert plain_code("sz000858") == "000858"

    def test_bj_prefix(self):
        assert plain_code("bj430047") == "430047"

    def test_no_prefix(self):
        assert plain_code("600519") == "600519"

    def test_uppercase(self):
        assert plain_code("SH600519") == "600519"


class TestInferExchange:
    def test_sh_60(self):
        assert infer_exchange("600519") == "sh"

    def test_sh_68(self):
        assert infer_exchange("688001") == "sh"

    def test_sz_00(self):
        assert infer_exchange("000858") == "sz"

    def test_sz_30(self):
        assert infer_exchange("300750") == "sz"

    def test_bj_43(self):
        assert infer_exchange("430047") == "bj"

    def test_already_prefixed(self):
        assert infer_exchange("sh600519") == "sh"
        assert infer_exchange("sz000858") == "sz"

    def test_etf_51(self):
        assert infer_exchange("510300") == "sh"

    def test_etf_15(self):
        assert infer_exchange("159915") == "sz"

    def test_cross_market_us(self):
        """美股代码返回空交易所前缀。"""
        assert infer_exchange("us:spy") == ""
        assert infer_exchange("us:^gspc") == ""

    def test_cross_market_hk(self):
        """港股代码返回空交易所前缀。"""
        assert infer_exchange("hk:0700") == ""
        assert infer_exchange("HK:9988") == ""


class TestNormalizeQuoteCode:
    def test_with_prefix(self):
        assert normalize_quote_code("sh600519") == "sh600519"

    def test_without_prefix(self):
        assert normalize_quote_code("600519") == "sh600519"

    def test_sz(self):
        assert normalize_quote_code("000858") == "sz000858"

    def test_cross_market_us(self):
        """美股代码原样小写返回。"""
        assert normalize_quote_code("us:spy") == "us:spy"
        assert normalize_quote_code("US:SPY") == "us:spy"
        assert normalize_quote_code("us:^gspc") == "us:^gspc"

    def test_cross_market_hk(self):
        """港股代码原样小写返回。"""
        assert normalize_quote_code("hk:0700") == "hk:0700"
        assert normalize_quote_code("HK:9988") == "hk:9988"


class TestNormalizeFinanceCode:
    def test_sh(self):
        assert normalize_finance_code("sh600519") == "SH600519"

    def test_sz(self):
        assert normalize_finance_code("sz000858") == "SZ000858"

    def test_no_prefix(self):
        result = normalize_finance_code("600519")
        assert result.startswith("SH")


class TestToSecid:
    def test_sh(self):
        assert to_secid("sh600519") == "1.600519"

    def test_sz(self):
        assert to_secid("sz000858") == "0.000858"

    def test_no_prefix_60(self):
        assert to_secid("600519") == "1.600519"

    def test_no_prefix_00(self):
        assert to_secid("000858") == "0.000858"


class TestBoardType:
    def test_main_board(self):
        assert board_type("600519") == "主板"
        assert board_type("000858") == "主板"

    def test_gem(self):
        assert board_type("300750") == "创业板"
        assert board_type("301001") == "创业板"

    def test_star(self):
        assert board_type("688001") == "科创板"

    def test_bse(self):
        assert board_type("430047") == "北交所"

    def test_etf(self):
        assert board_type("510300") == "ETF"
        assert board_type("159915") == "ETF"

    def test_other(self):
        assert board_type("999999") == "其他"


class TestIsEtf:
    def test_sh_etf(self):
        assert is_etf("510300") is True
        assert is_etf("560001") is True
        assert is_etf("580001") is True

    def test_sz_etf(self):
        assert is_etf("159915") is True
        assert is_etf("160001") is True
        assert is_etf("180001") is True

    def test_not_etf(self):
        assert is_etf("600519") is False
        assert is_etf("000858") is False


class TestBatchify:
    def test_exact_batch(self):
        assert batchify(["a", "b", "c", "d"], 2) == [["a", "b"], ["c", "d"]]

    def test_remainder(self):
        assert batchify(["a", "b", "c"], 2) == [["a", "b"], ["c"]]

    def test_single_batch(self):
        assert batchify(["a", "b"], 10) == [["a", "b"]]

    def test_empty(self):
        assert batchify([], 5) == []


class TestToFloat:
    def test_normal(self):
        assert to_float("3.14") == 3.14

    def test_none(self):
        assert to_float(None) == 0.0

    def test_empty(self):
        assert to_float("") == 0.0

    def test_dash(self):
        assert to_float("-") == 0.0

    def test_comma(self):
        assert to_float("1,234.56") == 1234.56

    def test_custom_default(self):
        assert to_float(None, default=-1.0) == -1.0

    def test_invalid(self):
        assert to_float("abc") == 0.0


class TestToInt:
    def test_normal(self):
        assert to_int("42") == 42

    def test_float_string(self):
        assert to_int("3.14") == 3

    def test_none(self):
        assert to_int(None) == 0

    def test_comma(self):
        assert to_int("1,234") == 1234


class TestClamp:
    def test_within_range(self):
        assert clamp(50, 0, 100) == 50

    def test_below_range(self):
        assert clamp(-10, 0, 100) == 0

    def test_above_range(self):
        assert clamp(150, 0, 100) == 100

    def test_default_range(self):
        assert clamp(150) == 100
        assert clamp(-10) == 0


class TestComputeVolumeRatio:
    def test_insufficient_data(self):
        assert compute_volume_ratio([1, 2, 3], 5, 10) == 1.0

    def test_equal_volumes(self):
        vols = [100] * 15
        assert compute_volume_ratio(vols, 5, 10) == 1.0

    def test_recent_higher(self):
        vols = [100] * 10 + [200] * 5
        ratio = compute_volume_ratio(vols, 5, 10)
        assert ratio > 1.0

    def test_zero_base(self):
        """基础成交量为 0 时，recent_vol / base_vol 返回 1.0。"""
        vols = [0] * 10 + [100] * 5
        # base_vol=mean([0]*5+[100]*5)=50, recent_vol=mean([100]*5)=100
        # 实际 base_vol 不为 0，比值 = 2.0
        ratio = compute_volume_ratio(vols, 5, 10)
        assert ratio == 2.0


class TestNormalizeVolume:
    def test_tencent(self):
        assert normalize_volume(100, "tencent") == 10000

    def test_eastmoney(self):
        assert normalize_volume(100, "eastmoney") == 10000

    def test_sina(self):
        assert normalize_volume(1000, "sina") == 1000

    def test_none(self):
        assert normalize_volume(None, "tencent") == 0


class TestNormalizeAmount:
    def test_tencent(self):
        assert normalize_amount(100, "tencent") == 1000000

    def test_eastmoney(self):
        assert normalize_amount(100, "eastmoney") == 100

    def test_sina(self):
        assert normalize_amount(100, "sina") == 100


class TestBoardLimitPct:
    def test_main(self):
        assert board_limit_pct("主板") == 9.5

    def test_gem(self):
        assert board_limit_pct("创业板") == 19.5

    def test_star(self):
        assert board_limit_pct("科创板") == 19.5

    def test_bse(self):
        assert board_limit_pct("北交所") == 29.5

    def test_default(self):
        assert board_limit_pct("其他") == 9.5


class TestAtomicWriteJson:
    """atomic_write_json 原子写入测试。"""

    def test_writes_correct_content(self, tmp_path):
        """写入的文件内容正确。"""
        path = tmp_path / "data.json"
        obj = {"key": "值", "num": 42, "nested": {"a": 1}}
        atomic_write_json(path, obj)
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written == obj

    def test_creates_parent_dir(self, tmp_path):
        """目标目录不存在时自动创建。"""
        path = tmp_path / "sub" / "dir" / "data.json"
        atomic_write_json(path, {"x": 1})
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == {"x": 1}

    def test_preserves_existing_file_on_failure(self, tmp_path):
        """os.replace 失败时原文件不被损坏。"""
        path = tmp_path / "data.json"
        path.write_text(json.dumps({"original": True}), encoding="utf-8")

        with patch("common.utils.os.replace", side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                atomic_write_json(path, {"new": True})

        # 原文件内容完好
        written = json.loads(path.read_text(encoding="utf-8"))
        assert written == {"original": True}

    def test_cleans_up_tempfile_on_failure(self, tmp_path):
        """写入失败时临时文件被清理。"""
        path = tmp_path / "data.json"
        before = set(tmp_path.iterdir())

        with patch("common.utils.os.replace", side_effect=OSError("fail")):
            with pytest.raises(OSError):
                atomic_write_json(path, {"new": True})

        after = set(tmp_path.iterdir())
        # 不应残留 .tmp 临时文件（原文件不存在，故 after == before）
        tmpfiles = [f for f in after if f.suffix == ".tmp"]
        assert len(tmpfiles) == 0

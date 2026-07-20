"""
scripts/common/utils.py 的单元测试。

按 FRAMEWORK.md 规范：纯函数无 IO，使用 parametrize 与显式命名。
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from common.exceptions import DataError
from common.utils import (
    atomic_write_json,
    batchify,
    board_exact_limit_pct,
    board_limit_pct,
    board_type,
    clamp,
    compute_optimal_workers,
    compute_volume_ratio,
    infer_exchange,
    is_etf,
    normalize_amount,
    normalize_finance_code,
    normalize_quote_code,
    normalize_volume,
    plain_code,
    split_codes,
    strip_prefix,
    to_float,
    to_int,
    to_secid,
)

# ═══════════════════════════════════════════════════════════════
# 代码转换
# ═══════════════════════════════════════════════════════════════


class TestPlainCode:
    """去除 sh/sz/bj 前缀，返回大写 6 位代码。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("sh600519", "600519"),
            ("SH600519", "600519"),
            ("sz000001", "000001"),
            ("bj430047", "430047"),
            ("600519", "600519"),  # 无前缀
        ],
    )
    def test_strips_prefix(self, raw, expected):
        assert plain_code(raw) == expected


class TestInferExchange:
    """按数字段推断交易所。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("600519", "sh"),  # 主板沪
            ("688981", "sh"),  # 科创板
            ("510500", "sh"),  # 上证 ETF
            ("000001", "sz"),  # 主板深
            ("300750", "sz"),  # 创业板
            ("159915", "sz"),  # 深证 ETF
            ("430047", "bj"),  # 北交所
            ("sh600519", "sh"),  # 已带前缀直接返回
            ("us:aapl", ""),  # 跨市场返回空
            ("hk:0700", ""),  # 跨市场返回空
            ("unknown", ""),  # 无法识别
        ],
    )
    def test_exchange_inference(self, code, expected):
        assert infer_exchange(code) == expected


class TestNormalizeQuoteCode:
    """归一化为腾讯/新浪用的小写前缀。"""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("600519", "sh600519"),
            ("sh600519", "sh600519"),
            ("000001", "sz000001"),
            ("430047", "bj430047"),
            ("us:aapl", "us:aapl"),  # 跨市场原样
            ("US:AAPL", "us:aapl"),  # 大写归一
            ("hk:0700", "hk:0700"),
        ],
    )
    def test_normalize(self, raw, expected):
        assert normalize_quote_code(raw) == expected


class TestNormalizeFinanceCode:
    """归一化为东财用的大写前缀。"""

    def test_a_share_uppercase(self):
        assert normalize_finance_code("sh600519") == "SH600519"
        assert normalize_finance_code("600519") == "SH600519"

    def test_cross_market_kept(self):
        """跨市场代码在 finance 层：prefix 大写，符号保留原大小写。

        实际行为：finance 层把 prefix 大写（us → US），符号部分大小写保留。
        """
        assert normalize_finance_code("us:aapl") == "US:AAPL"
        assert normalize_finance_code("us:SPY") == "US:SPY"


class TestToSecid:
    """东财 secid 格式：sh→1.x, sz/bj→0.x."""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("sh600519", "1.600519"),
            ("sz000858", "0.000858"),
            ("600519", "1.600519"),  # 无前缀按数字段推断
            ("000858", "0.000858"),
            ("688981", "1.688981"),
            ("430047", "0.430047"),  # 默认 sj 路径
        ],
    )
    def test_secid_format(self, code, expected):
        assert to_secid(code) == expected


class TestStripPrefix:
    """strip_prefix 去除连续 sh/sz/bj 前缀。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("sh600519", "600519"),
            ("SHsh600519", "600519"),  # 多次前缀
            ("bj430047", "430047"),
            ("600519", "600519"),  # 无前缀原样
        ],
    )
    def test_strip(self, code, expected):
        assert strip_prefix(code) == expected


# ═══════════════════════════════════════════════════════════════
# 板块识别
# ═══════════════════════════════════════════════════════════════


class TestBoardType:
    """粗分 A 股板块。ETF 优先于具体板块识别。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("510500", "ETF"),  # 上证 ETF
            ("159915", "ETF"),  # 深证 ETF
            ("688981", "科创板"),
            ("300750", "创业板"),
            ("301xxx"[:6].replace("x", "0"), "创业板"),
            ("430047", "北交所"),
            ("600519", "主板"),
            ("000001", "主板"),
            ("999999", "其他"),  # 未知
        ],
    )
    def test_board_classification(self, code, expected):
        assert board_type(code) == expected


class TestIsEtf:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("510500", True),
            ("563000", True),
            ("588000", True),
            ("159915", True),
            ("164906", True),
            ("184801", True),
            ("600519", False),
            ("000001", False),
        ],
    )
    def test_etf_detection(self, code, expected):
        assert is_etf(code) is expected


class TestBoardLimitPct:
    """预警宽松阈值（实际涨跌停 -0.5%）。"""

    def test_known_boards(self):
        assert board_limit_pct("主板") == 9.5
        assert board_limit_pct("创业板") == 19.5
        assert board_limit_pct("科创板") == 19.5
        assert board_limit_pct("北交所") == 29.5

    def test_unknown_returns_default(self):
        assert board_limit_pct("未知板块") == 9.5


class TestBoardExactLimitPct:
    def test_known_boards(self):
        assert board_exact_limit_pct("主板") == 10.0
        assert board_exact_limit_pct("创业板") == 20.0
        assert board_exact_limit_pct("科创板") == 20.0
        assert board_exact_limit_pct("北交所") == 30.0

    def test_unknown_returns_default(self):
        assert board_exact_limit_pct("未知板块") == 10.0


# ═══════════════════════════════════════════════════════════════
# 类型转换
# ═══════════════════════════════════════════════════════════════


class TestToFloat:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("3.14", 3.14),
            ("1,000.50", 1000.50),  # 含逗号 → 去除
            (42, 42.0),
            (None, 0.0),
            ("", 0.0),
            ("-", 0.0),
            ("abc", 0.0),  # 异常值用 default
            ("abc", 99.9),  # custom default
        ],
    )
    def test_safe_float_conversion(self, raw, expected):
        if raw == "abc" and expected == 99.9:
            assert to_float(raw, default=99.9) == 99.9
        else:
            assert to_float(raw) == pytest.approx(expected)


class TestToInt:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("42", 42),
            ("3.14", 3),  # 浮点字符串转 int（向下取整语义）
            (None, 0),
            ("", 0),
            ("-", 0),
            ("abc", 0),
            ("1,234", 1234),
        ],
    )
    def test_safe_int_conversion(self, raw, expected):
        assert to_int(raw) == expected

    def test_custom_default(self):
        assert to_int("abc", default=99) == 99


class TestBatchify:
    def test_basic_batches(self):
        """32 个元素按 size=15 切分为 3 个 batch。"""
        result = batchify([str(i) for i in range(32)], size=15)
        assert len(result) == 3
        assert len(result[0]) == 15
        assert len(result[1]) == 15
        assert len(result[2]) == 2  # 剩余 2 个
        # 全部元素不丢不重
        assert sum(result, []) == [str(i) for i in range(32)]

    def test_exact_multiple(self):
        """30 个元素按 size=15 切分为 2 个 batch。"""
        result = batchify([str(i) for i in range(30)], size=15)
        assert len(result) == 2
        assert all(len(batch) == 15 for batch in result)

    def test_smaller_than_batch(self):
        """元素少于 batch 时只返回 1 个 batch。"""
        result = batchify(["a", "b", "c"], size=15)
        assert result == [["a", "b", "c"]]

    def test_empty_list(self):
        assert batchify([]) == []


class TestClamp:
    @pytest.mark.parametrize(
        "value,low,high,expected",
        [
            (50, 0, 100, 50),
            (-5, 0, 100, 0),
            (150, 0, 100, 100),
            (0, 0, 100, 0),  # 边界
            (100, 0, 100, 100),  # 边界
        ],
    )
    def test_clamp(self, value, low, high, expected):
        assert clamp(value, low, high) == expected


class TestComputeVolumeRatio:
    def test_normal_case(self):
        """基期与近期相同 → 1.0。"""
        volumes = [100] * 15
        ratio = compute_volume_ratio(volumes)
        assert ratio == pytest.approx(1.0)

    def test_recent_increase(self):
        """语义：最近 5 日均 vs 基础 10 日均（base_window 含 recent_window）。

        构造：15 个数据点，前 5 个 [100]，中间 5 个 [100]，后 5 个 [200]。
        - base 窗口（最后 10）均值 = (100*5 + 200*5) / 10 = 150
        - recent 窗口（最后 5）均值 = 200
        - ratio = 200 / 150 ≈ 1.333
        """
        volumes = [100] * 10 + [200] * 5
        assert compute_volume_ratio(volumes) == pytest.approx(1.333, rel=1e-3)

    def test_insufficient_data_returns_default(self):
        """数据不足时返回 1.0。"""
        volumes = [100] * 5  # 少于 base_window=10
        assert compute_volume_ratio(volumes) == 1.0

    def test_zero_base_volume_returns_default(self):
        """基期全 0 时返回 1.0（避免除零）。"""
        assert compute_volume_ratio([0] * 15) == 1.0

    def test_custom_windows(self):
        """自定义 recent_window / base_window。

        10 个数据点：[100,100,100,100,100,200,200,200,200,200]
        recent_window=3 → 最后 3 个 = [200,200,200]，mean=200
        base_window=7 → 最后 7 个 = [100,100,200,200,200,200,200]
                          = 2 个 100 + 5 个 200 = 1200 / 7 ≈ 171.43
        ratio ≈ 200 / 171.43 ≈ 1.167
        """
        volumes = [100] * 5 + [200] * 5
        assert compute_volume_ratio(
            volumes, recent_window=3, base_window=7
        ) == pytest.approx(1.1667, rel=1e-3)


class TestComputeOptimalWorkers:
    """线程数计算：min(item_count // 10, cpu*2)，下限 4。"""

    def test_with_item_count(self):
        result = compute_optimal_workers(item_count=100)
        cpu = os.cpu_count() or 4
        expected = min(max(100 // 10, 4), cpu * 2)
        assert result == expected

    def test_floor_at_4(self):
        """小数据量不应低于 4 线程。"""
        result = compute_optimal_workers(item_count=1)
        assert result >= 4

    def test_no_items_returns_default(self):
        cpu = os.cpu_count() or 4
        result = compute_optimal_workers()
        assert result == min(cpu * 2, 32)


# ═══════════════════════════════════════════════════════════════
# 数据单位归一化
# ═══════════════════════════════════════════════════════════════


class TestNormalizeVolume:
    """不同数据源成交量 → 股 的换算。"""

    @pytest.mark.parametrize(
        "source",
        [
            "tencent",
            "eastmoney",
            "efinance",
            "akshare",
            "tushare",
            "pytdx",
            "ths",
            "xueqiu",
        ],
    )
    def test_hands_to_shares(self, source):
        """手 → 股：×100."""
        assert normalize_volume(12345, source) == 1234500

    def test_sina_already_shares(self):
        """新浪已是股单位。"""
        assert normalize_volume(12345, "sina") == 12345

    def test_baostock_already_shares(self):
        assert normalize_volume(12345, "baostock") == 12345

    def test_unknown_source_assumed_shares(self):
        assert normalize_volume(12345, "unknown_source") == 12345

    def test_none_returns_zero(self):
        assert normalize_volume(None, "tencent") == 0


class TestNormalizeAmount:
    @pytest.mark.parametrize(
        "amount,source,expected",
        [
            (12345.67, "tencent", 123456700.0),  # 万元 → 元 (×10000)
            (12345.67, "tushare", 12345670.0),  # 千元 → 元 (×1000)
            (12345.67, "eastmoney", 12345.67),  # 原值
            (12345.67, "sina", 12345.67),
        ],
    )
    def test_conversion(self, amount, source, expected):
        assert normalize_amount(amount, source) == pytest.approx(expected)


# ═══════════════════════════════════════════════════════════════
# split_codes
# ═══════════════════════════════════════════════════════════════


class TestSplitCodes:
    def test_csv_string(self):
        assert split_codes("sh600519,sz000001") == ["sh600519", "sz000001"]

    def test_whitespace_filtered(self):
        assert split_codes(" sh600519 , , sz000001 ") == ["sh600519", "sz000001"]

    def test_empty_string(self):
        assert split_codes("") == []

    def test_file_path_prefix(self):
        """@file 前缀从文件读取（路径必须在允许范围内）。"""
        with pytest.raises((ValueError, FileNotFoundError)):
            split_codes("@/nonexistent/path")

    def test_file_outside_allowed_dir_rejected(self):
        """不在 DATA_DIR 下方的文件应拒绝（防越权读）。"""
        with pytest.raises(ValueError, match="不在允许范围内"):
            split_codes("@/etc/passwd")


# ═══════════════════════════════════════════════════════════════
# err 错误抛出
# ═══════════════════════════════════════════════════════════════


class TestErr:
    """err() 抛 DataError 而非 sys.exit。"""

    def test_raises_data_error(self):
        with pytest.raises(DataError, match="自定义错误"):
            from common.utils import err

            err("自定义错误")

    def test_writes_to_stderr(self, capsys):
        with pytest.raises(DataError):
            from common.utils import err

            err("stderr 内容")
        captured = capsys.readouterr()
        assert "stderr 内容" in captured.err


# ═══════════════════════════════════════════════════════════════
# atomic_write_json
# ═══════════════════════════════════════════════════════════════


class TestAtomicWriteJson:
    def test_writes_valid_json(self, tmp_path: Path):
        target = tmp_path / "out.json"
        obj = {"a": 1, "b": [1, 2, 3], "c": {"nested": True}}
        atomic_write_json(target, obj)
        assert target.exists()
        import json

        assert json.loads(target.read_text(encoding="utf-8")) == obj

    def test_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "out.json"
        atomic_write_json(target, {"x": 1})
        assert target.exists()

    def test_no_temp_file_left_on_success(self, tmp_path: Path):
        target = tmp_path / "out.json"
        atomic_write_json(target, {"k": "v"})
        # 临时文件应被 os.replace 替换，不应残留
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == []

    def test_unsupported_type_raises(self, tmp_path: Path):
        """不能序列化的对象应抛 TypeError 且不残留 tmp 文件。"""
        target = tmp_path / "out.json"
        with pytest.raises(TypeError):
            atomic_write_json(target, {"set"})  # set 不可 JSON 化
        # 失败时清理临时文件
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == []


# ═══════════════════════════════════════════════════════════════
# 并发线程池
# ═══════════════════════════════════════════════════════════════


class TestSharedExecutor:
    """get_shared_executor 应是单例 + 线程安全。"""

    def teardown_method(self):
        """每个测试后重置模块单例，避免污染其他测试。"""
        import common.utils as utils

        if utils._shared_executor is not None:
            try:
                utils._shared_executor.shutdown(wait=False)
            except Exception:
                pass
        utils._shared_executor = None

    def test_returns_executor_instance(self):
        from concurrent.futures import ThreadPoolExecutor

        from common.utils import get_shared_executor

        ex = get_shared_executor()
        assert isinstance(ex, ThreadPoolExecutor)

    def test_returns_same_instance(self):
        from common.utils import get_shared_executor

        ex1 = get_shared_executor()
        ex2 = get_shared_executor()
        assert ex1 is ex2

    def test_thread_safe_initialization(self):
        """并发首次访问只应初始化一次。"""
        from common.utils import get_shared_executor

        results: list = []
        errors: list = []

        def worker():
            try:
                results.append(get_shared_executor())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        # 全部获取同一实例
        assert len(results) >= 1
        first = results[0]
        assert all(r is first for r in results)

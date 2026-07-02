"""
multi_stock_backtest.py 单元测试：覆盖报告生成/代码去重/CLI 参数处理。
（不依赖真实网络数据，只测纯函数）
"""

import sys
from pathlib import Path

# 添加 scripts 到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from multi_stock_backtest import (
    DEFAULT_CODES,
    BENCHMARKS,
    load_codes,
    format_report,
)


class TestLoadCodes:
    """load_codes 函数：CLI 参数 + 默认 50 只跨板块。"""

    def test_default_codes_count(self):
        """默认代码池 ≥ 50 只。"""
        codes = load_codes(None)
        assert len(codes) >= 50, f"默认仅 {len(codes)} 只，应 ≥ 50"

    def test_default_codes_dedup(self):
        """去重后没有重复（DEFAULT_CODES 跨类别有重复）。"""
        codes = load_codes(None)
        assert len(codes) == len(set(codes)), "应去重"

    def test_default_codes_format(self):
        """默认代码都是 sh/sz/bj 前缀 + 6 位数字。"""
        for c in load_codes(None):
            assert len(c) == 8, f"代码 {c} 长度不对"
            assert c[:2] in ("sh", "sz", "bj"), f"代码 {c} 前缀不对"

    def test_custom_codes(self):
        """CLI 传入时用 CLI 值。"""
        codes = load_codes("sh600519,sz000807")
        assert codes == ["sh600519", "sz000807"]

    def test_empty_custom_falls_back_to_default(self):
        """CLI 传空字符串（',' 分割后为空列表）走默认。"""
        codes = load_codes("")
        assert len(codes) >= 50

    def test_custom_codes_strip_whitespace(self):
        """CLI 值去空格。"""
        codes = load_codes(" sh600519 , sz000807 ")
        assert codes == ["sh600519", "sz000807"]


class TestBenchmarks:
    """基准指数常量。"""

    def test_two_benchmarks(self):
        """至少包含沪深 300 + 中证 500。"""
        names = [n for _, n in BENCHMARKS]
        assert "沪深300" in names
        assert "中证500" in names

    def test_benchmark_codes_format(self):
        for code, name in BENCHMARKS:
            assert code.startswith("sh"), f"基准 {name} 代码 {code} 应以 sh 开头"


class TestFormatReport:
    """format_report 函数：markdown 输出结构。"""

    def test_report_contains_strategy_table(self):
        sr = [
            {
                "strategy": "balanced",
                "codes_count": 50,
                "result": {
                    "total_return_pct": 5.0,
                    "avg_return_pct": 30.0,
                    "sharpe_ratio": 1.2,
                    "max_drawdown_pct": 10.0,
                    "win_rate_pct": 55.0,
                },
            }
        ]
        br = [
            {
                "benchmark": "沪深300",
                "code": "sh000300",
                "result": {
                    "total_return_pct": 3.0,
                    "avg_return_pct": 18.0,
                    "sharpe_ratio": 0.9,
                    "max_drawdown_pct": 12.0,
                },
            }
        ]
        out = format_report(sr, br, load_codes(None))
        assert "## 1. 策略回测结果" in out
        assert "## 2. 基准对比" in out
        assert "## 3. 超额收益" in out
        assert "## 4. 重要提示" in out
        assert "balanced" in out
        assert "沪深300" in out
        assert "30.00" in out  # avg_return_pct 30%
        assert "+12.00%" in out  # alpha = 30 - 18

    def test_report_handles_errors(self):
        """engine import 失败时报告仍可生成（标 ⚠️）。"""
        sr = [
            {"strategy": "balanced", "codes_count": 50, "error": "engine import failed"}
        ]
        br = [{"benchmark": "沪深300", "code": "sh000300", "error": "boom"}]
        out = format_report(sr, br, ["sh600519"])
        assert "engine import failed" in out
        assert "boom" in out

    def test_report_no_benchmark_no_alpha(self):
        """无基准结果时不计算 alpha。"""
        sr = [
            {
                "strategy": "x",
                "codes_count": 50,
                "result": {
                    "total_return": 0,
                    "annual_return": 0,
                    "sharpe": 0,
                    "max_drawdown": 0,
                    "win_rate": 0,
                },
            }
        ]
        out = format_report(sr, [], ["sh600519"])
        assert "## 3. 超额收益" in out
        # alpha 行应缺失（因为 br 为空）
        assert "alpha =" not in out

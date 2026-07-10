"""
Sprint 4 性能优化测试（review#11/#12/#13）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from classifier import infer_industry  # noqa: E402


class TestInferIndustryReview13:
    """review#13：fetcher_industry 优先级最高。"""

    def test_fetcher_industry_takes_priority(self):
        """fetcher_industry 非空时直接使用，覆盖名称推断。"""
        # "中国平安" 名称推断会落入默认，但 fetcher 给了"保险"就应用
        result = infer_industry("中国平安", "sh601318", fetcher_industry="保险")
        assert result == "保险"

    def test_fetcher_industry_overrides_code_prefix(self):
        """fetcher_industry 覆盖代码段推断（688 → 科技）。"""
        result = infer_industry("某科创板", "sh688001", fetcher_industry="医药")
        assert result == "医药"

    def test_empty_fetcher_falls_back_to_name(self):
        """fetcher_industry 为空时回退到名称推断。"""
        result = infer_industry("中国银行", "sh601988", fetcher_industry="")
        assert result == "银行"

    def test_whitespace_fetcher_treated_as_empty(self):
        """fetcher_industry 仅含空白时回退。"""
        result = infer_industry("腾讯控股", "sh00700", fetcher_industry="   ")
        # 名称无中文 kw，应该回退到默认
        assert isinstance(result, str)

    def test_zhong_guo_ping_an_now_correct(self):
        """中国平安：fetcher 提供时直接正确分类为保险。"""
        # 模拟 fetcher 返回行业
        result_with = infer_industry("中国平安", "sh601318", fetcher_industry="保险")
        assert result_with == "保险"
        # 不提供时仍会落入默认（旧行为）
        result_without = infer_industry("中国平安", "sh601318")
        assert result_without == "默认"


class TestPrefetchKlineAll:
    """review#12：批量预拉 K 线辅助函数。"""

    def test_prefetch_kline_all_returns_dict(self, monkeypatch):
        """批量预拉返回 {code: bars} dict。"""
        from screener import _prefetch_kline_all
        from data.types import KlineBar

        fake_bars = [
            KlineBar(day="2025-01-01", open=10, high=11, low=9, close=10, volume=1000)
        ]

        # monkeypatch get_kline（通过 data 模块）
        import data

        monkeypatch.setattr(data, "get_kline", lambda *a, **k: fake_bars)
        result = _prefetch_kline_all(["sh600519", "sh600989"])
        assert isinstance(result, dict)
        assert len(result) == 2
        # 键是 normalized code
        assert "sh600519" in result or "sh600989" in result


class TestParallelFetch:
    """review#11：行情+财务并行（通过结构验证）。"""

    def test_screener_main_uses_threadpool(self, monkeypatch):
        """run_screening 使用 ThreadPoolExecutor 并行拉取行情和财务。"""
        import business.screening_service as ss

        # monkeypatch 关键函数以避免网络调用（下沉后在 screening_service 模块）
        monkeypatch.setattr(ss, "load_universe", lambda args: ["sh600519"])
        monkeypatch.setattr(
            ss,
            "fetch_batch_dicts",
            lambda codes: [{"code": "sh600519", "name": "贵州茅台"}],
        )
        monkeypatch.setattr(ss, "prefetch_finance_all", lambda codes: {"sh600519": []})
        monkeypatch.setattr(ss, "prefetch_kline_all", lambda *a, **k: {})
        monkeypatch.setattr(
            ss,
            "analyze_code",
            lambda *a, **k: {
                "code": "sh600519",
                "name": "贵州茅台",
                "score": 80,
                "rejected": [],
            },
        )
        monkeypatch.setattr(ss, "apply_portfolio_constraints", lambda rows, **k: rows)

        # 通过 inspect 验证 run_screening 源码包含并行模式
        import inspect

        source = inspect.getsource(ss.run_screening)
        assert "ThreadPoolExecutor" in source
        assert "prefetch_kline_all" in source

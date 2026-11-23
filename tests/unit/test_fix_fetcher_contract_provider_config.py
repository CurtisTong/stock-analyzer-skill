"""review 3.1-P1-6 回归测试：四域 fetcher 的 provider 声明与 YAML 配置生效。

修复前 flow/lhb/event/chip 各 fetcher 的 provider 由 name 隐式推断为
northbound/stock/lhb/earnings/margin 等，与 data_source.yaml 的
eastmoney/sina 键不匹配，priority/timeout/retry/enabled 全部失效；
两个北向 fetcher 还共用同一个 name → 共享熔断器。
"""

from __future__ import annotations

import copy

import pytest

from fetchers.chip.eastmoney_chip import HolderFetcher, MarginFetcher, TopHolderFetcher
from fetchers.event.eastmoney_event import (
    DividendCalendarFetcher,
    EarningsCalendarFetcher,
    LockupCalendarFetcher,
    ShareholderChangeFetcher,
    ViolationFetcher,
)
from fetchers.event.performance_forecast import PerformanceForecastFetcher
from fetchers.flow.eastmoney_flow import NorthboundFlowFetcher, StockFlowFetcher
from fetchers.flow.sina_flow import SinaNorthboundFlowFetcher
from fetchers.lhb.eastmoney_lhb import LhbDetailFetcher, LhbSeatFetcher


def _config_with_distinct_overrides(section: str, overrides: dict):
    """读取真实 YAML 结构，但用差异化数值覆盖，证明配置确实被 fetcher 接收。"""
    from config.loader import ConfigLoader

    cfg = copy.deepcopy(ConfigLoader.load("data_source.yaml").get(section, {}))
    for provider, values in overrides.items():
        assert provider in cfg, f"YAML 缺少 provider 键: {section}.{provider}"
        cfg[provider].update(values)
    return cfg


def test_northbound_fetchers_have_distinct_names_and_breakers():
    """两个北向 fetcher 必须不同名、不同 provider、不同熔断器实例。"""
    em = NorthboundFlowFetcher()
    sina = SinaNorthboundFlowFetcher()

    assert em.name != sina.name
    assert em.provider == "eastmoney"
    assert sina.provider == "sina"
    assert em.circuit_breaker is not sina.circuit_breaker


@pytest.mark.parametrize(
    "factory",
    [
        StockFlowFetcher,
        LhbDetailFetcher,
        LhbSeatFetcher,
        EarningsCalendarFetcher,
        LockupCalendarFetcher,
        DividendCalendarFetcher,
        ShareholderChangeFetcher,
        ViolationFetcher,
        PerformanceForecastFetcher,
        MarginFetcher,
        HolderFetcher,
        TopHolderFetcher,
    ],
)
def test_all_eastmoney_fetchers_declare_provider(factory):
    """flow/lhb/event/chip 全部显式声明 provider=eastmoney。"""
    assert factory().provider == "eastmoney"


def test_flow_yaml_config_applied_to_fetchers():
    """flow_sources 的 priority/timeout/retry 按 provider 键覆盖到真实 fetcher。"""
    from common.fetcher_base import DataFetcherManager

    cfg = _config_with_distinct_overrides(
        "flow_sources",
        {
            "eastmoney": {"priority": 41, "timeout": 11, "retry": 7},
            "sina": {"priority": 12, "timeout": 13, "retry": 8},
        },
    )
    em = NorthboundFlowFetcher()
    stock = StockFlowFetcher()
    sina = SinaNorthboundFlowFetcher()
    DataFetcherManager([em, stock, sina], source_config=cfg)

    assert (em.priority, em.timeout, em.retry) == (41, 11, 7)
    assert (stock.priority, stock.timeout, stock.retry) == (41, 11, 7)
    assert (sina.priority, sina.timeout, sina.retry) == (12, 13, 8)


def test_lhb_event_chip_yaml_config_applied_to_fetchers():
    """lhb/event/chip 三域同样按 eastmoney 键接收 priority/timeout/retry。"""
    from common.fetcher_base import DataFetcherManager

    groups = [
        ("lhb_sources", [LhbDetailFetcher(), LhbSeatFetcher()]),
        (
            "event_sources",
            [
                EarningsCalendarFetcher(),
                LockupCalendarFetcher(),
                DividendCalendarFetcher(),
                ShareholderChangeFetcher(),
                ViolationFetcher(),
                PerformanceForecastFetcher(),
            ],
        ),
        ("chip_sources", [MarginFetcher(), HolderFetcher(), TopHolderFetcher()]),
    ]
    for section, fetchers in groups:
        cfg = _config_with_distinct_overrides(
            section, {"eastmoney": {"priority": 51, "timeout": 17, "retry": 6}}
        )
        DataFetcherManager(fetchers, source_config=cfg)
        for f in fetchers:
            assert (f.priority, f.timeout, f.retry) == (51, 17, 6), f"{section}: {f.name}"

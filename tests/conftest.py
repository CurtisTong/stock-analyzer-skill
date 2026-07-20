"""pytest 全局 fixtures。

按 FRAMEWORK.md 规范：
- autouse fixtures 保证每个测试干净运行
- 行情/K 线 fixture 委托 tests.helpers.market_data 生成
- CLI 入口通过 tests.helpers.cli_runner.CliRunner 封装
"""

from __future__ import annotations

import pytest

from tests.helpers.market_data import (
    fenxing_bottom,
    fenxing_top,
    generate_sideways,
    generate_trend,
    limit_up,
)
from tests.helpers.cli_runner import CliRunner

# ═══════════════════════════════════════════════════════════════
# autouse fixtures（隔离副作用）
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reload_config_loader():
    """每个测试前重置 ConfigLoader 缓存，确保测试隔离。"""
    try:
        from config.loader import ConfigLoader

        ConfigLoader.reload()
    except ImportError:
        pass
    yield


@pytest.fixture(autouse=True)
def _reset_expert_registry():
    """每个测试前重置 EXPERT_REGISTRY，确保专家注册表隔离。

    experts/__init__.py 移除了顶层 _ensure_loaded()，改为 lazy 守卫。
    部分测试直接 from experts.registry import EXPERT_REGISTRY 读 dict 引用，
    不触发 lazy 守卫，此处强制每个测试前 clear + reload。
    """
    try:
        from experts.registry import EXPERT_REGISTRY, _ensure_loaded

        EXPERT_REGISTRY.clear()
        _ensure_loaded()
    except ImportError:
        pass
    yield
    # teardown 不再 clear：下一个测试的 setup 会 clear + reload


# ═══════════════════════════════════════════════════════════════
# K 线 fixtures（委托 helpers.market_data）
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def kline_uptrend():
    """20 根上升趋势 K 线。"""
    return generate_trend("up", 20)


@pytest.fixture
def kline_downtrend():
    """20 根下降趋势 K 线。"""
    return generate_trend("down", 20)


@pytest.fixture
def kline_sideways():
    """30 根横盘震荡 K 线。"""
    return generate_sideways(30)


@pytest.fixture
def kline_with_top_fenxing():
    """5 根标准顶分型。"""
    return fenxing_top()


@pytest.fixture
def kline_with_bottom_fenxing():
    """5 根标准底分型。"""
    return fenxing_bottom()


@pytest.fixture
def kline_macd_golden_cross():
    """30 根 MACD 金叉场景（先跌后涨）。"""
    records = generate_trend("down", 15)
    records.extend(generate_trend("up", 15, base_price=8.0))
    return records


@pytest.fixture
def kline_macd_death_cross():
    """30 根 MACD 死叉场景（先涨后跌）。"""
    records = generate_trend("up", 15)
    records.extend(generate_trend("down", 15, base_price=15.0))
    return records


@pytest.fixture
def kline_limit_up():
    """含涨停 K 线的 A 股特化场景。"""
    records = generate_trend("up", 10)
    records.append(limit_up(prev_close=records[-1]["close"]))
    return records


# ═══════════════════════════════════════════════════════════════
# 行情/财务 fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def sample_quote() -> dict:
    """归一化后行情（volume=股，amount=元）。"""
    return {
        "code": "600519",
        "name": "贵州茅台",
        "price": "1800.00",
        "prev_close": "1790.00",
        "open": "1795.00",
        "change_pct": "0.56",
        "change_amt": "10.00",
        "high": "1810.00",
        "low": "1790.00",
        "volume": "1234500",
        "amount": "22345670000",
        "turnover": "0.15",
        "pe": "25.6",
        "pb": "8.2",
        "total_cap": "22600",
        "circulating_cap": "22600",
    }


@pytest.fixture
def sample_finance() -> dict:
    """东财字段名归一化财务。"""
    return {
        "EPSJB": "50.00",
        "ROEJQ": "30.5",
        "TOTALOPERATEREVETZ": "15.2",
        "PARENTNETPROFITTZ": "18.3",
        "XSMLL": "91.5",
        "XSJLL": "52.3",
        "ZCFZL": "18.7",
        "BPS": "180.00",
        "MGJYXJJE": "55.00",
    }


@pytest.fixture
def sample_finance_akshare() -> dict:
    """akshare 财务数据（中文字段名）。"""
    return {
        "基本每股收益": "50.00",
        "净资产收益率": "30.5",
        "营收同比(%)": "15.2",
        "净利润同比(%)": "18.3",
        "销售毛利率(%)": "91.5",
        "销售净利率(%)": "52.3",
        "资产负债率(%)": "18.7",
        "每股净资产": "180.00",
        "每股经营现金流": "55.00",
        "报告日期": "2026-03-31",
    }


@pytest.fixture
def sample_finance_efinance() -> dict:
    """efinance 财务数据（中文字段名变体）。"""
    return {
        "每股收益": "50.00",
        "ROE": "30.5",
        "营业收入同比": "15.2",
        "归母净利润同比": "18.3",
        "毛利率": "91.5",
        "净利率": "52.3",
        "资产负债率": "18.7",
        "每股净资产": "180.00",
        "每股现金流量净额": "55.00",
    }


# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def mock_http_get(monkeypatch):
    """Mock common.http_get，避免真实网络请求。

    注：fetchers 测试优先使用 respx_mock（见 helpers.http_fixtures），
    此 fixture 仅供旧式 monkeypatch 测试使用。
    """

    def _mock(url, timeout=10):
        return b""

    import common

    monkeypatch.setattr(common, "http_get", _mock)
    return _mock


@pytest.fixture
def mock_fetch_kline(monkeypatch, kline_uptrend):
    """Mock kline.fetch，返回标准上升趋势数据。"""
    import kline

    monkeypatch.setattr(
        kline, "fetch", lambda code, scale="day", limit=250: kline_uptrend
    )
    return kline_uptrend


@pytest.fixture
def mock_fetch_batch(monkeypatch, sample_quote):
    """Mock quote.fetch_batch，返回标准行情。"""
    import quote

    monkeypatch.setattr(
        quote, "fetch_batch", lambda codes: {c: sample_quote for c in codes}
    )
    return sample_quote


# ═══════════════════════════════════════════════════════════════
# 新增 fixtures（CLI runner / 时间冻结）
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def cli_runner() -> CliRunner:
    """CLI 子进程执行器（替代散落的 subprocess.run）。"""
    return CliRunner()


@pytest.fixture
def freeze_time(monkeypatch):
    """冻结当前时间到固定值。

    用法：
        def test_x(freeze_time):
            freeze_time("2026-07-20 10:30:00")
            ...
    """
    from datetime import datetime

    def _freeze(iso: str) -> None:
        fixed = datetime.fromisoformat(iso)
        try:
            from dev import clock

            monkeypatch.setattr(clock, "_now_func", lambda: fixed)
        except ImportError:
            pass

    return _freeze


# ═══════════════════════════════════════════════════════════════
# pytest 配置
# ═══════════════════════════════════════════════════════════════


def pytest_configure(config):
    """注册自定义 marker。"""
    config.addinivalue_line("markers", "unit: 纯函数/单类单元测试")
    config.addinivalue_line("markers", "integration: 跨模块集成测试")
    config.addinivalue_line("markers", "e2e: 端到端 CLI 测试")
    config.addinivalue_line("markers", "contracts: schema/yaml 合约测试")
    config.addinivalue_line("markers", "slow: 慢速测试")
    config.addinivalue_line("markers", "network: 需要真实网络访问")


def pytest_addoption(parser):
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="运行需要网络的测试",
    )


def pytest_collection_modifyitems(config, items):
    """默认 skip network 测试；按目录自动打 layer marker。"""
    if not config.getoption("--run-network"):
        skip_network = pytest.mark.skip(reason="需要 --run-network 选项")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)

    # 按目录自动打 layer marker（避免每个文件手写 pytestmark）
    from pathlib import Path

    auto_markers = {
        "tests/unit/": "unit",
        "tests/integration/": "integration",
        "tests/e2e/": "e2e",
        "tests/contracts/": "contracts",
    }
    for item in items:
        fspath = str(item.fspath).replace("\\", "/")
        for prefix, marker in auto_markers.items():
            if prefix in fspath:
                item.add_marker(getattr(pytest.mark, marker))
                break

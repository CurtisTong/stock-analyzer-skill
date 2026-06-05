"""
pytest 全局 fixtures：标准 K 线数据、行情数据、mock 网络请求。
"""
import json
import pytest
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


# ═══════════════════════════════════════════════════════════════
# 标准 K 线 fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def kline_uptrend():
    """上升趋势 K 线（20 根），适合测试均线多头排列、MACD 金叉。"""
    return _generate_trend("up", 20)


@pytest.fixture
def kline_downtrend():
    """下降趋势 K 线（20 根），适合测试均线空头排列、MACD 死叉。"""
    return _generate_trend("down", 20)


@pytest.fixture
def kline_sideways():
    """横盘震荡 K 线（30 根），适合测试粘合度、箱体。"""
    return _generate_sideways(30)


@pytest.fixture
def kline_with_top_fenxing():
    """含标准顶分型的 K 线序列（5 根）。"""
    return [
        {"day": "2025-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.3, "volume": 1000},
        {"day": "2025-01-02", "open": 10.3, "high": 11.0, "low": 10.2, "close": 10.8, "volume": 1200},
        {"day": "2025-01-03", "open": 10.8, "high": 11.5, "low": 10.6, "close": 11.2, "volume": 1500},
        {"day": "2025-01-06", "open": 11.2, "high": 11.3, "low": 10.4, "close": 10.5, "volume": 1100},
        {"day": "2025-01-07", "open": 10.5, "high": 10.7, "low": 10.0, "close": 10.1, "volume": 900},
    ]


@pytest.fixture
def kline_with_bottom_fenxing():
    """含标准底分型的 K 线序列（5 根）。"""
    return [
        {"day": "2025-01-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.1, "volume": 1000},
        {"day": "2025-01-02", "open": 10.1, "high": 10.2, "low": 9.3, "close": 9.5, "volume": 1200},
        {"day": "2025-01-03", "open": 9.5, "high": 9.6, "low": 9.0, "close": 9.1, "volume": 1500},
        {"day": "2025-01-06", "open": 9.1, "high": 10.0, "low": 9.2, "close": 9.9, "volume": 1100},
        {"day": "2025-01-07", "open": 9.9, "high": 10.4, "low": 9.8, "close": 10.3, "volume": 900},
    ]


@pytest.fixture
def kline_macd_golden_cross():
    """MACD 金叉场景 K 线（先跌后涨，30 根）。"""
    records = _generate_trend("down", 15)
    records.extend(_generate_trend("up", 15, base_price=8.0))
    return records


@pytest.fixture
def kline_macd_death_cross():
    """MACD 死叉场景 K 线（先涨后跌，30 根）。"""
    records = _generate_trend("up", 15)
    records.extend(_generate_trend("down", 15, base_price=15.0))
    return records


@pytest.fixture
def kline_limit_up():
    """含涨停 K 线的数据（A 股特化测试）。"""
    records = _generate_trend("up", 10)
    # 涨停 K 线：涨幅 ~10%
    prev_close = records[-1]["close"]
    records.append({
        "day": "2025-02-01", "open": prev_close,
        "high": round(prev_close * 1.1, 2),
        "low": prev_close,
        "close": round(prev_close * 1.1, 2),
        "volume": 5000,
    })
    return records


# ═══════════════════════════════════════════════════════════════
# 行情数据 fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_quote():
    """标准行情数据（模拟腾讯接口返回格式）。"""
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
        "volume": "12345",
        "amount": "2234567",
        "turnover": "0.15",
        "pe": "25.6",
        "pb": "8.2",
        "total_cap": "22600",
        "circulating_cap": "22600",
    }


@pytest.fixture
def sample_finance():
    """标准财务数据（模拟东财接口返回格式）。"""
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


# ═══════════════════════════════════════════════════════════════
# Mock helpers
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def mock_http_get(monkeypatch):
    """Mock common.http_get，避免真实网络请求。"""
    def _mock(url, timeout=10):
        return b""
    import common
    monkeypatch.setattr(common, "http_get", _mock)
    return _mock


@pytest.fixture
def mock_fetch_kline(monkeypatch, kline_uptrend):
    """Mock kline.fetch，返回标准上升趋势数据。"""
    import kline
    monkeypatch.setattr(kline, "fetch", lambda code, scale="day", limit=250: kline_uptrend)
    return kline_uptrend


@pytest.fixture
def mock_fetch_batch(monkeypatch, sample_quote):
    """Mock quote.fetch_batch，返回标准行情。"""
    import quote
    monkeypatch.setattr(quote, "fetch_batch", lambda codes: {c: sample_quote for c in codes})
    return sample_quote


# ═══════════════════════════════════════════════════════════════
# 内部工具
# ═══════════════════════════════════════════════════════════════

def _generate_trend(direction, n, base_price=10.0):
    """生成趋势 K 线序列。"""
    records = []
    price = base_price
    for i in range(n):
        if direction == "up":
            change = 0.3 + (i % 3) * 0.1
        else:
            change = -0.3 - (i % 3) * 0.1
        open_p = price
        close_p = round(price + change, 2)
        high_p = round(max(open_p, close_p) + 0.2, 2)
        low_p = round(min(open_p, close_p) - 0.2, 2)
        records.append({
            "day": f"2025-01-{i+1:02d}" if i < 20 else f"2025-02-{i-19:02d}",
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": 1000 + i * 50,
        })
        price = close_p
    return records


def _generate_sideways(n, center=10.0, amplitude=0.5):
    """生成横盘震荡 K 线序列。"""
    import math
    records = []
    for i in range(n):
        offset = amplitude * math.sin(i * 0.5)
        price = center + offset
        records.append({
            "day": f"2025-01-{i+1:02d}" if i < 20 else f"2025-02-{i-19:02d}",
            "open": round(price - 0.1, 2),
            "high": round(price + 0.3, 2),
            "low": round(price - 0.3, 2),
            "close": round(price + 0.1, 2),
            "volume": 1000 + (i % 5) * 100,
        })
    return records

"""测试 scripts/fetchers/flow/sina_flow.py：新浪北向资金 fetcher。"""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# sina_flow.py 路径: scripts/fetchers/flow/sina_flow.py
_spec = importlib.util.spec_from_file_location(
    "sina_flow_mod",
    PROJECT_ROOT / "scripts" / "fetchers" / "flow" / "sina_flow.py",
)
sina_flow = importlib.util.module_from_spec(_spec)
sys.modules["sina_flow_mod"] = sina_flow
_spec.loader.exec_module(sina_flow)


class TestSinaNorthboundFlowFetcher:
    def test_init(self):
        """初始化：name + priority 备份源。"""
        f = sina_flow.SinaNorthboundFlowFetcher()
        assert f.name == "northbound_flow"
        assert f.priority == 8

    def test_fetch_http_error(self):
        """http_get 抛错时返回 None。"""
        with patch("sina_flow_mod.http_get", side_effect=Exception("net")):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is None

    def test_fetch_invalid_json(self):
        """JSON 解析失败时返回 None。"""
        with patch("sina_flow_mod.http_get", return_value="not json {"):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is None

    def test_fetch_empty_data(self):
        """空数据列表时返回 None。"""
        with patch("sina_flow_mod.http_get", return_value="[]"):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is None

    def test_fetch_non_list_data(self):
        """非 list 数据时返回 None。"""
        with patch("sina_flow_mod.http_get", return_value='{"not": "list"}'):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is None

    def test_fetch_success(self):
        """成功解析北向资金数据。"""
        # 新浪返回 1d 的 close 字段为净流入额（亿元）
        raw = json.dumps(
            [
                {
                    "day": "2026-07-01",
                    "open": 1.0,
                    "close": 2.5,
                    "high": 3.0,
                    "low": 0.5,
                    "volume": 1000,
                },
                {
                    "day": "2026-07-02",
                    "open": 0.0,
                    "close": -1.5,
                    "high": 0.5,
                    "low": -2.0,
                    "volume": 800,
                },
            ]
        )
        with patch("sina_flow_mod.http_get", return_value=raw):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is not None
        assert result["type"] == "northbound"
        assert result["source"] == "sina"
        assert len(result["days"]) == 2
        # 2.5 亿元 * 10000 = 25000 万元
        assert result["days"][0]["total_net"] == 25000.0
        # sh_net / sz_net 不区分
        assert result["days"][0]["sh_net"] == 0
        assert result["days"][0]["sz_net"] == 0

    def test_fetch_non_dict_rows(self):
        """非 dict 行被跳过。"""
        raw = json.dumps(
            [
                "not a dict",
                {"day": "2026-07-01", "close": 1.0},
            ]
        )
        with patch("sina_flow_mod.http_get", return_value=raw):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        # 只有 1 个有效 dict 行
        assert len(result["days"]) == 1

    def test_fetch_days_param(self):
        """days 参数正确传递给 URL。"""
        with patch("sina_flow_mod.http_get", return_value="[]") as m:
            f = sina_flow.SinaNorthboundFlowFetcher()
            f.fetch(code="", days=30)
        # URL 应当含 datalen=30
        assert "datalen=30" in m.call_args[0][0]

    def test_no_data_returns_none(self):
        """rows 全是非 dict 时返回 None。"""
        raw = json.dumps(["x", "y", "z"])
        with patch("sina_flow_mod.http_get", return_value=raw):
            f = sina_flow.SinaNorthboundFlowFetcher()
            result = f.fetch(code="", days=10)
        assert result is None

"""资金流向数据层聚合测试（T24）。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import data.flow as flow_mod  # noqa: E402


class TestGetNorthboundFlow:
    """get_northbound_flow 多源故障转移 + 数据聚合。"""

    def test_empty_fetchers_returns_empty(self):
        """无 fetcher 时返回空列表。"""
        with patch.object(flow_mod, "_registry") as mock_reg:
            mock_reg.get_all.return_value = []
            result = flow_mod.get_northbound_flow("sh000001", days=5)
            assert result == []

    def test_successful_fetch_returns_data(self):
        """正常 fetch 返回格式化后的数据。"""
        mock_fetcher = MagicMock()
        mock_fetcher.name = "northbound_flow"
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = {
            "type": "northbound",
            "days": [
                {"date": "2026-07-01", "sh_net": 10, "sz_net": 5, "total_net": 15},
                {"date": "2026-07-02", "sh_net": -3, "sz_net": 2, "total_net": -1},
            ],
        }
        with patch.object(flow_mod, "_registry") as mock_reg:
            mock_reg.get_all.return_value = [mock_fetcher]
            result = flow_mod.get_northbound_flow("sh000001", days=5)
            assert len(result) == 2
            assert result[0]["date"] == "2026-07-01"
            assert result[0]["net_buy"] == 15
            assert result[0]["sh_net"] == 10
            assert result[1]["net_buy"] == -1

    def test_fallback_to_second_source(self):
        """第一源失败时回退到第二源。"""
        mock_fetcher1 = MagicMock()
        mock_fetcher1.name = "northbound_flow"
        mock_fetcher1.is_available.return_value = True
        mock_fetcher1.fetch.side_effect = Exception("network error")

        mock_fetcher2 = MagicMock()
        mock_fetcher2.name = "northbound_flow_sina"
        mock_fetcher2.is_available.return_value = True
        mock_fetcher2.fetch.return_value = {
            "type": "northbound",
            "days": [{"date": "2026-07-01", "sh_net": 8, "sz_net": 4, "total_net": 12}],
        }
        with patch.object(flow_mod, "_registry") as mock_reg:
            mock_reg.get_all.return_value = [mock_fetcher1, mock_fetcher2]
            result = flow_mod.get_northbound_flow("sh000001", days=5)
            assert len(result) == 1
            assert result[0]["net_buy"] == 12


class TestGetStockFlow:
    """get_stock_flow 个股资金流向。"""

    def test_returns_none_when_no_fetcher(self):
        with patch.object(flow_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = None
            result = flow_mod.get_stock_flow("sh600519")
            assert result is None

    def test_returns_data_when_successful(self):
        mock_fetcher = MagicMock()
        mock_fetcher.is_available.return_value = True
        mock_fetcher.fetch.return_value = {"type": "stock_flow", "days": []}
        with patch.object(flow_mod, "_registry") as mock_reg:
            mock_reg.find.return_value = mock_fetcher
            result = flow_mod.get_stock_flow("sh600519")
            assert result is not None
            assert result["type"] == "stock_flow"

"""fetchers/eastmoney_chip.py 单元测试：筹码相关数据源。"""

import json
import pytest
from unittest.mock import patch, MagicMock

from common import NetworkError
from fetchers.chip.eastmoney_chip import (
    _get_secid,
    MarginFetcher,
    HolderFetcher,
    TopHolderFetcher,
)


class TestGetSecid:
    """_get_secid 代码转换测试。"""

    def test_sh_prefix(self):
        assert _get_secid("sh600989") == "SH600989"

    def test_sz_prefix(self):
        assert _get_secid("sz000807") == "SZ000807"

    def test_uppercase_prefix(self):
        assert _get_secid("SH600989") == "SH600989"

    def test_pure_code_starts_with_6(self):
        assert _get_secid("600989") == "SH600989"

    def test_pure_code_starts_with_0(self):
        assert _get_secid("000807") == "SZ000807"

    def test_pure_code_starts_with_3(self):
        assert _get_secid("300001") == "SZ300001"

    def test_pure_code_starts_with_9(self):
        assert _get_secid("900901") == "SH900901"

    def test_bj_prefix(self):
        """北交所代码应返回 BJ 前缀。"""
        assert _get_secid("bj430047") == "BJ430047"

    def test_pure_code_starts_with_43(self):
        """43 开头纯数字应识别为北交所。"""
        assert _get_secid("430047") == "BJ430047"

    def test_pure_code_starts_with_83(self):
        """83 开头纯数字应识别为北交所。"""
        assert _get_secid("830001") == "BJ830001"


class TestMarginFetcher:
    """MarginFetcher 测试。"""

    def test_name_and_priority(self):
        f = MarginFetcher()
        assert f.name == "margin"
        assert f.priority == 5

    def test_fetch_propagates_network_error(self):
        """NetworkError 应传播到 DataFetcherManager 统一处理故障转移。"""
        f = MarginFetcher()
        with patch(
            "fetchers.chip.eastmoney_chip.http_get",
            side_effect=NetworkError("http://example.com", "网络错误"),
        ):
            with pytest.raises(NetworkError):
                f.fetch("sh600989")

    def test_fetch_returns_none_on_invalid_json(self):
        f = MarginFetcher()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=b"not json"):
            result = f.fetch("sh600989")
        assert result is None

    def test_fetch_returns_none_on_api_failure(self):
        f = MarginFetcher()
        resp = json.dumps({"success": False}).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")
        assert result is None

    def test_fetch_parses_valid_data(self):
        f = MarginFetcher()
        resp = json.dumps(
            {
                "success": True,
                "result": {
                    "data": [
                        {
                            "TRADE_DATE": "2025-06-20",
                            "RZYE": 1000000000,
                            "RQYE": 5000000,
                            "RZMRE": 50000000,
                            "RZCHE": 30000000,
                            "RZJME": 20000000,
                            "RQMCL": 100000,
                            "RQCHL": 50000,
                            "RQJMG": 50000,
                            "RQYL": 200000,
                        }
                    ]
                },
            }
        ).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")

        assert result is not None
        assert len(result) == 1
        assert result[0]["date"] == "2025-06-20"
        assert result[0]["rzye"] == 1000000000


class TestHolderFetcher:
    """HolderFetcher 测试。"""

    def test_name_and_priority(self):
        f = HolderFetcher()
        assert f.name == "holder"
        assert f.priority == 5

    def test_fetch_returns_none_on_empty_gdrs(self):
        f = HolderFetcher()
        resp = json.dumps({"gdrs": []}).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")
        assert result is None

    def test_fetch_returns_none_on_missing_gdrs(self):
        f = HolderFetcher()
        resp = json.dumps({"other": "data"}).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")
        assert result is None

    def test_fetch_parses_holder_data(self):
        f = HolderFetcher()
        resp = json.dumps(
            {
                "gdrs": [
                    {
                        "END_DATE": "2025-03-31",
                        "HOLDER_TOTAL_NUM": 50000,
                        "AVG_FREE_SHARES": 2000.0,
                        "TOTAL_NUM_RATIO": -5.0,
                        "HOLD_FOCUS": "比较集中",
                    },
                    {
                        "END_DATE": "2024-12-31",
                        "HOLDER_TOTAL_NUM": 52000,
                        "AVG_FREE_SHARES": 1900.0,
                        "TOTAL_NUM_RATIO": 2.0,
                        "HOLD_FOCUS": "相对集中",
                    },
                ]
            }
        ).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989", periods=2)

        assert result is not None
        assert len(result) == 2
        # 按日期降序，最新在前
        assert result[0]["end_date"] == "2025-03-31"
        assert result[0]["holder_num"] == 50000
        assert result[0]["concentration"] == "集中"
        assert result[1]["concentration"] == "一般"

    def test_concentration_mapping(self):
        """测试各种集中度映射。"""
        f = HolderFetcher()
        test_cases = [
            ("非常集中", "集中"),
            ("比较集中", "集中"),
            ("相对集中", "一般"),
            ("非常分散", "分散"),
            ("比较分散", "分散"),
            ("其他", "持平"),
        ]
        for hold_focus, expected in test_cases:
            resp = json.dumps(
                {
                    "gdrs": [
                        {
                            "END_DATE": "2025-03-31",
                            "HOLDER_TOTAL_NUM": 1000,
                            "AVG_FREE_SHARES": 100.0,
                            "TOTAL_NUM_RATIO": 0,
                            "HOLD_FOCUS": hold_focus,
                        }
                    ]
                }
            ).encode()
            with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
                result = f.fetch("sh600989", periods=1)
            assert result[0]["concentration"] == expected, f"HOLD_FOCUS={hold_focus}"


class TestTopHolderFetcher:
    """TopHolderFetcher 测试。"""

    def test_name_and_priority(self):
        f = TopHolderFetcher()
        assert f.name == "top_holder"
        assert f.priority == 5

    def test_fetch_returns_none_on_missing_sdltgd(self):
        f = TopHolderFetcher()
        resp = json.dumps({"other": "data"}).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")
        assert result is None

    def test_fetch_parses_top_holders(self):
        f = TopHolderFetcher()
        resp = json.dumps(
            {
                "sdltgd": [
                    {
                        "END_DATE": "2025-03-31",
                        "HOLDER_RANK": 1,
                        "HOLDER_NAME": "中国证券金融股份有限公司",
                        "SHARES_TYPE": "流通A股",
                        "HOLD_NUM": 500000000,
                        "HOLD_NUM_RATIO": 5.0,
                        "HOLD_NUM_CHANGE": 10000000,
                        "CHANGE_TYPE": "增持",
                    },
                    {
                        "END_DATE": "2025-03-31",
                        "HOLDER_RANK": 2,
                        "HOLDER_NAME": "张三",
                        "SHARES_TYPE": "流通A股",
                        "HOLD_NUM": 300000000,
                        "HOLD_NUM_RATIO": 3.0,
                        "HOLD_NUM_CHANGE": 0,
                        "CHANGE_TYPE": "不变",
                    },
                ]
            }
        ).encode()
        with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
            result = f.fetch("sh600989")

        assert result is not None
        assert len(result) == 2
        assert result[0]["rank"] == 1
        assert result[0]["is_institution"] is True  # "中国证券" 匹配机构关键词
        assert result[0]["change_type"] == "增持"
        assert result[1]["is_institution"] is False
        assert result[1]["change_type"] == "不变"

    def test_institution_detection(self):
        """测试机构关键词识别。"""
        f = TopHolderFetcher()
        keywords = ["华夏基金", "QFII", "社保基金", "中信证券", "中国人寿保险"]
        for name in keywords:
            resp = json.dumps(
                {
                    "sdltgd": [
                        {
                            "END_DATE": "2025-03-31",
                            "HOLDER_RANK": 1,
                            "HOLDER_NAME": name,
                            "SHARES_TYPE": "流通A股",
                            "HOLD_NUM": 100000,
                            "HOLD_NUM_RATIO": 1.0,
                            "HOLD_NUM_CHANGE": 0,
                            "CHANGE_TYPE": "不变",
                        }
                    ]
                }
            ).encode()
            with patch("fetchers.chip.eastmoney_chip.http_get", return_value=resp):
                result = f.fetch("sh600989")
            assert result[0]["is_institution"] is True, f"Failed for: {name}"

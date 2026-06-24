"""公告/研报模块测试。"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from announcements import (
    render_announcements,
    render_reports,
    fetch_announcements,
    fetch_reports,
)


class TestRenderAnnouncements:
    """render_announcements 函数测试。"""

    def test_empty_list(self):
        """空列表返回提示。"""
        assert render_announcements([]) == "(无公告)"

    def test_single_item(self):
        """单条公告。"""
        items = [{"title": "关于分红公告", "notice_date": "2026-06-20"}]
        result = render_announcements(items)
        assert "2026-06-20" in result
        assert "关于分红公告" in result

    def test_multiple_items(self):
        """多条公告。"""
        items = [
            {"title": "公告1", "notice_date": "2026-06-20"},
            {"title": "公告2", "notice_date": "2026-06-19"},
            {"title": "公告3", "notice_date": "2026-06-18"},
        ]
        result = render_announcements(items)
        lines = result.strip().split("\n")
        assert len(lines) == 3

    def test_max_10_items(self):
        """最多显示 10 条。"""
        items = [
            {"title": f"公告{i}", "notice_date": f"2026-06-{20-i:02d}"}
            for i in range(15)
        ]
        result = render_announcements(items)
        lines = result.strip().split("\n")
        assert len(lines) == 10

    def test_missing_fields(self):
        """字段缺失时不崩溃。"""
        items = [{"title": "", "notice_date": ""}]
        result = render_announcements(items)
        assert "|" in result

    def test_alternative_date_field(self):
        """支持 notice_time 字段。"""
        items = [{"title": "测试公告", "notice_time": "2026-06-20 10:00:00"}]
        result = render_announcements(items)
        assert "2026-06-20" in result


class TestRenderReports:
    """render_reports 函数测试。"""

    def test_empty_list(self):
        """空列表返回提示。"""
        assert render_reports([]) == "(无研报)"

    def test_single_report(self):
        """单条研报。"""
        items = [
            {"title": "深度报告", "orgSName": "中信证券", "publishDate": "2026-06-20"}
        ]
        result = render_reports(items)
        assert "中信证券" in result
        assert "深度报告" in result
        assert "2026-06-20" in result

    def test_multiple_reports(self):
        """多条研报。"""
        items = [
            {"title": "报告1", "orgSName": "中信", "publishDate": "2026-06-20"},
            {"title": "报告2", "orgSName": "海通", "publishDate": "2026-06-19"},
        ]
        result = render_reports(items)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_max_10_reports(self):
        """最多显示 10 条。"""
        items = [
            {"title": f"报告{i}", "orgSName": "券商", "publishDate": "2026-06-20"}
            for i in range(15)
        ]
        result = render_reports(items)
        lines = result.strip().split("\n")
        assert len(lines) == 10


class TestFetchAnnouncements:
    """fetch_announcements 函数测试（mock HTTP）。"""

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_success(self, mock_cache, mock_http):
        """成功获取公告数据。"""
        mock_cache.return_value = None
        mock_http.return_value = (
            '{"data": {"list": [{"title": "测试公告", "notice_date": "2026-06-20"}]}}'
        )
        result = fetch_announcements("sh600989", use_cache=False)
        assert len(result) == 1
        assert result[0]["title"] == "测试公告"

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_empty(self, mock_cache, mock_http):
        """无公告数据。"""
        mock_cache.return_value = None
        mock_http.return_value = '{"data": {"list": []}}'
        result = fetch_announcements("sh600989", use_cache=False)
        assert result == []

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_json_error(self, mock_cache, mock_http):
        """JSON 解析失败返回空列表。"""
        mock_cache.return_value = None
        mock_http.return_value = "invalid json"
        result = fetch_announcements("sh600989", use_cache=False)
        assert result == []

    @patch("announcements.cache_get")
    def test_fetch_cache_hit(self, mock_cache):
        """缓存命中时直接返回。"""
        mock_cache.return_value = '[{"title": "缓存公告"}]'
        result = fetch_announcements("sh600989", use_cache=True)
        assert len(result) == 1
        assert result[0]["title"] == "缓存公告"


class TestFetchReports:
    """fetch_reports 函数测试（mock HTTP）。"""

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_success(self, mock_cache, mock_http):
        """成功获取研报数据。"""
        mock_cache.return_value = None
        mock_http.return_value = (
            '{"hits": 1, "data": [{"title": "深度报告", "orgSName": "中信"}]}'
        )
        result = fetch_reports("sh600989", use_cache=False)
        assert len(result) == 1
        assert result[0]["title"] == "深度报告"

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_empty(self, mock_cache, mock_http):
        """无研报数据。"""
        mock_cache.return_value = None
        mock_http.return_value = '{"hits": 0, "data": []}'
        result = fetch_reports("sh600989", use_cache=False)
        assert result == []

    @patch("announcements.http_get")
    @patch("announcements.cache_get")
    def test_fetch_json_error(self, mock_cache, mock_http):
        """JSON 解析失败返回空列表。"""
        mock_cache.return_value = None
        mock_http.return_value = "invalid json"
        result = fetch_reports("sh600989", use_cache=False)
        assert result == []

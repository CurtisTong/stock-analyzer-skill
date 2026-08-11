"""scripts/monitor.py 顶层健康检查 CLI 的单元测试。

覆盖 check_cache_status + format_sources_table。
不发起真实网络请求。

注意：scripts/monitor.py 是顶层模块而非包，但 Python "包优先于同名模块" 的
import 规则会优先加载 scripts/monitor/ 包。为避免命名冲突，本测试使用
importlib 直接加载顶层 monitor.py 源码。

按 FRAMEWORK.md 规范：覆盖 cache 统计 + 表格格式化 + 数据源扫描。
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def monitor_cli():
    """加载 scripts/monitor.py 顶层文件（避开 monitor 包命名冲突），模块级缓存。"""
    spec = importlib.util.spec_from_file_location(
        "monitor_cli",
        Path(__file__).parent.parent.parent / "scripts" / "monitor.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────────────────────────────────────────
# check_cache_status：缓存目录统计
# ────────────────────────────────────────────────────────────────


class TestCheckCacheStatus:
    """缓存目录状态扫描。"""

    def test_missing_cache_dir_returns_zeros(self, monitor_cli, tmp_path: Path):
        """缓存目录不存在时返回全 0 结果而非抛错。"""
        with patch.object(monitor_cli, "CACHE_DIR", tmp_path / "nonexistent"):
            result = monitor_cli.check_cache_status()
        assert result == {
            "total_files": 0,
            "total_size_kb": 0.0,
            "expired_files": 0,
            "by_prefix": {},
        }

    def test_empty_cache_dir_returns_zeros(self, monitor_cli, tmp_path: Path):
        """空缓存目录返回 0 文件统计。"""
        with patch.object(monitor_cli, "CACHE_DIR", tmp_path):
            result = monitor_cli.check_cache_status()
        assert result["total_files"] == 0
        assert result["total_size_kb"] == 0.0
        assert result["expired_files"] == 0

    def test_counts_cache_files(self, monitor_cli, tmp_path: Path):
        """扫描 *.cache 文件并统计大小与数量。"""
        (tmp_path / "sh600519_2026-08-07.cache").write_bytes(b"x" * 2048)
        (tmp_path / "sz000001_2026-08-07.cache").write_bytes(b"y" * 1024)
        (tmp_path / "ignored.txt").write_bytes(b"z")  # 非 .cache 文件应忽略

        with patch.object(monitor_cli, "CACHE_DIR", tmp_path):
            result = monitor_cli.check_cache_status()
        assert result["total_files"] == 2
        assert result["total_size_kb"] == 3.0  # (2048+1024)/1024
        assert result["by_prefix"] == {"sh600519": 1, "sz000001": 1}

    def test_marks_expired_files(self, monitor_cli, tmp_path: Path):
        """超过 6 小时未访问的文件标记为 expired。"""
        import os

        old_file = tmp_path / "old.cache"
        old_file.write_bytes(b"x" * 100)
        # 修改 mtime 到 7 小时前
        seven_hours_ago = time.time() - 7 * 3600
        os.utime(old_file, (seven_hours_ago, seven_hours_ago))

        fresh_file = tmp_path / "fresh.cache"
        fresh_file.write_bytes(b"y" * 100)

        with patch.object(monitor_cli, "CACHE_DIR", tmp_path):
            result = monitor_cli.check_cache_status()
        assert result["total_files"] == 2
        assert result["expired_files"] == 1

    def test_groups_files_by_prefix(self, monitor_cli, tmp_path: Path):
        """按文件名首段前缀分组统计。"""
        (tmp_path / "sh600519_x.cache").write_bytes(b"a")
        (tmp_path / "sh600989_x.cache").write_bytes(b"b")
        (tmp_path / "sz000001_x.cache").write_bytes(b"c")
        (tmp_path / "no_prefix.cache").write_bytes(b"d")

        with patch.object(monitor_cli, "CACHE_DIR", tmp_path):
            result = monitor_cli.check_cache_status()
        assert result["by_prefix"] == {
            "sh600519": 1,
            "sh600989": 1,
            "sz000001": 1,
            "no": 1,  # 按下划线 split 第一段
        }


# ────────────────────────────────────────────────────────────────
# format_sources_table：数据源表格格式化
# ────────────────────────────────────────────────────────────────


class TestFormatSourcesTable:
    """数据源健康度矩阵格式化。"""

    def test_empty_dict_returns_no_content(self, monitor_cli):
        """空 dict 返回空字符串（不会 print 任何行）。"""
        assert monitor_cli.format_sources_table({}) == ""

    def test_formats_multiple_domains(self, monitor_cli):
        """多数据域（quote/kline/finance）均正确输出。"""
        sources = {
            "quote": [
                {
                    "name": "tencent",
                    "priority": 10,
                    "available": True,
                    "state": "closed",
                    "failure_count": 0,
                },
                {
                    "name": "eastmoney",
                    "priority": 8,
                    "available": False,
                    "state": "open",
                    "failure_count": 5,
                },
            ],
            "kline": [
                {
                    "name": "akshare",
                    "priority": 5,
                    "available": True,
                    "state": "half_open",
                    "failure_count": 2,
                },
            ],
        }
        out = monitor_cli.format_sources_table(sources)
        assert "=== quote 数据源 ===" in out
        assert "=== kline 数据源 ===" in out
        assert "tencent" in out and "✅" in out
        assert "eastmoney" in out and "❌" in out
        assert "akshare" in out
        assert "试探" in out  # half_open 标签
        assert "熔断" in out  # open 标签

    def test_unknown_state_label_falls_back_to_value(self, monitor_cli):
        """未知熔断状态值直接显示原值而非抛错。"""
        sources = {
            "quote": [
                {
                    "name": "test",
                    "priority": 1,
                    "available": True,
                    "state": "weird_state",
                    "failure_count": 0,
                }
            ]
        }
        out = monitor_cli.format_sources_table(sources)
        assert "weird_state" in out  # 未知状态值原样输出

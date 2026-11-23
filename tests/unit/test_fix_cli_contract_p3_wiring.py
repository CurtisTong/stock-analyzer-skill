"""[review P3] CLI 接线回归测试：sector_summary 错误处理 / hot_rank 模块头。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import hot_rank
import sector_summary

PKG_ROOT = Path(__file__).resolve().parent.parent.parent


class TestSectorSummaryHandleErrors:
    def test_fetch_exception_exits_1_with_message(self, monkeypatch, capsys):
        """[review P3] main 未接 handle_errors 时异常直接冒 traceback。"""
        def boom(*args, **kwargs):
            raise ValueError("模拟板块抓取失败")

        monkeypatch.setattr(sector_summary, "fetch_sector_summary", boom)
        monkeypatch.setenv("STOCK_DEBUG", "1")  # handle_errors 默认隐藏细节
        monkeypatch.setattr(sys, "argv", ["sector_summary.py", "-j"])
        with pytest.raises(SystemExit) as exc:
            sector_summary.main()
        assert exc.value.code == 1
        assert "模拟板块抓取失败" in capsys.readouterr().err

    def test_json_success_still_works(self, monkeypatch, capsys):
        """[review P3] 接入 handle_errors 不破坏正常 JSON 输出。"""
        monkeypatch.setattr(
            sector_summary,
            "fetch_sector_summary",
            lambda **kwargs: {
                "as_of": "2026-11-21T10:00:00",
                "source": "ths",
                "items": [],
                "data_quality": {"degraded_fields": [], "source": "ths"},
            },
        )
        monkeypatch.setattr(sys, "argv", ["sector_summary.py", "-j"])
        sector_summary.main()
        payload = json.loads(capsys.readouterr().out)
        assert payload["source"] == "ths"


class TestHotRankModuleHeader:
    def test_module_docstring_is_preserved(self):
        """[review P3] import 挤在 docstring 前导致 __doc__ 为 None。"""
        assert hot_rank.__doc__ is not None
        assert "热度榜" in hot_rank.__doc__

    def test_import_after_sys_path_insert(self):
        """[review P3] 项目内 import 必须排在 sys.path.insert 之后。"""
        source = (PKG_ROOT / "scripts" / "hot_rank.py").read_text(encoding="utf-8")
        docstring_end = source.index('"""', source.index('"""') + 3)
        path_insert = source.index("sys.path.insert")
        silent_import = source.index("from common.exceptions.silent_fallback import log_silent_fallback")
        assert docstring_end < source.index("import argparse")
        assert path_insert < silent_import

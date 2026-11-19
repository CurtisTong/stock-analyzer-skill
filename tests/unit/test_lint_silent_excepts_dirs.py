"""静默吞错 lint 的 --dirs 分批清零参数（P0-4c）。

为什么需要：全仓 90+ 处裸 except Exception 一次性 strict 会逼所有人一天内重排
错误处理；分批清零要求 lint 支持"只对已清零目录阻断"，同时保留全仓 advisory。

本文件只测参数解析与作用范围，不依赖仓库当前的真实清零进度
（用 tmp_path 造样本文件，避免"扫的是仓库自身"导致用例随他人提交变红）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_LINT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "dev" / "lint_silent_excepts.py"


@pytest.fixture(scope="module")
def lint_mod():
    spec = importlib.util.spec_from_file_location("lint_silent_excepts_under_test", _LINT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _write_bad(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception:\n"
        "        return 0\n",
        encoding="utf-8",
    )


def _write_good(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "def f():\n"
        "    try:\n"
        "        return 1\n"
        "    except Exception as e:\n"
        "        log_silent_fallback('x.f', e)\n"
        "        return 0\n",
        encoding="utf-8",
    )


class TestDirArgParsing:
    def test_space_form(self, lint_mod):
        assert lint_mod._parse_dirs(["x.py", "--dirs", "scripts/common,scripts/data"]) == [
            Path("scripts/common"),
            Path("scripts/data"),
        ]

    def test_equals_form(self, lint_mod):
        assert lint_mod._parse_dirs(["--dirs=scripts/business"]) == [Path("scripts/business")]

    def test_absent_means_full_scan(self, lint_mod):
        assert lint_mod._parse_dirs(["lint_silent_excepts.py"]) is None


class TestScope:
    def test_bad_file_in_scanned_dir_is_reported(self, lint_mod, tmp_path):
        _write_bad(tmp_path / "pkg" / "bad.py")
        _, adv = lint_mod.check_file(tmp_path / "pkg" / "bad.py")
        assert adv, "裸 except 必须被报告"

    def test_logged_except_is_compliant(self, lint_mod, tmp_path):
        _write_good(tmp_path / "pkg" / "good.py")
        _, adv = lint_mod.check_file(tmp_path / "pkg" / "good.py")
        assert adv == []

    def test_missing_dir_exits_2(self, lint_mod, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["lint", "--strict", "--dirs", "no_such_dir"])
        assert lint_mod.main() == 2
        assert "目录不存在" in capsys.readouterr().err

    def test_clean_dir_passes_strict(self, lint_mod, monkeypatch, tmp_path):
        _write_good(tmp_path / "pkg" / "ok.py")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["lint", "--strict", "--dirs", "pkg"])
        assert lint_mod.main() == 0

    def test_dirty_dir_blocks_in_strict(self, lint_mod, monkeypatch, tmp_path):
        _write_bad(tmp_path / "pkg" / "bad.py")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["lint", "--strict", "--dirs", "pkg"])
        assert lint_mod.main() == 1

"""零安装冒烟门禁的解析与软链校验测试。

不跑真实 install.sh（那会改开发机 ~/.claude 并拖慢单测），只锁住两段
纯逻辑：软链完整性判定 + init_pool 人类可读前缀之后的 JSON 抽取。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PKG_ROOT / "scripts" / "dev"))

import check_install_smoke as smoke  # noqa: E402


class TestParsePoolOutput:
    def test_accepts_human_prefix_before_json(self):
        stdout = "✅ 股票池已存在（14 个板块，280 只股票），跳过初始化\n" '{"status": "ok", "mode": "default"}\n'
        assert smoke.parse_pool_output(stdout) == "ok"

    def test_rejects_non_ok_status(self):
        with pytest.raises(smoke.SmokeFailure, match="非 ok"):
            smoke.parse_pool_output('{"status": "degraded"}')

    def test_rejects_non_json(self):
        with pytest.raises(smoke.SmokeFailure, match="不是合法 JSON"):
            smoke.parse_pool_output("Traceback: boom")


class TestCheckLinks:
    def _make_links(self, home: Path, dangling: tuple[str, ...] = ()) -> None:
        for root in (home / ".claude" / "skills", home / ".codex" / "skills"):
            root.mkdir(parents=True)
            for skill in smoke.SKILLS:
                target = home / "src" / skill
                target.mkdir(parents=True, exist_ok=True)
                (root / skill).symlink_to(target if skill not in dangling else home / "missing" / skill)

    def test_all_links_valid(self, tmp_path):
        self._make_links(tmp_path)
        assert smoke.check_links(tmp_path) == []

    def test_dangling_link_reported(self, tmp_path):
        self._make_links(tmp_path, dangling=("stock",))
        problems = smoke.check_links(tmp_path)
        assert any("悬空" in p for p in problems)

    def test_missing_link_reported(self, tmp_path):
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        problems = smoke.check_links(tmp_path)
        assert len(problems) == len(smoke.SKILLS) * 2
        assert all("不是软链" in p for p in problems)

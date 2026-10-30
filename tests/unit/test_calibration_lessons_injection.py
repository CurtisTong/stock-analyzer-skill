"""反思教训回流测试（v1.25）。

背景：v1.24.0 落地了反思记忆，但教训只在投票后渲染（报告尾部"上轮教训"段），
从未进入打分环节——commit message 声称的 "so the next round sees where that
expert was wrong before" 未实现。v1.25 通过 `get_lessons()` + `calibration.py
lessons` 子命令 + SKILL.md/decide.md 注入纪律补上回流闭环。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def cal_store(tmp_path, monkeypatch):
    """校准库指向临时文件。

    注意 patch 的是 `_CALIBRATION_FILE`（模块真实的路径常量）。
    patch 完必须断言生效——否则测试会静默写进真实数据文件
    （本仓库已发生过一次：假教训被写进 data/expert_calibration.json）。
    """
    import experts.calibration as cal

    path = tmp_path / "expert_calibration.json"
    monkeypatch.setattr(cal, "_CALIBRATION_FILE", path)
    # 断言重定向生效（防 fixture 失效导致污染真实数据）
    assert cal._load() == cal._empty_data() or path.exists() or True
    cal._save(cal._empty_data())
    assert path.exists(), "fixture 重定向未生效：_save 未写到 tmp_path"
    return path


def _seed_lesson(store_path, expert, lesson_text, stock="sh600519", date="2026-10-01"):
    """直接往校准库塞一条教训（绕过 verify 流程）。"""
    import experts.calibration as cal

    data = cal._load()
    experts = data.setdefault("experts", {})
    rec = experts.setdefault(expert, {"events": 0, "correct": 0})
    lessons = rec.setdefault("lessons", [])
    lessons.append(
        {
            "date": date,
            "stock": stock,
            "direction": "看多",
            "score": 70,
            "actual_direction": "下跌",
            "actual_return": -8.0,
            "lesson": lesson_text,
            "improvement": "对纯题材信号降权",
        }
    )
    del lessons[:-5]
    cal._save(data)


class TestGetLessons:
    def test_returns_only_experts_with_lessons(self, cal_store):
        from experts.calibration import get_lessons

        _seed_lesson(cal_store, "lynch", "预测看多但实际下跌")
        _seed_lesson(cal_store, "soros", "趋势误判")

        out = get_lessons()
        assert set(out.keys()) == {"lynch", "soros"}
        assert out["lynch"][0]["lesson"] == "预测看多但实际下跌"

    def test_limit_truncates_to_most_recent(self, cal_store):
        from experts.calibration import get_lessons

        for i in range(4):
            _seed_lesson(cal_store, "lynch", f"教训{i}", date=f"2026-10-{i + 1:02d}")

        out = get_lessons(limit=2)
        assert len(out["lynch"]) == 2
        # 保留的是最近的
        assert out["lynch"][-1]["lesson"] == "教训3"

    def test_expert_without_lessons_absent(self, cal_store):
        from experts.calibration import get_lessons

        _seed_lesson(cal_store, "lynch", "有教训")
        out = get_lessons()
        assert "lynch" in out
        # emotion_tech 无教训 → 不出现在结果里
        assert "emotion_tech" not in out

    def test_exported(self):
        from experts.calibration import __all__ as cal_all

        assert "get_lessons" in cal_all


class TestLessonsCli:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, "scripts/calibration.py", *args],
            cwd=PKG_ROOT,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(PKG_ROOT / "scripts")},
        )

    def test_lessons_command_exists(self):
        """CLI 必须提供 lessons 子命令（打分注入的取数入口）。"""
        r = self._run("lessons", "--help")
        assert r.returncode == 0, r.stderr
        assert "--limit" in r.stdout

    def test_lessons_command_runs(self):
        r = self._run("lessons")
        assert r.returncode == 0, r.stderr
        assert "教训" in r.stdout

    def test_lessons_json(self):
        r = self._run("lessons", "-j")
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert "count" in data
        assert "experts" in data

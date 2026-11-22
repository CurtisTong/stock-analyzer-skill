"""[review P1-21] refresh_pool / snapshots JSON 输出混流与参数覆盖回归测试。

修复前：
- refresh_pool `--diff -j` 把人类可读 diff print 到 stdout，与 JSON 混流；
- snapshots `-j diff A B` 被子命令 -j 默认值覆盖，输出文本而非 JSON。
本测试锁定：JSON 模式 stdout 只有合法 JSON，diff 文本走 stderr。
"""

from __future__ import annotations

import json
import sys

import pytest

import refresh_pool as rp
import snapshots


def _run_main(monkeypatch, capsys, module, argv):
    monkeypatch.setattr(sys, "argv", [argv[0], *argv[1:]])
    module.main()
    return capsys.readouterr()


class TestRefreshPoolJsonStream:
    @pytest.mark.parametrize("argv", [["refresh_pool.py", "--diff", "-j"], ["refresh_pool.py", "-j", "--diff"]])
    def test_diff_json_stdout_is_pure_json(self, monkeypatch, capsys, argv):
        """[review P1-21] -j 模式下 diff 文本必须降到 stderr。"""
        monkeypatch.setattr(rp, "load_current_pool", lambda: {"机器人": ["sh600000"]})
        monkeypatch.setattr(
            rp,
            "refresh_pool",
            lambda **kwargs: {"机器人": ["sh600000", "sh600001"]},
        )
        captured = _run_main(monkeypatch, capsys, rp, argv)
        payload = json.loads(captured.out)  # 纯 JSON
        assert payload["status"] == "ok"
        assert "股票池变更对比" in captured.err
        assert "股票池变更对比" not in captured.out

    def test_text_mode_still_prints_diff_to_stdout(self, monkeypatch, capsys):
        """[review P1-21] 非 JSON 模式保持原有 diff 输出（向后兼容）。"""
        monkeypatch.setattr(rp, "load_current_pool", lambda: {"机器人": ["sh600000"]})
        monkeypatch.setattr(rp, "refresh_pool", lambda **kwargs: {"机器人": ["sh600001"]})
        captured = _run_main(monkeypatch, capsys, rp, ["refresh_pool.py", "--diff"])
        assert "股票池变更对比" in captured.out


class TestSnapshotsJsonStream:
    @pytest.fixture()
    def two_snapshots(self, tmp_path, monkeypatch):
        monkeypatch.setattr(snapshots, "DATA_DIR", str(tmp_path / "data"))
        a = snapshots.save_snapshot("balanced", [{"code": "sh600519", "name": "茅台", "score": 80}], ["sh600519"])
        b = snapshots.save_snapshot(
            "balanced",
            [{"code": "sh600519", "name": "茅台", "score": 85}, {"code": "sh600000", "name": "浦发", "score": 70}],
            ["sh600519", "sh600000"],
        )
        return a, b

    @pytest.mark.parametrize(
        "flag_order",
        [["-j", "diff"], ["diff", "-j"]],
    )
    def test_diff_json_both_orders(self, monkeypatch, capsys, two_snapshots, flag_order):
        """[review P1-21] -j 前置/后置的 diff 都输出纯 JSON。"""
        a, b = two_snapshots
        argv = ["snapshots.py", *flag_order, str(a), str(b)]
        captured = _run_main(monkeypatch, capsys, snapshots, argv)
        payload = json.loads(captured.out)
        assert "added" in payload and "removed" in payload
        assert "sh600000" in payload["added"]

    @pytest.mark.parametrize("argv", [["snapshots.py", "-j", "list"], ["snapshots.py", "list", "-j"]])
    def test_list_json_both_orders(self, monkeypatch, capsys, two_snapshots, argv):
        """[review P1-21] list 子命令同样不能被 -j 覆盖成文本输出。"""
        captured = _run_main(monkeypatch, capsys, snapshots, argv)
        payload = json.loads(captured.out)
        assert payload["count"] == 2
        assert all(str(p).endswith(".json") for p in payload["items"])

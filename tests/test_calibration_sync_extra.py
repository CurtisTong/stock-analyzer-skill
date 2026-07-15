"""calibration_sync.py 补充测试：auto/status/push/main 的更多分支。

补充覆盖 auto()（本地>=远程推送 / 远程>本地跳过 / 无 gist 创建）、
push()（更新已有 gist / 创建新 gist）、status()（远程可读 / 远程不可读 / 本地存在）、
pull()（备份本地数据路径 / 远程数据结构无效 / 远程不可读）、main() 分发。
所有 subprocess/文件 I/O 均 mock。
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import calibration_sync


# ═══════════════════════════════════════════════════════════════
# push：更新已有 gist / 创建新 gist
# ═══════════════════════════════════════════════════════════════


class TestPushBranches:
    def test_push_updates_existing_gist(self, tmp_path, capsys):
        """push 时 gist 已存在 -> 更新。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(
            json.dumps({"predictions": [{"stock": "sh600519", "expert_scores": {}}]}),
            encoding="utf-8",
        )
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(
                calibration_sync, "_update_gist", return_value=True
            ) as mock_update,
        ):
            result = calibration_sync.push()
        assert result is True
        mock_update.assert_called_once()
        captured = capsys.readouterr()
        assert "更新" in captured.out

    def test_push_update_fails(self, tmp_path, capsys):
        """push 更新失败时返回 False。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_update_gist", return_value=False),
        ):
            result = calibration_sync.push()
        assert result is False
        captured = capsys.readouterr()
        assert "失败" in captured.out

    def test_push_creates_new_gist(self, tmp_path, capsys):
        """push 时无 gist -> 创建。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value=None),
            patch.object(calibration_sync, "_create_gist", return_value="newgist456"),
        ):
            result = calibration_sync.push()
        assert result is True
        captured = capsys.readouterr()
        assert "创建" in captured.out

    def test_push_create_fails(self, tmp_path, capsys):
        """push 创建失败（返回 None）时返回 False。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value=None),
            patch.object(calibration_sync, "_create_gist", return_value=None),
        ):
            result = calibration_sync.push()
        assert result is False
        captured = capsys.readouterr()
        assert "失败" in captured.out


# ═══════════════════════════════════════════════════════════════
# auto：本地>=远程推送 / 远程>本地跳过 / 无 gist 创建 / 无本地文件
# ═══════════════════════════════════════════════════════════════


class TestAutoBranches:
    def test_auto_local_more_pushes(self, tmp_path, capsys):
        """本地 predictions >= 远程 -> 推送。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(
            json.dumps(
                {
                    "predictions": [
                        {"stock": "sh600519", "expert_scores": {}},
                        {"stock": "sh600000", "expert_scores": {}},
                    ]
                }
            ),
            encoding="utf-8",
        )
        remote = {"predictions": [{"stock": "sz000001", "expert_scores": {}}]}
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_get_gist_content", return_value=remote),
            patch.object(calibration_sync, "pull", return_value=True),
            patch.object(calibration_sync, "push", return_value=True) as mock_push,
        ):
            result = calibration_sync.auto()
        assert result is True
        mock_push.assert_called_once()
        captured = capsys.readouterr()
        assert "本地数据更多" in captured.out

    def test_auto_remote_more_skips_push(self, tmp_path, capsys):
        """远程 predictions > 本地 -> 跳过推送。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(
            json.dumps({"predictions": [{"stock": "sh600519", "expert_scores": {}}]}),
            encoding="utf-8",
        )
        remote = {
            "predictions": [
                {"stock": f"sh60000{i}", "expert_scores": {}} for i in range(5)
            ]
        }
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_get_gist_content", return_value=remote),
            patch.object(calibration_sync, "pull", return_value=True),
            patch.object(calibration_sync, "push") as mock_push,
        ):
            result = calibration_sync.auto()
        assert result is True
        mock_push.assert_not_called()
        captured = capsys.readouterr()
        assert "远程数据更多" in captured.out

    def test_auto_no_gist_creates(self, tmp_path, capsys):
        """无远程 gist -> 创建新 gist。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value=None),
            patch.object(calibration_sync, "pull", return_value=True),
            patch.object(calibration_sync, "push", return_value=True) as mock_push,
        ):
            result = calibration_sync.auto()
        assert result is True
        mock_push.assert_called_once()
        captured = capsys.readouterr()
        assert "创建" in captured.out

    def test_auto_no_local_file_returns_false(self, tmp_path, capsys):
        """pull 后本地文件不存在 -> 返回 False。"""
        with (
            patch.object(calibration_sync, "_find_gist", return_value=None),
            patch.object(calibration_sync, "pull", return_value=False),
            patch.object(calibration_sync, "_CALIBRATION_FILE", tmp_path / "nope.json"),
        ):
            result = calibration_sync.auto()
        assert result is False


# ═══════════════════════════════════════════════════════════════
# status：本地存在 / 远程可读 / 远程不可读
# ═══════════════════════════════════════════════════════════════


class TestStatusBranches:
    def test_status_with_local_and_remote(self, tmp_path, capsys):
        """本地存在 + 远程可读。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(
            json.dumps(
                {
                    "predictions": [
                        {"stock": "sh600519", "expert_scores": {}, "verified": True}
                    ],
                    "experts": {"lynch": {"events": 1}},
                }
            ),
            encoding="utf-8",
        )
        remote = {
            "predictions": [
                {"stock": "sh600000", "expert_scores": {}, "verified": False}
            ],
        }
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_get_gist_content", return_value=remote),
        ):
            calibration_sync.status()
        captured = capsys.readouterr()
        assert "本地" in captured.out
        assert "远程" in captured.out
        assert "gist123" in captured.out

    def test_status_gist_exists_but_unreadable(self, tmp_path, capsys):
        """gist 存在但无法读取。"""
        fake_file = tmp_path / "expert_calibration.json"
        fake_file.write_text(json.dumps({"predictions": []}), encoding="utf-8")
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist456"),
            patch.object(calibration_sync, "_get_gist_content", return_value=None),
        ):
            calibration_sync.status()
        captured = capsys.readouterr()
        assert "无法读取" in captured.out

    def test_status_no_local_data(self, capsys, tmp_path):
        """本地无数据文件。"""
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", tmp_path / "nope.json"),
            patch.object(calibration_sync, "_find_gist", return_value=None),
        ):
            calibration_sync.status()
        captured = capsys.readouterr()
        assert "无数据" in captured.out


# ═══════════════════════════════════════════════════════════════
# pull：备份路径 / 远程不可读
# ═══════════════════════════════════════════════════════════════


class TestPullBranches:
    def test_pull_backs_up_local_file(self, tmp_path, capsys):
        """pull 有效远程数据时备份本地文件到 .bak。"""
        fake_file = tmp_path / "expert_calibration.json"
        local_data = {
            "predictions": [{"stock": "sh600519", "expert_scores": {}}],
            "experts": {"lynch": {"events": 1}},
        }
        fake_file.write_text(json.dumps(local_data), encoding="utf-8")
        remote = {
            "predictions": [
                {
                    "stock": "sh600000",
                    "direction": "看多",
                    "expert_scores": {"lynch": 80},
                }
            ],
            "experts": {"lynch": {"events": 2}},
        }
        with (
            patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file),
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_get_gist_content", return_value=remote),
        ):
            result = calibration_sync.pull()
        assert result is True
        backup = fake_file.with_suffix(".json.bak")
        assert backup.exists()
        captured = capsys.readouterr()
        assert "备份" in captured.out

    def test_pull_remote_unreadable(self, tmp_path, capsys):
        """远程数据无法读取时返回 False。"""
        with (
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(calibration_sync, "_get_gist_content", return_value=None),
        ):
            result = calibration_sync.pull()
        assert result is False
        captured = capsys.readouterr()
        assert "无法读取" in captured.out

    def test_pull_rejects_non_dict_remote(self, tmp_path, capsys):
        """远程数据非 dict 时拒绝写入。"""
        with (
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(
                calibration_sync, "_get_gist_content", return_value="not a dict"
            ),
        ):
            result = calibration_sync.pull()
        assert result is False
        captured = capsys.readouterr()
        assert "拒绝" in captured.out or "无效" in captured.out

    def test_pull_rejects_predictions_not_list(self, tmp_path, capsys):
        """predictions 不是 list 时拒绝。"""
        bad_remote = {"predictions": "not_a_list"}
        with (
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(
                calibration_sync, "_get_gist_content", return_value=bad_remote
            ),
        ):
            result = calibration_sync.pull()
        assert result is False

    def test_pull_rejects_prediction_not_dict(self, tmp_path, capsys):
        """predictions 元素不是 dict 时拒绝。"""
        bad_remote = {"predictions": ["not_a_dict"]}
        with (
            patch.object(calibration_sync, "_find_gist", return_value="gist123"),
            patch.object(
                calibration_sync, "_get_gist_content", return_value=bad_remote
            ),
        ):
            result = calibration_sync.pull()
        assert result is False


# ═══════════════════════════════════════════════════════════════
# main：子命令分发
# ═══════════════════════════════════════════════════════════════


class TestMain:
    def test_main_pull(self):
        with patch.object(calibration_sync, "pull", return_value=True) as mock_pull:
            with patch("sys.argv", ["calibration_sync.py", "--pull"]):
                calibration_sync.main()
        mock_pull.assert_called_once()

    def test_main_push(self):
        with patch.object(calibration_sync, "push", return_value=True) as mock_push:
            with patch("sys.argv", ["calibration_sync.py", "--push"]):
                calibration_sync.main()
        mock_push.assert_called_once()

    def test_main_auto(self):
        with patch.object(calibration_sync, "auto", return_value=True) as mock_auto:
            with patch("sys.argv", ["calibration_sync.py", "--auto"]):
                calibration_sync.main()
        mock_auto.assert_called_once()

    def test_main_status(self):
        with patch.object(calibration_sync, "status") as mock_status:
            with patch("sys.argv", ["calibration_sync.py", "--status"]):
                calibration_sync.main()
        mock_status.assert_called_once()

    def test_main_no_args_exits(self):
        """无参数（required=True）时 argparse 报错退出。"""
        with patch("sys.argv", ["calibration_sync.py"]):
            with pytest.raises(SystemExit):
                calibration_sync.main()


# ═══════════════════════════════════════════════════════════════
# _create_gist / _update_gist：临时文件清理
# ═══════════════════════════════════════════════════════════════


class TestGistTempFiles:
    def test_create_gist_cleans_temp_file(self, tmp_path):
        """_create_gist 完成后删除临时文件。"""
        data = {"predictions": [{"stock": "sh600519", "expert_scores": {}}]}
        mock_result = MagicMock(
            returncode=0, stdout="https://gist.github.com/x/abc123", stderr=""
        )
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            gist_id = calibration_sync._create_gist(data)
        assert gist_id == "abc123"
        # 临时文件应被删除（os.unlink 在 finally 中调用）
        # mock_run 被调用时 tmp_path 已创建并写入
        assert mock_run.call_count == 1

    def test_update_gist_returns_true_on_success(self):
        data = {"predictions": []}
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._update_gist("gist123", data) is True

    def test_update_gist_returns_false_on_failure(self):
        data = {"predictions": []}
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._update_gist("gist123", data) is False

"""
测试 scripts/calibration_sync.py：校准数据 Gist 双向同步。

策略：mock subprocess.run 模拟 gh CLI 调用，避免真实 GitHub API。
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
# _run_gh: gh CLI 调用
# ═══════════════════════════════════════════════════════════════


class TestRunGh:
    def test_returns_tuple(self):
        """返回 (returncode, stdout, stderr)。"""
        mock_result = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            code, out, err = calibration_sync._run_gh(["--version"])
        assert code == 0
        assert out == "ok"
        assert err == ""

    def test_handles_gh_not_installed(self):
        """gh 未安装时返回错误。"""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            code, out, err = calibration_sync._run_gh(["--version"])
        assert code == 1
        assert "未安装" in err

    def test_handles_timeout(self):
        """gh 超时时返回错误。"""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30)):
            code, out, err = calibration_sync._run_gh(["--version"])
        assert code == 1
        assert "超时" in err


# ═══════════════════════════════════════════════════════════════
# _find_gist: 查找现有 gist
# ═══════════════════════════════════════════════════════════════


class TestFindGist:
    def test_returns_none_when_gh_fails(self):
        """gh 调用失败时返回 None。"""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._find_gist() is None

    def test_returns_none_when_invalid_json(self):
        """stdout 非 JSON 时返回 None。"""
        mock_result = MagicMock(returncode=0, stdout="not json", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._find_gist() is None

    def test_finds_matching_gist(self):
        """找到描述匹配的 gist。"""
        gists = json.dumps(
            [
                {"id": "abc123", "description": "other gist"},
                {"id": "xyz789", "description": calibration_sync._GIST_DESC},
            ]
        )
        mock_result = MagicMock(returncode=0, stdout=gists, stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._find_gist() == "xyz789"

    def test_finds_legacy_description(self):
        """兼容旧描述（"calibration" + "stock"）。"""
        gists = json.dumps(
            [
                {"id": "abc123", "description": "stock calibration data"},
            ]
        )
        mock_result = MagicMock(returncode=0, stdout=gists, stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._find_gist() == "abc123"

    def test_returns_none_when_no_match(self):
        """无匹配 gist 时返回 None。"""
        gists = json.dumps(
            [
                {"id": "abc", "description": "unrelated"},
            ]
        )
        mock_result = MagicMock(returncode=0, stdout=gists, stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._find_gist() is None


# ═══════════════════════════════════════════════════════════════
# _get_gist_content: 拉取 gist 内容
# ═══════════════════════════════════════════════════════════════


class TestGetGistContent:
    def test_returns_dict_on_success(self):
        """成功时返回 dict。"""
        data = {"predictions": [{"stock": "sh600989"}]}
        mock_result = MagicMock(returncode=0, stdout=json.dumps(data), stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = calibration_sync._get_gist_content("gist123")
        assert result == data

    def test_returns_none_on_failure(self):
        """失败时返回 None。"""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._get_gist_content("gist123") is None

    def test_returns_none_on_invalid_json(self):
        """无效 JSON 时返回 None。"""
        mock_result = MagicMock(returncode=0, stdout="not json", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._get_gist_content("gist123") is None


# ═══════════════════════════════════════════════════════════════
# _create_gist: 创建新 gist
# ═══════════════════════════════════════════════════════════════


class TestCreateGist:
    def test_returns_id_on_success(self):
        """成功时从 URL 提取 gist ID。"""
        mock_result = MagicMock(
            returncode=0,
            stdout="https://gist.github.com/user/new_gist_123\n",
            stderr="",
        )
        with patch("subprocess.run", return_value=mock_result):
            result = calibration_sync._create_gist({"data": "test"})
        assert result == "new_gist_123"

    def test_returns_none_on_failure(self):
        """失败时返回 None。"""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._create_gist({"data": "test"}) is None

    def test_returns_empty_id_when_no_url(self):
        """stdout 无 URL 时返回空字符串（实现容错弱，但行为可预测）。"""
        mock_result = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            result = calibration_sync._create_gist({"data": "test"})
        # 实现是 "".split("/")[-1] = ""，行为可预测但容错弱
        assert result == ""


# ═══════════════════════════════════════════════════════════════
# _update_gist: 更新现有 gist
# ═══════════════════════════════════════════════════════════════


class TestUpdateGist:
    def test_returns_true_on_success(self):
        """成功时返回 True。"""
        mock_result = MagicMock(returncode=0, stdout="ok", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._update_gist("gist123", {"data": "test"}) is True

    def test_returns_false_on_failure(self):
        """失败时返回 False。"""
        mock_result = MagicMock(returncode=1, stdout="", stderr="error")
        with patch("subprocess.run", return_value=mock_result):
            assert calibration_sync._update_gist("gist123", {"data": "test"}) is False


# ═══════════════════════════════════════════════════════════════
# pull / push / auto / status 集成（mock 所有外部依赖）
# ═══════════════════════════════════════════════════════════════


class TestSyncOperations:
    """端到端测试 pull/push/auto/status。"""

    def test_pull_no_gist(self, tmp_path, capsys):
        """pull 时无现有 gist。"""
        with patch.object(calibration_sync, "_find_gist", return_value=None):
            result = calibration_sync.pull()
        assert result is False
        captured = capsys.readouterr()
        assert (
            "未找到" in captured.out or "不存在" in captured.out or "无" in captured.out
        )

    def test_push_no_local_file(self, capsys, tmp_path):
        """push 时无本地数据文件。"""
        # mock _CALIBRATION_FILE 路径为不存在的临时路径
        fake_file = tmp_path / "nonexistent.json"
        with patch.object(calibration_sync, "_CALIBRATION_FILE", fake_file):
            with patch.object(calibration_sync, "_find_gist", return_value=None):
                result = calibration_sync.push()
        assert result is False

    def test_status_no_gist(self, capsys):
        """status 时无 gist。"""
        with patch.object(calibration_sync, "_find_gist", return_value=None):
            calibration_sync.status()
        captured = capsys.readouterr()
        assert "未" in captured.out or "无" in captured.out or "不存在" in captured.out

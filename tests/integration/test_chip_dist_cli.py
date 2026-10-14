"""成本分布 CLI 集成测试（需要真实网络）。

默认 skip；运行方式：
    pytest --run-network tests/integration/test_chip_dist_cli.py

回归目标：图例逻辑（中际旭创式"上方密集区"）与低位沉淀（宝丰式"筹码在脚下"）
在真实数据上仍然成立。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.network


def _single(cli_runner, code: str) -> dict:
    result = cli_runner.run("chip_dist.py", code, "-j")
    result.assert_ok()
    return json.loads(result.stdout)


class TestChipDistCli:
    """CLI 契约与真实数据回归。"""

    def test_single_json_schema(self, cli_runner):
        """单股 JSON 返回 {meta, chip}，获利盘+套牢盘守恒。"""
        payload = _single(cli_runner, "sh600989")
        assert set(payload) == {"meta", "chip"}
        assert payload["chip"] is not None
        assert payload["meta"]["adjust"] in {"raw", "qfq"}
        chip = payload["chip"]
        assert chip["profit_ratio"] + chip["trapped_ratio"] == pytest.approx(100.0, abs=0.2)

    def test_batch_sorted_desc_by_trapped(self, cli_runner):
        """批量模式按套牢盘降序返回。"""
        result = cli_runner.run("chip_dist.py", "--codes", "sh600989,sh601689", "-j")
        result.assert_ok()
        payload = json.loads(result.stdout)
        assert payload["count"] == 2
        trapped = [it["trapped_ratio"] for it in payload["items"]]
        assert trapped == sorted(trapped, reverse=True)

    def test_baofeng_chip_at_foot(self, cli_runner):
        """宝丰能源：筹码沉淀在低位，密集区包住现价。"""
        chip = _single(cli_runner, "sh600989")["chip"]
        assert chip["tier"] == "筹码在脚下"
        assert chip["profit_ratio"] > 10.0
        assert chip["rebound_to_main_pct"] < 10.0

    def test_zhongji_xuchuang_deep_trap(self, cli_runner):
        """中际旭创：上方密集区在现价之上 15% 以上（图例逻辑）。"""
        chip = _single(cli_runner, "sz300308")["chip"]
        assert chip["tier"] == "深度套牢"
        assert chip["trapped_ratio"] > 85.0
        assert chip["rebound_to_main_pct"] > 15.0

    def test_text_mode_no_overhead_cluster_does_not_crash(self, cli_runner):
        """现价上方无筹码密集区（250 日新高）时文本渲染不得崩溃。

        回归：main_cluster=None -> 需反弹/墙厚为 None，曾因 f-string 直接格式化 None
        抛 TypeError。工商银行长期位于窗口新高，是该路径的稳定样本。
        """
        result = cli_runner.run("chip_dist.py", "sh601398")
        result.assert_ok()
        assert "主密集区 无" in result.stdout

    def test_batch_keeps_failed_code(self, cli_runner):
        """批量模式：取数失败的代码保留为行，不被静默丢弃。"""
        result = cli_runner.run("chip_dist.py", "--codes", "sh600989,sh999999")
        result.assert_ok()
        assert "sh999999" in result.stdout
        assert "取数失败" in result.stdout

    def test_technical_chip_flag_renders(self, cli_runner):
        """technical.py --chip 在无上方密集区标的上同样可渲染（回归 report.py None 格式化）。"""
        result = cli_runner.run("technical.py", "sh601398", "--chip")
        result.assert_ok()
        assert "成本分布" in result.stdout
        assert "主密集区 无" in result.stdout

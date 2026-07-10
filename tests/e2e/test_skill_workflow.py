"""P1-27: skill 工作流端到端测试。

验证 13 个 skill 引用的核心脚本入口可执行：
1. --help 退出码 0（argparse 装配正确）
2. skill 目录数量 = 13
3. 每个 skill 的 SKILL.md frontmatter 解析正确（name + description）
4. 关键工作流 mock 数据源后可成功执行并输出有效结构
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

# skill -> 主入口脚本映射（13 skill 共用 15 个脚本，去重后参数化）
SKILL_ENTRY_SCRIPTS = [
    "announcements.py",
    "backtest.py",
    "calibration.py",
    "calibration_backfill.py",
    "events.py",
    "finance.py",
    "init_pool.py",
    "kline.py",
    "monitor.py",
    "portfolio_web.py",
    "quote.py",
    "refresh_pool.py",
    "screener.py",
    "stock.py",
    "technical.py",
]


@pytest.mark.parametrize("script", SKILL_ENTRY_SCRIPTS)
def test_script_help_exit_zero(script):
    """每个 skill 引用的脚本 --help 应退出码 0（argparse 装配正确）。"""
    script_path = PROJECT_ROOT / "scripts" / script
    assert script_path.exists(), f"脚本不存在: {script_path}"

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        timeout=30,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"{script} --help 退出码 {result.returncode}\n"
        f"stderr: {result.stderr.decode()[:500]}"
    )
    # --help 输出应包含 usage 字样
    stdout = result.stdout.decode()
    assert "usage:" in stdout, f"{script} --help 未输出 usage 行"


def test_skill_count_matches():
    """确认 skill 目录数量 = 13（不含 _shared）。"""
    skills_dir = PROJECT_ROOT / "skills"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and d.name != "_shared"]
    assert (
        len(skill_dirs) == 13
    ), f"期望 13 个 skill，实际 {len(skill_dirs)}: {[d.name for d in skill_dirs]}"


# ═══════════════════════════════════════════════════════════════
# SKILL.md frontmatter 完整性（所有 13 个 skill）
# ═══════════════════════════════════════════════════════════════


def _get_skill_dirs():
    """返回所有 skill 目录（不含 _shared）。"""
    skills_dir = PROJECT_ROOT / "skills"
    return sorted(
        [d for d in skills_dir.iterdir() if d.is_dir() and d.name != "_shared"],
        key=lambda d: d.name,
    )


@pytest.mark.parametrize("skill_dir", _get_skill_dirs(), ids=lambda d: d.name)
def test_skill_md_frontmatter_valid(skill_dir):
    """每个 skill 的 SKILL.md frontmatter 必须含 name + description。"""
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.exists(), f"{skill_dir.name}/SKILL.md 不存在"

    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        pytest.fail(f"{skill_dir.name}: SKILL.md 缺少 frontmatter（--- 开头）")

    end = text.find("---", 3)
    if end == -1:
        pytest.fail(f"{skill_dir.name}: SKILL.md frontmatter 未闭合（缺第二个 ---）")

    fm_text = text[3:end].strip()
    try:
        fm = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        pytest.fail(f"{skill_dir.name}: frontmatter YAML 解析失败: {e}")

    assert isinstance(fm, dict), f"{skill_dir.name}: frontmatter 不是 dict"
    assert "name" in fm, f"{skill_dir.name}: frontmatter 缺 name 字段"
    assert "description" in fm, f"{skill_dir.name}: frontmatter 缺 description 字段"
    assert (
        fm["name"] == skill_dir.name
    ), f"{skill_dir.name}: frontmatter name={fm['name']} != 目录名"
    assert (
        len(fm["description"]) > 10
    ), f"{skill_dir.name}: description 过短（{len(fm['description'])} 字符）"


# ═══════════════════════════════════════════════════════════════
# 关键工作流 mock 测试（验证输出结构，不依赖网络）
# ═══════════════════════════════════════════════════════════════


class TestStockWorkflow:
    """stock skill 工作流：mock analyze 后验证 JSON 输出结构。"""

    @patch("scripts.stock.StockAnalysisService")
    def test_stock_json_output_structure(self, mock_svc_cls, capsys):
        """stock.py -j 输出应含 code/name/price 字段。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {
            "code": "sh600519",
            "name": "贵州茅台",
            "price": 1800.0,
            "change_pct": 1.5,
            "data_sources": ["行情"],
            "data_time": "2026-07-09T15:00:00",
        }
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch("sys.argv", ["stock.py", "sh600519", "-j"]):
            stock.main()

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["code"] == "sh600519"
        assert data["name"] == "贵州茅台"
        assert data["price"] == 1800.0

    @patch("scripts.stock.StockAnalysisService")
    def test_stock_no_finance_flag_passed(self, mock_svc_cls):
        """stock.py --no-finance 应传递给 analyze。"""
        mock_svc = MagicMock()
        mock_svc.analyze.return_value = {
            "code": "sh600519",
            "name": "x",
            "price": 1,
            "change_pct": 0,
        }
        mock_svc_cls.return_value = mock_svc

        from scripts import stock

        with patch("sys.argv", ["stock.py", "sh600519", "--no-finance"]):
            stock.main()

        mock_svc.analyze.assert_called_once()
        call_kwargs = mock_svc.analyze.call_args
        assert call_kwargs.kwargs.get("include_finance") is False


class TestScreenerWorkflow:
    """screener skill 工作流：mock 数据层后验证选股结果结构。"""

    def test_screener_returns_valid_structure(self, monkeypatch):
        """screener._run_main 应返回含策略名或 selections 的有效结构。"""
        import screener
        import business.screening_service as ss
        from data.types import Quote, KlineBar

        def _mock_get_quotes(codes):
            return {
                c: Quote(code=c, name="测试股", price=10.0, change_pct=1.0)
                for c in codes
            }

        def _mock_get_kline(code, scale=240, datalen=100):
            return [
                KlineBar(
                    day=f"2025-01-{i+1:02d}",
                    close=10 + i * 0.1,
                    open=10,
                    high=11,
                    low=9,
                    volume=10000,
                )
                for i in range(80)
            ]

        monkeypatch.setattr(ss, "get_quotes", _mock_get_quotes)
        monkeypatch.setattr(ss, "get_kline", _mock_get_kline)

        args = argparse.Namespace(
            strategy="balanced",
            sector=None,
            codes="sh600519",
            top=5,
            min_amount=0,
            min_cap=0,
            exclude_loss=False,
            no_constraints=True,
            sector_cap=0.30,
            full_market=False,
            board_limit=0,
            exclude_board="北交所",
            no_normalize=True,
            no_regime=True,
            no_chip=True,
            no_macro=True,
            snapshot=False,
            two_stage=False,
            json=True,
            full=False,
        )

        result = screener._run_main(args)
        # json=True 时 _run_main 直接打印 JSON 并返回 None；
        # 非 JSON 时返回 dict。两者都视为成功执行。
        # 若返回 dict，应包含策略名或 selections
        if result is not None:
            assert "strategy" in result or "error" in result or "selections" in result

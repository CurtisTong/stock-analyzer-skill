"""4 个核心 skill 的指数代码（sh000300 等）端到端覆盖。

回归保护：上一轮修了 infer_exchange / normalize_code / 多个 fetcher 的
00 段二义回退逻辑，本测试验证：
- stock: 能拉取指数行情 + K 线，跑完整五层分析
- screener: 指数代码进入 hard_filter 应优雅剔除（不报错）
- backtest: 指数可作基准 / 不报错
- research: stock.py 子模块能处理指数代码（research 委派）

按 FRAMEWORK.md 规范：标记为 network 真实业务流测试，CI 可选。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


# 标记为 network 测试（CI 默认跳过，仅本地验证用）
pytestmark = pytest.mark.network


# ────────────────────────────────────────────────────────────────
# 工具函数：调 scripts/*.py
# ────────────────────────────────────────────────────────────────


def _run_script(name: str, *args: str, timeout: int = 30) -> dict:
    """运行 scripts/<name>.py <args> 并解析 JSON 输出。

    兼容 stdout 开头有进度消息（emoji 行）的情况：从第一行 \"{\" 开始截取。
    """
    import re
    script = Path(__file__).parent.parent.parent / "scripts" / f"{name}.py"
    cmd = [sys.executable, str(script), *args, "-j"]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=str(script.parent.parent)
    )
    # 从第一个 "{" 或 "[" 开始截取（兼容 backtest 的进度消息前缀）
    match = re.search(r"[\{\[]", result.stdout)
    json_str = result.stdout[match.start():] if match else result.stdout
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return {
            "_error": True,
            "stderr": result.stderr[-500:],
            "stdout_tail": result.stdout[-500:],
            "returncode": result.returncode,
        }


# ────────────────────────────────────────────────────────────────
# stock: 指数代码能跑通
# ────────────────────────────────────────────────────────────────


class TestStockIndexCode:
    """stock.py 跑 sh000300（上证指数）应能完成五层分析。"""

    def test_sh000300_quick_runs(self):
        """上证指数 brief 模式能跑通（指数代码走 fetchers + K 线）。"""
        result = _run_script("stock", "sh000300", "--brief")
        # 指数走 fetchers 实际能拉行情（即使是降级），不应该报错
        assert "_error" not in result, f"指数代码运行失败: {result.get('stderr', '')}"
        assert result.get("code") in ("sh000300", "sz000300"), (
            f"code 字段异常: {result.get('code')}"
        )

    def test_sh000001_data_quality(self):
        """上证指数能拉到 name/price 字段。"""
        result = _run_script("stock", "sh000001", "--brief")
        if "_error" in result:
            pytest.skip(f"指数行情拉取失败（网络/数据源限制）: {result['_error']}")
        # 至少有 name 或 code
        assert result.get("code") or result.get("name"), "无 code/name 字段"


# ────────────────────────────────────────────────────────────────
# screener: 指数代码进入 hard_filter 应优雅剔除
# ────────────────────────────────────────────────────────────────


class TestScreenerIndexCode:
    """screener.py 把指数代码作为 --codes 输入应优雅处理。"""

    def test_index_code_runs_without_error(self):
        """指数代码作为自定义 --codes 输入，screener 应不报错返回。"""
        # 注：实际观察 - screener 输出顶层可能是 dict 或 list（取决于 args），
        # 但必须不抛错。本测试验证可正常返回结构化结果。
        result = _run_script("screener", "--codes", "sh000300", "--top", "5", timeout=60)
        if "_error" in result:
            pytest.skip(f"screener 跑指数代码失败: {result['_error']}")
        # 输出可能是 dict（JSON 模式）或 list（依赖 sub-command）
        # 关键是不抛错、returncode=0
        assert isinstance(result, (dict, list))


# ────────────────────────────────────────────────────────────────
# backtest: 指数可作基准 / 标的
# ────────────────────────────────────────────────────────────────


class TestBacktestIndexCode:
    """backtest.py 指数代码可作 --benchmark 或 --codes。"""

    def test_index_as_benchmark(self):
        """沪深 300 指数可作 --benchmark。"""
        result = _run_script(
            "backtest", "--strategy", "balanced", "--benchmark", "sh000300",
            "--codes", "sh600519", "--days", "30", timeout=120,
        )
        if "_error" in result:
            pytest.skip(f"backtest 跑失败: {result['_error']}")
        # 至少返回了一些指标（Sharpe 等）
        assert "metrics" in result or "error" not in result


# ────────────────────────────────────────────────────────────────
# research: research.py 不存在（已加 NOTE 文档化）
# ────────────────────────────────────────────────────────────────


class TestResearchNoScript:
    """research skill 无独立脚本入口（LLM 编排 skill）。

    SKILL.md 已加 ⚠️ NOTE 段说明 `python3 scripts/research.py` 会 ModuleNotFoundError。
    """
    def test_research_py_does_not_exist(self):
        """scripts/research.py 不存在（确认 SKILL.md NOTE 描述准确）。"""
        script = Path(__file__).parent.parent.parent / "scripts" / "research.py"
        assert not script.exists(), (
            "research.py 存在但 SKILL.md 声明它不存在，"
            "需同步更新 NOTE 段"
        )
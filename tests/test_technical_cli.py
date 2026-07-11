"""scripts/technical.py CLI 入口测试。

scripts/technical.py 被 technical/ 包遮蔽（同名包优先），
需用 importlib.util.spec_from_file_location 显式加载该文件模块，
测试 TechnicalInput dataclass、_compute_all() 和 main() CLI。
所有数据获取函数均 mock，避免网络请求。
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

# 必须先把 scripts 插入 sys.path，否则 technical.py 内部的
# `from common import ...` / `from technical.core import ...` 无法解析
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_TECHNICAL_PATH = SCRIPTS_DIR / "technical.py"


def _load_technical_cli_module():
    """用 importlib 加载 scripts/technical.py（避开 technical 包遮蔽）。"""
    spec = importlib.util.spec_from_file_location(
        "_technical_cli_under_test", str(_TECHNICAL_PATH)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 加载一次，后续测试复用
tech_cli = _load_technical_cli_module()


# ═══════════════════════════════════════════════════════════════
# 辅助：构造合法 K 线数据
# ═══════════════════════════════════════════════════════════════


def _make_records(n: int = 30, base: float = 10.0):
    """构造 n 条合法 K 线（close/open/high/low/volume 均 > 0）。"""
    records = []
    for i in range(n):
        price = base + i * 0.1
        records.append(
            {
                "date": f"2026-01-{i + 1:02d}",
                "open": price,
                "close": price + 0.05,
                "high": price + 0.2,
                "low": price - 0.1,
                "volume": 1000 + i * 10,
            }
        )
    return records


def _make_input(n: int = 30, classify: bool = False, no_chan: bool = False):
    """构造 TechnicalInput（不触发网络，数据本地构造）。"""
    records = _make_records(n)
    from technical.core import _parse_records

    closes, opens, highs, lows, volumes = _parse_records(records)
    args = MagicMock()
    args.classify = classify
    args.no_chan = no_chan
    args.market_index = None
    return tech_cli.TechnicalInput(
        closes=closes,
        opens=opens,
        highs=highs,
        lows=lows,
        volumes=volumes,
        records=records,
        board="主板",
        quote={"code": "sh600519", "name": "贵州茅台", "price": 10.0, "pe": 20},
        args=args,
    )


# ═══════════════════════════════════════════════════════════════
# 1. TechnicalInput dataclass
# ═══════════════════════════════════════════════════════════════


class TestTechnicalInput:
    def test_is_dataclass(self):
        from dataclasses import is_dataclass, fields

        assert is_dataclass(tech_cli.TechnicalInput)

    def test_fields_present(self):
        from dataclasses import fields

        names = {f.name for f in fields(tech_cli.TechnicalInput)}
        assert {
            "closes",
            "opens",
            "highs",
            "lows",
            "volumes",
            "records",
            "board",
            "quote",
        }.issubset(names)

    def test_args_default_none(self):
        inp = tech_cli.TechnicalInput(
            closes=[],
            opens=[],
            highs=[],
            lows=[],
            volumes=[],
            records=[],
            board="主板",
            quote={},
        )
        assert inp.args is None

    def test_construction_preserves_values(self):
        inp = _make_input(n=15)
        assert len(inp.closes) == 15
        assert inp.board == "主板"
        assert inp.quote["code"] == "sh600519"


# ═══════════════════════════════════════════════════════════════
# 2. _compute_all（基础模式，无 classify）
# ═══════════════════════════════════════════════════════════════


class TestComputeAllBasic:
    def test_returns_dict_with_core_features(self):
        inp = _make_input(n=40)
        features = tech_cli._compute_all(inp)
        assert isinstance(features, dict)
        for key in (
            "ma_system",
            "macd",
            "kdj",
            "bollinger",
            "rsi",
            "volume",
            "patterns",
            "support_resistance",
            "box",
            "wave",
            "limit_analysis",
            "valuation",
            "market_environment",
            "chan_theory",
            "local_patterns",
        ):
            assert key in features, f"缺少 {key}"

    def test_chan_theory_not_enabled_without_classify(self):
        inp = _make_input(n=40)
        features = tech_cli._compute_all(inp)
        assert features["chan_theory"]["valid"] is False
        assert "未启用" in features["chan_theory"]["error"]

    def test_market_environment_default_when_no_classify(self):
        inp = _make_input(n=40)
        features = tech_cli._compute_all(inp)
        me = features["market_environment"]
        assert me["state"] == "震荡"
        assert me["confidence"] == "低"

    def test_valuation_peg_zero_when_no_growth(self):
        inp = _make_input(n=40)
        features = tech_cli._compute_all(inp)
        assert features["valuation"]["peg"] == 0
        assert "pe_percentile" in features["valuation"]

    def test_breakout_empty_when_no_resistance(self):
        """nearest_resistance 为空时 breakout 为 {}。"""
        inp = _make_input(n=40)
        with patch.object(tech_cli, "support_resistance", return_value={}):
            features = tech_cli._compute_all(inp)
        assert features["breakout"] == {}


# ═══════════════════════════════════════════════════════════════
# 3. _compute_all（classify 模式）
# ═══════════════════════════════════════════════════════════════


class TestComputeAllClassify:
    def test_classify_triggers_classification_field(self):
        inp = _make_input(n=40, classify=True)
        with patch("classifier.classify_stock", return_value={"type": "白马股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch("strategies.thresholds.get_industry_threshold", side_effect=[15, 25, 40]):
            features = tech_cli._compute_all(inp)
        assert "classification" in features
        assert features["classification"]["type"] == "白马股"

    def test_classify_chan_enabled_with_enough_data(self):
        inp = _make_input(n=40, classify=True)
        with patch("classifier.classify_stock", return_value={"type": "普通股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch("strategies.thresholds.get_industry_threshold", side_effect=[15, 25, 40]), \
             patch("chan.chan_full_analysis", return_value={"valid": True, "state": "上升"}):
            features = tech_cli._compute_all(inp)
        assert features["chan_theory"]["valid"] is True

    def test_classify_no_chan_skips_chan(self):
        inp = _make_input(n=40, classify=True, no_chan=True)
        with patch("classifier.classify_stock", return_value={"type": "普通股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch("strategies.thresholds.get_industry_threshold", side_effect=[15, 25, 40]):
            features = tech_cli._compute_all(inp)
        assert features["chan_theory"]["valid"] is False
        # do_classify=True but no_chan -> else 分支，do_classify 为真 -> "数据不足"
        assert features["chan_theory"]["error"] == "数据不足"

    def test_classify_chan_skipped_when_data_insufficient(self):
        """records < 30 时跳过缠论。"""
        inp = _make_input(n=20, classify=True)
        with patch("classifier.classify_stock", return_value={"type": "普通股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch("strategies.thresholds.get_industry_threshold", side_effect=[15, 25, 40]):
            features = tech_cli._compute_all(inp)
        assert features["chan_theory"]["valid"] is False

    def test_classify_market_environment_with_market_index(self):
        inp = _make_input(n=40, classify=True)
        inp.args.market_index = "sh000001"
        with patch("classifier.classify_stock", return_value={"type": "普通股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch("strategies.thresholds.get_industry_threshold", side_effect=[15, 25, 40]), \
             patch("quote.fetch_batch", return_value=[{"code": "sh000001"}]), \
             patch.object(tech_cli, "detect_market_environment", return_value={"state": "牛市"}):
            features = tech_cli._compute_all(inp)
        assert features["market_environment"]["state"] == "牛市"

    def test_local_patterns_fallback_on_exception(self):
        inp = _make_input(n=40)
        with patch(
            "strategies.patterns.detect_all_local_patterns",
            side_effect=RuntimeError("boom"),
        ), patch("strategies.patterns.PatternInput", MagicMock()):
            features = tech_cli._compute_all(inp)
        lp = features["local_patterns"]
        assert lp["count"] == 0
        assert "失败" in lp["summary"]


# ═══════════════════════════════════════════════════════════════
# 4. main() CLI
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    def _setup_mocks(self, records=None, quote=None, datalen_ok=True):
        records = records if records is not None else _make_records(30)
        quote = quote or {"code": "sh600519", "name": "贵州茅台", "price": 10.0}
        return records, quote

    def test_main_json_output(self, capsys):
        records, quote = self._setup_mocks()
        with patch("sys.argv", ["technical.py", "sh600519", "-j"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]), \
             patch.object(tech_cli, "composite_score", return_value=75.0), \
             patch.object(tech_cli, "render_report", return_value="REPORT"), \
             patch.object(tech_cli, "render_quick", return_value="QUICK"):
            tech_cli.main()
        out = capsys.readouterr().out
        # JSON 模式输出 JSON（含 meta/score/features）
        assert '"meta"' in out and '"score"' in out

    def test_main_quick_output(self, capsys):
        records, quote = self._setup_mocks()
        with patch("sys.argv", ["technical.py", "sh600519", "--quick"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]), \
             patch.object(tech_cli, "composite_score", return_value=80.0), \
             patch.object(tech_cli, "render_quick", return_value="QUICK_REPORT"):
            tech_cli.main()
        assert "QUICK_REPORT" in capsys.readouterr().out

    def test_main_full_report(self, capsys):
        records, quote = self._setup_mocks()
        with patch("sys.argv", ["technical.py", "sh600519"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]), \
             patch.object(tech_cli, "composite_score", return_value=70.0), \
             patch.object(tech_cli, "render_report", return_value="FULL_REPORT"):
            tech_cli.main()
        assert "FULL_REPORT" in capsys.readouterr().out

    def test_main_exit_when_no_kline(self):
        with patch("sys.argv", ["technical.py", "sh600519"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=[]):
            with pytest.raises(SystemExit):
                tech_cli.main()

    def test_main_exit_when_no_quote(self):
        records, _ = self._setup_mocks()
        with patch("sys.argv", ["technical.py", "sh600519"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[]):
            with pytest.raises(SystemExit):
                tech_cli.main()

    def test_main_exit_when_data_insufficient(self):
        records, quote = self._setup_mocks(records=_make_records(5))
        with patch("sys.argv", ["technical.py", "sh600519"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]):
            with pytest.raises(SystemExit):
                tech_cli.main()

    def test_main_classify_json_includes_classify_features(self, capsys):
        records, quote = self._setup_mocks()
        with patch("sys.argv", ["technical.py", "sh600519", "--classify", "-j"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]), \
             patch.object(tech_cli, "composite_score", return_value=60.0), \
             patch("classifier.classify_stock", return_value={"type": "白马股"}), \
             patch("classifier.profile_stock", return_value={"industry": "默认"}), \
             patch(
                 "strategies.thresholds.get_industry_threshold",
                 side_effect=[15, 25, 40],
             ):
            tech_cli.main()
        out = capsys.readouterr().out
        assert '"classification"' in out
        assert '"chan_theory"' in out

    def test_main_stop_loss_pct_when_support_exists(self, capsys):
        records, quote = self._setup_mocks()
        quote["price"] = 100.0
        with patch("sys.argv", ["technical.py", "sh600519", "-j"]), \
             patch("common.cache.cleanup_tmp_files"), \
             patch.object(tech_cli, "fetch_kline", return_value=records), \
             patch.object(tech_cli, "fetch_batch", return_value=[quote]), \
             patch.object(tech_cli, "composite_score", return_value=50.0), \
             patch.object(tech_cli, "_compute_all") as mock_compute:
            # _compute_all 返回带 nearest_support 的 features
            mock_compute.return_value = {
                "support_resistance": {"nearest_support": 90.0},
                "market_environment": {"state": "震荡"},
            }
            tech_cli.main()
        # main 应正常输出 JSON（stop_loss_pct 计算行已执行但不计入白名单）
        out = capsys.readouterr().out
        assert '"score": 50.0' in out

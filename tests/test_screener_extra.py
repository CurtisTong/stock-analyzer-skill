"""screener.py 补充测试：hard_filter / volume_price_features / render / render_brief / _build_parser。"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import screener


def _make_quote_dict(
    code="sh600000",
    name="测试",
    amount=1e8,  # 元（内部 /10000 转万元）
    total_cap=100,  # 亿元
    change_pct=1.0,
):
    return {
        "code": code,
        "name": name,
        "amount": str(amount),
        "total_cap": str(total_cap),
        "change_pct": str(change_pct),
    }


def _make_fin_dict(eps=0.5, roe=10.0):
    return {"EPSJB": str(eps), "roe": str(roe)}


def _make_args(**kwargs):
    defaults = {
        "min_amount": 5000,
        "min_cap": 40,
        "exclude_loss": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ═══════════════════════════════════════════════════════════════
# hard_filter
# ═══════════════════════════════════════════════════════════════


class TestHardFilter:
    def test_normal_stock_passes(self):
        q = _make_quote_dict()
        fin = _make_fin_dict(eps=0.5)
        reasons, warnings = screener.hard_filter(q, fin, _make_args())
        assert reasons == []

    def test_low_amount_filtered(self):
        q = _make_quote_dict(amount=1e6)  # 1e6/1e4 = 100 < 5000
        fin = _make_fin_dict()
        reasons, _ = screener.hard_filter(q, fin, _make_args())
        assert any("成交额" in r for r in reasons)

    def test_low_cap_filtered(self):
        q = _make_quote_dict(total_cap=5)  # < 40
        fin = _make_fin_dict()
        reasons, _ = screener.hard_filter(q, fin, _make_args())
        assert any("市值" in r for r in reasons)

    def test_exclude_loss_filtered(self):
        """exclude_loss=True 且 EPS<=0 被过滤。"""
        q = _make_quote_dict()
        fin = _make_fin_dict(eps=-0.5)
        args = _make_args(exclude_loss=True)
        reasons, _ = screener.hard_filter(q, fin, args)
        assert any("EPS" in r for r in reasons)

    def test_exclude_loss_zero_eps_filtered(self):
        """exclude_loss=True 且 EPS=0 也被过滤（<=0）。"""
        q = _make_quote_dict()
        fin = _make_fin_dict(eps=0)
        args = _make_args(exclude_loss=True)
        reasons, _ = screener.hard_filter(q, fin, args)
        assert any("EPS" in r for r in reasons)

    def test_exclude_loss_disabled_zero_eps_passes(self):
        """exclude_loss=False 时 EPS=0 通过（但 filter_loss 默认仍过滤 <0）。"""
        q = _make_quote_dict()
        fin = _make_fin_dict(eps=0)
        args = _make_args(exclude_loss=False)
        reasons, _ = screener.hard_filter(q, fin, args)
        assert all("EPS<=0" not in r for r in reasons)

    def test_limit_up_filtered(self):
        """涨停被过滤。"""
        q = _make_quote_dict(change_pct=10.0)
        fin = _make_fin_dict()
        reasons, _ = screener.hard_filter(q, fin, _make_args())
        assert any("涨跌停" in r for r in reasons)

    def test_limit_down_filtered(self):
        """跌停被过滤。"""
        q = _make_quote_dict(change_pct=-10.0)
        fin = _make_fin_dict()
        reasons, _ = screener.hard_filter(q, fin, _make_args())
        assert any("涨跌停" in r for r in reasons)

    def test_zero_min_amount_passes(self):
        """min_amount=0 不按金额过滤。"""
        q = _make_quote_dict(amount=0)
        fin = _make_fin_dict()
        args = _make_args(min_amount=0)
        reasons, _ = screener.hard_filter(q, fin, args)
        assert all("成交额" not in r for r in reasons)

    def test_zero_min_cap_passes(self):
        """min_cap=0 不按市值过滤。"""
        q = _make_quote_dict(total_cap=0)
        fin = _make_fin_dict()
        args = _make_args(min_cap=0)
        reasons, _ = screener.hard_filter(q, fin, args)
        assert all("市值<" not in r for r in reasons)


# ═══════════════════════════════════════════════════════════════
# volume_price_features
# ═══════════════════════════════════════════════════════════════


class TestVolumePriceFeatures:
    def test_insufficient_data(self):
        """数据 <6 返回数据不足。"""
        result = screener.volume_price_features([1, 2, 3], [100, 200, 300])
        assert result["signal"] == 0
        assert "数据不足" in result["desc"]

    def test_normal_analysis(self):
        """正常量价分析委托 volume_analysis。"""
        closes = [10 + i * 0.1 for i in range(10)]
        volumes = [1000 + i * 100 for i in range(10)]
        mock_result = {"volume_price_signal": 1, "volume_price": "放量上涨"}
        with patch("technical.volume.volume_analysis", return_value=mock_result):
            result = screener.volume_price_features(closes, volumes)
        assert result["signal"] == 1
        assert "放量上涨" in result["desc"]

    def test_volume_analysis_returns_none(self):
        """volume_analysis 返回 None -> 数据不足。"""
        closes = [10] * 10
        volumes = [1000] * 10
        with patch("technical.volume.volume_analysis", return_value=None):
            result = screener.volume_price_features(closes, volumes)
        assert result["signal"] == 0
        assert "数据不足" in result["desc"]

    def test_default_desc_when_missing(self):
        """volume_price 字段缺失 -> 默认量价中性。"""
        closes = [10] * 10
        volumes = [1000] * 10
        mock_result = {"volume_price_signal": 0}  # 无 volume_price 键
        with patch("technical.volume.volume_analysis", return_value=mock_result):
            result = screener.volume_price_features(closes, volumes)
        assert result["desc"] == "量价中性"


# ═══════════════════════════════════════════════════════════════
# render
# ═══════════════════════════════════════════════════════════════


def _make_row(**kwargs):
    defaults = {
        "code": "sh600000",
        "name": "测试股",
        "industry": "新能源",
        "board": "主板",
        "score": 65,
        "quality": 60,
        "valuation": 50,
        "momentum": 70,
        "liquidity": 55,
        "pe": 15.0,
        "roe": 10.0,
        "rsi": 55,
        "ret20": 5.0,
        "trend": "↑",
        "macd_signal": 1,
        "vol_price": "放量",
        "chip": 60,
        "rejected": False,
    }
    defaults.update(kwargs)
    return defaults


class TestRender:
    def test_render_with_chip(self, capsys):
        rows = [_make_row()]
        screener.render(rows, "balanced", top=10, show_chip=True)
        out = capsys.readouterr().out
        assert "sh600000" in out
        assert "筹码" in out

    def test_render_without_chip(self, capsys):
        rows = [_make_row()]
        screener.render(rows, "balanced", top=10, show_chip=False)
        out = capsys.readouterr().out
        assert "sh600000" in out

    def test_render_with_rejected(self, capsys):
        rows = [
            _make_row(),
            _make_row(code="sh600001", rejected=True, name="剔除股"),
        ]
        rows[1]["rejected"] = ["金额不足"]
        screener.render(rows, "balanced", top=10, show_chip=False)
        out = capsys.readouterr().out
        assert "剔除样本" in out

    def test_render_custom_title(self, capsys):
        rows = [_make_row()]
        screener.render(rows, "balanced", top=10, title="自定义标题")
        out = capsys.readouterr().out
        assert "自定义标题" in out

    def test_render_top_limit(self, capsys):
        """top 限制输出行数。"""
        rows = [_make_row(code=f"sh60000{i}") for i in range(5)]
        screener.render(rows, "balanced", top=2, show_chip=False)
        out = capsys.readouterr().out
        # 前 2 行输出，后 3 行不输出
        assert "sh600000" in out
        assert "sh600001" in out

    def test_render_macd_icons(self, capsys):
        """macd_signal 正/负/零对应不同图标。"""
        rows = [
            _make_row(code="sh600000", trend="趋", macd_signal=1),
            _make_row(code="sh600001", trend="趋", macd_signal=-1),
            _make_row(code="sh600002", trend="趋", macd_signal=0),
        ]
        screener.render(rows, "balanced", top=10, show_chip=False)
        out = capsys.readouterr().out
        assert "↑" in out
        assert "↓" in out
        assert "\u2192" in out  # Unicode RIGHTWARDS ARROW (中性图标)


# ═══════════════════════════════════════════════════════════════
# render_brief
# ═══════════════════════════════════════════════════════════════


class TestRenderBrief:
    def test_no_accepted(self, capsys):
        """无入选 -> 提示原因。"""
        rows = [_make_row(rejected=True)]
        rows[0]["rejected"] = ["金额不足"]
        screener.render_brief(rows, "balanced", top=10)
        out = capsys.readouterr().out
        assert "无符合条件" in out
        assert "股票池未初始化" in out

    def test_brief_with_results(self, capsys):
        rows = [_make_row(score=70)]
        screener.render_brief(rows, "balanced", top=10)
        out = capsys.readouterr().out
        assert "sh600000" in out
        assert "建议关注" in out or "可观望" in out or "首选" in out

    def test_brief_custom_title(self, capsys):
        rows = [_make_row()]
        screener.render_brief(rows, "balanced", top=10, title="自定义")
        out = capsys.readouterr().out
        assert "自定义" in out

    def test_brief_strong_watch_split(self, capsys):
        """分数分层：strong/watch 建议分组。"""
        rows = [
            _make_row(code="sh600000", name="强股", score=80),
            _make_row(code="sh600001", name="中股", score=55),
            _make_row(code="sh600002", name="弱股", score=30),
        ]
        screener.render_brief(rows, "balanced", top=10)
        out = capsys.readouterr().out
        assert "建议关注" in out


# ═══════════════════════════════════════════════════════════════
# _build_parser
# ═══════════════════════════════════════════════════════════════


class TestBuildParser:
    def test_returns_argument_parser(self):
        parser = screener._build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_default_strategy(self):
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert args.strategy == "balanced"

    def test_default_top(self):
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert args.top == 10

    def test_default_min_amount(self):
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert args.min_amount == 5000

    def test_default_min_cap(self):
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert args.min_cap == 40

    def test_full_market_flag(self):
        parser = screener._build_parser()
        args = parser.parse_args(["--full-market"])
        assert args.full_market is True

    def test_json_flag(self):
        parser = screener._build_parser()
        args = parser.parse_args(["--json"])
        assert args.json is True

    def test_exclude_board_default(self):
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert "北交所" in args.exclude_board

    def test_custom_top(self):
        parser = screener._build_parser()
        args = parser.parse_args(["--top", "5"])
        assert args.top == 5

    def test_no_chip_flag(self):
        parser = screener._build_parser()
        args = parser.parse_args(["--no-chip"])
        assert args.no_chip is True


# ═══════════════════════════════════════════════════════════════
# latest_finance / daily_features 薄包装
# ═══════════════════════════════════════════════════════════════


class TestThinWrappers:
    def test_latest_finance_delegates(self):
        """latest_finance 委托给 fetch_finance_first。"""
        mock_fin = MagicMock()
        with patch("screener.fetch_finance_first", return_value=mock_fin):
            result = screener.latest_finance("sh600000")
        assert result is mock_fin

    def test_daily_features_delegates(self):
        """daily_features 委托给 compute_features。"""
        mock_features = {"rsi": 50}
        with patch("screener.compute_features", return_value=mock_features):
            result = screener.daily_features("sh600000")
        assert result is mock_features


# ═══════════════════════════════════════════════════════════════
# _default_progress_callback
# ═══════════════════════════════════════════════════════════════


class TestDefaultProgressCallback:
    def test_init_empty_universe(self, capsys):
        screener._default_progress_callback(
            "init", {"halted": True, "reason": "empty_universe"}
        )
        out = capsys.readouterr().out
        assert "股票池为空" in out

    def test_init_macro_red(self, capsys):
        screener._default_progress_callback(
            "init", {"halted": True, "reason": "macro_red"}
        )
        out = capsys.readouterr().out
        assert "系统性风险" in out

    def test_init_halted_unknown_reason(self, capsys):
        """halted 但未知 reason -> 静默返回。"""
        screener._default_progress_callback(
            "init", {"halted": True, "reason": "unknown"}
        )
        out = capsys.readouterr().out
        assert out == ""

    def test_init_with_regime(self, capsys):
        """市场状态 overlay 输出。"""
        regime = MagicMock()
        regime.label = "牛市"
        regime.value = "bull"
        screener._default_progress_callback("init", {"regime": regime})
        out = capsys.readouterr().out
        assert "市场状态" in out
        assert "regime overlay" in out

    def test_init_regime_no_overlay(self, capsys):
        """_no_regime 属性为 True -> 输出已禁用（getattr 访问，需对象属性）。"""
        regime = MagicMock()
        regime.label = "牛市"
        regime.value = "bull"
        payload = MagicMock()
        payload.get = lambda k, d=None: {"regime": regime}.get(k, d)
        payload._no_regime = True
        payload.halted = None
        screener._default_progress_callback("init", payload)
        out = capsys.readouterr().out
        assert "已禁用" in out

    def test_init_macro_msg(self, capsys):
        screener._default_progress_callback("init", {"macro_msg": "宏观提示文字"})
        out = capsys.readouterr().out
        assert "宏观提示文字" in out

    def test_phase1(self, capsys):
        screener._default_progress_callback(
            "phase1", {"count_in": 100, "count_out": 30, "elapsed": 1.5}
        )
        out = capsys.readouterr().out
        assert "Phase 1" in out
        assert "100" in out

    def test_phase2(self, capsys):
        screener._default_progress_callback(
            "phase2", {"count": 30, "elapsed": 2.0, "saved_kline": 0, "total": 3.5}
        )
        out = capsys.readouterr().out
        assert "Phase 2" in out

    def test_phase2_with_saved_kline(self, capsys):
        """saved_kline > 0 -> 输出节省信息。"""
        screener._default_progress_callback(
            "phase2", {"count": 30, "elapsed": 2.0, "saved_kline": 50, "total": 3.5}
        )
        out = capsys.readouterr().out
        assert "两阶段管线完成" in out
        assert "节省" in out

    def test_snapshot(self, capsys):
        screener._default_progress_callback("snapshot", {"path": "/tmp/snap.json"})
        out = capsys.readouterr().out
        assert "快照已保存" in out
        assert "/tmp/snap.json" in out

    def test_unknown_event(self, capsys):
        """未知事件静默。"""
        screener._default_progress_callback("unknown", {})
        assert capsys.readouterr().out == ""


# ═══════════════════════════════════════════════════════════════
# _run_main / main
# ═══════════════════════════════════════════════════════════════


class TestRunMain:
    def _args(self, **kwargs):
        defaults = {
            "strategy": "balanced",
            "top": 10,
            "json": False,
            "full": False,
            "full_market": False,
            "sector": None,
            "no_chip": False,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_json_output(self, capsys):
        """JSON 模式输出 JSON。"""
        rows = [{"code": "sh600000", "name": "甲"}]
        with patch(
            "screener.run_screening", return_value={"halted": False, "rows": rows}
        ):
            screener._run_main(self._args(json=True))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["code"] == "sh600000"

    def test_brief_output(self, capsys):
        """非 JSON 非 full -> render_brief。"""
        rows = [_make_row()]
        with patch(
            "screener.run_screening", return_value={"halted": False, "rows": rows}
        ):
            screener._run_main(self._args())
        out = capsys.readouterr().out
        assert "sh600000" in out

    def test_full_output(self, capsys):
        """full 模式 -> render。"""
        rows = [_make_row()]
        with patch(
            "screener.run_screening", return_value={"halted": False, "rows": rows}
        ):
            screener._run_main(self._args(full=True))
        out = capsys.readouterr().out
        assert "sh600000" in out

    def test_full_market_title(self, capsys):
        """full_market + sector -> 标题含板块名。"""
        rows = [_make_row()]
        with patch(
            "screener.run_screening", return_value={"halted": False, "rows": rows}
        ):
            screener._run_main(self._args(full_market=True, sector="创业板"))
        out = capsys.readouterr().out
        assert "全市场筛选" in out
        assert "创业板" in out

    def test_full_market_no_sector_title(self, capsys):
        """full_market 无 sector -> 标题全市场筛选。"""
        rows = [_make_row()]
        with patch(
            "screener.run_screening", return_value={"halted": False, "rows": rows}
        ):
            screener._run_main(self._args(full_market=True))
        out = capsys.readouterr().out
        assert "全市场筛选" in out

    def test_halted_non_json_returns(self, capsys):
        """halted 且非 JSON -> 直接返回。"""
        with patch("screener.run_screening", return_value={"halted": True, "rows": []}):
            screener._run_main(self._args(json=False))
        out = capsys.readouterr().out
        assert out == ""

    def test_halted_json_outputs_empty(self, capsys):
        """halted 且 JSON -> 仍输出空 JSON。"""
        with patch("screener.run_screening", return_value={"halted": True, "rows": []}):
            screener._run_main(self._args(json=True))
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed == []


class TestMain:
    def test_main_delegates_to_run_main(self):
        """main() 调用 _run_main。"""
        with patch("common.cache.cleanup_tmp_files"):
            with patch("screener._run_main") as mock_run:
                with patch.object(sys, "argv", ["screener.py"]):
                    screener.main()
        mock_run.assert_called_once()

    def test_main_with_args(self):
        """main() 解析参数后传给 _run_main。"""
        with patch("common.cache.cleanup_tmp_files"):
            with patch("screener._run_main") as mock_run:
                with patch.object(sys, "argv", ["screener.py", "--top", "5", "--json"]):
                    screener.main()
        args = mock_run.call_args[0][0]
        assert args.top == 5
        assert args.json is True

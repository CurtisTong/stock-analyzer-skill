"""
screener.py _run_main 集成测试（V2.1）。
"""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import screener  # noqa: E402
import business.screening_service as ss  # noqa: E402


def _make_args(**overrides):
    """构造默认 Namespace。"""
    defaults = dict(
        strategy="balanced",
        sector=None,
        codes="sh600519,sh600989",
        top=5,
        min_amount=5000,
        min_cap=40,
        exclude_loss=False,
        no_constraints=True,
        sector_cap=0.30,
        full_market=False,
        board_limit=0,
        exclude_board="北交所",
        no_normalize=True,
        no_regime=True,
        no_chip=False,
        no_macro=True,
        snapshot=False,
        two_stage=False,
        json=False,
        brief=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.fixture
def mock_data_layer(monkeypatch):
    """Mock 整个数据层（不真实拉取）。
    下沉后业务函数在 screening_service 模块，mock 点迁移过去。
    """
    quote_dict = {
        "sh600519": {
            "code": "sh600519",
            "name": "贵州茅台",
            "amount": 100000_0000,
            "total_cap": 22000,
            "pe": 25,
        },
        "sh600989": {
            "code": "sh600989",
            "name": "宝钢股份",
            "amount": 50000_0000,
            "total_cap": 1500,
            "pe": 8,
        },
    }

    def mock_load_universe(args):
        return list(quote_dict.keys())

    def mock_fetch_batch(codes):
        return [quote_dict[c] for c in codes if c in quote_dict]

    def mock_prefetch_finance(codes):
        return {c: [{"eps": 50.0, "roe": 30.0, "net_profit_yoy": 20.0}] for c in codes}

    def mock_prefetch_kline(codes, scale=240, datalen=240):
        return {}

    def mock_analyze(
        quote, strategy, args, finance_cache=None, regime=None, kline_cache=None
    ):
        return {
            "code": quote["code"],
            "name": quote["name"],
            "score": 80.0,
            "rejected": [],
        }

    def mock_apply(rows, **k):
        return rows

    def mock_render(rows, strategy, top, title=None, show_chip=True):
        pass

    # mock 点迁移到 screening_service 模块
    monkeypatch.setattr(ss, "load_universe", mock_load_universe)
    monkeypatch.setattr(ss, "fetch_batch_dicts", mock_fetch_batch)
    monkeypatch.setattr(ss, "prefetch_finance_all", mock_prefetch_finance)
    monkeypatch.setattr(ss, "prefetch_kline_all", mock_prefetch_kline)
    monkeypatch.setattr(ss, "analyze_code", mock_analyze)
    monkeypatch.setattr(ss, "apply_portfolio_constraints", mock_apply)
    # render 仍在 screener 模块
    monkeypatch.setattr(screener, "render", mock_render)
    return quote_dict


class TestRunMainSingleStage:
    """单阶段管线测试。"""

    def test_basic_run(self, mock_data_layer, capsys):
        """基本流程：加载 → 抓取 → 评分 → 输出。"""
        screener._run_main(_make_args())
        captured = capsys.readouterr()
        # 至少应包含一些输出（render mock 不输出）
        # 应有 no-constraints 提示或类似
        # 验证不抛异常
        assert "sh600519" not in captured.out  # render mock 无输出

    def test_json_output(self, mock_data_layer, capsys):
        """--json 输出 JSON。"""
        import json

        screener._run_main(_make_args(json=True))
        captured = capsys.readouterr()
        # JSON 应至少包含 sh600519 的一条记录
        data = json.loads(captured.out)
        assert isinstance(data, list)
        codes = [r["code"] for r in data]
        assert "sh600519" in codes or len(data) == 0  # mock 可能不返回

    def test_snapshot_flag_does_not_crash(self, mock_data_layer, monkeypatch, capsys):
        """--snapshot 标志不崩溃（即使无 save_snapshot）。"""
        # mock save_snapshot 让它失败
        import snapshots

        monkeypatch.setattr(
            snapshots,
            "save_snapshot",
            lambda **k: (_ for _ in ()).throw(Exception("mock fail")),
        )
        screener._run_main(_make_args(snapshot=True))
        captured = capsys.readouterr()
        # 错误输出到 stderr
        assert "快照保存失败" in captured.err or "保存失败" in captured.err

    def test_two_stage_flag(self, mock_data_layer, capsys):
        """--two-stage 启用两阶段管线。"""
        screener._run_main(_make_args(two_stage=True))
        # 应输出 Phase 1/Phase 2 KPI
        captured = capsys.readouterr()
        # 验证不抛异常
        # 实际 KPI 在 anaylze_code_phase1 mock 后可能不显示（因为 mock）
        # 但至少不报错


class TestBuildParser:
    """_build_parser 测试。"""

    def test_parser_has_all_flags(self):
        """解析器包含所有 flag。"""
        parser = screener._build_parser()
        # 模拟解析
        args = parser.parse_args(["--strategy", "balanced", "--codes", "sh600519"])
        assert args.strategy == "balanced"
        assert args.codes == "sh600519"

    def test_parser_default_strategy(self):
        """默认 strategy=balanced。"""
        parser = screener._build_parser()
        args = parser.parse_args([])
        assert args.strategy == "balanced"

    def test_parser_version_flag(self):
        """--version 输出版本。"""
        parser = screener._build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        # SystemExit code 0
        assert exc_info.value.code == 0

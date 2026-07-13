"""测试 experts/decide.py：run_debate 闭环编排器。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from experts import decide
from experts import decide as _decide_mod  # 用于 patch.object(decide, ...)


def _make_expert(name="buffett", score=75, direction="看多", group="long_term"):
    return {"name": name, "score": score, "direction": direction, "group": group}


def _make_aggregate_result(direction="看多", score=72):
    return {
        "code": "sh600519",
        "direction": direction,
        "composite_score": score,
        "avg_score": score,
        "confidence": 75,
        "expert_results": [_make_expert("buffett", score, direction),
                           _make_expert("lynch", 70, direction)],
        "votes": {"买入": 2, "持有": 0, "卖出": 0, "bull": 2, "bear": 0},
    }


class TestRunDebate:
    def test_basic(self):
        """基本流程：拉校准 → 投票 → 落库。"""
        with patch("experts.calibration.compute_calibration_factor", return_value=0.1), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()), \
             patch("experts.calibration.record_prediction",
                   return_value="pred_123"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            result = decide.run_debate("sh600519", [_make_expert()])
        assert result["direction"] == "看多"
        assert result["_pred_id"] == "pred_123"
        assert result["_calibration_factor"] == 0.1

    def test_calibration_failure_uses_default(self):
        """校准因子获取失败时使用 0.0。"""
        with patch("experts.calibration.compute_calibration_factor",
                   side_effect=Exception("cal err")), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()), \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            result = decide.run_debate("sh600519", [_make_expert()])
        assert result["_calibration_factor"] == 0.0

    def test_record_prediction_failure_continues(self):
        """落库失败不影响 debate 结果。"""
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()), \
             patch("experts.calibration.record_prediction",
                   side_effect=Exception("db err")), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            result = decide.run_debate("sh600519", [_make_expert()])
        assert result["_pred_id"] is None
        assert result["direction"] == "看多"

    def test_with_pending_predictions(self):
        """有 pending 预测时记录数量。"""
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()), \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions",
                   return_value=[{"id": "p1"}, {"id": "p2"}, {"id": "p3"}]):
            result = decide.run_debate("sh600519", [_make_expert()])
        assert result["_pending_verification_count"] == 3

    def test_with_market_state(self):
        """外部传入 market_state。"""
        market_state = {
            "state": "bull", "confidence": 0.8,
            "long_weight": 0.6, "short_weight": 0.4,
        }
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()) as m_agg, \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate("sh600519", [_make_expert()], market_state=market_state)
        # market_state 应被传给 aggregate_votes
        assert m_agg.call_args.kwargs.get("market_state") == market_state

    def test_horizon_parameter(self):
        """horizon 参数传递。"""
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()) as m_agg, \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate("sh600519", [_make_expert()], horizon="long")
        assert m_agg.call_args.kwargs.get("horizon") == "long"

    def test_composite_score_fallback(self):
        """composite_score 缺失时回退到 avg_score。"""
        result_no_composite = _make_aggregate_result()
        del result_no_composite["composite_score"]
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=result_no_composite), \
             patch("experts.calibration.record_prediction", return_value="pred") as m_rec, \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate("sh600519", [_make_expert()])
        # 应使用 avg_score
        assert m_rec.call_args.kwargs["composite_score"] == 72

    def test_with_veto(self):
        """veto_results 传递给 aggregate（向后兼容旧格式）。"""
        # 修复：原 {"vetoed": True} 结构与 vote_engine 期望的
        # {expert_name: {cond: bool}} 不符。改为正确结构。
        veto = {
            "buffett": {"ROE < 10% 或负债率 > 70%（金融业除外）": True}
        }
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()) as m_agg, \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate("sh600519", [_make_expert()], veto_results=veto)
        assert m_agg.call_args.kwargs.get("veto_results") == veto
        # stock_data 未传时不应生成 risk_coefficients
        assert m_agg.call_args.kwargs.get("risk_coefficients") is None

    def test_with_risk_coefficients_via_stock_data(self):
        """stock_data 传入时自动生成 risk_coefficients 并透传给 aggregate。"""
        # 构造触发弹性风险系数的 stock_data：ROE 8% < 10%
        stock_data = {
            "finance": {"ROEJQ": 8.0, "ZCFZL": 45.0, "MGJYXJJE": 1.5},
            "quote": {"pe": 20},
        }
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()) as m_agg, \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate(
                "sh600519", [_make_expert()], stock_data=stock_data
            )
        rc = m_agg.call_args.kwargs.get("risk_coefficients")
        # 应生成非 None 的 risk_coefficients，且 buffett 的 coeff < 1.0
        assert rc is not None
        assert "buffett" in rc
        assert rc["buffett"] < 1.0

    def test_risk_coefficients_none_when_no_trigger(self):
        """stock_data 无触发条件时 risk_coefficients 为 None。"""
        # ROE 25%、FCF 正、负债率低 -> 无触发
        stock_data = {
            "finance": {"ROEJQ": 25.0, "ZCFZL": 30.0, "MGJYXJJE": 3.0},
            "quote": {"pe": 15},
        }
        with patch("experts.calibration.compute_calibration_factor", return_value=0.0), \
             patch.object(_decide_mod, "aggregate_votes",
                   return_value=_make_aggregate_result()) as m_agg, \
             patch("experts.calibration.record_prediction", return_value="pred"), \
             patch("experts.calibration.get_pending_predictions", return_value=[]):
            decide.run_debate(
                "sh600519", [_make_expert()], stock_data=stock_data
            )
        # 无触发条件时 risk_coefficients 被过滤为 None
        assert m_agg.call_args.kwargs.get("risk_coefficients") is None
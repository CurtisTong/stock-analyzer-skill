"""
experts/calibration.py 单元测试：覆盖校准数据记录、验证、因子计算。
"""

import json
import pytest
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


@pytest.fixture(autouse=True)
def temp_calibration_file(tmp_path):
    """每个测试使用临时校准文件，避免污染真实数据。"""
    cal_file = tmp_path / "expert_calibration.json"
    with patch("experts.calibration._CALIBRATION_FILE", cal_file):
        yield cal_file


from experts.calibration import (
    record_prediction,
    verify_predictions,
    get_calibration,
    get_pending_predictions,
    compute_calibration_factor,
    get_calibration_report,
)

# ═══════════════════════════════════════════════════════════════
# 1. record_prediction
# ═══════════════════════════════════════════════════════════════


class TestRecordPrediction:
    def test_creates_record(self):
        pred_id = record_prediction(
            stock_code="sh600989",
            expert_scores={"buffett": 72, "lynch": 65},
            direction="看多",
        )
        assert "sh600989" in pred_id

    def test_record_persisted(self):
        record_prediction(
            stock_code="sh600989",
            expert_scores={"buffett": 72},
            direction="看多",
        )
        cal = get_calibration()
        assert "buffett" in cal

    def test_dedup_same_stock_same_day(self):
        record_prediction("sh600989", {"buffett": 70}, "看多")
        record_prediction("sh600989", {"buffett": 80}, "强烈看多")
        # 应该更新而非新增
        from experts.calibration import _load

        data = _load()
        sh_records = [p for p in data["predictions"] if p["stock"] == "sh600989"]
        assert len(sh_records) == 1
        assert sh_records[0]["expert_scores"]["buffett"] == 80

    def test_different_stocks_separate(self):
        record_prediction("sh600989", {"buffett": 70}, "看多")
        record_prediction("sh600519", {"buffett": 80}, "强烈看多")
        from experts.calibration import _load

        data = _load()
        assert len(data["predictions"]) == 2

    def test_verify_days_set(self):
        record_prediction("sh600989", {"buffett": 70}, "看多", verify_days=60)
        from experts.calibration import _load

        data = _load()
        pred = data["predictions"][0]
        expected = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        assert pred["verify_after"] == expected


# ═══════════════════════════════════════════════════════════════
# 2. verify_predictions
# ═══════════════════════════════════════════════════════════════


class TestVerifyPredictions:
    def _create_expired_prediction(self, direction="看多"):
        """创建一条已过期的预测记录。"""
        past_date = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")
        verify_after = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        from experts.calibration import _load, _save

        data = _load()
        data["predictions"].append(
            {
                "id": f"pred_{past_date.replace('-', '')}_sh600989",
                "stock": "sh600989",
                "date": past_date,
                "direction": direction,
                "composite_score": 65.0,
                "expert_scores": {"buffett": 72, "lynch": 65},
                "verified": False,
                "verify_after": verify_after,
                "actual_return": None,
                "actual_direction": None,
            }
        )
        _save(data)

    def test_verifies_expired_predictions(self):
        self._create_expired_prediction()
        result = verify_predictions()
        assert result["verified"] == 1

    def test_marks_as_verified(self):
        self._create_expired_prediction()
        verify_predictions()
        from experts.calibration import _load

        data = _load()
        assert data["predictions"][0]["verified"] is True

    def test_does_not_verify_future(self):
        record_prediction("sh600989", {"buffett": 70}, "看多", verify_days=30)
        result = verify_predictions()
        assert result["verified"] == 0

    def test_with_price_function(self):
        self._create_expired_prediction("看多")

        def mock_price_fn(stock, start, end):
            return 10.0  # 上涨 10%

        result = verify_predictions(get_price_fn=mock_price_fn)
        assert result["verified"] == 1
        assert result["details"][0]["actual_return"] == 10.0
        assert result["details"][0]["correct"] is True  # 看多 + 上涨 = 正确

    def test_wrong_prediction(self):
        self._create_expired_prediction("看多")

        def mock_price_fn(stock, start, end):
            return -15.0  # 下跌 15%

        result = verify_predictions(get_price_fn=mock_price_fn)
        assert result["details"][0]["correct"] is False  # 看多 + 下跌 = 错误

    def test_sell_correct_on_drop(self):
        self._create_expired_prediction("看空")

        def mock_price_fn(stock, start, end):
            return -10.0

        result = verify_predictions(get_price_fn=mock_price_fn)
        assert result["details"][0]["correct"] is True  # 看空 + 下跌 = 正确


# ═══════════════════════════════════════════════════════════════
# 3. compute_calibration_factor
# ═══════════════════════════════════════════════════════════════


class TestCalibrationFactor:
    def test_no_data_returns_zero(self):
        factor = compute_calibration_factor()
        assert factor == 0.0

    def test_perfect_calibration_positive(self):
        """所有专家校准率 100% → 正因子。"""
        from experts.calibration import _load, _save

        data = _load()
        for name in data["experts"]:
            data["experts"][name] = {
                "events": 10,
                "correct": 10,
                "last_updated": "2026-06-01",
            }
        _save(data)
        factor = compute_calibration_factor()
        assert factor > 0.5

    def test_poor_calibration_negative(self):
        """所有专家校准率 0% → 负因子。"""
        from experts.calibration import _load, _save

        data = _load()
        for name in data["experts"]:
            data["experts"][name] = {
                "events": 10,
                "correct": 0,
                "last_updated": "2026-06-01",
            }
        _save(data)
        factor = compute_calibration_factor()
        assert factor < -0.5

    def test_mixed_calibration(self):
        """混合校准率应产生介于极端值之间的因子。"""
        from experts.calibration import _load, _save

        data = _load()
        # 一半专家好，一半差
        names = list(data["experts"].keys())
        for i, name in enumerate(names):
            if i < 4:
                data["experts"][name] = {
                    "events": 10,
                    "correct": 8,
                    "last_updated": "2026-06-01",
                }
            else:
                data["experts"][name] = {
                    "events": 10,
                    "correct": 3,
                    "last_updated": "2026-06-01",
                }
        _save(data)
        factor = compute_calibration_factor()
        assert -1.0 <= factor <= 1.0


# ═══════════════════════════════════════════════════════════════
# 4. get_calibration_report
# ═══════════════════════════════════════════════════════════════


class TestCalibrationReport:
    def test_report_contains_header(self):
        report = get_calibration_report()
        assert "专家校准报告" in report

    def test_report_contains_all_experts(self):
        report = get_calibration_report()
        for name in [
            "buffett",
            "lynch",
            "soros",
            "duan_yongping",
            "xu_xiang",
            "zhao_laoge",
            "chaogu_yangjia",
            "zuoshou_xinyi",
        ]:
            assert name in report

    def test_report_with_data(self):
        from experts.calibration import _load, _save

        data = _load()
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        data["predictions"].append(
            {
                "id": "test_report",
                "stock": "sh600989",
                "date": past,
                "direction": "看多",
                "composite_score": 65.0,
                "expert_scores": {"buffett": 72},
                "verified": False,
                "verify_after": past,
                "actual_return": None,
                "actual_direction": None,
            }
        )
        _save(data)
        report = get_calibration_report()
        assert "sh600989" in report or "待验证" in report


# ═══════════════════════════════════════════════════════════════
# 5. get_pending_predictions
# ═══════════════════════════════════════════════════════════════


class TestPendingPredictions:
    def test_empty_when_no_predictions(self):
        pending = get_pending_predictions()
        assert len(pending) == 0

    def test_future_not_pending(self):
        record_prediction("sh600989", {"buffett": 70}, "看多", verify_days=30)
        pending = get_pending_predictions()
        assert len(pending) == 0  # 30天后才到期

    def test_expired_is_pending(self):
        from experts.calibration import _load, _save

        data = _load()
        past = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        data["predictions"].append(
            {
                "id": "test_pending",
                "stock": "sh600989",
                "date": past,
                "direction": "看多",
                "composite_score": 65.0,
                "expert_scores": {"buffett": 70},
                "verified": False,
                "verify_after": past,
                "actual_return": None,
                "actual_direction": None,
            }
        )
        _save(data)
        pending = get_pending_predictions()
        assert len(pending) == 1

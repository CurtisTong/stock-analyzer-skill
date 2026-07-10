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
        # buffett 是 legacy 名，归一化为 active 名 value_institution
        assert "value_institution" in cal

    def test_dedup_same_stock_same_day(self):
        record_prediction("sh600989", {"buffett": 70}, "看多")
        record_prediction("sh600989", {"buffett": 80}, "强烈看多")
        # 应该更新而非新增
        from experts.calibration import _load

        data = _load()
        sh_records = [p for p in data["predictions"] if p["stock"] == "sh600989"]
        assert len(sh_records) == 1
        # expert_scores 键归一化为 active 名
        assert sh_records[0]["expert_scores"]["value_institution"] == 80

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
                "expert_scores": {"value_institution": 72, "lynch": 65},
                "verified": False,
                "verify_after": verify_after,
                "actual_return": None,
                "actual_direction": None,
            }
        )
        _save(data)

    def test_skips_expired_without_price_fn(self):
        """v2.4.3：无 get_price_fn 时跳过而非标记 verified（防重验证锁死）。"""
        self._create_expired_prediction()
        result = verify_predictions()
        assert result["verified"] == 0
        assert result["skipped"] == 1

    def test_marks_as_verified_with_price_fn(self):
        """有 get_price_fn 时正常标记 verified。"""
        self._create_expired_prediction("看多")

        def mock_price_fn(stock, start, end):
            return 8.0  # 上涨

        verify_predictions(get_price_fn=mock_price_fn)
        from experts.calibration import _load

        data = _load()
        assert data["predictions"][0]["verified"] is True

    def test_mark_only_marks_verified(self):
        """mark_only=True 时标记 verified（无网络环境，不更新校准数据）。"""
        self._create_expired_prediction()
        result = verify_predictions(mark_only=True)
        assert result["verified"] == 1

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
# 3.5. legacy -> merged 数据迁移
# ═══════════════════════════════════════════════════════════════


class TestLegacyMigration:
    """legacy 专家名数据迁移到 active 名测试。"""

    def test_legacy_migrated_to_active_on_load(self):
        """_load 将 legacy 名记录合并到 active 名。"""
        from experts.calibration import _load, _save

        # 构造含 legacy 名 + active 名的原始数据
        raw = {
            "predictions": [],
            "experts": {
                "buffett": {"events": 5, "correct": 4, "last_updated": "2026-06-16"},
                "duan_yongping": {
                    "events": 5,
                    "correct": 4,
                    "last_updated": "2026-06-15",
                },
                "value_institution": {
                    "events": 2,
                    "correct": 1,
                    "last_updated": "2026-06-10",
                },
                "lynch": {"events": 5, "correct": 2, "last_updated": "2026-06-16"},
            },
        }
        _save(raw)
        data = _load()

        # buffett + duan_yongping 合并到 value_institution
        assert "buffett" not in data["experts"]
        assert "duan_yongping" not in data["experts"]
        vi = data["experts"]["value_institution"]
        assert vi["events"] == 5 + 5 + 2  # 12
        assert vi["correct"] == 4 + 4 + 1  # 9
        # last_updated 取较新者
        assert vi["last_updated"] == "2026-06-16"
        # lynch（active）保留不变
        assert data["experts"]["lynch"]["events"] == 5
        # 迁移标志
        assert data["_migrated"] is True

    def test_migration_idempotent(self):
        """已迁移的数据再次 _load 不重复合并。"""
        from experts.calibration import _load, _save

        raw = {
            "predictions": [],
            "experts": {
                "buffett": {"events": 5, "correct": 4, "last_updated": "2026-06-16"},
            },
        }
        _save(raw)
        data1 = _load()
        _save(data1)
        data2 = _load()
        # 第二次加载不应再次合并（value_institution events 应保持 5，非 10）
        assert data2["experts"]["value_institution"]["events"] == 5

    def test_record_prediction_normalizes_legacy_names(self):
        """record_prediction 将 legacy 名归一化为 active 名存储。"""
        record_prediction(
            "sh600989",
            {"buffett": 72, "duan_yongping": 68, "lynch": 65},
            "看多",
        )
        from experts.calibration import _load

        data = _load()
        scores = data["predictions"][0]["expert_scores"]
        # legacy 名归一化为 active 名
        assert "buffett" not in scores
        assert "duan_yongping" not in scores
        assert "value_institution" in scores
        assert "lynch" in scores
        # 同一 active 名多次映射取较高分
        assert scores["value_institution"] == 72

    def test_verify_updates_merged_expert(self):
        """verify_predictions 正确更新 active 名专家（迁移后 in 检查通过）。"""
        from experts.calibration import _load, _save

        past_date = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")
        verify_after = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
        data = _load()
        data["predictions"].append(
            {
                "id": f"pred_{past_date.replace('-', '')}_sh600989",
                "stock": "sh600989",
                "date": past_date,
                "direction": "看多",
                "composite_score": 65.0,
                "expert_scores": {"value_institution": 72},
                "verified": False,
                "verify_after": verify_after,
                "actual_return": None,
                "actual_direction": None,
            }
        )
        _save(data)

        def mock_price_fn(stock, start, end):
            return 10.0  # 上涨 10%

        verify_predictions(get_price_fn=mock_price_fn)

        data2 = _load()
        # value_institution 专家校准数据应被更新（events +1）
        assert data2["experts"]["value_institution"]["events"] >= 1


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

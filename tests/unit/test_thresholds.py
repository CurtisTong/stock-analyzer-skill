"""
scripts/strategies/thresholds.py 的单元测试。

按 FRAMEWORK.md 规范：
- 测试类 TestXxxYyy
- 测试方法 test_行为_期望
- parametrize 优先
- 文件 IO 通过 monkeypatch + tmp_path 隔离（pure unit）

覆盖：
- load_industry_thresholds：缓存 + 文件缺失 + 文件存在
- get_industry_threshold：行业存在/不存在/默认行业兜底/key 不存在
"""

from __future__ import annotations

import json

import pytest

# ═══════════════════════════════════════════════════════════════
# Fixtures：隔离全局缓存 + DATA_DIR
# ═══════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_thresholds_cache():
    """每个测试前清空 _industry_thresholds 全局缓存。"""
    import strategies.thresholds as thresholds_mod

    thresholds_mod._industry_thresholds = None
    yield
    thresholds_mod._industry_thresholds = None


@pytest.fixture
def mock_data_dir(monkeypatch, tmp_path):
    """monkeypatch common.DATA_DIR 到临时目录。"""

    def _create_config(content: dict | None) -> None:
        """content 为 None → 不创建文件（测试缺失路径）。"""
        if content is None:
            return
        (tmp_path / "industry_thresholds.json").write_text(
            json.dumps(content, ensure_ascii=False), encoding="utf-8"
        )

    import common

    monkeypatch.setattr(common, "DATA_DIR", tmp_path)
    return _create_config


# ═══════════════════════════════════════════════════════════════
# load_industry_thresholds
# ═══════════════════════════════════════════════════════════════


class TestLoadIndustryThresholds:
    def test_missing_file_returns_empty_dict(self, mock_data_dir):
        """industry_thresholds.json 缺失时返回空 dict（不抛异常）。"""
        mock_data_dir(content=None)

        from strategies.thresholds import load_industry_thresholds

        assert load_industry_thresholds() == {}

    def test_existing_file_loaded(self, mock_data_dir):
        """存在文件时正确加载。"""
        mock_data_dir(
            content={
                "默认": {"pe_undervalued": 15, "pe_reasonable": 25},
                "科技": {"pe_undervalued": 30, "pe_reasonable": 50},
            }
        )

        from strategies.thresholds import load_industry_thresholds

        result = load_industry_thresholds()
        assert "默认" in result
        assert "科技" in result
        assert result["科技"]["pe_undervalued"] == 30

    def test_caches_result(self, mock_data_dir):
        """多次调用应使用缓存，不重复读文件。"""
        mock_data_dir(content={"默认": {"pe_undervalued": 15}})

        from strategies.thresholds import load_industry_thresholds

        first = load_industry_thresholds()
        # 修改文件内容，缓存命中应返回旧值
        import strategies.thresholds as t

        (t.__class__.__module__)  # noqa
        second = load_industry_thresholds()
        assert first is second  # 同一对象引用

    def test_invalid_json_raises_json_decode_error(self, monkeypatch, tmp_path):
        """非法 JSON 应抛 JSONDecodeError（产品代码未做容错）。

        注：此为产品代码已知限制，调用方应确保配置文件合法。
        如未来要做容错，应在 load_industry_thresholds 加 try/except。
        """
        import common

        monkeypatch.setattr(common, "DATA_DIR", tmp_path)
        (tmp_path / "industry_thresholds.json").write_text(
            "{invalid json", encoding="utf-8"
        )

        from strategies.thresholds import load_industry_thresholds

        with pytest.raises(json.JSONDecodeError):
            load_industry_thresholds()


# ═══════════════════════════════════════════════════════════════
# get_industry_threshold
# ═══════════════════════════════════════════════════════════════


class TestGetIndustryThreshold:
    def test_known_industry_known_key(self, mock_data_dir):
        """已知行业 + 已知 key → 返回配置值。"""
        mock_data_dir(content={"科技": {"pe_undervalued": 30, "pe_reasonable": 50}})

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("科技", "pe_undervalued", 15) == 30
        assert get_industry_threshold("科技", "pe_reasonable", 25) == 50

    def test_unknown_industry_falls_back_to_default(self, mock_data_dir):
        """未知行业 → 回退到 '默认' 行业的配置。"""
        mock_data_dir(
            content={
                "默认": {"pe_undervalued": 12},
                "科技": {"pe_undervalued": 30},
            }
        )

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("不存在的行业", "pe_undervalued", 99) == 12

    def test_unknown_industry_no_default_falls_back_to_arg(self, mock_data_dir):
        """未知行业 + 无 '默认' 配置 → 返回入参 default。"""
        mock_data_dir(content={"科技": {"pe_undervalued": 30}})

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("不存在", "pe_undervalued", 99) == 99

    def test_known_industry_missing_key_returns_arg(self, mock_data_dir):
        """已知行业但 key 不存在 → 返回入参 default。"""
        mock_data_dir(content={"科技": {"pe_undervalued": 30}})

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("科技", "不存在的key", 99) == 99

    def test_empty_thresholds_file(self, mock_data_dir):
        """thresholds 文件为空 dict 时所有查询都返回 default。"""
        mock_data_dir(content={})

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("任何行业", "任何key", 42) == 42

    def test_missing_thresholds_file(self, mock_data_dir):
        """thresholds 文件缺失时所有查询都返回 default。"""
        mock_data_dir(content=None)

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold("任何行业", "任何key", 42) == 42

    @pytest.mark.parametrize(
        "industry,key,default,expected",
        [
            ("科技", "pe_undervalued", 15, 25),
            ("科技", "pe_reasonable", 25, 45),
            ("默认", "pe_undervalued", 99, 12),  # 用 '默认' 兜底
            ("不存在的", "unknown_key", 77, 77),  # 既不在行业也不在默认 → default
        ],
    )
    def test_priority_resolution(self, mock_data_dir, industry, key, default, expected):
        """优先级：行业配置 > '默认' 行业配置 > 入参 default。"""
        mock_data_dir(
            content={
                "默认": {"pe_undervalued": 12, "pe_reasonable": 30, "x": 50},
                "科技": {"pe_undervalued": 25, "pe_reasonable": 45},
            }
        )

        from strategies.thresholds import get_industry_threshold

        assert get_industry_threshold(industry, key, default) == expected


# ═══════════════════════════════════════════════════════════════
# 与 score_utils 集成
# ═══════════════════════════════════════════════════════════════


class TestThresholdIntegrationWithScoreUtils:
    """验证 thresholds 与 score_utils.pe_percentile 的协作。"""

    def test_pe_percentile_uses_industry_specific_thresholds(self, mock_data_dir):
        """pe_percentile 通过 industry 加载不同阈值表。"""
        mock_data_dir(
            content={
                "科技": {"pe_undervalued": 30, "pe_reasonable": 50, "pe_expensive": 80}
            }
        )

        from strategies.factors.score_utils import pe_percentile

        # 科技 PE=35 应在 mid 段 (30, 50] → 线性插值
        # (35-30)/(50-30) = 0.25, 15+0.25*35 = 23.75
        result = pe_percentile(35, "科技")
        assert result == pytest.approx(23.75, rel=1e-3)

    def test_pe_percentile_falls_back_when_industry_missing(self, mock_data_dir):
        """pe_percentile 在行业缺失时用代码硬编码默认阈值。"""
        mock_data_dir(content={})  # 无任何配置

        from strategies.factors.score_utils import pe_percentile

        # 默认代码硬编码：15/25/40
        assert pe_percentile(20) == 32.5
        assert pe_percentile(20, "不存在的行业") == 32.5

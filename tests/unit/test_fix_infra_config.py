"""2026-11-21 code review §4.1 #8 回归：死配置与并行超时误用。

- YAML cache.max_size/max_age 进入 DataConfig，供 common.cache 消费；
- parallel_timeout 有独立配置键，不再被 http.read_timeout 意外改写。
"""

from __future__ import annotations

import pytest

from data import config as dc


@pytest.fixture
def no_env(monkeypatch):
    """隔离环境变量，保证 YAML -> 默认值链路可断言。"""
    for name in (
        "DATA_HTTP_TIMEOUT",
        "DATA_PARALLEL_TIMEOUT",
        "DATA_CACHE_MAX_SIZE",
        "DATA_CACHE_MAX_AGE",
    ):
        monkeypatch.delenv(name, raising=False)


class TestP2ParallelTimeout:
    """parallel_timeout 不再误用 http.read_timeout。"""

    def test_read_timeout_no_longer_changes_parallel_budget(self, monkeypatch, no_env):
        monkeypatch.setattr(
            dc,
            "_load_yaml_config",
            lambda: {"http": {"connect_timeout": 9, "read_timeout": 55}},
        )
        cfg = dc.DataConfig.from_yaml_and_env()
        assert cfg.http_timeout == 9
        assert cfg.parallel_timeout == 30, "改单次读超时不应改变批量并行预算"

    def test_dedicated_yaml_key_and_env_override(self, monkeypatch, no_env):
        monkeypatch.setattr(
            dc,
            "_load_yaml_config",
            lambda: {"http": {"parallel_timeout": 12, "read_timeout": 55}},
        )
        assert dc.DataConfig.from_yaml_and_env().parallel_timeout == 12
        monkeypatch.setenv("DATA_PARALLEL_TIMEOUT", "17")
        assert dc.DataConfig.from_yaml_and_env().parallel_timeout == 17


class TestP2CacheLimitsConfig:
    """cache.max_size/max_age 由死配置变成有效配置。"""

    def test_defaults_when_yaml_missing(self, monkeypatch, no_env):
        monkeypatch.setattr(dc, "_load_yaml_config", lambda: {})
        cfg = dc.DataConfig.from_yaml_and_env()
        assert cfg.cache_max_size == 1000
        assert cfg.cache_max_age == 604800

    def test_yaml_values_loaded(self, monkeypatch, no_env):
        monkeypatch.setattr(dc, "_load_yaml_config", lambda: {"cache": {"max_size": 42, "max_age": 99}})
        cfg = dc.DataConfig.from_yaml_and_env()
        assert cfg.cache_max_size == 42
        assert cfg.cache_max_age == 99

    def test_env_override(self, monkeypatch, no_env):
        monkeypatch.setattr(dc, "_load_yaml_config", lambda: {"cache": {"max_size": 42, "max_age": 99}})
        monkeypatch.setenv("DATA_CACHE_MAX_SIZE", "7")
        monkeypatch.setenv("DATA_CACHE_MAX_AGE", "11")
        cfg = dc.DataConfig.from_yaml_and_env()
        assert cfg.cache_max_size == 7
        assert cfg.cache_max_age == 11

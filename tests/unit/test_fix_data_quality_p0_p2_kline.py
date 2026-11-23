"""P0-2 / P2 回归测试（2026-11-21 review）。

- P0-2：sina 不复权 K 线源必须是最后兜底；KlineBar 记录 adjust 口径；
  缓存键按口径区分。
- P2：数据源配置加载失败必须 warning 告警并在 manager 暴露生效标记。
"""

from __future__ import annotations

import logging

import pytest

from data import _dict_to_kline_bar
from data.types import KlineBar


# ---------- P0-2：优先级 ----------


def test_yaml_declares_sina_as_lowest_kline_priority():
    from config.loader import ConfigLoader

    sources = ConfigLoader.load("data_source.yaml").get("kline_sources", {})
    assert sources["sina"]["priority"] <= 0, "sina 不复权源必须降到最低优先级"
    assert sources["sina"]["priority"] < sources["eastmoney"]["priority"]
    assert sources["sina"]["priority"] < sources["tencent"]["priority"]


def test_kline_manager_first_fetcher_is_not_sina():
    from fetchers import get_kline_manager
    from fetchers.kline.sina_kline import SinaKlineFetcher

    mgr = get_kline_manager()
    assert mgr.fetchers, "manager 未加载任何 K 线 fetcher"
    assert not isinstance(mgr.fetchers[0], SinaKlineFetcher), "首位仍是 sina 不复权源（P0-2）"

    names = [f.name for f in mgr.fetchers]
    assert "sina_kline" in names
    idx = {name: i for i, name in enumerate(names)}
    assert idx["eastmoney_kline"] < idx["sina_kline"], "前复权源 eastmoney 必须排在 sina 前"
    assert idx["tencent_kline"] < idx["sina_kline"], "前复权源 tencent 必须排在 sina 前"

    sina = next(f for f in mgr.fetchers if f.name == "sina_kline")
    assert sina.priority <= 0, "sina fetcher 运行时优先级未降至最低"


# ---------- P0-2：adjust 元信息 ----------


def test_kline_bar_has_adjust_field_with_backcompat_default():
    assert KlineBar().adjust == "", "新增字段必须带默认值，保持 dataclass 向后兼容"
    assert KlineBar(day="2026-11-21", close=10.0).to_dict()["adjust"] == ""


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"source": "sina"}, "none"),
        ({"source": "eastmoney"}, "qfq"),
        ({"source": "tencent"}, "qfq"),
        ({"source": "unknown_source"}, ""),
        ({"source": "sina", "adjust": "qfq"}, "qfq"),  # 显式值优先
    ],
)
def test_kline_bar_adjust_inferred_from_source(record, expected):
    bar = _dict_to_kline_bar(record, "sh600989")
    assert bar.adjust == expected


# ---------- P0-2：缓存键按口径隔离 ----------


def test_kline_cache_key_distinguishes_adjust(monkeypatch, tmp_path):
    import common.cache as cache_mod
    import data as data_mod

    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    data_mod._load_fetchers()
    mgr = data_mod._kline_manager
    calls: list[tuple] = []

    def fake_fetch(code, scale=240, datalen=30, **kwargs):
        calls.append((code, scale, datalen))
        return [{"day": "2026-11-21", "close": "10.5", "source": "eastmoney"}]

    original = mgr.fetch
    mgr.fetch = fake_fetch
    try:
        data_mod.get_kline("sh600989", adjust="qfq")
        data_mod.get_kline("sh600989", adjust="qfq")
        assert len(calls) == 1, "同口径二次调用应命中缓存"
        data_mod.get_kline("sh600989", adjust="none")
        assert len(calls) == 2, "不同口径必须独立缓存键，触发重新 fetch（P0-2）"
        data_mod.get_kline("sh600989")  # 默认桶
        assert len(calls) == 3, "默认口径也应有自己的缓存桶"
    finally:
        mgr.fetch = original


def test_kline_cached_records_carry_adjust(monkeypatch, tmp_path):
    import common.cache as cache_mod
    import data as data_mod

    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    data_mod._load_fetchers()
    mgr = data_mod._kline_manager
    original = mgr.fetch
    mgr.fetch = lambda code, **kw: [
        {"day": "2026-11-21", "close": "10.5", "source": "sina"},
    ]
    try:
        bars = data_mod.get_kline("sh600989")
        assert bars[0].adjust == "none"
        bars2 = data_mod.get_kline("sh600989")  # 缓存命中
        assert bars2[0].adjust == "none", "缓存命中后仍需保留复权口径（P0-2）"
    finally:
        mgr.fetch = original


# ---------- P2：配置加载失败告警 + 标记 ----------


def test_config_load_failure_warns_and_marks_manager(monkeypatch, caplog):
    import fetchers as fetchers_mod
    from config.loader import ConfigLoader

    def boom(*args, **kwargs):
        raise RuntimeError("YAML 解析失败")

    monkeypatch.setattr(ConfigLoader, "load", staticmethod(boom))
    monkeypatch.setattr(fetchers_mod, "_managers", {})
    monkeypatch.setattr(fetchers_mod, "_source_config_status", {})

    with caplog.at_level(logging.WARNING, logger="fetchers"):
        cfg = fetchers_mod._load_source_config("quote_sources")
        mgr = fetchers_mod.get_quote_manager()

    assert cfg == {}, "配置加载失败应退回空配置"
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("quote_sources" in msg and "加载失败" in msg for msg in warnings), (
        "配置加载失败必须至少 warning 级告警（P2）"
    )
    assert getattr(mgr, "source_config_applied", None) is False, "manager 必须暴露配置未生效标记"
    assert fetchers_mod.is_source_config_applied("quote") is False


def test_config_applied_flag_true_on_success():
    import fetchers as fetchers_mod

    mgr = fetchers_mod.get_kline_manager()
    assert getattr(mgr, "source_config_applied", None) is True
    assert fetchers_mod.is_source_config_applied("kline") is True

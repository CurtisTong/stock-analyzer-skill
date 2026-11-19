"""log_silent_fallback 的去重与分级（2026-11-20）。

真实问题：全市场取数时每只股票都会触发同一个可选依赖缺失
（`No module named 'akshare'`），warning 每行一条，stderr 被刷 1 万+ 字节，
真降级被噪音淹没。

锁死三条规则：
1. 已知可选依赖缺失 → debug 级，单进程内只输出一次；
2. 其他失败（网络/接口改版）→ 首次 warning，同因后续降为 debug；
3. 去重键 = (module, 异常类型[+可选依赖名])，不同模块各自首次都要能看到。
"""

from __future__ import annotations

import logging

import pytest

from common.exceptions import silent_fallback as sf


@pytest.fixture(autouse=True)
def _reset():
    sf.reset_dedupe()
    yield
    sf.reset_dedupe()


def _calls(caplog, level):
    return [r for r in caplog.records if r.levelno == level and "静默降级" in r.getMessage()]


class TestOptionalDependencyMissing:
    def test_missing_akshare_logs_once_at_debug(self, caplog):
        caplog.set_level(logging.DEBUG)
        exc = ModuleNotFoundError("No module named 'akshare'", name="akshare")
        for _ in range(5):
            sf.log_silent_fallback("akshare_industry.fetch_industry", exc, fallback_reason="可选依赖")
        debugs = [r for r in _calls(caplog, logging.DEBUG) if "可选依赖缺失" in r.getMessage()]
        warnings = [r for r in _calls(caplog, logging.WARNING) if "akshare_industry" in r.getMessage()]
        assert len(debugs) == 1, f"可选依赖缺失必须只提示一次，实际 {len(debugs)}"
        assert warnings == [], "可选依赖缺失不得用 warning 刷屏"

    def test_different_modules_each_get_one_hint(self, caplog):
        caplog.set_level(logging.DEBUG)
        exc = ModuleNotFoundError("No module named 'akshare'", name="akshare")
        sf.log_silent_fallback("akshare_industry.fetch", exc)
        sf.log_silent_fallback("industry_beta.fetch", exc)
        debugs = [r for r in _calls(caplog, logging.DEBUG) if "可选依赖缺失" in r.getMessage()]
        assert len(debugs) == 2

    def test_importerror_message_form_is_detected(self):
        exc = ImportError("No module named 'pandas'")
        assert sf._missing_optional_dep(exc) == "pandas"

    def test_unknown_module_is_not_treated_as_optional(self):
        exc = ModuleNotFoundError("No module named 'my_internal_mod'", name="my_internal_mod")
        assert sf._missing_optional_dep(exc) is None


class TestRealDataFailure:
    def test_first_failure_warns_then_dedupes(self, caplog):
        caplog.set_level(logging.DEBUG)
        exc = ConnectionError("Remote end closed connection")
        for _ in range(4):
            sf.log_silent_fallback("fetchers.quote.xueqiu_quote.fetch", exc, fallback_reason="切换数据源")
        warnings = [r for r in _calls(caplog, logging.WARNING) if "xueqiu" in r.getMessage()]
        debugs = [r for r in _calls(caplog, logging.DEBUG) if "同因已提示过" in r.getMessage()]
        assert len(warnings) == 1, "同因真失败只应有一条 warning"
        assert len(debugs) == 3, "后续同因应降到 debug"

    def test_different_exception_types_both_warn(self, caplog):
        caplog.set_level(logging.DEBUG)
        sf.log_silent_fallback("fetchers.quote.sina.fetch", ConnectionError("net"))
        sf.log_silent_fallback("fetchers.quote.sina.fetch", ValueError("接口改版"))
        warnings = [r for r in _calls(caplog, logging.WARNING) if "sina" in r.getMessage()]
        assert len(warnings) == 2

    def test_warning_keeps_extra_silent_flag(self, caplog):
        caplog.set_level(logging.DEBUG)
        sf.log_silent_fallback("fetchers.quote.sina.fetch", ConnectionError("net"))
        rec = [r for r in _calls(caplog, logging.WARNING)][0]
        assert getattr(rec, "silent", None) is True
        assert getattr(rec, "location", None) == "fetchers.quote.sina.fetch"

    def test_no_exception_still_logs(self, caplog):
        caplog.set_level(logging.DEBUG)
        sf.log_silent_fallback("universe_loader.blacklist", None, default_value=[])
        assert len([r for r in _calls(caplog, logging.WARNING)]) == 1

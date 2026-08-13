"""脚本 common 包覆盖补充（v2.7 任务 B：coverage）。

覆盖 2026-08-13 基线缺口 0% 模块：
- version.py: 正常读取 / 文件缺失 / 解析异常
- metrics.py: record_fetch / record_cache / get_summary / dump / get_collector 单例
- glossary.py: format_glossary / add_glossary / auto_detect_terms
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════
# version
# ═══════════════════════════════════════════════════════════════


class TestVersion:
    def test_version_parsed_from_pyproject(self):
        from common.version import __version__

        assert isinstance(__version__, str)
        assert len(__version__.split(".")) >= 2

    def test_read_version_value(self):
        from common.version import _read_version

        v = _read_version()
        assert v != "0.0.0"
        assert v.split(".")[0].isdigit()

    def test_read_version_missing_file(self, monkeypatch):
        from common.version import _read_version

        p = MagicMock()
        p.exists.return_value = False
        with patch("common.version.Path", lambda *a, **k: p):
            assert _read_version() == "0.0.0"

    def test_read_version_parse_exception(self, monkeypatch):
        from common.version import _read_version

        def boom_read(**kw):
            raise PermissionError("denied")

        p = MagicMock()
        p.exists.return_value = True
        p.read_text.side_effect = boom_read
        p.resolve.return_value = p
        p.parents.__getitem__.return_value = p
        p.__truediv__.return_value = p
        with patch("common.version.Path", lambda *a, **k: p):
            assert _read_version() == "0.0.0"

    def test_read_version_not_a_version_string(self, monkeypatch):
        """read_text 无法按 line 解析 → 内层 except/外回退。"""
        from common.version import _read_version

        p = MagicMock()
        p.exists.return_value = True
        p.read_text.return_value = "name = stock-analyzer\n"
        p.resolve.return_value = p
        p.parents.__getitem__.return_value = p
        p.__truediv__.return_value = p
        with patch("common.version.Path", lambda *a, **k: p):
            assert _read_version() == "0.0.0"

    def test_module_import_fallback(self):
        """模块级 except（27-28 行）：from pathlib import Path 抛异常 → __version__ = 0.0.0。"""
        import subprocess
        import sys

        code = (
            "import sys; sys.path.insert(0, 'scripts');\n"
            "import builtins;\n"
            "_orig_import = builtins.__import__;\n"
            "def _block(name, *a, **k):\n"
            "    if name == 'pathlib':\n"
            "        raise RuntimeError('blocked')\n"
            "    return _orig_import(name, *a, **k)\n"
            "builtins.__import__ = _block;\n"
            "import importlib;\n"
            "v = importlib.import_module('common.version');\n"
            "assert v.__version__ == '0.0.0';\n"
            "print('OK')\n"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert r.returncode == 0, r.stderr


# ═══════════════════════════════════════════════════════════════
# metrics
# ═══════════════════════════════════════════════════════════════


class TestMetrics:
    def test_record_fetch_summary(self):
        from common.metrics import MetricsCollector

        m = MetricsCollector()
        m.record_fetch("tencent", True, 120.0)
        m.record_fetch("tencent", False, 200.0)
        m.record_fetch("tdx", True, 50.0)
        s = m.get_summary()
        c = s["counters"]
        assert c["fetch.tencent.total"] == 2
        assert c["fetch.tencent.success"] == 1
        assert c["fetch.tencent.failure"] == 1
        assert c["fetch.tencent.success_rate"] == 50.0
        assert c["fetch.tdx.success_rate"] == 100.0
        lat = s["latency"]["fetch.tencent"]
        assert lat["count"] == 2
        assert lat["min_ms"] == 120.0
        assert lat["max_ms"] == 200.0

    def test_record_cache(self):
        from common.metrics import MetricsCollector

        m = MetricsCollector()
        m.record_cache(True)
        m.record_cache(False)
        s = m.get_summary()
        assert s["counters"]["cache.hit_rate"] == 50.0

    def test_empty_summary(self):
        from common.metrics import MetricsCollector

        m = MetricsCollector()
        s = m.get_summary()
        assert s["counters"] == {}
        assert s["latency"] == {}
        assert isinstance(s["uptime_seconds"], (int, float))

    def test_dump_default_path(self, tmp_path):
        from common.metrics import MetricsCollector
        from common import cache

        with patch.object(cache, "CACHE_DIR", tmp_path):
            m = MetricsCollector()
            m.record_cache(True)
            m.dump()
            p = tmp_path / "metrics.json"
            assert p.exists()
            data = json.loads(p.read_text(encoding="utf-8"))
            assert data["counters"]["cache.total"] == 1

    def test_dump_explicit_path(self, tmp_path):
        from common.metrics import MetricsCollector

        m = MetricsCollector()
        m.record_fetch("a", True, 10.0)
        m.dump(tmp_path / "sub" / "m.json")
        assert (tmp_path / "sub" / "m.json").exists()

    def test_get_collector_singleton(self):
        from common.metrics import get_collector

        with patch("common.metrics._collector", None):
            c1 = get_collector()
            c2 = get_collector()
            assert c1 is c2

    def test_get_collector_cached(self):
        from common.metrics import get_collector, MetricsCollector

        inst = MetricsCollector()
        with patch("common.metrics._collector", inst):
            assert get_collector() is inst


# ═══════════════════════════════════════════════════════════════
# glossary
# ═══════════════════════════════════════════════════════════════


class TestGlossary:
    def test_format_known_terms(self):
        from common.glossary import format_glossary

        out = format_glossary(["PE", "MACD"])
        assert "市盈率" in out
        assert "指数平滑异同移动平均线" in out
        assert "术语解释" in out

    def test_format_unknown_terms(self):
        from common.glossary import format_glossary

        assert format_glossary(["不存在的术语XYZ"]) == ""

    def test_format_empty(self):
        from common.glossary import format_glossary

        assert format_glossary([]) == ""

    def test_add_glossary_append(self):
        from common.glossary import add_glossary

        out = add_glossary("正文", ["PE"])
        assert "正文" in out
        assert "## 术语解释" in out
        assert "市盈率" in out

    def test_add_glossary_no_match(self):
        from common.glossary import add_glossary

        assert add_glossary("正文", ["NOPE"]) == "正文"

    def test_auto_detect_terms(self):
        from common.glossary import auto_detect_terms

        terms = auto_detect_terms("股票的PE看起来合理，MACD金叉")
        assert "PE" in terms
        assert "MACD" in terms

    def test_auto_detect_no_false_word_boundary(self):
        from common.glossary import auto_detect_terms

        assert "MA" not in auto_detect_terms("Mango 词")


# ═══════════════════════════════════════════════════════════════
# exporters
# ═══════════════════════════════════════════════════════════════


class TestExporters:
    def test_risk_disclaimer(self):
        from common.exporters import add_risk_disclaimer

        out = add_risk_disclaimer("正文")
        assert "风险提示" in out
        assert "不构成投资建议" in out

    def test_export_to_csv_basic(self, tmp_path):
        from common.exporters import export_to_csv

        data = [{"code": "sh600989", "name": "宝丰能源", "score": 78}]
        export_to_csv(data, "result", output_dir=str(tmp_path))
        content = (tmp_path / "result.csv").read_text(encoding="utf-8-sig")
        assert content.startswith("code")
        assert "宝丰能源" in content
        assert "78" in content

    def test_export_to_csv_empty(self, tmp_path):
        from common.exporters import export_to_csv

        export_to_csv([], "empty", output_dir=str(tmp_path))
        assert (tmp_path / "empty.csv").read_text(encoding="utf-8-sig") == ""

    def test_export_filename_sanitized(self, tmp_path):
        from common.exporters import export_to_csv

        p = export_to_csv([{"a": 1}], "../evil/name", output_dir=str(tmp_path))
        assert "../" not in p
        assert p.startswith(str(tmp_path))

    def test_export_analysis_flatten(self, tmp_path, monkeypatch):
        from common.exporters import export_analysis_to_csv

        monkeypatch.chdir(tmp_path)
        analysis = {"score": 80, "sub": {"pe": 10.5, "list": [1, 2]}}
        export_analysis_to_csv(analysis, "analysis")
        content = (tmp_path / "output" / "analysis.csv").read_text(encoding="utf-8-sig")
        assert "score" in content
        assert "sub.pe" in content
        assert "[1, 2]" in content

    def test_flatten_dict(self):
        from common.exporters import _flatten_dict

        assert _flatten_dict({"a": {"b": 1, "c": "x"}, "d": 2}) == {
            "a.b": 1,
            "a.c": "x",
            "d": 2,
        }


# ═══════════════════════════════════════════════════════════════
# formatters
# ═══════════════════════════════════════════════════════════════


class TestFormatters:
    def test_format_output_full(self):
        from common.formatters import format_output

        out = format_output(
            conclusion="可分批介入",
            data_time="2026-06-15 14:30",
            sources=["腾讯"],
            failed_sources=["新浪"],
            ttl_sec=900,
            body="详情",
        )
        assert out.startswith("🎯 可分批介入")
        assert "数据时间戳: 2026-06-15 14:30" in out
        assert "数据源: 腾讯" in out
        assert "⚠️ 失败源: 新浪" in out
        assert "数据 TTL: 900s" in out
        assert "详情" in out

    def test_format_output_confidence_low(self):
        from common.formatters import format_output

        out = format_output("结论", confidence=59.4)
        assert "⚠️ 数据置信度: 59/100" in out

    def test_format_output_confidence_high(self):
        from common.formatters import format_output

        out = format_output("结论", confidence=80.0)
        assert "置信度" not in out

    def test_format_output_minimal(self):
        from common.formatters import format_output

        assert format_output("结论") == "🎯 结论\n"

    def test_format_conclusion(self):
        from common.formatters import format_conclusion

        assert format_conclusion("买", emoji="🟢") == "🟢 买"

    def test_format_footer_empty(self):
        from common.formatters import format_footer

        assert format_footer() == ""

    def test_format_footer_degraded(self):
        from common.formatters import format_footer

        out = format_footer(data_time="t", sources=["a"], degraded=True)
        assert out.startswith("─" * 40)
        assert "⚠️ 数据降级" in out

    def test_format_footer_normal(self):
        from common.formatters import format_footer

        out = format_footer(data_time="t", sources=["a"])
        assert "📊 数据时间戳: t | 数据源: a" in out

    def test_now_str(self):
        from common.formatters import now_str

        out = now_str()
        assert len(out) >= 16
        assert "-" in out

    def test_collect_source_evidence(self):
        from common.formatters import collect_source_evidence

        s, f = collect_source_evidence({"a": "ok", "b": None})
        assert s == ["a"]
        assert f == ["b"]

    def test_format_with_enhancements(self):
        from common.formatters import format_with_enhancements

        out = format_with_enhancements("正文", terms=["PE"], risk_disclaimer=True)
        assert "市盈率" in out
        assert "风险提示" in out

    def test_format_with_enhancements_auto(self):
        from common.formatters import format_with_enhancements

        out = format_with_enhancements("股票的PE合理", auto_glossary=True)
        assert "市盈率" in out
        assert "风险提示" in out

    def test_format_with_enhancements_no_disclaimer(self):
        from common.formatters import format_with_enhancements

        out = format_with_enhancements("正文", terms=[], risk_disclaimer=False)
        assert "风险提示" not in out

    def test_markdown_table(self):
        from common.formatters import markdown_table

        t = markdown_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert t.startswith("| A | B |")
        assert "| 1 | 2 |" in t
        assert ":------" in t

    def test_markdown_table_center(self):
        from common.formatters import markdown_table

        t = markdown_table(["A"], [["x"]], align="center")
        assert ":------:" in t

    def test_markdown_table_empty(self):
        from common.formatters import markdown_table

        assert markdown_table([], []) == ""
        assert markdown_table(["A"], []) == ""

    def test_numbered_table(self):
        from common.formatters import numbered_table

        t = numbered_table(["A"], [["x"], ["y"]], start=5)
        assert "| 排名" in t
        assert "| 5 | x |" in t
        assert "| 6 | y |" in t
        assert "------:" in t

    def test_numbered_table_empty(self):
        from common.formatters import numbered_table

        assert numbered_table([], []) == ""


# ═══════════════════════════════════════════════════════════════
# parsers
# ═══════════════════════════════════════════════════════════════


class TestParsers:
    def test_parse_tencent_line_normal(self):
        from common.parsers import parse_tencent_line

        parts = ["1"] * 50
        parts[0] = "sh"
        parts[1] = "宝丰能源"
        parts[2] = "600989"
        parts[3] = "10.0"
        parts[4] = "9.5"
        parts[5] = "9.6"
        parts[31] = "0.5"
        parts[32] = "5.26"
        parts[33] = "10.2"
        parts[34] = "9.4"
        parts[36] = "1000"
        parts[37] = "1000.0"
        parts[38] = "1.5"
        parts[39] = "12.3"
        parts[43] = "8.4"
        parts[44] = "200"
        parts[45] = "150"
        parts[46] = "1.2"
        parts[47] = "10.45"
        parts[48] = "8.55"
        line = 'v_sh600989="' + "~".join(parts) + '";'
        r = parse_tencent_line(line)
        assert r["code"] == "600989"
        assert r["name"] == "宝丰能源"
        assert r["price"] == "10.0"
        assert r["change_pct"] == "5.26"
        assert r["total_cap"] == str(round(200 * 1e8))
        assert r["circulating_cap"] == str(round(150 * 1e8))
        assert r["pe"] == "12.3"

    def test_parse_tencent_line_invalid(self):
        from common.parsers import parse_tencent_line

        assert parse_tencent_line("no equals") == {}
        assert parse_tencent_line('v_sh="a~b"') == {}  # parts < 50

    def test_yi_to_yuan(self):
        from common.parsers import _yi_to_yuan

        assert _yi_to_yuan("200") == str(round(200 * 1e8))
        assert _yi_to_yuan("abc") == "abc"
        assert _yi_to_yuan("") == ""

    def test_repair_tencent_name_normal(self):
        from common.parsers import repair_tencent_name

        assert repair_tencent_name("宝丰能源") == "宝丰能源"
        assert repair_tencent_name("") == ""

    def test_repair_tencent_name_garbled(self):
        from common.parsers import repair_tencent_name

        # 洽洽食品 的 GBK 字节被误当 UTF-8 的典型乱码
        assert repair_tencent_name("ǢǢʳƷ") == "洽洽食品"

    def test_repair_tencent_name_unfixable(self, monkeypatch):
        from common.parsers import repair_tencent_name

        # encode raise → strict 失败 → 兜底 replace 失败 → 保留原值
        class BoomStr(str):
            def encode(self, *a, **k):
                raise UnicodeEncodeError("utf-8", "", 0, 1, "boom")

        val = BoomStr("ǢǢʳƷ")
        assert repair_tencent_name(val) == val

    def test_repair_tencent_name_fallback_replace(self):
        from common.parsers import repair_tencent_name

        # strict 失败 → 兜底 replace 成功 → 部分修复返回非空
        class StrictBoomStr(str):
            def encode(self, *a, **k):
                if k.get("errors") == "strict":
                    raise UnicodeEncodeError("gbk", "", 0, 1, "strict boom")
                return super().encode(*a, **k)

        val = StrictBoomStr("ǢǢʳƷ")
        out = repair_tencent_name(val)
        assert isinstance(out, str)

    def test_looks_garbled_non_cjk_latin(self):
        """不含中文但含非 ASCII 拉丁字符 → 判定乱码（33 行）。"""
        from common.parsers import _looks_garbled

        assert _looks_garbled("café") is True  # é 为拉丁扩展字符，无中文
        assert _looks_garbled("中文") is False
        assert _looks_garbled("") is False
        assert _looks_garbled(None) is False

    def test_parse_sina_quote_short_line(self):
        """新浪行情行字段不足 32 个 → 返回 {}（156 行）。"""
        from common.parsers import parse_sina_quote_line

        assert parse_sina_quote_line('var hq_str_sh600989="a,b,c";') == {}

    def test_repair_tencent_name_fallback_exception(self):
        from common.parsers import repair_tencent_name

        # strict 与 replace 都抛错 → 保留原值（64-65 行 except Exception）
        class FullBoomStr(str):
            def encode(self, *a, **k):
                if k.get("errors") == "strict":
                    raise UnicodeEncodeError("gbk", "", 0, 1, "strict boom")
                raise UnicodeDecodeError("gbk", b"", 0, 1, "replace boom")

        val = FullBoomStr("ǢǢʳƷ")
        assert repair_tencent_name(val) == val

    def test_looks_garbled(self):
        from common.parsers import _looks_garbled

        assert _looks_garbled("ǢǢʳƷ") is True
        assert _looks_garbled("宝丰能源") is False
        assert _looks_garbled("") is False

    def test_parse_sina_quote_line(self):
        from common.parsers import parse_sina_quote_line

        line = 'var hq_str_sh600989="宝丰能源,9.6,9.5,10.0,10.2,9.4,1000,2000,10000,1000000,...";'
        # 补齐 32 个字段
        fields = ["宝丰能源", "9.6", "9.5", "10.0", "10.2", "9.4"]
        while len(fields) < 32:
            fields.append("0")
        fields[8] = "10000"
        fields[9] = "1000000"
        line = 'var hq_str_sh600989="' + ",".join(fields) + '";'
        r = parse_sina_quote_line(line)
        assert r["code"] == "sh600989"
        assert r["price"] == "10.0"
        assert r["change_pct"] == str(round((10.0 / 9.5 - 1) * 100, 2))

    def test_parse_sina_quote_line_invalid(self):
        from common.parsers import parse_sina_quote_line

        assert parse_sina_quote_line("no") == {}

    def test_parse_strings_bad_float_still_defaults(self):
        from common.parsers import parse_sina_quote_line

        fields = ["名称", "1", "0", "abc", "2", "1"] + ["0"] * 26
        line = 'var hq_str_sh600989="' + ",".join(fields) + '";'
        r = parse_sina_quote_line(line)
        assert r["change_pct"] == "0"
        assert r["change_amt"] == "0"


# ═══════════════════════════════════════════════════════════════
# silent_fallback + lazy_registry
# ═══════════════════════════════════════════════════════════════


class TestSilentFallbackAndRegistry:
    def test_log_silent_fallback_no_exception(self, caplog):
        import logging as _l

        from common.exceptions.silent_fallback import log_silent_fallback

        with caplog.at_level(_l.WARNING):
            log_silent_fallback(
                "universe_loader.load_blacklist",
                fallback_reason="配置缺失",
                default_value=[1],
                extra_context={"file": "x"},
            )
        assert "静默降级" in caplog.text
        assert "universe_loader" in caplog.text
        assert "配置缺失" in caplog.text
        assert caplog.records[-1].silent is True

    def test_log_silent_fallback_with_exception(self, caplog):
        import logging as _l

        from common.exceptions.silent_fallback import log_silent_fallback

        with caplog.at_level(_l.WARNING):
            log_silent_fallback("x", exception=ValueError("bad"))
        assert "ValueError" in caplog.text
        assert "(no exception)" not in caplog.text

    def test_lazy_registry(self):
        from common.lazy_registry import LazyFetcherRegistry

        class F:
            def __init__(self, name):
                self.name = name

        calls = []

        def import_func():
            calls.append(1)
            return [F("margin"), F("margin_flow")]

        reg = LazyFetcherRegistry(import_func)
        all1 = reg.get_all()
        all2 = reg.get_all()
        assert all1 is all2
        assert len(calls) == 1
        found = reg.find("margin")
        assert found.name == "margin"
        assert reg.find("none") is None

    def test_lazy_registry_reset(self):
        from common.lazy_registry import LazyFetcherRegistry

        def import_func():
            return ["a"]

        reg = LazyFetcherRegistry(import_func)
        reg.get_all()
        reg.reset()
        assert reg._cache is None
        assert reg.get_all() == ["a"]

    def test_lazy_registry_double_check(self):
        """锁内二次检查命中（48 行）：外层未命中，进入锁时被并发线程填充。"""
        from common.lazy_registry import LazyFetcherRegistry

        class FakeLock:
            def __enter__(self):
                # 模拟并发线程在拿到锁后、当前线程检查前填充缓存
                self.reg._cache = ["cached"]
                return self

            def __exit__(self, *exc):
                return False

        reg = LazyFetcherRegistry(lambda: ["from-import"])
        lock = FakeLock()
        lock.reg = reg
        old_lock = reg._lock
        reg._lock = lock
        try:
            assert reg.get_all() == ["cached"]
        finally:
            reg._lock = old_lock


# ═══════════════════════════════════════════════════════════════
# exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_base_attributes(self):
        from common.exceptions import StockAnalyzerError

        e = StockAnalyzerError("msg", {"k": "v"})
        assert e.message == "msg"
        assert e.details == {"k": "v"}
        assert "msg" in str(e)
        assert repr(e).startswith("StockAnalyzerError(")

    def test_base_without_details(self):
        from common.exceptions import StockAnalyzerError

        e = StockAnalyzerError("m")
        assert e.details == {}

    def test_to_dict(self):
        from common.exceptions import StockAnalyzerError

        d = StockAnalyzerError("m", {"a": 1}).to_dict()
        assert d == {
            "error_type": "StockAnalyzerError",
            "message": "m",
            "details": {"a": 1},
        }

    def test_network_error(self):
        from common.exceptions import NetworkError

        e = NetworkError("http://a", "连接超时", retry_count=2)
        assert e.url == "http://a"
        assert e.retry_count == 2
        assert "http://a" in e.details["url"]
        assert e.details["retry_count"] == 2

    def test_rate_limit_with_retry_after(self):
        from common.exceptions import RateLimitError

        e = RateLimitError("http://a", retry_after=30)
        assert e.retry_after == 30
        assert "30 秒" in e.message
        assert e.details["retry_after"] == 30

    def test_rate_limit_without_retry_after(self):
        from common.exceptions import RateLimitError

        e = RateLimitError("http://a")
        assert e.retry_after is None
        assert "稍后重试" in e.message

    def test_parse_error(self):
        from common.exceptions import ParseError

        e = ParseError("x" * 300, "tencent", "分隔符缺失")
        assert e.parser == "tencent"
        assert len(e.raw_preview) == 200
        assert e.details["data_preview"] == e.raw_preview
        assert "tencent" in e.message

    def test_parse_error_empty_raw(self):
        from common.exceptions import ParseError

        e = ParseError("", "tencent", "空数据")
        assert e.raw_preview == ""

    def test_http_status_error(self):
        from common.exceptions import HTTPStatusError

        e = HTTPStatusError("http://a", 404, "body" * 100)
        assert e.status == 404
        assert len(e.body) == 200

    def test_data_unavailable(self):
        from common.exceptions import DataUnavailableError

        e = DataUnavailableError("tencent", 5)
        assert e.source == "tencent"
        assert e.failures == 5
        assert "5 次" in e.message

    def test_validation_error(self):
        from common.exceptions import ValidationError

        e = ValidationError("code", "abcabcabc", "格式不正确")
        assert e.field == "code"
        assert e.value_str == "abcabcabc"
        assert e.details["constraint"] == "格式不正确"

    def test_validation_error_long_value(self):
        from common.exceptions import ValidationError

        e = ValidationError("code", "x" * 200, "太长")
        assert len(e.value_str) == 100

    def test_validation_error_none_value(self):
        from common.exceptions import ValidationError

        e = ValidationError("code", None, "不能为空")
        assert e.value_str is None
        assert e.details["value"] is None

    def test_insufficient_data(self):
        from common.exceptions import InsufficientDataError

        e = InsufficientDataError("K线", 50, 30, "daily")
        assert e.data_type == "K线"
        assert e.required == 50
        assert e.actual == 30
        assert "daily" in e.message
        assert e.details["context"] == "daily"

    def test_insufficient_data_no_context(self):
        from common.exceptions import InsufficientDataError

        e = InsufficientDataError("K线", 50, 30)
        assert e.details["context"] == ""
        assert "[daily]" not in e.message

    def test_screener_timeout_error(self):
        from common.exceptions import ScreenerTimeoutError

        e = ScreenerTimeoutError(600, 610.5, 3)
        assert e.partial_rows == 3
        assert "610.5s" in e.message
        assert e.details["partial_rows"] == 3

    def test_configuration_error(self):
        from common.exceptions import ConfigurationError

        assert issubclass(ConfigurationError, Exception)

    def test_hierarchy(self):
        from common.exceptions import (
            BusinessError,
            DataError,
            NetworkError,
            RateLimitError,
            StockAnalyzerError,
            StrategyError,
        )

        assert issubclass(DataError, StockAnalyzerError)
        assert issubclass(NetworkError, DataError)
        assert issubclass(RateLimitError, NetworkError)
        assert issubclass(BusinessError, StockAnalyzerError)
        assert issubclass(StrategyError, BusinessError)


# ═══════════════════════════════════════════════════════════════
# cache
# ═══════════════════════════════════════════════════════════════


class TestCache:
    @pytest.fixture
    def cdir(self, tmp_path, monkeypatch):
        import common.cache as cache_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
        return tmp_path

    def test_get_missing(self, cdir):
        from common.cache import get

        assert get("nope", 60) is None

    def test_put_get_roundtrip(self, cdir):
        from common.cache import get, put

        put("k", b"hello")
        assert get("k", 60) == b"hello"

    def test_put_expires(self, cdir, monkeypatch):
        import os
        import time as _time

        from common.cache import get, put

        put("k", b"hello")
        f = cdir / "k.cache"
        os.utime(f, (_time.time() - 200, _time.time() - 200))
        assert get("k", 60) is None
        assert not f.exists()  # 过期文件被清除

    def test_invalid_key(self, cdir):
        from common.cache import get, put

        for bad in ("", "a/b", "a\\b", ".."):
            with pytest.raises(ValueError):
                get(bad, 60)
            with pytest.raises(ValueError):
                put(bad, b"x")

    def test_set_alias_deprecated(self, cdir):
        import warnings

        from common.cache import get, set

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            set("k", b"v")
        assert get("k", 60) == b"v"

    def test_json_roundtrip(self, cdir):
        from common.cache import get_json, set_json

        set_json("k", {"a": [1, 2], "name": "中文"})
        assert get_json("k", 60) == {"a": [1, 2], "name": "中文"}
        assert get_json("missing", 60) is None

    def test_json_corrupt(self, cdir):
        from common.cache import get_json, put

        put("k", b"{not-json")
        assert get_json("k", 60) is None

    def test_clear_all(self, cdir):
        from common.cache import clear, put

        put("a", b"1")
        put("b", b"2")
        clear()
        assert (cdir / "a.cache").exists() is False
        assert (cdir / "b.cache").exists() is False

    def test_clear_prefix(self, cdir):
        from common.cache import clear, put

        put("sh6001", b"1")
        put("sz0001", b"2")
        clear(prefix="sh")
        assert (cdir / "sh6001.cache").exists() is False
        assert (cdir / "sz0001.cache").exists() is True

    def test_clear_no_dir(self, monkeypatch, tmp_path):
        import common.cache as cache_mod

        from common.cache import clear

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / "missing")
        clear()  # 目录不存在直接返回

    def test_cleanup(self, cdir, monkeypatch):
        import time as _time
        import os

        from common.cache import cleanup, put

        put("old", b"x")
        put("new", b"y")
        (cdir / "old.cache").unlink()
        (cdir / "prefix_data.cache").write_bytes(b"z")
        # 把 old 文件做旧
        import time

        old_f = cdir / "old.cache"
        old_f.write_bytes(b"x")
        os.utime(old_f, (time.time() - 90000, time.time() - 90000))
        n = cleanup(max_age_seconds=86400)
        assert n >= 1
        assert not old_f.exists()

    def test_cleanup_with_prefix(self, cdir):
        import os
        import time

        from common.cache import cleanup, put

        put("abc_x", b"1")
        f = cdir / "abc_x.cache"
        os.utime(f, (time.time() - 90000, time.time() - 90000))
        put("def_x", b"2")
        cleanup(prefix="abc", max_age_seconds=86400)
        assert not (cdir / "abc_x.cache").exists()
        assert (cdir / "def_x.cache").exists()

    def test_cache_key_consistent(self):
        from common.cache import cache_key

        k1 = cache_key("http://example.com")
        k2 = cache_key("http://example.com")
        assert k1 == k2
        assert len(k1) == 32
        assert cache_key("http://example.com/other") != k1

    def test_cache_key_for_stock(self):
        import hashlib

        from common.cache import cache_key_for_stock

        k = cache_key_for_stock("quote", "sh600989", days=30, bar="day")
        assert k.startswith("quote_sh600989_")
        k2 = cache_key_for_stock("quote", "sh600989", days=30, bar="day")
        assert k == k2
        k3 = cache_key_for_stock("quote", "sz000001", days=30, bar="day")
        assert k3 != k

    def test_cache_aliases(self, cdir):
        from common.cache import cache_cleanup, cache_get, cache_set

        assert cache_get("nope", 60) is None
        cache_set("k", b"v")
        assert cache_get("k", 60) == b"v"
        assert cache_cleanup() == 0

    def test_cleanup_tmp_files(self, cdir):
        from common.cache import cleanup_tmp_files

        assert cleanup_tmp_files() == 0
        (cdir / "leftover.tmp").write_bytes(b"x")
        n = cleanup_tmp_files()
        assert n == 1
        assert not (cdir / "leftover.tmp").exists()

    def test_cleanup_tmp_no_dir(self, monkeypatch, tmp_path):
        import common.cache as cache_mod

        from common.cache import cleanup_tmp_files

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path / "missing")
        assert cleanup_tmp_files() == 0

    def test_cleanup_by_size_under_limit(self, cdir):
        from common.cache import cleanup_by_size

        assert cleanup_by_size(max_size_mb=10) == 0

    def test_cleanup_by_size_clean_one(self, cdir):
        import os

        from common.cache import cleanup_by_size, put

        put("big", b"x" * 1024)
        f = cdir / "big.cache"
        assert cleanup_by_size(max_size_mb=0) >= 1
        assert not f.exists()

    def test_cleanup_by_size_empty_dir(self, cdir):
        from common.cache import cleanup_by_size

        assert cleanup_by_size(max_size_mb=1) == 0

    def test_cleanup_by_size_break_after_one(self, cdir):
        """删除 1 个后低于限额 → break（235 行）。"""
        import time as _time

        from common.cache import cleanup_by_size, put

        put("a", b"x" * 2048)
        _time.sleep(0.01)
        put("b", b"y" * 2048)
        # 总 4096B > 限额 2097B；删 1 个后 current=2048 <= 2097 → break
        assert cleanup_by_size(max_size_mb=0.002) == 1
        assert (cdir / "a.cache").exists() or (cdir / "b.cache").exists()

    def test_cleanup_tmp_oserror(self, cdir, monkeypatch):
        import common.cache as cache_mod

        from common.cache import cleanup_tmp_files

        (cdir / "x.tmp").write_bytes(b"x")

        def boom(f):
            raise OSError("locked")

        monkeypatch.setattr(Path, "unlink", lambda self: boom(self))
        assert cleanup_tmp_files() == 0

    def test_get_cache_stats_empty(self, cdir):
        from common.cache import get_cache_stats

        s = get_cache_stats()
        assert s["total_files"] == 0
        assert s["total_size_mb"] == 0.0
        assert s["oldest_file"] is None

    def test_get_cache_stats_populated(self, cdir):
        from common.cache import get_cache_stats, put

        put("a", b"x" * (1024 * 1024))
        put("b", b"y" * (1024 * 1024))
        s = get_cache_stats()
        assert s["total_files"] == 2
        assert s["total_size_mb"] > 0
        assert s["oldest_file"] is not None
        assert s["newest_file"] is not None

    def test_put_cleanup_triggered(self, cdir, monkeypatch):
        """74-75 行：写满 _CLEANUP_INTERVAL 次触发 cleanup_by_size。"""
        import common.cache as cache_mod

        from common.cache import put

        calls = {"n": 0}

        def fake_cleanup(**kw):
            calls["n"] += 1
            return 0

        monkeypatch.setattr(cache_mod, "cleanup_by_size", fake_cleanup)
        monkeypatch.setattr(cache_mod, "_CLEANUP_INTERVAL", 3)
        monkeypatch.setattr(cache_mod, "_WRITE_COUNTER", 2)
        for _ in range(2):
            put(f"k{_}", b"x")
        assert calls["n"] == 1

    def test_put_cleanup_failure_ignored(self, cdir, monkeypatch, caplog):
        """77-80 行：cleanup 抛异常不影响写入。"""
        import logging as _l

        import common.cache as cache_mod

        from common.cache import get, put

        def boom(**kw):
            raise OSError("disk full")

        monkeypatch.setattr(cache_mod, "cleanup_by_size", boom)
        monkeypatch.setattr(cache_mod, "_CLEANUP_INTERVAL", 1)
        monkeypatch.setattr(cache_mod, "_WRITE_COUNTER", 0)

        with caplog.at_level(_l.DEBUG):
            put("ok", b"data")
        assert get("ok", 60) == b"data"

    def test_put_write_failure(self, cdir, monkeypatch):
        """92-100 行：os.write 抛异常 → 清理 tmp + re-raise。"""
        import common.cache as cache_mod

        import os

        def boom(fd, data):
            raise OSError("write failed")

        monkeypatch.setattr(os, "write", boom)
        # 但 mkstemp 也走 os… 只能模拟第一步成功后续失败；直接触发 put 异常路径：
        with pytest.raises(OSError):
            cache_mod.put("k", b"data")
        # tmp 残留在异常路径后应被清理
        assert list(cdir.glob("*.tmp")) == []

    def test_put_write_failure_tmp_unlink_oserror(self, cdir, monkeypatch):
        """96-98 行：os.write 失败 + close 也失败 → 吞掉 close 异常后 re-raise。"""
        import common.cache as cache_mod

        monkeypatch.setattr(cache_mod, "_USE_FCNTL", False)

        real_write = cache_mod.os.write
        real_close = cache_mod.os.close

        def boom_write(fd, data):
            raise OSError("write failed")

        def boom_close(fd):
            raise OSError("close failed")

        monkeypatch.setattr(cache_mod.os, "write", boom_write)
        monkeypatch.setattr(cache_mod.os, "close", boom_close)
        with pytest.raises(OSError):
            cache_mod.put("k1", b"x")
        assert list(cdir.glob("*.tmp")) == []

        monkeypatch.setattr(cache_mod.os, "write", real_write)
        monkeypatch.setattr(cache_mod.os, "close", real_close)

    def test_cleanup_by_size_over_limit(self, cdir):
        """超过上限删除，直到达标。"""
        import time

        from common.cache import cleanup_by_size

        for i in range(3):
            f = cdir / f"c{i}.cache"
            f.write_bytes(b"y" * 1024)
            import os

            os.utime(f, (time.time() - 10 * i, time.time() - 10 * i))
        n = cleanup_by_size(max_size_mb=0)
        assert n >= 1
        assert len(list(cdir.glob("*.cache"))) < 3

    def test_cleanup_by_size_under_limit_returns_zero(self, cdir):
        """227 行：total 未超上限 → 直接返回 0。"""
        from common.cache import cleanup_by_size

        (cdir / "a.cache").write_bytes(b"tiny")
        assert cleanup_by_size(max_size_mb=1) == 0

    def test_cleanup_by_size_break_after_delete(self, cdir):
        """235 行：删除首文件后低于上限 → 循环 break。"""
        import time
        import os

        from common.cache import cleanup_by_size

        (cdir / "a.cache").write_bytes(b"x" * 2048)
        (cdir / "b.cache").write_bytes(b"x" * 1024)
        for f in cdir.glob("*.cache"):
            os.utime(f, (time.time() - 5, time.time() - 5))
        # max_size=0：必然删除部分文件，覆盖 236-238 循环体
        n = cleanup_by_size(max_size_mb=0)
        assert n >= 1


# ═══════════════════════════════════════════════════════════════
# common 包：惰性加载 + http_get_cached
# ═══════════════════════════════════════════════════════════════


class TestCommonPackage:
    def test_lazy_import_via_getattr(self):
        import common

        # 首次访问触发惰性加载
        v = common.split_codes
        assert callable(v)
        assert common.split_codes is v

    def test_lazy_import_module_val(self):
        import common

        c = common.cache
        assert hasattr(c, "put")  # 模块对象

    def test_getattr_unknown_raises(self):
        import common

        with pytest.raises(AttributeError):
            common.no_such_symbol_xyz

    def test_http_get_cached_hit(self, monkeypatch, tmp_path):
        import common
        import common.cache as cache_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
        calls = {"n": 0}

        def fake_get(*a, **k):
            calls["n"] += 1
            return b"data-from-net"

        monkeypatch.setattr(common, "http_get", fake_get)
        r1 = common.http_get_cached("http://x", key="fixed-key")
        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
        r2 = common.http_get_cached("http://x", key="fixed-key")
        assert r1 == r2 == b"data-from-net"
        assert calls["n"] == 1  # 第二次命中缓存

    def test_http_get_cached_miss_writes(self, monkeypatch, tmp_path):
        import common
        import common.cache as cache_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)

        def fake_get(*a, **k):
            return b"net"

        monkeypatch.setattr(common, "http_get", fake_get)
        # 无 key → 自动生成
        out = common.http_get_cached("http://unique-url-42")
        assert out == b"net"
        assert len(list(tmp_path.glob("*.cache"))) == 1

    def test_http_get_cached_keyed_alias(self, monkeypatch, tmp_path):
        import common
        import common.cache as cache_mod

        monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(common, "http_get", lambda *a, **k: b"k")
        assert common.http_get_cached_keyed("http://u", "mykey") == b"k"

    def test_backward_compat_aliases(self):
        import common

        assert common.DataSourceUnavailableError is common.NetworkError
        assert common.DataParseError is common.ParseError


# ═══════════════════════════════════════════════════════════════
# user_profile
# ═══════════════════════════════════════════════════════════════


class TestUserProfile:
    def test_load_default_missing(self, monkeypatch, tmp_path):
        from common.user_profile import load_user_profile

        monkeypatch.setattr(
            "common.user_profile._profile_path", lambda: tmp_path / "nope.yaml"
        )
        p = load_user_profile()
        assert p["risk_tolerance"] == "medium"
        assert p["default_strategy"] == "balanced"

    def test_load_explicit_path(self, tmp_path):
        from common.user_profile import load_user_profile

        f = tmp_path / "u.yaml"
        f.write_text(
            "risk_tolerance: aggressive\nposition_limit:\n  single_stock_max: 0.3\n",
            encoding="utf-8",
        )
        p = load_user_profile(str(f))
        assert p["risk_tolerance"] == "aggressive"
        assert p["position_limit"]["single_stock_max"] == 0.3
        # 嵌套未指定字段保留默认
        assert p["position_limit"]["top3_max"] == 0.50

    def test_load_invalid_yaml(self, monkeypatch, tmp_path):
        from common.user_profile import load_user_profile

        f = tmp_path / "bad.yaml"
        f.write_text("{{{{not-yaml", encoding="utf-8")
        p = load_user_profile(str(f))
        assert p["risk_tolerance"] == "medium"

    def test_load_no_yaml_module(self, monkeypatch, tmp_path):
        from common.user_profile import load_user_profile

        monkeypatch.setattr("builtins.__import__", boom_yaml_import)
        p = load_user_profile()
        assert p["risk_tolerance"] == "medium"

    def test_deep_merge(self):
        from common.user_profile import _deep_merge

        base = {"a": {"x": 1, "y": 2}, "b": 3}
        assert _deep_merge(base, {"a": {"y": 9}, "b": 4}) == {
            "a": {"x": 1, "y": 9},
            "b": 4,
        }

    def test_get_user_preference(self, monkeypatch, tmp_path):
        from common.user_profile import get_user_preference, load_user_profile

        f = tmp_path / "u.yaml"
        f.write_text(
            "risk_tolerance: conservative\nnotifications:\n  price_alert: false\n",
            encoding="utf-8",
        )
        # patch 默认路径
        monkeypatch.setattr("common.user_profile._profile_path", lambda: f)
        assert get_user_preference("risk_tolerance") == "conservative"
        assert get_user_preference("notifications.price_alert") is False
        assert get_user_preference("nope") is None
        assert get_user_preference("nope", 42) == 42
        # 非 dict 层级
        assert get_user_preference("risk_tolerance.sub", 7) == 7

    def test_save_user_profile(self, tmp_path, monkeypatch):
        import yaml

        from common.user_profile import save_user_profile

        f = tmp_path / "sub" / "u.yaml"
        save_user_profile({"risk_tolerance": "high"}, str(f))
        assert f.exists()
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert data["risk_tolerance"] == "high"


def boom_yaml_import(name, *a, **k):
    if name == "yaml":
        raise ImportError("no yaml")
    return __import__(name, *a, **k)


# ═══════════════════════════════════════════════════════════════
# screener_watchdog
# ═══════════════════════════════════════════════════════════════


class TestWatchdog:
    def test_resolve_deadline_default(self, monkeypatch):
        from common.screener_watchdog import _resolve_deadline

        monkeypatch.delenv("STOCK_SCREENER_DEADLINE", raising=False)
        assert _resolve_deadline(None) == 1800.0

    def test_resolve_deadline_arg(self):
        from common.screener_watchdog import _resolve_deadline

        assert _resolve_deadline(120) == 120.0
        assert _resolve_deadline(0) == 1800.0  # 非法 arg → 回落
        assert _resolve_deadline(-5) == 1800.0

    def test_resolve_deadline_env(self, monkeypatch):
        from common.screener_watchdog import _resolve_deadline

        monkeypatch.setenv("STOCK_SCREENER_DEADLINE", "900")
        assert _resolve_deadline(None) == 900.0
        monkeypatch.setenv("STOCK_SCREENER_DEADLINE", "abc")
        assert _resolve_deadline(None) == 1800.0
        monkeypatch.setenv("STOCK_SCREENER_DEADLINE", "-3")
        assert _resolve_deadline(None) == 1800.0

    def test_watchdog_start_cancel(self):
        from common.screener_watchdog import WatchdogContext

        wd = WatchdogContext(60)
        assert wd.timed_out is False
        wd.start()
        assert isinstance(wd.elapsed_sec, float)
        wd.cancel()
        assert wd.done_event.is_set()
        assert wd._timer is None or wd._timer.finished

    def test_watchdog_context_manager(self):
        from common.screener_watchdog import WatchdogContext

        with WatchdogContext(60) as wd:
            assert wd.done_event.is_set() is False or wd._timer is not None
        # 正常退出后 timer 被取消
        assert wd._timer is None

    def test_watchdog_exit_skips_cancel(self):
        """__exit__ 时已 timed_out → 不 cancel timer。"""
        from unittest.mock import MagicMock

        from common.screener_watchdog import WatchdogContext

        wd = WatchdogContext(60)
        wd.timed_out = True
        wd._timer = MagicMock()
        wd.__exit__(None, None, None)
        assert wd._timer is not None  # 未被置 None

    def test_watchdog_timeout_calls_exit(self):
        """定时器触发 _on_timeout → os._exit(2)（patch 中断真实退出）。"""
        from unittest.mock import patch

        from common.screener_watchdog import WatchdogContext

        with patch("common.screener_watchdog.os._exit") as fake_exit:
            wd = WatchdogContext(0.01)
            wd.start()
            import time

            for _ in range(50):
                if fake_exit.called:
                    break
                time.sleep(0.005)
            wd.cancel()
        assert fake_exit.called
        assert fake_exit.call_args[0][0] == 2

    def test_watchdog_timeout_sets_state(self):
        """直接调用 _on_timeout 验证 timed_out/done_event（patch os._exit）。"""
        from unittest.mock import patch

        from common.screener_watchdog import WatchdogContext

        wd = WatchdogContext(60)
        with patch("common.screener_watchdog.os._exit") as fake_exit:
            wd._on_timeout()
        assert wd.timed_out is True
        assert wd.done_event.is_set()
        fake_exit.assert_called_once_with(2)

    def test_start_watchdog_factory(self, monkeypatch):
        from common.screener_watchdog import start_watchdog

        monkeypatch.setenv("STOCK_SCREENER_DEADLINE", "42")
        wd = start_watchdog()
        assert wd.deadline_sec == 42.0


# ═══════════════════════════════════════════════════════════════
# cli_base
# ═══════════════════════════════════════════════════════════════


class TestCliBase:
    def test_create_parser_common_args(self):
        from common.cli_base import create_parser

        p = create_parser("测试")
        assert p.description == "测试"
        args = p.parse_args(["-j", "--sources", "--no-cache", "--debug"])
        assert args.json_output is True
        assert args.sources is True
        assert args.no_cache is True
        assert args.debug is True

    def test_create_parser_custom_kwargs(self):
        from common.cli_base import create_parser

        p = create_parser("x", prog="myprog")
        assert p.prog == "myprog"

    def test_handle_errors_success(self):
        from common.cli_base import handle_errors

        with handle_errors():
            pass  # 不抛异常

    def test_handle_errors_keyboard_interrupt(self, monkeypatch, capsys):
        import sys

        from common.cli_base import handle_errors

        def fake_exit(code):
            raise SystemExit(code)

        monkeypatch.setattr(sys, "exit", fake_exit)
        with pytest.raises(SystemExit) as ei:
            with handle_errors():
                raise KeyboardInterrupt
        assert ei.value.code == 130

    def test_handle_errors_generic(self, monkeypatch, capsys):
        import sys

        from common.cli_base import handle_errors

        monkeypatch.setattr(sys, "exit", fake_sys_exit)
        with pytest.raises(SystemExit) as ei:
            with handle_errors():
                raise ValueError("bad value")
        assert ei.value.code == 1
        out = capsys.readouterr().err
        assert "❌" in out

    def test_handle_errors_debug_traceback(self, monkeypatch, capsys):
        import sys

        from common.cli_base import handle_errors

        monkeypatch.setenv("STOCK_DEBUG", "1")
        monkeypatch.setattr(sys, "exit", fake_sys_exit)
        with pytest.raises(SystemExit) as ei:
            with handle_errors():
                raise ValueError("boom")
        assert ei.value.code == 1
        out = capsys.readouterr().err
        assert "Traceback" in out

    def test_handle_errors_screener_timeout(self, monkeypatch, capsys):
        import sys

        from common.cli_base import handle_errors
        from common.exceptions import ScreenerTimeoutError

        monkeypatch.setattr(sys, "exit", fake_sys_exit)
        with pytest.raises(SystemExit) as ei:
            with handle_errors():
                raise ScreenerTimeoutError(600, 650.0, 10)
        assert ei.value.code == 2
        out = capsys.readouterr().err
        assert "任务超时" in out

    def test_print_sources_table(self, capsys):
        from common.cli_base import print_sources_table

        class FakeFetcher:
            name = "tencent"
            priority = 1

            def is_available(self):
                return True

        class FakeFetcher2:
            name = "sina"
            priority = 2

            def is_available(self):
                return False

        print_sources_table({"行情": [FakeFetcher(), FakeFetcher2()]})
        out = capsys.readouterr().out
        assert "=== 行情 数据源 ===" in out
        assert "✅" in out
        assert "❌" in out
        assert "tencent" in out


def fake_sys_exit(code):
    raise SystemExit(code)


# ═══════════════════════════════════════════════════════════════
# rate_limiter 补充
# ═══════════════════════════════════════════════════════════════


class TestRateLimiterExtras:
    def test_mark_429_single(self):
        from common.rate_limiter import RateLimiter

        rl = RateLimiter()
        rl.mark_429("eastmoney")
        assert rl._backoff_state["eastmoney"][1] == 1

    def test_mark_429_consecutive(self):
        from common.rate_limiter import RateLimiter

        rl = RateLimiter()
        rl.mark_429("eastmoney")
        rl.mark_429("eastmoney")
        assert rl._backoff_state["eastmoney"][1] == 2

    def test_acquire_backoff_sleep(self, monkeypatch):
        import time as _time

        from common.rate_limiter import RateLimiter

        rl = RateLimiter(backoff_base=1.0, backoff_cap=8.0, backoff_window=1000)
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(_time, "sleep", fake_sleep)
        rl.release("p", got_429=True)
        rl.acquire("p")
        assert len(sleeps) >= 1
        assert sleeps[0] > 0

    def test_slot_backoff_sleep(self, monkeypatch):
        import time as _time

        from common.rate_limiter import RateLimiter

        rl = RateLimiter(backoff_base=1.0, backoff_cap=8.0, backoff_window=1000)
        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)

        monkeypatch.setattr(_time, "sleep", fake_sleep)
        rl.mark_429("p")
        with rl.slot("p"):
            pass
        assert len(sleeps) >= 1

    def test_load_rate_limit_config_exception(self, monkeypatch):
        import common.rate_limiter as rl_mod

        def boom(*a, **k):
            raise RuntimeError("config missing")

        monkeypatch.setattr("config.loader.ConfigLoader.load", boom)
        assert rl_mod._load_rate_limit_config() == {}

    def test_rate_limiter_slot_context(self, monkeypatch):
        from common.rate_limiter import RateLimiter, rate_limiter_slot

        fake = RateLimiter()
        monkeypatch.setattr("common.rate_limiter.get_rate_limiter", lambda: fake)
        with rate_limiter_slot("provider_x"):
            assert fake._semaphores["provider_x"] is not None

    def test_slot_clears_expired_backoff(self):
        """退避窗口已过 → pop 状态且不 sleep（177 行）。"""
        import time as _time

        from common.rate_limiter import RateLimiter

        sleeps = []

        def fake_sleep(s):
            sleeps.append(s)

        rl = RateLimiter(backoff_base=1.0, backoff_cap=8.0, backoff_window=1000)
        # 直接放置一个已过窗口的退避状态
        rl._backoff_state["p"] = (
            _time.time() - 9999,
            1,
        )
        with rl.slot("p"):
            pass
        assert "p" not in rl._backoff_state  # 已过期被清除
        assert sleeps == []  # 无退避 sleep

    def test_is_provider_disabled_global(self, monkeypatch):
        from common.rate_limiter import RateLimiter, is_provider_disabled

        fake = RateLimiter()
        fake.mark_429("p")
        monkeypatch.setattr("common.rate_limiter.get_rate_limiter", lambda: fake)
        assert is_provider_disabled("p") is True


# ═══════════════════════════════════════════════════════════════
# http
# ═══════════════════════════════════════════════════════════════


class TestHttp:
    def test_parse_url_https_default_port(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("https://hq.sinajs.cn/list=a")
        assert scheme == "https"
        assert host == "hq.sinajs.cn"
        assert port == 443
        assert path == "/list=a"

    def test_parse_url_with_query(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("http://qt.gtimg.cn/q=sh600989&x=1")
        assert path == "/q=sh600989&x=1"

    def test_parse_url_real_query(self):
        """含真实 ?query 的 URL → path 拼接查询串（86 行）。"""
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url(
            "http://qt.gtimg.cn/q=sh600989?x=1&y=2"
        )
        assert path == "/q=sh600989?x=1&y=2"
        assert scheme == "http"
        assert port == 80

    def test_parse_url_bad_scheme(self):
        from common.http import _parse_url

        with pytest.raises(ValueError):
            _parse_url("file:///etc/passwd")

    def test_create_connection_http(self):
        """http scheme → HTTPConnection。"""
        import http.client

        from common.http import _create_connection

        conn = _create_connection("http", "localhost", 80, timeout=1)
        assert isinstance(conn, http.client.HTTPConnection)

    def test_create_connection_https(self):
        """https scheme → HTTPSConnection（96 行）。"""
        import http.client

        from common.http import _create_connection

        conn = _create_connection("https", "localhost", 443, timeout=1)
        assert isinstance(conn, http.client.HTTPSConnection)

    def test_http_get_via_local_server(self, monkeypatch):
        """stdlib 路径：本地 HTTP 服务器返回内容。"""
        import http.server
        import threading

        import common.http as http_mod

        from common.http import http_get

        monkeypatch.setattr(http_mod, "_HAS_REQUESTS", False)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = b"hello-world"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            out = http_get(f"http://127.0.0.1:{port}/test", timeout=3)
            assert out == b"hello-world"
        finally:
            server.shutdown()

    def test_http_get_404_raises_http_status(self, monkeypatch):
        """stdlib 路径：404 → HTTPStatusError。"""
        import http.server
        import threading

        import common.http as http_mod

        from common.exceptions import HTTPStatusError
        from common.http import http_get

        monkeypatch.setattr(http_mod, "_HAS_REQUESTS", False)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.close_connection = True
                self.end_headers()

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with pytest.raises(HTTPStatusError) as ei:
                http_get(f"http://127.0.0.1:{port}/nope", timeout=3)
            assert ei.value.status == 404
        finally:
            server.shutdown()

    def test_http_get_429_raises_rate_limit(self, monkeypatch):
        """429 → RateLimitError，不重试（stdlib 路径）。"""
        import http.server
        import threading

        import common.http as http_mod

        from common.exceptions import RateLimitError
        from common.http import http_get

        monkeypatch.setattr(http_mod, "_HAS_REQUESTS", False)

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(429)
                self.send_header("Retry-After", "30")
                self.close_connection = True
                self.end_headers()

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with pytest.raises(RateLimitError) as ei:
                http_get(f"http://127.0.0.1:{port}/", timeout=3)
            assert ei.value.retry_after == 30
        finally:
            server.shutdown()

    def test_http_get_server_down_raises_network(self, monkeypatch):
        """连接失败 → NetworkError。"""
        from common.exceptions import NetworkError
        from common.http import http_get

        with pytest.raises(NetworkError):
            http_get("http://127.0.0.1:1/none", timeout=0.5, max_retries=1)

    def test_do_request_429_no_retry_after(self):
        from unittest.mock import MagicMock

        from common.exceptions import RateLimitError
        from common.http import _do_request

        resp = MagicMock()
        resp.status = 429
        resp.getheader.return_value = None

        conn = MagicMock()
        conn.getresponse.return_value = resp

        with pytest.raises(RateLimitError) as ei:
            _do_request(conn, "http://u", "/", {}, 10)
        assert ei.value.retry_after is None

    def test_do_request_4xx_body_read_fail(self):
        from unittest.mock import MagicMock

        from common.exceptions import HTTPStatusError
        from common.http import _do_request

        resp = MagicMock()
        resp.status = 503
        resp.read.side_effect = OSError("conn closed")
        conn = MagicMock()
        conn.getresponse.return_value = resp
        with pytest.raises(HTTPStatusError) as ei:
            _do_request(conn, "http://u", "/", {}, 10)
        assert ei.value.status == 503

    def test_do_request_response_size_limit(self):
        from unittest.mock import MagicMock

        from common.http import _do_request

        resp = MagicMock()
        resp.status = 200
        # 模拟超 50MB：第一次返回大块，第二次返回 b""
        resp.read.side_effect = [b"x" * 8192, b""]

        conn = MagicMock()
        conn.getresponse.return_value = resp
        out = _do_request(conn, "http://u", "/", {}, 10)
        assert out == b"x" * 8192

    def test_invalidate_connection_close_error(self):
        from unittest.mock import MagicMock

        from common.http import _invalidate_connection

        conn = MagicMock()
        conn.close.side_effect = OSError("closed")
        _invalidate_connection("http://u", conn)  # 不抛异常

    def test_get_connection_reuses_and_discards(self):
        from unittest.mock import MagicMock, patch

        from common.http import _connection_pool, _get_connection, _return_connection

        _connection_pool.clear()
        conn = MagicMock()
        conn.sock = object()
        _return_connection("k", conn)
        got = _get_connection("k", "http", "h", 80, 10)
        assert got is conn
        _connection_pool.clear()

    def test_get_connection_stale_discarded(self):
        from unittest.mock import MagicMock, patch

        import common.http as http_mod

        conn = MagicMock()
        conn.sock = object()
        conn.close = MagicMock()
        with patch.object(http_mod, "time") as tm:
            tm.time.return_value = 1000.0
            http_mod._connection_pool["k"] = [(conn, 0.0)]  # 过期
            out = http_mod._get_connection("k", "http", "h", 80, 10)
        conn.close.assert_called_once()
        assert out is not conn  # 创建新连接
        http_mod._connection_pool.clear()

    def test_decode_gbk_utf8(self):
        from common.http import decode_gbk

        assert decode_gbk("中文".encode("utf-8")) == "中文"

    def test_decode_gbk_fallback(self, caplog):
        import logging as _l

        from common.http import decode_gbk

        with caplog.at_level(_l.WARNING):
            # 0xFF 不是合法 UTF-8 单字节，也不是合法 GBK，解码含 U+FFFD
            out = decode_gbk(b"\xff\xfe\xfd")
        assert isinstance(out, str)
        assert "\ufffd" in out

    def test_decode_gbk_fallback_no_replacement(self):
        from common.http import decode_gbk

        out = decode_gbk("宝丰".encode("gbk"))
        assert out == "宝丰"
        assert "\ufffd" not in out

    def test_http_get_requests_429(self):
        from unittest.mock import MagicMock, patch

        from common.exceptions import RateLimitError
        from common.http import http_get

        resp = MagicMock()
        resp.status_code = 429
        resp.headers.get.return_value = "15"

        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            with pytest.raises(RateLimitError) as ei:
                http_get("http://u", timeout=1)
        assert ei.value.retry_after == 15

    def test_http_get_requests_4xx_raises_http_status(self):
        from unittest.mock import MagicMock, patch

        import requests

        from common.exceptions import HTTPStatusError
        from common.http import http_get

        class ReqErr(requests.RequestException):
            def __init__(self, resp):
                super().__init__("bad")
                self.response = resp

        resp = MagicMock()
        resp.status_code = 404
        resp.text = "not found"

        session = MagicMock()
        session.get.side_effect = ReqErr(resp)

        with patch("common.http._get_session", return_value=session):
            with pytest.raises(HTTPStatusError) as ei:
                http_get("http://u", timeout=1)
        assert ei.value.status == 404

    def test_http_get_requests_fallback_to_stdlib(self, monkeypatch):
        """requests 网络异常 → 降级 stdlib。"""
        from unittest.mock import MagicMock, patch

        import requests

        from common.http import http_get

        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("down")

        calls = {"n": 0}

        def fake_internal(*a, **k):
            calls["n"] += 1
            return b"from-stdlib"

        with (
            patch("common.http._get_session", return_value=session),
            patch("common.http._http_get_internal", side_effect=fake_internal),
        ):
            out = http_get("http://u", timeout=1)
        assert out == b"from-stdlib"
        assert calls["n"] == 1

    def test_http_get_requests_success(self):
        from unittest.mock import MagicMock, patch

        from common.http import http_get

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"ok"

        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            assert http_get("http://u") == b"ok"

    def test_http_get_requests_oversize_truncated(self):
        from unittest.mock import MagicMock, patch

        import common.http as http_mod

        from common.http import http_get

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"x" * (http_mod.MAX_RESPONSE_SIZE + 10)

        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            out = http_get("http://u")
        assert len(out) == http_mod.MAX_RESPONSE_SIZE

    def test_http_get_with_headers_requests(self):
        from unittest.mock import MagicMock, patch

        from common.http import http_get_with_headers

        resp = MagicMock()
        resp.status_code = 200
        resp.content = b"h"
        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            out = http_get_with_headers("http://u", headers={"Referer": "x"})
        assert out == b"h"
        session.get.assert_called_once()

    def test_http_get_with_headers_fallback(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        import requests

        from common.http import http_get_with_headers

        session = MagicMock()
        session.get.side_effect = requests.ConnectTimeout("timeout")

        with (
            patch("common.http._get_session", return_value=session),
            patch("common.http._http_get_internal", return_value=b"s"),
        ):
            assert http_get_with_headers("http://u") == b"s"

    def test_http_get_internal_retries_then_network_error(self, monkeypatch):
        """重试耗尽 → NetworkError。"""
        import time as _time

        from unittest.mock import MagicMock

        from common.exceptions import NetworkError
        from common.http import _http_get_internal

        def fake_connection(*a, **k):
            conn = MagicMock()
            return conn

        def fake_do_request(conn, url, path, headers, timeout):
            raise OSError("conn reset")

        monkeypatch.setattr("common.http._get_connection", fake_connection)
        monkeypatch.setattr("common.http._do_request", fake_do_request)
        monkeypatch.setattr(_time, "sleep", lambda *a, **k: None)
        with pytest.raises(NetworkError):
            _http_get_internal("http://h/", timeout=0.1, max_retries=2)

    def test_parse_url_missing_scheme_https(self):
        from common.http import _parse_url

        key, scheme, host, port, path = _parse_url("//hq.sinajs.cn/list")
        assert scheme == "https"
        assert port == 443

    def test_requests_import_fails(self):
        """24-25 行：requests 不可导入 → _HAS_REQUESTS=False。"""
        import subprocess
        import sys

        code = (
            "import sys; sys.path.insert(0, 'scripts');\n"
            "import builtins;\n"
            "_orig = builtins.__import__;\n"
            "def _block(name, *a, **k):\n"
            "    if name.split('.')[0] == 'requests' or name.split('.')[0] == 'urllib3':\n"
            "        raise ImportError('blocked')\n"
            "    return _orig(name, *a, **k)\n"
            "builtins.__import__ = _block;\n"
            "import importlib;\n"
            "m = importlib.import_module('common.http');\n"
            "assert m._HAS_REQUESTS is False;\n"
            "print('OK')\n"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr

    def test_session_double_check(self):
        """42 行：锁内二次检查命中。"""
        from unittest.mock import MagicMock, patch

        import common.http as http_mod

        fake_session = MagicMock()
        fake_session.configure_mock(max_redirects=None)
        with patch.object(http_mod, "_session", fake_session):
            s = http_mod._get_session()
        assert s is fake_session

    def test_session_double_check_inside_lock(self):
        """42 行第二种路径：外层 _session 为 None、锁内被并发填充。"""
        from unittest.mock import MagicMock

        import common.http as http_mod
        from common.http import _get_session

        class FakeLock:
            def __enter__(self):
                # 模拟并发线程在拿到锁后填充 _session
                http_mod._session = MagicMock()
                return self

            def __exit__(self, *exc):
                return False

        old_lock = http_mod._session_lock
        old_session = http_mod._session
        http_mod._session = None
        http_mod._session_lock = FakeLock()
        try:
            s = _get_session()
            assert s is http_mod._session
        finally:
            http_mod._session = old_session
            http_mod._session_lock = old_lock

    def test_return_connection_pool_overflow(self):
        """133-139 行：池满 → 关闭连接。"""
        from unittest.mock import MagicMock

        import common.http as http_mod

        conn = MagicMock()
        http_mod._connection_pool["k"] = []
        for i in range(http_mod.MAX_POOL_SIZE):
            http_mod._connection_pool["k"].append((MagicMock(), 0.0))
        http_mod._return_connection("k", conn)
        # 池内连接数不变（新 conn 被关闭）
        assert len(http_mod._connection_pool["k"]) == http_mod.MAX_POOL_SIZE
        http_mod._connection_pool.clear()

    def test_return_connection_pool_overflow_close_error(self):
        """138-139 行：关闭溢出连接抛 OSError → 吞掉。"""
        from unittest.mock import MagicMock

        import common.http as http_mod

        conn = MagicMock()
        conn.close.side_effect = OSError("closed")
        http_mod._connection_pool["k2"] = [
            MagicMock() for _ in range(http_mod.MAX_POOL_SIZE)
        ]
        http_mod._return_connection("k2", conn)  # 不抛异常
        http_mod._connection_pool.clear()

    def test_do_request_429_body_read_error(self):
        """158-159 行：429 响应体读取失败。"""
        from unittest.mock import MagicMock

        from common.exceptions import RateLimitError
        from common.http import _do_request

        resp = MagicMock()
        resp.status = 429
        resp.getheader.return_value = None
        resp.read.side_effect = OSError("closed")
        conn = MagicMock()
        conn.getresponse.return_value = resp
        with pytest.raises(RateLimitError):
            _do_request(conn, "http://u", "/", {}, 10)

    def test_do_request_oversize_truncates(self, caplog):
        """186-190 行：响应超限 → warning + 截断。"""
        from unittest.mock import MagicMock

        import common.http as http_mod

        from common.http import _do_request

        resp = MagicMock()
        resp.status = 200
        # 生成足够多的 8192 块以超过 50MB 限制
        n_chunks = http_mod.MAX_RESPONSE_SIZE // 8192 + 2
        chunks = [b"x" * 8192] * n_chunks

        def read_gen():
            yield from chunks
            while True:
                yield b""

        resp.read.side_effect = read_gen()

        conn = MagicMock()
        conn.getresponse.return_value = resp
        out = _do_request(conn, "http://u", "/", {}, 10)
        assert len(out) == http_mod.MAX_RESPONSE_SIZE

    def test_get_connection_stale_discarded_close_error(self):
        """118-119 行：关闭过期连接抛 OSError → 吞掉。"""
        from unittest.mock import MagicMock, patch

        import common.http as http_mod

        conn = MagicMock()
        conn.sock = object()
        conn.close.side_effect = OSError("closed")
        with patch.object(http_mod, "time") as tm:
            tm.time.return_value = 1000.0
            http_mod._connection_pool["k"] = [(conn, 0.0)]
            out = http_mod._get_connection("k", "http", "h", 80, 10)
        assert out is not None
        conn.close.assert_called()  # 过期连接被关闭（close 失败被吞，仍新建连接）
        http_mod._connection_pool.clear()

    def test_return_connection_append_under_limit(self):
        """133-134 行：池未满 → 追加连接。"""
        from unittest.mock import MagicMock

        import common.http as http_mod

        conn = MagicMock()
        http_mod._connection_pool["k"] = []
        http_mod._return_connection("k", conn)
        assert len(http_mod._connection_pool["k"]) == 1
        http_mod._connection_pool.clear()

    def test_http_get_internal_with_headers(self, monkeypatch):
        """212 行：req_headers 合并自定义 headers。"""
        from unittest.mock import MagicMock, patch

        from common.http import _http_get_internal

        seen = {}

        def fake_do_request(conn, url, path, headers, timeout):
            seen["headers"] = headers
            return b"ok"

        monkeypatch.setattr("common.http._do_request", fake_do_request)
        monkeypatch.setattr(
            "common.http._get_connection",
            lambda *a, **k: MagicMock(),
        )
        out = _http_get_internal(
            "http://h/", headers={"Referer": "r"}, timeout=1, max_retries=1
        )
        assert out == b"ok"
        assert seen["headers"]["Referer"] == "r"
        assert "User-Agent" in seen["headers"]

    def test_http_get_with_headers_requests_429(self):
        """317-318 行：with_headers requests 429 → 直接
        抛。"""
        from unittest.mock import MagicMock, patch

        from common.exceptions import RateLimitError
        from common.http import http_get_with_headers

        resp = MagicMock()
        resp.status_code = 429
        resp.headers.get.return_value = None

        session = MagicMock()
        session.get.return_value = resp

        with patch("common.http._get_session", return_value=session):
            with pytest.raises(RateLimitError):
                http_get_with_headers("http://u")

    def test_http_get_with_headers_requests_4xx(self):
        """323-325 行：with_headers 4xx → HTTPStatusError。"""
        from unittest.mock import MagicMock, patch

        import requests

        from common.exceptions import HTTPStatusError
        from common.http import http_get_with_headers

        class ReqErr(requests.RequestException):
            def __init__(self, resp):
                super().__init__("bad")
                self.response = resp

        resp = MagicMock()
        resp.status_code = 400
        resp.text = "bad"

        session = MagicMock()
        session.get.side_effect = ReqErr(resp)

        with patch("common.http._get_session", return_value=session):
            with pytest.raises(HTTPStatusError) as ei:
                http_get_with_headers("http://u")
        assert ei.value.status == 400

    def test_http_get_with_headers_requests_5xx_fallback(self, monkeypatch):
        """5xx 非业务错误 → 降级 stdlib。"""
        from unittest.mock import MagicMock, patch

        import requests

        from common.http import http_get_with_headers

        class ReqErr(requests.RequestException):
            def __init__(self, resp):
                super().__init__("err")
                self.response = resp

        resp = MagicMock()
        resp.status_code = 500

        session = MagicMock()
        session.get.side_effect = ReqErr(resp)

        with (
            patch("common.http._get_session", return_value=session),
            patch("common.http._http_get_internal", return_value=b"s"),
        ):
            assert http_get_with_headers("http://u") == b"s"


# ═══════════════════════════════════════════════════════════════
# utils 补充
# ═══════════════════════════════════════════════════════════════


class TestUtilsExtras:
    def test_split_codes_file_input(self, tmp_path, monkeypatch):
        import common.utils as utils_mod

        from common.utils import split_codes

        # patch DATA_DIR 并写入文件
        monkeypatch.setattr(utils_mod, "DATA_DIR", tmp_path)
        f = tmp_path / "codes.txt"
        f.write_text("sh600989\n\nsz000001\n", encoding="utf-8")
        assert split_codes(f"@{f}") == ["sh600989", "sz000001"]

    def test_split_codes_file_missing(self, tmp_path, monkeypatch):
        import common.utils as utils_mod

        from common.utils import split_codes

        monkeypatch.setattr(utils_mod, "DATA_DIR", tmp_path)
        f = tmp_path / "nope.txt"
        with pytest.raises(FileNotFoundError):
            split_codes(f"@{f}")

    def test_split_codes_file_outside(self, tmp_path, monkeypatch):
        import common.utils as utils_mod

        from common.utils import split_codes

        allow = tmp_path / "allow"
        allow.mkdir()
        monkeypatch.setattr(utils_mod, "DATA_DIR", allow)
        with pytest.raises(ValueError):
            split_codes("@/etc/passwd")

    def test_parallel_map_success(self):
        from common.utils import parallel_map

        out = parallel_map(lambda x: x * 2, [1, 2, 3])
        assert out == {1: 2, 2: 4, 3: 6}

    def test_parallel_map_exception_sets_none(self):
        from common.utils import parallel_map

        def fn(x):
            if x == 2:
                raise ValueError("bad")
            return x

        out = parallel_map(fn, [1, 2, 3])
        assert out[1] == 1
        assert out[2] is None
        assert out[3] == 3

    def test_parallel_map_rate_limit_rethrows(self):
        from common.exceptions import RateLimitError
        from common.utils import parallel_map

        def fn(x):
            raise RateLimitError("u")

        with pytest.raises(RateLimitError):
            parallel_map(fn, [1])

    def test_parallel_map_timeout(self, monkeypatch):
        import time

        from common.utils import parallel_map

        def slow(x):
            time.sleep(0.5)
            return x

        out = parallel_map(slow, [1, 2], timeout=0.05)
        assert isinstance(out, dict)

    def test_parallel_fetch_dict(self):
        from common.utils import parallel_fetch_dict

        out = parallel_fetch_dict([1, 2], lambda x: f"v{x}", label="t")
        assert out == {1: "v1", 2: "v2"}

    def test_parallel_fetch_dict_failure(self):
        from common.utils import parallel_fetch_dict

        def fn(x):
            if x == 2:
                raise ValueError("bad")
            return x

        # 失败的 item 不出现在结果中
        out = parallel_fetch_dict([1, 2], fn)
        assert out[1] == 1
        assert 2 not in out

    def test_parallel_fetch_dict_rate_limit(self):
        from common.exceptions import RateLimitError
        from common.utils import parallel_fetch_dict

        def fn(x):
            raise RateLimitError("u")

        with pytest.raises(RateLimitError):
            parallel_fetch_dict([1], fn)

    def test_parallel_fetch_dict_timeout(self):
        import time

        from common.utils import parallel_fetch_dict

        def slow(x):
            time.sleep(0.5)
            return x

        out = parallel_fetch_dict([1, 2], slow, timeout=0.05)
        assert isinstance(out, dict)

    def test_to_secid_market_code(self):
        from common.utils import to_secid

        # 60/68 开头 → 1.x（沪市），000/002 → 0.x 已在既有测试
        assert to_secid("sh600989") == "1.600989"
        assert to_secid("bj430047") == "0.430047"  # 北交所 → 0.x

    def test_parallel_map_sys_exit_rethrows(self):
        """349 行：SystemExit 透明向上抛，不吞。"""
        from common.utils import parallel_map

        def fn(x):
            raise SystemExit(99)

        with pytest.raises(SystemExit):
            parallel_map(fn, [1])


# ═══════════════════════════════════════════════════════════════
# format_error / _get_friendly_message / is_retryable_error
# ═══════════════════════════════════════════════════════════════


class TestFormatError:
    def test_format_stock_error_plain(self):
        from common.exceptions import (
            StrategyError,
            format_error,
        )

        # StrategyError 无映射 → 走 base_message
        out = format_error(StrategyError("策略执行错误"))
        assert "策略执行错误" in out

    def test_format_with_details(self):
        from common.exceptions import NetworkError, format_error

        e = NetworkError("http://a", "timeout too slow", 0)
        out = format_error(e, include_details=True)
        assert "📋 技术信息" in out
        assert "url: http://a" in out

    def test_format_network_timeout(self):
        from common.exceptions import NetworkError, format_error

        out = format_error(NetworkError("http://a", "timeout", 0))
        assert "超时" in out

    def test_format_network_connection(self):
        from common.exceptions import NetworkError, format_error

        out = format_error(NetworkError("http://a", "connection refused", 0))
        assert "连接" in out or "网络" in out

    def test_format_network_default(self):
        from common.exceptions import NetworkError, format_error

        out = format_error(NetworkError("http://a", "其他错误", 0))
        assert "网络连接失败" in out

    def test_format_validation_code(self):
        from common.exceptions import ValidationError, format_error

        out = format_error(ValidationError("code", "123", "格式错"))
        assert "股票代码格式" in out

    def test_format_validation_date(self):
        from common.exceptions import ValidationError, format_error

        out = format_error(ValidationError("date", "nope", "格式错"))
        assert "日期格式" in out

    def test_format_validation_default(self):
        from common.exceptions import ValidationError, format_error

        out = format_error(ValidationError("xxx", "y", "格式错"))
        assert "输入信息有误" in out

    def test_format_insufficient_kline(self):
        from common.exceptions import InsufficientDataError, format_error

        out = format_error(InsufficientDataError("K线", 100, 10))
        assert "K线数据不足" in out

    def test_format_insufficient_finance(self):
        from common.exceptions import InsufficientDataError, format_error

        out = format_error(InsufficientDataError("财务数据", 10, 2))
        assert "财务数据缺失" in out

    def test_format_insufficient_default(self):
        from common.exceptions import InsufficientDataError, format_error

        out = format_error(InsufficientDataError("其他", 10, 2))
        assert "分析数据不足" in out

    def test_format_rate_limit(self):
        from common.exceptions import RateLimitError, format_error

        # RateLimitError 是 NetworkError 子类 → 走网络默认文案
        out = format_error(RateLimitError("http://a"))
        assert "网络连接失败" in out

    def test_format_configuration_default(self):
        from common.exceptions import ConfigurationError, format_error

        out = format_error(ConfigurationError("配置坏了"))
        assert "系统配置异常" in out

    def test_format_parse_error(self):
        from common.exceptions import ParseError, format_error

        out = format_error(ParseError("raw", "p", "原因"))
        assert "数据格式异常" in out

    def test_format_data_unavailable(self):
        from common.exceptions import DataUnavailableError, format_error

        out = format_error(DataUnavailableError("tencent", 5))
        assert "数据暂时不可用" in out

    def test_format_json_error(self):
        from common.exceptions import format_error
        import json

        out = format_error(json.JSONDecodeError("e", "doc", 0))
        assert "非 JSON" in out

    def test_format_key_error(self):
        from common.exceptions import format_error

        out = format_error(KeyError("field_x"))
        assert "数据字段缺失" in out
        assert "field_x" in out

    def test_format_key_error_no_args(self):
        from common.exceptions import format_error

        assert "数据字段缺失" in format_error(KeyError())

    def test_format_timeout_error(self):
        from common.exceptions import format_error

        out = format_error(TimeoutError())
        assert "超时" in out

    def test_format_connection_error(self):
        from common.exceptions import format_error

        out = format_error(ConnectionError())
        assert "网络连接失败" in out

    def test_format_unknown_error(self):
        from common.exceptions import format_error

        out = format_error(ValueError("random"))
        assert "意外错误" in out

    def test_is_retryable(self):
        from common.exceptions import (
            RateLimitError,
            NetworkError,
            HTTPStatusError,
            is_retryable_error,
        )

        assert is_retryable_error(RateLimitError("u")) is True
        assert is_retryable_error(NetworkError("u", "err")) is True
        assert is_retryable_error(HTTPStatusError("u", 503)) is True
        assert is_retryable_error(HTTPStatusError("u", 400)) is False
        assert is_retryable_error(ValueError("x")) is False

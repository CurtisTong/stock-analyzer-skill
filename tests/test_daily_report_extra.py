"""portfolio/daily_report.py 补充测试：DailyReportGenerator 方法 + 通知渠道。

mock: PortfolioManager, data.get_quote, data.get_kline, http_get。
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


# daily_report.py 顶部 from common import http_get 会触发 common.http 加载；
# 测试环境需保证 common.http 可正常 import（项目已配置 pythonpath）。
from portfolio.daily_report import DailyReportGenerator


# ═══════════════════════════════════════════════════════════════
# _get_pm / _is_real_portfolio
# ═══════════════════════════════════════════════════════════════


class TestGetPm:
    def test_get_pm_lazy_init(self):
        """_get_pm 惰性初始化 PortfolioManager。"""
        gen = DailyReportGenerator(portfolio_path="/nonexistent/portfolio.json")
        assert gen._pm is None
        # 路径不存在 -> PortfolioManager 抛异常 -> 回退 None
        result = gen._get_pm()
        assert result is None

    def test_get_pm_caches(self):
        """_get_pm 缓存结果（第二次不重新初始化）。"""
        gen = DailyReportGenerator()
        gen._pm = MagicMock()
        result = gen._get_pm()
        assert result is gen._pm

    def test_get_pm_with_mock_manager(self, tmp_path):
        """成功初始化时缓存 PortfolioManager 实例。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps({"positions": [{"code": "sh600000", "name": "测试", "quantity": 100, "cost": 10}]}),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch("portfolio.manager.PortfolioManager") as MockPM:
            mock_inst = MagicMock()
            mock_inst.is_example = False
            mock_inst.is_virtual = False
            mock_inst.get_positions.return_value = [{"code": "sh600000"}]
            MockPM.return_value = mock_inst
            result1 = gen._get_pm()
            assert result1 is mock_inst
            # 第二次调用不重新构造
            result2 = gen._get_pm()
            assert result2 is mock_inst
            assert MockPM.call_count == 1


class TestIsRealPortfolio:
    def test_no_pm_no_file_returns_false(self, tmp_path):
        """PortfolioManager 失败 + 文件不存在 -> False。"""
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        assert gen._is_real_portfolio() is False

    def test_no_pm_v1_list_returns_true(self, tmp_path):
        """PortfolioManager 失败 + v1 纯列表文件 -> True（回退文件读取）。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps([{"code": "sh600000", "shares": 100, "cost_price": 10}]),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        assert gen._is_real_portfolio() is True

    def test_pm_example_returns_false(self):
        """PortfolioManager 返回示例数据 -> False。"""
        gen = DailyReportGenerator()
        gen._pm = MagicMock()
        gen._pm.is_example = True
        gen._pm.is_virtual = False
        assert gen._is_real_portfolio() is False

    def test_pm_virtual_returns_false(self):
        """PortfolioManager 虚拟组合 -> False。"""
        gen = DailyReportGenerator()
        gen._pm = MagicMock()
        gen._pm.is_example = False
        gen._pm.is_virtual = True
        assert gen._is_real_portfolio() is False

    def test_pm_no_positions_returns_false(self):
        """PortfolioManager 无持仓 -> False。"""
        gen = DailyReportGenerator()
        gen._pm = MagicMock()
        gen._pm.is_example = False
        gen._pm.is_virtual = False
        gen._pm.get_positions.return_value = []
        assert gen._is_real_portfolio() is False

    def test_pm_with_positions_returns_true(self):
        """PortfolioManager 有真实持仓 -> True。"""
        gen = DailyReportGenerator()
        gen._pm = MagicMock()
        gen._pm.is_example = False
        gen._pm.is_virtual = False
        gen._pm.get_positions.return_value = [{"code": "sh600000"}]
        assert gen._is_real_portfolio() is True


# ═══════════════════════════════════════════════════════════════
# _load_portfolio_raw
# ═══════════════════════════════════════════════════════════════


class TestLoadPortfolioRaw:
    def test_file_not_exists_returns_empty(self, tmp_path):
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        assert gen._load_portfolio_raw() == []

    def test_v2_format_with_positions_key(self, tmp_path):
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps({"positions": [{"code": "sh600000"}]}), encoding="utf-8"
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        result = gen._load_portfolio_raw()
        assert len(result) == 1
        assert result[0]["code"] == "sh600000"

    def test_v1_format_list(self, tmp_path):
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps([{"code": "sh600000", "shares": 100}]), encoding="utf-8"
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        result = gen._load_portfolio_raw()
        assert len(result) == 1

    def test_invalid_json_returns_empty(self, tmp_path):
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text("not valid json{", encoding="utf-8")
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        assert gen._load_portfolio_raw() == []

    def test_dict_without_positions_returns_empty(self, tmp_path):
        """dict 但无 positions 键 -> 空列表。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(json.dumps({"other": 1}), encoding="utf-8")
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        assert gen._load_portfolio_raw() == []


# ═══════════════════════════════════════════════════════════════
# generate - 端到端（mock 外部依赖）
# ═══════════════════════════════════════════════════════════════


class TestGenerate:
    def test_empty_portfolio(self, tmp_path):
        gen = DailyReportGenerator(portfolio_path=str(tmp_path / "missing.json"))
        result = gen.generate()
        assert "暂无持仓" in result

    def test_with_v1_holdings_via_raw(self, tmp_path):
        """v1 格式（PM 初始化失败）-> 走 _load_portfolio_raw。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps(
                [{"code": "sh600000", "name": "测试股", "shares": 100, "cost_price": 10.0}]
            ),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch.object(
            gen,
            "_fetch_quotes",
            return_value={"sh600000": {"price": 12.0, "change_pct": 3.0}},
        ):
            result = gen.generate()
        assert "持仓日报" in result
        assert "测试股" in result
        assert "持仓概览" in result

    def test_with_v2_holdings_via_pm(self, tmp_path):
        """v2 格式（PM 成功）-> 走 pm.get_positions。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps(
                {"positions": [{"code": "sh600001", "name": "蓝筹股", "quantity": 200, "cost": 20.0}]}
            ),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch("portfolio.manager.PortfolioManager") as MockPM:
            mock_inst = MagicMock()
            mock_inst.is_example = False
            mock_inst.is_virtual = False
            mock_inst.get_positions.return_value = [
                {"code": "sh600001", "name": "蓝筹股", "quantity": 200, "cost": 20.0}
            ]
            MockPM.return_value = mock_inst
            with patch.object(
                gen,
                "_fetch_quotes",
                return_value={"sh600001": {"price": 22.0, "change_pct": 1.5}},
            ):
                result = gen.generate()
        assert "蓝筹股" in result
        assert "持仓概览" in result

    def test_zero_cost_no_division_error(self, tmp_path):
        """cost=0 时不抛 ZeroDivisionError。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps([{"code": "sh600000", "name": "零成本", "shares": 100, "cost_price": 0}]),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch.object(
            gen,
            "_fetch_quotes",
            return_value={"sh600000": {"price": 10.0, "change_pct": 1.0}},
        ):
            result = gen.generate()
        assert "持仓日报" in result

    def test_missing_price_treated_as_zero(self, tmp_path):
        """行情缺失 price -> 当作 0。"""
        portfolio_file = tmp_path / "portfolio.json"
        portfolio_file.write_text(
            json.dumps([{"code": "sh600000", "name": "测试", "shares": 100, "cost_price": 10}]),
            encoding="utf-8",
        )
        gen = DailyReportGenerator(portfolio_path=str(portfolio_file))
        with patch.object(gen, "_fetch_quotes", return_value={"sh600000": {}}):
            result = gen.generate()
        assert "持仓日报" in result


# ═══════════════════════════════════════════════════════════════
# _fetch_quotes
# ═══════════════════════════════════════════════════════════════


class TestFetchQuotes:
    def test_empty_portfolio_returns_empty(self):
        gen = DailyReportGenerator()
        assert gen._fetch_quotes([]) == {}

    def test_normal_fetch(self):
        """mock http_get + parse_tencent_line。"""
        gen = DailyReportGenerator()
        portfolio = [{"code": "sh600000"}]
        # mock http_get 返回腾讯格式行（ASCII 占位，实际解析由 parse_tencent_line mock 完成）
        mock_response = b'v_sh600000="1~TEST~sh600000~10.00~9.80~10.10~1234~";'
        with patch("portfolio.daily_report.http_get", return_value=mock_response):
            with patch("portfolio.daily_report.parse_tencent_line") as mock_parse:
                mock_parse.return_value = {
                    "name": "测试股",
                    "code": "sh600000",
                    "price": "10.00",
                    "change_pct": "2.0",
                }
                result = gen._fetch_quotes(portfolio)
        assert "sh600000" in result

    def test_fetch_exception_returns_zero_price(self):
        """http_get 异常 -> 返回 price=0 兜底。"""
        gen = DailyReportGenerator()
        portfolio = [{"code": "sh600000"}]
        with patch("portfolio.daily_report.http_get", side_effect=Exception("network error")):
            result = gen._fetch_quotes(portfolio)
        assert "sh600000" in result
        assert result["sh600000"]["price"] == 0


# ═══════════════════════════════════════════════════════════════
# _format_report 更多分支
# ═══════════════════════════════════════════════════════════════


class TestFormatReport:
    def _stock(self, name="测试", price=10, change=1, profit_rate=5):
        return {
            "code": "sh600000",
            "name": name,
            "quantity": 100,
            "cost": 10,
            "current_price": price,
            "change_pct": change,
            "market_value": price * 100,
            "profit": (price - 10) * 100,
            "profit_rate": profit_rate,
        }

    def test_positive_profit_sign(self):
        gen = DailyReportGenerator()
        out = gen._format_report(
            total_value=20000,
            total_profit=1000,
            total_profit_rate=5,
            stock_details=[self._stock()],
        )
        assert "+¥1,000" in out

    def test_negative_profit_no_plus(self):
        gen = DailyReportGenerator()
        out = gen._format_report(
            total_value=9000,
            total_profit=-1000,
            total_profit_rate=-5,
            stock_details=[self._stock(profit_rate=-5)],
        )
        assert "+¥-1,000" not in out
        assert "¥-1,000" in out

    def test_best_stock_highlight(self):
        """涨幅最大股票被提及。"""
        gen = DailyReportGenerator()
        stocks = [
            self._stock(name="甲股", change=2, price=12),
            self._stock(name="乙股", change=-1, price=9),
        ]
        out = gen._format_report(
            total_value=2100,
            total_profit=100,
            total_profit_rate=5,
            stock_details=stocks,
        )
        assert "甲股" in out

    def test_worst_stock_highlight(self):
        """跌幅最大股票被提及。"""
        gen = DailyReportGenerator()
        stocks = [
            self._stock(name="甲股", change=2, price=12),
            self._stock(name="乙股", change=-3, price=7),
        ]
        out = gen._format_report(
            total_value=1900,
            total_profit=-100,
            total_profit_rate=-5,
            stock_details=stocks,
        )
        assert "乙股" in out

    def test_empty_stock_details(self):
        """空持仓详情 -> 无个股表现段落。"""
        gen = DailyReportGenerator()
        out = gen._format_report(
            total_value=0,
            total_profit=0,
            total_profit_rate=0,
            stock_details=[],
        )
        assert "持仓数量：0 只" in out
        assert "个股表现" not in out

    def test_long_name_truncated_in_table(self):
        """个股表现表中长名称截断到 6 字符。"""
        gen = DailyReportGenerator()
        long_name = "这是一个很长的股票名称"
        out = gen._format_report(
            total_value=1000,
            total_profit=0,
            total_profit_rate=0,
            stock_details=[self._stock(name=long_name)],
        )
        # 个股表现表中名称截断（表格行），但今日关注段用全名
        table_section = out.split("个股表现")[1].split("今日关注")[0] if "个股表现" in out else ""
        assert long_name not in table_section  # 表格中不出现全名
        assert long_name[:6] in table_section  # 截断名出现


# ═══════════════════════════════════════════════════════════════
# send_notification
# ═══════════════════════════════════════════════════════════════


class TestSendNotification:
    def test_unsupported_channel_prints_message(self, capsys):
        gen = DailyReportGenerator()
        gen.send_notification("report", channel="unknown")
        out = capsys.readouterr().out
        assert "不支持的通知渠道" in out

    def test_wechat_channel_in_development(self, capsys):
        gen = DailyReportGenerator()
        gen.send_notification("report", channel="wechat")
        out = capsys.readouterr().out
        assert "开发中" in out

    def test_dingtalk_channel_in_development(self, capsys):
        gen = DailyReportGenerator()
        gen.send_notification("report", channel="dingtalk")
        out = capsys.readouterr().out
        assert "开发中" in out

    def test_bark_no_config_skips(self, capsys):
        """Bark 未配置 -> 跳过发送。"""
        gen = DailyReportGenerator()
        with patch("config.loader.ConfigLoader.get", return_value=""):
            gen.send_notification("report", channel="bark")
        out = capsys.readouterr().out
        assert "未配置" in out

    def test_notification_exception_handled(self, capsys):
        """通知异常被捕获不抛出。"""
        gen = DailyReportGenerator()
        with patch.object(gen, "_send_bark", side_effect=Exception("bark error")):
            gen.send_notification("report", channel="bark")
        out = capsys.readouterr().out
        assert "发送通知失败" in out


# ═══════════════════════════════════════════════════════════════
# _parse_quote 补充分支
# ═══════════════════════════════════════════════════════════════


class TestParseQuoteExtra:
    def test_parse_via_tencent_line_success(self):
        """parse_tencent_line 成功 -> 返回结构化 dict。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        with patch("portfolio.daily_report.parse_tencent_line") as mock_parse:
            mock_parse.return_value = {
                "name": "测试股",
                "code": "sh600000",
                "price": "10.5",
                "prev_close": "10.0",
                "open": "10.2",
                "change_pct": "5.0",
            }
            result = gen._parse_quote("some response", "sh600000")
        assert result is not None
        assert result["name"] == "测试股"
        assert result["price"] == 10.5

    def test_parse_via_tencent_line_none_fallback_35_fields(self):
        """parse_tencent_line 返回 None -> 走 35 字段回退解析。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        with patch("portfolio.daily_report.parse_tencent_line", return_value=None):
            parts = ["v_sh600989="] + ["0"] * 35
            parts[1] = "测试股"
            parts[2] = "sh600989"
            parts[3] = "20.00"
            parts[4] = "19.50"
            parts[5] = "19.80"
            parts[32] = "2.56"
            response = '"' + "~".join(parts) + '"'
            result = gen._parse_quote(response, "sh600989")
        assert result is not None
        assert result["price"] == 20.00

    def test_parse_both_fail_returns_none(self):
        """parse_tencent_line 失败 + 35 字段也失败 -> None。"""
        gen = DailyReportGenerator(portfolio_path="/tmp/missing.json")
        with patch("portfolio.daily_report.parse_tencent_line", return_value=None):
            result = gen._parse_quote("invalid", "sh600989")
        assert result is None


# ═══════════════════════════════════════════════════════════════
# _send_bark 成功路径
# ═══════════════════════════════════════════════════════════════


class TestSendBarkSuccess:
    def test_bark_with_server_key_config(self, capsys):
        """有 server+key 配置 -> 构造 URL 并发送。"""
        gen = DailyReportGenerator()
        with patch("config.loader.ConfigLoader.get", side_effect=["https://bark.example.com", "abc123"]):
            with patch("monitor.channels.base.validate_webhook_url", return_value="https://bark.example.com/abc123"):
                with patch("urllib.request.urlopen") as mock_urlopen:
                    gen._send_bark("report content")
        # urlopen 被调用
        mock_urlopen.assert_called_once()
        out = capsys.readouterr().out
        assert "Bark 通知已发送" in out

    def test_bark_old_url_config(self, capsys):
        """旧配置 bark.url 整体写法。"""
        gen = DailyReportGenerator()

        def mock_get(cfg, key, default=""):
            if key == "channels.bark.server":
                return ""
            if key == "channels.bark.key":
                return ""
            if key == "bark.url":
                return "https://bark.example.com/old"
            return default

        with patch("config.loader.ConfigLoader.get", side_effect=mock_get):
            with patch("monitor.channels.base.validate_webhook_url", return_value="https://bark.example.com/old"):
                with patch("urllib.request.urlopen"):
                    gen._send_bark("report")
        # 不应出现"未配置"
        out = capsys.readouterr().out
        assert "未配置" not in out

    def test_bark_send_exception_handled(self, capsys):
        """urlopen 异常被捕获。"""
        gen = DailyReportGenerator()
        with patch("config.loader.ConfigLoader.get", side_effect=["https://bark.example.com", "abc123"]):
            with patch("monitor.channels.base.validate_webhook_url", return_value="https://bark.example.com/abc123"):
                with patch("urllib.request.urlopen", side_effect=Exception("network error")):
                    gen._send_bark("report")
        out = capsys.readouterr().out
        assert "发送 Bark 通知失败" in out


# ═══════════════════════════════════════════════════════════════
# main() CLI 入口
# ═══════════════════════════════════════════════════════════════


class TestMainCLI:
    def test_main_prints_report(self, capsys):
        """无参数 -> 打印报告。"""
        with patch.object(sys, "argv", ["daily_report.py"]):
            with patch.object(DailyReportGenerator, "generate", return_value="日报内容"):
                from portfolio import daily_report

                daily_report.main()
        out = capsys.readouterr().out
        assert "日报内容" in out

    def test_main_output_to_file(self, tmp_path, capsys):
        """--output -> 写入文件。"""
        out_file = tmp_path / "report.txt"
        with patch.object(sys, "argv", ["daily_report.py", "--output", str(out_file)]):
            with patch.object(DailyReportGenerator, "generate", return_value="日报内容"):
                from portfolio import daily_report

                daily_report.main()
        assert out_file.read_text(encoding="utf-8") == "日报内容"
        out = capsys.readouterr().out
        assert "已保存到" in out

    def test_main_with_channel(self, capsys):
        """--channel -> 调用 send_notification。"""
        with patch.object(sys, "argv", ["daily_report.py", "--channel", "wechat"]):
            with patch.object(DailyReportGenerator, "generate", return_value="日报内容"):
                with patch.object(DailyReportGenerator, "send_notification") as mock_send:
                    from portfolio import daily_report

                    daily_report.main()
        mock_send.assert_called_once_with("日报内容", "wechat")

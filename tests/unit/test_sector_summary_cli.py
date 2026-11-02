"""sector_summary.py --sector 过滤顺序的回归测试（该脚本此前零单测）。

不变量：--sector 在截断前生效——目标板块不在 Top N 内时仍可命中
（放大拉取窗口至全榜），且 JSON 输出携带 filter 元信息、空结果可解释。

回归背景（2026-11-02 skill 审查 P1）：先 fetch_sector_summary(top=30)
截断再 filter_by_name，目标板块跌出涨幅榜前 30 时静默返回空列表。
"""

from __future__ import annotations

import json

import sector_summary


def _fake_items():
    return [
        {
            "rank": 1,
            "code": "",
            "name": "半导体",
            "change_pct": 3.0,
            "lead_stock": "A",
            "lead_change_pct": 5.0,
            "turnover_yi": 100.0,
            "net_inflow_yi": 1.0,
            "up_count": 10,
            "down_count": 2,
        },
        {
            "rank": 2,
            "code": "",
            "name": "游戏",
            "change_pct": 2.0,
            "lead_stock": "B",
            "lead_change_pct": 4.0,
            "turnover_yi": 90.0,
            "net_inflow_yi": 2.0,
            "up_count": 8,
            "down_count": 3,
        },
        {
            "rank": 3,
            "code": "",
            "name": "医疗服务",
            "change_pct": 1.0,
            "lead_stock": "C",
            "lead_change_pct": 3.0,
            "turnover_yi": 80.0,
            "net_inflow_yi": 3.0,
            "up_count": 6,
            "down_count": 4,
        },
    ]


def _patch_fetch(monkeypatch, captured):
    def fake_fetch(source="auto", top=30):
        captured["source"] = source
        captured["top"] = top
        return {
            "as_of": "2026-11-03T01:00:00",
            "source": "ths",
            # 模拟真实 fetch 的截断语义（ths head(top) / 东财 pz=top）
            "items": _fake_items()[:top],
            "data_quality": {"degraded_fields": [], "source": "ths"},
        }

    monkeypatch.setattr(sector_summary, "fetch_sector_summary", fake_fetch)


class TestSectorFilter:
    def test_filter_applies_before_truncation(self, monkeypatch, capsys):
        """目标板块在 Top N 之外（--top 2 但目标 rank 3）仍能命中。"""
        captured: dict = {}
        _patch_fetch(monkeypatch, captured)
        monkeypatch.setattr("sys.argv", ["sector_summary.py", "-j", "--top", "2", "--sector", "医疗"])
        sector_summary.main()

        out = json.loads(capsys.readouterr().out)
        assert captured["top"] == 500, "--sector 时必须放大拉取窗口至全榜"
        assert [it["name"] for it in out["items"]] == ["医疗服务"]
        assert out["items"][0]["rank"] == 1
        assert out["filter"] == {"sector": "医疗", "matched": 1, "board_size": 3}

    def test_no_sector_keeps_top_semantics(self, monkeypatch, capsys):
        """不带 --sector 时行为不变：--top 2 截断 2 条，无 filter 键。"""
        captured: dict = {}
        _patch_fetch(monkeypatch, captured)
        monkeypatch.setattr("sys.argv", ["sector_summary.py", "-j", "--top", "2"])
        sector_summary.main()

        out = json.loads(capsys.readouterr().out)
        assert captured["top"] == 2
        assert len(out["items"]) == 2
        assert "filter" not in out

    def test_no_match_is_explained(self, monkeypatch, capsys):
        """模糊匹配无命中：items 为空但携带可解释的 filter 元信息。"""
        captured: dict = {}
        _patch_fetch(monkeypatch, captured)
        monkeypatch.setattr("sys.argv", ["sector_summary.py", "-j", "--sector", "不存在板块"])
        sector_summary.main()

        out = json.loads(capsys.readouterr().out)
        assert out["items"] == []
        assert out["filter"] == {"sector": "不存在板块", "matched": 0, "board_size": 3}


class TestFilterByName:
    def test_substring_match(self):
        items = _fake_items()
        assert [it["name"] for it in sector_summary.filter_by_name(items, "半导体")] == ["半导体"]

    def test_empty_query_returns_all(self):
        items = _fake_items()
        assert len(sector_summary.filter_by_name(items, "")) == 3

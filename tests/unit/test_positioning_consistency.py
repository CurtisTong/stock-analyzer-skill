"""定位口径一致性测试。

背景：项目定位在 README / 产品架构 / 用户指南之间多次漂移（典型残留：
"零门槛 / 无需编程" 与实际需要终端环境不符；"AI 驱动的多因子选股" 与
策略外样本全部未达标的事实冲突）。docs/positioning.md 是唯一事实源，
本测试锁住"其他文档不回流禁用表述"，避免再次漂移。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent.parent
POSITIONING = PKG_ROOT / "docs" / "positioning.md"
ARCHITECTURE = PKG_ROOT / "docs" / "product-architecture.md"
INDEX = PKG_ROOT / "docs" / "INDEX.md"
README = PKG_ROOT / "README.md"
OOS_JSON = PKG_ROOT / "data" / "strategy_oos_validation.json"
EXPERTS_YAML = PKG_ROOT / "experts" / "yaml"

# 与定位事实冲突的表述，任何用户面文档不得再出现
BANNED_PHRASES = (
    "无需编程",
    "零门槛",
    "AI 驱动的多因子选股",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestPositioningSource:
    def test_positioning_doc_exists(self):
        assert POSITIONING.exists(), "docs/positioning.md 缺失，定位失去单一事实源"

    @pytest.mark.parametrize(
        "heading",
        ["一句话定位", "品类", "目标用户", "楔子", "护城河与反定位", "依据与证据", "成功指标"],
    )
    def test_required_sections_present(self, heading):
        assert heading in _read(POSITIONING), f"positioning.md 缺少章节：{heading}"

    def test_referenced_by_index_and_architecture(self):
        assert "positioning.md" in _read(INDEX), "docs/INDEX.md 未挂载定位文档"
        assert "positioning.md" in _read(ARCHITECTURE), "产品架构未引用定位文档"
        assert "positioning.md" in _read(README), "README 未引用定位文档"

    def test_readme_hero_matches_positioning(self):
        """首屏承诺必须与 positioning.md 的 10 分钟口径一致。"""
        hero = "\n".join(_read(README).splitlines()[:20])
        assert "每天 10 分钟做完 A 股持仓体检与复盘" in hero

    def test_readme_leads_with_daily_entries(self):
        """/portfolio health 与 /market quick 必须作为日常入口出现在首屏区域。"""
        head = "\n".join(_read(README).splitlines()[:20])
        assert "/portfolio health" in head
        assert "/market quick" in head
        assert "两个日常入口" in _read(README)


class TestNoConflictingClaims:
    @pytest.mark.parametrize("path", [README, ARCHITECTURE], ids=["README", "product-architecture"])
    @pytest.mark.parametrize("phrase", BANNED_PHRASES)
    def test_banned_phrase_absent(self, path, phrase):
        hits = [i + 1 for i, line in enumerate(_read(path).splitlines()) if phrase in line]
        assert not hits, f"{path.name} 仍含与定位冲突的表述 {phrase!r}（行 {hits}），应改为 positioning.md 的口径"


class TestExpertCountConsistency:
    def test_active_expert_count_is_eight(self):
        """对外始终称 8 位活跃专家（5 长线 + 3 短线），legacy 8 份已合并。"""
        active = [p for p in EXPERTS_YAML.glob("*.yaml") if "active: true" in _read(p)]
        assert len(active) == 8, f"活跃专家数应为 8，实际 {len(active)}"

    def test_architecture_does_not_claim_sixteen_active(self):
        text = _read(ARCHITECTURE)
        assert "16 人专家圆桌" not in text, "16 人指人设总数（8 active + 8 legacy），不能表述为 16 人圆桌"


class TestReportTemplateTiering:
    """quick 与 full 必须有独立模板：quick 不再借用 full 的论证密度。"""

    def test_quick_template_exists_and_is_referenced(self):
        quick = PKG_ROOT / "skills" / "stock" / "reports" / "quick-template.md"
        assert quick.exists(), "缺少 reports/quick-template.md，quick 模式没有独立输出契约"
        assert "quick-template.md" in _read(PKG_ROOT / "skills" / "stock" / "SKILL.md")

    def test_quick_template_stays_short(self):
        quick = PKG_ROOT / "skills" / "stock" / "reports" / "quick-template.md"
        lines = len(_read(quick).splitlines())
        assert lines <= 80, f"quick 模板 {lines} 行，已接近 full 模板体量（{80} 行上限）"


class TestEvidenceIntegrity:
    def test_positioning_mentions_oos_status_when_in_sample(self):
        """只要有策略仍为 in_sample，定位文档就必须保留外样本证据段落。"""
        data = json.loads(_read(OOS_JSON))
        unverified = [k for k, v in data.items() if v.get("validation_status") != "oos_verified"]
        if not unverified:
            pytest.skip("所有策略均已通过外样本验证，证据段落可重写")
        text = _read(POSITIONING)
        assert "in_sample" in text and "外样本" in text, "定位文档必须保留策略外样本未达标的证据表述"

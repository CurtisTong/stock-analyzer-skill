# Stock Analyzer Skills 工作流优化施工方案 v1.0

**日期**：2026-06-16
**范围**：仅 Skill 工作流（不含 scripts/ 内部重构）
**策略**：分 6 个 Phase，每个 Phase 一个或一组独立 PR；Phase 1-3 可独立合入；Phase 4-6 有依赖
**背景**：基于 2026-06-16 的 4 维度探子扫描（SKILL.md 结构 / Scripts 对账 / 专家圆桌 / 测试 CI）。

---

## Phase 1：P0 地基修复（PR #1，~4 小时，纯修复）

### P1.1 绝对路径改相对（影响 13 个 SKILL.md）
- 改动文件：13 个 SKILL.md 的 frontmatter `allowed-tools`
- 改动模式：`/Users/curtis/Documents/curtis/stock-analyzer-skill/...` → 相对项目根
- 新增测试：`tests/test_skill_metadata.py::test_no_absolute_paths_in_allowed_tools`

### P1.2 setup-test 安装 hypothesis
- 改动：`.github/actions/setup-test/action.yml:31` 增 hypothesis

### P1.3 pyproject.toml 集中 dev-dependencies
- 新增：`[project.optional-dependencies.test]`

### P1.4 clock 注入
- 新增：`scripts/dev/clock.py`
- 改动：替换 11 处 `datetime.now()` 调用（fetchers/eastmoney_chip.py 等）

### P1.5 conftest.py fixture 改相对日期
- 改动：`tests/conftest.py` 11 处硬编码 `2025-01-XX` 日期 → 相对 `datetime.now()`

---

## Phase 2：CI 闭环 + Schema Contracts（PR #2-3，~1 天）

### P2.1 smoke_test.sh 入 CI
- 新增 ci.yml `smoke` job（依赖 test job，单 Python 版本，concurrency 控制）

### P2.2 schema contracts 框架
- 新建：`skills/_shared/contracts/` 5 个 schema（stock/market/sector/portfolio/debate）+ README
- 新建：`scripts/dev/validate_contracts.py`

---

## Phase 3：CLI 一致性 + 策略单一事实源（PR #4-5，~1 天）

### P3.1 4 个核心脚本迁 argparse
- 改动：quote/finance/kline/announcements 4 个脚本

### P3.2 monitor.py 改 --log-json 为 --json
- 改动：`scripts/monitor.py`

### P3.3 strategies.md 单一事实源
- 新建：`skills/_shared/references/strategies.md`
- 改动：screener/backtest/research 3 个 SKILL.md 引用单一源

---

## Phase 4：专家去重 + 补盲区（PR #6-7，~2-3 天）

### P4.1 阶段 A：合并（8→5）
- 合并映射：
  - buffett + duan_yongping → value_anchor（价值双锚）
  - xu_xiang + zhao_laoge → topic_leader（题材龙头）
  - chaogu_yangjia + zuoshou_xinyi → emotion_tech（情绪技术复合）
- 保留：lynch / soros

### P4.2 阶段 B：补盲区（5→8）
- 新增：sector_specialist / institution / risk_manager

### P4.3 冲突解决修复
- decide.py 加优先级判断：horizon 权重优先于 market_state

---

## Phase 5：文档瘦身（PR #8-10，~1 天）

### P5.1 portfolio 拆分
- 新建：portfolio-web/SKILL.md、portfolio-natural/SKILL.md
- 缩 portfolio/SKILL.md 到 ~180 行

### P5.2 stock 拆 technical
- 新建：stock-technical/SKILL.md
- stock/SKILL.md 移除 Step 5

### P5.3 research report 去重
- research/SKILL.md Step 3 改为调用 `/stock full`

### P5.4 help 动态化
- 新建：scripts/dev/list_skills.py

---

## Phase 6：测试补全（PR #11+，~2 天）

### P6.1 0 覆盖核心脚本
- 新建：test_stock.py / test_portfolio_daily_report.py / test_portfolio_performance.py / test_calibration_sync.py

### P6.2 property test 扩展
- 新建：test_technical_properties.py / test_screener_properties.py / test_finance_mapping_properties.py

### P6.3 集成测试
- 扩 tests/integration/test_install.sh

---

## 风险与回滚

| Phase | 风险 | 回滚 |
|---|---|---|
| 1 | 路径改错 | git revert 单 commit |
| 2 | smoke 暴露历史问题 | 本地预热后再合 |
| 3 | argparse 迁移破坏调用方 | 保留 `-j` 短选项兼容 |
| 4 | 专家合并输出变化 | 双轨期保留 `--use-legacy-experts` |
| 5 | skill 拆分破坏 install | install.sh 测试必过 |
| 6 | property test 发现 bug | 分批合 |

---

## 关键依赖

```
Phase 1 ─┬─→ Phase 2 ─┬─→ Phase 3 ─┬─→ Phase 4 ─┬─→ Phase 5 ─┐
         └────────────┴────────────┴────────────┴────────────┴─→ Phase 6
```

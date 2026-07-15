# Stock Analyzer Skill · 深度审查与推演报告（2026-07-15）

> **审查时间**：2026-07-15  
> **审查者**：Claude Code 综合勘察（源码 + 测试 + 文档三维印证）  
> **基线版本**：v1.15.0 (commit `4ac345a` 体系)  
> **当前分支**：`main`（干净）  
> **关联文档**：[architecture-review-2026-07-07.md](architecture-review-2026-07-07.md) ·
> [full-module-review-2026-07-02.md](full-module-review-2026-07-02.md) ·
> [review-issues.md](review-issues.md) ·
> [review-verification.md](review-verification.md)
>
> **本报告定位**：在 2026-07-07 架构审查 + 2026-07-09 R7-R11 全量修复完成之后的**当前健康度诊断与前瞻性风险推演**。

---

## 一、执行摘要

### 一句话诊断

> ⚠️ **项目处于"债务已收官，但门禁松散"的状态**。前几轮 121 项技术债（21 架构 + 75 深度审阅 + 25 历史债）已基本清零，**代码层质量确实优秀**；但**测试基础设施和发布门禁存在明显漏洞**，导致 67 个测试失败被合并入 main 仍未被拦截，**事实上削弱了前几轮清理的可信度**。

### 关键定量指标

| 指标 | Round 11 后 (ec4c290) | 当前实测 (2026-07-15) |
|:---|---:|---:|
| 测试用例数（collected） | ~2,725 | **5,506** |
| 通过数 | 2,725 | **5,382** ✅ |
| 失败数 | 0 | **67 failed** ⚠️ |
| 跳过数 | 25 | 21 skipped |
| ruff 错误 | 0 | 0 ✅ |
| Pre-commit hooks | 配置存在 | **❌ 未安装** ⚠️ |
| Stale commit 数（最近 30 天） | — | **503** commits |

> 测试用例数翻倍是好信号（覆盖率 91.7% → ~97%），但 67 失败意味着**相当一部分"质量提升"建立在沙地之上**。

---

## 二、67 个失败的精确分类（核心发现）

### 2.1 全量失败 vs 单跑失败的对照实验

通过逐文件隔离运行，67 failed 实际分为两类：

| 类型 | 数量 | 性质 | 修复难度 |
|:---|---:|:---|:---:|
| **🔴 稳定失败**（隔离单跑也失败） | **~14** | 代码与测试真的漂移 | 中 |
| **🟡 顺序污染**（仅全量跑失败） | **~53** | 测试间状态污染 | 中-高 |

> 这个分类本身比失败数量更值得关注：**53 个"看起来失败其实是污染"的测试，掩盖了真正漂移的严重性**。

### 2.2 🔴 14 个稳定失败 — 根因矩阵

| # | 测试文件 | 测试 | 期望 | 实测 | 根因 | 引入 commit |
|:--|:---------|:-----|:----:|:----:|:-----|:-------------|
| 1 | `tests/test_screening_service_final.py` | `TestBoardLimit::test_main_board` | 9.5 | 10.0 | **business C2 修复为精确阈值**（9.5→10.0），测试跟随旧值 | 771c15f（**晚于修复**）⚠️ |
| 2 | 同上 | `test_gem` | 19.5 | 20.0 | 同上 | 771c15f ⚠️ |
| 3 | 同上 | `test_star` | 19.5 | 20.0 | 同上 | 771c15f ⚠️ |
| 4 | 同上 | `TestMinSurvivalCap::test_main` | 类型契约变 | — | 排雷阈值被 P2-06 行业扩展改写 | 771c15f ⚠️ |
| 5-7 | 同上 | `test_other` + `TestThresholds`（goodwill/pledge） | — | — | 排雷阈值漂移 | 771c15f |
| 8 | `tests/test_market_regime.py` | `test_range_mid_signal` | `RANGE` | `RANGE_LOW_VOL` | **3c07ff7 把 RANGE 拆为 LOW_VOL/CHOPPY**，测试未同步 | **3c07ff7** ⚠️ |
| 9 | 同上 | `test_default_zero_signals` | `RANGE` | `RANGE_LOW_VOL` | 同上 | **3c07ff7** ⚠️ |
| 10-12 | `tests/test_regime_classifier.py` | empty/边界/boundary_volatility | `RANGE` | `RANGE_LOW_VOL/CHOPPY` | 同上 | **3c07ff7** ⚠️ |
| 13 | `tests/test_beichi_final2.py` | `test_short_data` | — | `AttributeError` | `detect_beichi` 函数已重命名/迁移 | 085a3b7 |
| 14 | 同上 | `test_with_bis` | — | `AttributeError` | 同上 | 085a3b7 |
| 15 | `tests/test_data_init_final.py` | `test_empty`（get_kline） | — | `AttributeError` | `_get_kline_manager` 私有方法已迁移/重命名 | 771c15f ⚠️ |
| 16 | 同上 | `test_returns_list`（get_finance） | — | `AttributeError` | 同上 | 771c15f |
| 17 | `tests/test_alert_engine_unit_extra.py` | `test_briefing_json` | `"简报文本"` | `"test"` | mock 返回值优先级被修改，期望的是源码默认生成的字段 | a00dfa9 |
| 18-21 | `tests/test_sync_version_final[2].py` | `_apply_patterns` 系列 | 2-tuple | 3-tuple | **P2-30 声明式改写后参数顺序变更** `(content, version, patterns)` → `(content, patterns, version)`，测试未跟进 | ee353e2 / afa57f7 |

> ⚠️ **"测试晚于修复"** 模式反复出现，至少 4 起（#1-6、#15-16、#17、#18-21）。这是 `tests/README_TEST_NAMING.md` 已记录的**测试蔓延问题**——批量增补覆盖率时未对齐源码签名变更。
>
> 注意：表格里 21 行 ≠ 14 项——部分聚合是为了清晰，实际文件级失败数为 7/2/2/2/1/3 个（详见后文"按文件分布"）。

### 2.3 按文件分布（实测）

| 文件 | FAILED 数 | 性质 | 是否"晚于修复" |
|:----|---:|:---|:---:|
| `tests/test_scoring.py` | 13 | 🟡 顺序污染 | — |
| `tests/test_momentum_trader.py` | 8 | 🟡 顺序污染 | — |
| `tests/test_screening_service_final.py` | 7 | 🔴 稳定 | ✅ |
| `tests/test_regime_classifier.py` | 4 | 🔴 稳定 | ✅ |
| `tests/test_data_init_final.py` | 3 | 🔴 稳定 | ✅ |
| `tests/test_beichi_final2.py` | 3 | 🔴 稳定 | ✅ |
| `tests/test_vote_engine_gating.py` | 2 | 🟡 顺序污染 | — |
| `tests/test_sync_version_final2.py` | 2 | 🔴 稳定 | ✅ |
| `tests/test_sync_version_final.py` | 2 | 🔴 稳定 | ✅ |
| `tests/test_scoring_experts.py` | 2 | 🟡 顺序污染 | — |
| `tests/test_yaml_consistency.py` | 1（实际 ~26） | 🟡 顺序污染 | — |
| 其他（chip/flow/lhb/buffett 等） | ~20 | 🟡 顺序污染 | — |
| **总计** | **~67** | 14 稳定 + 53 顺序污染 | |

### 2.4 🟡 53 个顺序污染失败的根因锁定

**根本原因**：`experts/__init__.py:29` 在模块 import 时直接执行 `_ensure_loaded()`：

```python
# experts/__init__.py
from experts.types import ExpertProfile, DIRECTION_THRESHOLDS, direction_from_score

# 导入注册表（放在模块底部以利用 dataclass 定义）
from .registry import (
    EXPERT_REGISTRY,
    _ensure_loaded,
)  # noqa: E402

_ensure_loaded()   # ← 副作用：调用 yaml_loader 写入全局 EXPERT_REGISTRY
```

**为什么形成污染**：
- **单跑时**：每个测试 module 重新 `import experts`，触发首次 `_ensure_loaded()`，数据正确
- **全量跑时**：第一个测试 module 加载后 `EXPERT_REGISTRY` 被填充；后续测试如果**修改了 yaml loader 内部状态**或 mock 了某个路径，污染会传染到所有依赖 `experts` 模块的对象

**受影响最严重的测试文件**：
- `test_scoring.py`（13 个）：专家评分函数依赖全局注册表
- `test_momentum_trader.py`（8 个）：动量指标 + 阈值映射被污染
- `test_yaml_consistency.py`（~26 个）：本身就是 yaml 加载测试，每个测试都改全局 registry

**修复方案（4h）**：
1. 把 `_ensure_loaded()` 从 `experts/__init__.py` 顶层移到一个显式函数，如 `ensure_experts_loaded()`
2. 在每个需要专家注册表的入口处显式调用（典型 6-8 处）
3. `tests/conftest.py` 加 `_reload_expert_registry()` autouse fixture，每次测试前重置 `EXPERT_REGISTRY`

---

## 三、关键风险点推演（前瞻性分析）

### 3.1 🔴 P0 隐患：发布门禁失能

| 现象 | 影响 |
|:-----|:-----|
| 67 个测试失败已合入 main，未被 PR 阻断 | CI 应有 `-x` 选项**未拦住第一个失败**？ |
| Pre-commit hooks 配置存在但**未安装** | 本地提交无任何门禁，PR 也只依赖 CI |
| `ci.yml` 与 `release.yml` 重复跑全量测试但参数不一致 | release 路径 `pytest tests/test_skill_metadata.py tests/test_skill_consistency.py -v` 比 ci 宽松，**绕过覆盖率门槛 `--cov-fail-under=60`** |
| `sync_skill_test_versions.py` 仍用脆弱正则（review P0-15） | **Round 7 应修未修**——README 已列 ✅ 但只 commit `afa57f7` 修了一半 |

**推演**：当前 PR 合并流程如果只看 GH web UI 的绿色勾，**实际是 `pytest -v -q` 跳过部分失败**——靠 5506 测试中只有 67 失败维持绿。如果再 batch 添加 100 个测试，PR 失败率会急剧上升。

### 3.2 🟡 P1 隐患：报告生成层（`stock.py`）= 测试盲区

| 现实 | 后果 |
|:-----|:-----|
| `scripts/stock.py` 的核心输出**没有任何测试** | 5 层分析报告、专家辩论输出格式**完全没有契约** |
| `experts/formatter.py` 单跑测试都过，但 v1.15.0 重写了 3 段式排版（commit `fb9f8c1`）| 新报告格式是否被破坏**只能靠人眼** |
| `skills/stock/SKILL.md` 与实际 `format_debate_brief()` 的字段不一致问题**历史上反复出现**（decide.md 否决评分 0 vs 20）| 文档与实现可观察性下降 |

**推演**：报告生成是用户最常接触的接口（`/stock 600519`），但是测试基础设施最薄弱的地方。如果 report 格式回归，会在用户层面默默发生。

### 3.3 🟡 P1 隐患：专家校准链路过拟合风险

**问题域**：

```
round 7 P0-08（vote_engine）→ round 8 长短线稳定 → round 9 registry 清理 → round 10 value_institution 三阶段 → round 11 9 项收尾
```

**逻辑链**：
- Round 8: lynch 单独成长专家 + value_institution 合并（替代 value_anchor/institution 同质化）
- Round 10 (44e28a0 `feat(experts)`): value-anchor-optimization 分支，三阶段：展示层约束 + veto 风险分级 + **周期矩阵**

**风险点**：
- 短历史样本（v1.10-v1.15）支撑的"信心-权重"参数矩阵，**无 walk-forward 验证**
- 周期矩阵（"牛市/熊市/震荡"）的转换函数如果写错，**所有圆桌结论系统性偏移**
- 3 个 Round 10/11 之间的 `experts/vote_engine.py` 改动 + P0-09 全空分支重排未做交互回归测试

**推演**：专家系统是项目**核心差异化卖点**（16 份专家圆桌），但其"调优→校准→验证"闭环仍未形成——**这是商业风险点**。

### 3.4 🟢 P2 隐患：缠论 / 战法模块的可信度缺口

- 缠论 5 项核心算法偏离原文（C1-C5 of full-module-review）已用"标注而非重构"暂缓
- **但 `oos_validated: false` 字段写入了 `patterns/config.json`（P2-28 修复）**，机器可读警示还没进 SKILL.md 显式提示
- 71.4% 胜率警示出现在 `CLAUDE.md` 而非每次 `/stock` 输出——**用户可见性低**

---

## 四、架构与产品质量（已巩固部分）

前几轮确实把架构债清干净了，下列是**已落地、质量优秀**的成果（**应继续保持**）：

### 4.1 三层架构执行干净

```
SKILL.md → scripts/*.py (47 个 CLI 入口) → business/ → fetchers/
                  ↑ common/              ↑ data/
                  ↑ config/yaml          ↑ monitoring/
```

| 抽象 | 状态 | 备注 |
|:-----|:----:|:-----|
| `BaseFetcher` + `DataFetcherManager` | ✅ | timeout/retry 由 YAML 控制（P0-03 修复） |
| `CircuitBreaker` 三态机 | ✅ | recovery_timeout 最小值校验（P0-05） |
| `RateLimitError` 不熔断 | ✅ | P0-04 修复 |
| 异常体系 `StockAnalyzerError` 树 | ✅ | 用户友好消息映射完整 |
| `ConfigLoader` 线程安全 | ✅ | 加 `_lock` + 双重检查 |
| `cache_key_for_stock()` 版本前缀 | ✅ | `_DATA_FORMAT_VERSION=v2` |
| 多源故障转移 `fetch_with_fallback` | ✅ | chip/flow/lhb/event 四域 YAML 化 |

### 4.2 投资逻辑体系

| 维度 | 现状 | 评价 |
|:-----|:-----|:-----|
| 5 层分析框架 | `scripts/business/stock_analysis.py` 完整 | 输出契约清晰 |
| 8 active 专家圆桌 | `vote_engine.py` 8 种冲突分支 | 已修复伪多元化（同质化 / 否决权过度） |
| 5 层数据源熔断 | 27 fetchers × 35 类 | 工业级冗余 |
| 6 种选股策略 | `strategies/registry.py` | 注册表机制好 |
| 缠论 + 战法 | `chan/` + `patterns/` | ⚠️ 标准缠论偏离需标注 |

### 4.3 工程化基础设施（已配置但部分未启用）

| 项 | 状态 | 备注 |
|:---|:----:|:-----|
| `pyproject.toml` SemVer + 可选依赖分组 | ✅ | 测试依赖独立分组 |
| `mypy.ini` + `ruff` 双 lint | ✅ | ruff 0 errors |
| `pre-commit-config.yaml` 5 个钩子 | ⚠️ | **未安装**（`.git/hooks/` 全为空） |
| `sync_skill_test_versions.py` | ⚠️ | 已存在但仍脆弱正则（P0-15 部分修） |
| GitHub Actions：ci / release / changelog | ✅ | 但 release 与 ci 参数不一致 |
| ADR 文档 4 篇 | ✅ | ADR-001~004 完整 |

---

## 五、需要立即行动的关键改进（Top 10 推演）

> 按"影响 × 可逆性"排序。每项给出**真实 PR diff 的代码量级**。

### 🔴 P0：立刻修（≤ 1 天）

| # | 项 | 文件 | 工作量 | 风险 |
|:--|:---|:-----|:------:|:----:|
| 1 | **测试隔离：把 `_ensure_loaded()` 从 `experts/__init__.py` 顶层移除，改成显式调用** | `experts/__init__.py` + 所有调用方 | 4h | 低（向后兼容） |
| 2 | **修复 14 个稳定失败**（特别：`_board_limit` 期望值 9.5→10.0、19.5→20.0；RANGE→RANGE_LOW_VOL 适配；`detect_beichi` 与 `_get_kline_manager` 新签名适配；`sync_version` 参数顺序） | 测试 7 个文件 | 4h | 低 |
| 3 | **`detect_beichi` / `_get_kline_manager` 暴露稳定公共接口**（如果尚未暴露） | `scripts/chan/beichi.py`、`scripts/data/__init__.py` | 1h | 低 |
| 4 | **CI 跑全量但 release 不跑覆盖率**：统一参数 | `.github/workflows/release.yml` | 1h | 低 |
| 5 | **安装 pre-commit hooks**（`pre-commit install`） | repo 级一次操作 | 0.5h | 极低 |

> P0 全部完成后预期：**67 failed → 0**，测试基线从"沙地"恢复"混凝土"。

### 🟡 P1：本周内（≤ 1 周）

| # | 项 | 文件 | 工作量 | 风险 |
|:--|:---|:-----|:------:|:----:|
| 6 | **为 `scripts/stock.py` 五层分析报告加 E2E 测试**（mock quote/kline/finance/各 expert） | `tests/e2e/test_stock_workflow.py` | 8h | 低 |
| 7 | **为 `experts/vote_engine.py` 8 种冲突分支加矩阵测试** | `tests/test_vote_engine_matrix.py` | 4h | 中 |
| 8 | **为 `experts/formatter.py` 加黄金快照测试**（golden snapshot） | `tests/experts/test_formatter_snap.py` | 4h | 低 |
| 9 | **缠论 / 战法的"`oos_validated: false`" 推到 SKILL.md 显著位置** | `skills/stock-technical/SKILL.md` | 1h | 低 |
| 10 | **专家"周期矩阵"加 walk-forward 验证**（即使简化版） | `experts/veto_evaluator.py` + 新 `tests/test_veto_walk_forward.py` | 8h | 中 |

### 🟢 P2：版本节奏（< 1 月）

| # | 项 | 备注 |
|:--|:---|:-----|
| 11 | 把 `scripts/macro/` + `historical snapshot` 接入 `/market briefing` | 已存在 macro/，需 skill 串联 |
| 12 | `experts/_merge.py` 抽出 `VetoPolicy` 抽象层 | review P1-06 |
| 13 | 增加 `tests/test_concurrency_*.py`（portfolio web 多进程 / monitor 多实例） | review P1 / 后续 |
| 14 | `data/api-reference.md` 与 OpenAPI-style spec 同步 | 当前已大量文档 |

---

## 六、推演性结论

### 6.1 项目定位的真实评估

**优秀**的部分（应保护）：
- **专家圆桌辩论** 是同类工具罕见能力
- **三级数据源 + 熔断器** 是工业级容错设计
- **零外部依赖** 是安装成本杀手锏
- **13 个 skill 的语义化覆盖** 是产品设计能力

**薄弱**的部分（需重点投资）：
- **测试可观察性**：覆盖率数字漂亮，但 **实质回归 / 漂移信号被掩盖**
- **发布门禁**：CI 绿但发布路径绕过覆盖率门槛
- **报告生成层契约**：用户最关心却最缺测试保护

### 6.2 推演未来的 3 个风险窗口

| 窗口 | 风险 | 防御建议 |
|:-----|:-----|:------|
| **下次大重构**（如 stock.py 五层改 v2.0） | 测试盲区导致 silently 改变输出契约 | **先写 E2E 测试再重构**（#6） |
| **数据源大规模迁移**（akshare 升级失败 pyproject.toml 已记录） | 多个 fetcher 同时降级 | **加"fetcher 健康度矩阵"** 监控 |
| **专家系统参数调优**（value-anchor-optimization 仍在持续） | 历史样本 < 半年的校准易过拟合 | **OOS 验证门禁**（#10） |

### 6.3 最终评级

| 维度 | 评分 | 评价 |
|:-----|:---:|:------|
| 架构质量 | 8.5/10 | 三层分离、依赖倒置、配置外部化都已成熟 |
| 测试覆盖率（行） | 7/10 | 数量足够但**契约覆盖薄弱** |
| 测试稳定性 | 4/10 | 53 个顺序污染 = **结构性 bug** |
| 可观察性 | 6/10 | 有 skill footer 时间戳、benchmark，但 e2e 缺位 |
| 工程化门禁 | 4/10 | pre-commit 未装、release 路径绕过覆盖率 |
| 投资逻辑深度 | 7/10 | 圆桌 16 份是亮点，但 walk-forward 缺位 |
| 文档完整性 | 8/10 | ADR + 多份审查 + 教程齐全 |
| 商业可持续性 | 6/10 | 核心差异化（圆桌）需加固而非继续扩张 |

**综合**：**7.0 / 10**。项目距离"v2.0 工业级"还差**一次系统性的测试基础设施加固**（P0-P1 共 5-7 天）。

---

## 七、推荐执行节奏

```
本周 P0 (5 项, ~1 工作日)
  ├─ #2 修稳定失败 → 67 → 53 failed
  ├─ #1 _ensure_loaded 隔离 → 53 → 0 failed
  ├─ #5 安装 pre-commit hooks → 后续 PR 自带门禁
  ├─ #4 release 路径复用 ci → 防止覆盖率绕过
  └─ #3 重写 test_beichi_final2 适配新签名

下迭代 P1 (5 项, ~3 工作日)
  ├─ #6 stock.py E2E
  ├─ #7 vote_engine 矩阵测试
  ├─ #8 formatter 黄金快照
  └─ #10 周期矩阵 walk-forward

1 个月 P2 (4 项, 持续)
  └─ 优先级跟随用户反馈
```

---

## 八、附录：所有发现的可执行 Checklist

> 这是一份**纯清单**，无叙事。复制到 issue tracker 即可推进。

### 🔴 P0 必须修复

- [ ] `experts/__init__.py` 顶层移除 `_ensure_loaded()`，改显式调用
- [ ] `_board_limit` 测试期望 9.5/19.5 → 10.0/20.0（4 个测试）
- [ ] test_screening_service_final: goodwill/pledge/min_survival 适配新阈值（3 个测试）
- [ ] `3c07ff7` 引入 RANGE 拆分后更新 test_market_regime.py × 2 与 test_regime_classifier.py × 4
- [ ] test_beichi_final2.py × 3 适配 `detect_beichi` 新位置
- [ ] test_data_init_final.py × 3 适配 `_get_kline_manager` 新位置
- [ ] test_alert_engine_unit_extra.py::test_briefing_json 期望值与 mock 返回对齐
- [ ] test_sync_version_final[2].py × 4 适配 `_apply_patterns` 参数顺序
- [ ] CI 与 release 参数一致（`--cov-fail-under=60` 必须 release 也跑）
- [ ] `pre-commit install` 执行并写入文档

### 🟡 P1 一周内

- [ ] `tests/e2e/test_stock_workflow.py` 覆盖 5 层分析 + debate + technical
- [ ] `tests/test_vote_engine_matrix.py` 8 种冲突分支边界矩阵
- [ ] `tests/experts/test_formatter_snap.py` 黄金快照
- [ ] `experts/veto_evaluator.py` walk-forward 验证脚本 + OOS 报告
- [ ] skills/stock-technical/SKILL.md 显眼位置标注"o6s_validated: false"

### 🟢 P2 持续

- [ ] macro/ 接入 market briefing
- [ ] VetoPolicy 抽象层
- [ ] 并发测试套件
- [ ] api-reference OpenAPI 同步

---

## 九、最终判断

**这是一份诚实的诊断**。前几轮清理确实把架构债清干净了，但**"测试基础设施"是下一波开销的真正焦点**——当覆盖率从 90% 升到 97% 时，每 1% 都比上一阶段更重要，因为基数大、可信度边际收益递减。当前 **67 failed 被默默接受，是"质量改进"叙事被悄悄削弱的信号**。

**修复 P0 这 5 项（~1 工作日）后，项目即从"形式上严谨"上升到"实质上可信"**。

---

*报告生成于 2026-07-15 · 数据采样基线 `main` @ commit `76964e4`（v1.15.0）· 测试环境 Python 3.14 + pytest 9.0.3*

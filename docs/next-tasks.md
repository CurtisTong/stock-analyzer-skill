# 后续任务（Next Tasks）详细描述与适配场景

> 版本：v2.7 | 更新日期：2026-08-13
> 说明：本目录交接当前待办，按 ROI（收益 / 成本）从高到低排列。每项含**背景与现状**（基于实测）、**详细描述**、**适配场景**（何时做）、**验收标准**。

---

## A. experts/ 纳入 mypy 白名单（新发现 · 近似零成本）

### 背景与现状
- 现状：`experts/`（16 份人设、`registry.py`、`vote_engine.py`、`calibration.py`、`types.py` 等 29 个源文件）**不在**任何 mypy 白名单命令内——CI 只检查 `scripts/` 下 6 脚本 + 11 目录 + 22 个 CLI。
- 2026-08-13 实测：`MYPYPATH=scripts python3 -m mypy --follow-imports=silent --no-incremental --ignore-missing-imports experts/` → **Success: no issues found in 29 source files**（100% 全绿，无需改代码）。

### 关键根因（务必记住的坑）
- mypy **不读 `PYTHONPATH`，只读 `MYPYPATH`**。裸跑 experts/（`PYTHONPATH=scripts`）时 `from data import *` 会把 `data` 解析到**仓库根的 `data/` 目录**（无 `__init__.py` 的 namespace 包，被 git 追踪的 `a_share_holidays.json`/`expert_calibration.json`/`reports/`），而非 `scripts/data/__init__.py`，导致 `get_kline` 等 attr-defined 误报。
- 解法一行：命令加 `MYPYPATH=scripts`。

### 详细描述
1. 在 CI、pre-commit 各新增一条 `mypy experts 层` 命令：
   `MYPYPATH=scripts python3 -m mypy --follow-imports=silent --no-incremental --ignore-missing-imports experts/`
2. 意图是专家系统（人设阈值、投票逻辑、`from common/data/config` 消费）改动不脱管，与 scripts 层白名单形成三件套（主命令 scripts 目录层 / CLI 层 / experts 层）。
3. **不要**把 `experts/` 并入现有主命令——experts 里 `from common import` / `from data import` 与主命令中 `scripts/common/`、`scripts/data/` 同跑会产生 module 双身份或路径歧义，独立命令最稳（与 technical.py/chan.py 双身份同治理逻辑）。

### 适配场景
- 任何专家系统改动：新增/调整 `experts/yaml/*.yaml`、修改 `vote_engine`、`registry`、`calibration` 的导入链。
- 未来的全仓 mypy 治理（见 C）。
- 谁来验收：CI 绿 + pre-commit 本地生效。

### 验收标准
- `MYPYPATH=scripts` 跑 experts/ 仍 29 文件全绿。
- ci.yml 与 pre-commit 各多一条 `mypy experts 层` hook，字样与本文一致。
- 全量测试不回归。

---

## B. 核心目录测试覆盖率 ≥80%（v2.7 #4 · 结构性前置）

### 背景与现状
- v2.7 评估时判定为"低 ROI"暂缓：当前单元测试以业务计算为主，`common/`、`data/`、`fetchers/`、`technical/`、`monitor/`、`portfolio/` 等基建目录的深入路径（网络降级、熔断、缓存过期、多源切换）未达 80%。
- 现状 1592 个测试全绿，覆盖冒烟 + 单元 + 部分集成，但 coverage 数值未量化追踪。

### 详细描述
1. 先做**可测性改造**：把顶层 CLI 的 argv 解析 → 业务函数调用拆到 `business/`、`service` 层（纯函数、可注入 fetcher 桩），CLI 保持薄壳。粗 stdin/正则校验无法覆盖深层降级路径，必须先有可注入入口。
2. 引入可选依赖 `pytest-cov`（测试阶段，不违反运行时零依赖），`--cov=scripts` 量化基线。
3. 按领域分桶追赶：`data`（缓存/归一化/降级）→ `fetchers`（故障转移/CircuitBreaker/RateLimiter）→ `technical`（指标空值/边界）→ `portfolio`（CRUD 边界）→ `monitor`（多通道适配器）。
4. 阈值：核心目录（data/fetchers/common/business/technical/portfolio/monitor/backtest）行覆盖 ≥80%，测试失败则 CI 拦截。

### 适配场景
- 下一次动 CLI 壳、重构数据获取或指标计算之前（改造窗口最省力）。
- 引入 `--cov` 后任何 MR 触发 coverage 不达标告警。
- 不作为硬性门禁强绑：先报告后拦截（允许 90 天缓冲期），避免阻塞日常迭代。

### 验收标准
- `pytest --cov=scripts` 可量化，核心目录 ≥80%。
- 至少 3 条深层降级路径（熔断开启、缓存过期重拉、fetcher 全挂 fallback）有显式断言测试。
- CI 新增 coverage step，报告而非强制（缓冲期内）。

---

## C. 依赖治理（lockfile）——维持不引入，文档化结论

### 背景与现状
- 项目运行时零外部依赖：仅 stdlib + PyYAML 配置加载；可选第三方（akshare/efinance/baostock）运行期自动检测、缺失静默跳过。
- lockfile 在零依赖树场景下 ROI 极低，audit §D 与 review-issues P2-P5 已两次结论一致。

### 详细描述
无动作。仅在出现以下"适配场景"时重新评估。

### 适配场景
- 引入**第三个**运行时必需第三方依赖（当前 PyYAML 是唯一必需项）——此时需要明确 lockfile 方案（`pip-tools` / `uv`）并把 PyYAML 也纳入。
- 或某可选依赖上游发布破坏性版本影响行为（当前网络抓取脚本在 `--run-network` 下联调）。
- 或 CI 环境与本地行为不一致出现（复现性问题）。

### 验收标准
- 不发生不做事：每次复评估在 review-issues 追加一行结论与日期，防止遗忘。

---

## D. CI ↔ pre-commit 手动同步命令的固化（防再次漂移）

### 背景与现状
- `ci.yml` 与 `.pre-commit-config.yaml` 各有 **4 条同源命令**靠手工复刻保持一致：mypy 主命令（212 文件）、mypy CLI 层（22 文件）、版本同步、SKILL 版本一致性。
- 现状已做到 lint 组全对应（silent-excepts/black/ruff + 2 条 mypy + sync-check hooks 均在）。风险仅在**新增/减少检查文件时两边不同步**。

### 详细描述
1. ✅ 已完成（2026-08-13）：新增 `scripts/dev/sync_ci_precommit.py --check`，解析 ci.yml 的 `run:` 与 pre-commit 的 `entry:`，抽取 3 条 mypy 命令（目录层/CLI 层/experts 层）的目标路径列表逐条比对；缺失/漂移 exit 1。
2. CI 新增「CI ↔ pre-commit mypy 白名单同步校验」step，pre-commit 新增同名 hook，双端守护。
3. 已做故障演练验证：单层缺失、路径漂移均正确 exit 1。

### 适配场景
- 任何一次白名单扩围（如任务 A 加 experts/、任务 B 加 --cov），只要手改 ci.yml 就触发。
- 新人接手时无须记忆"两处要一起改"。

### 验收标准
- `sync_ci_precommit.py --check` 通过时两边文件列表逐字一致；不同步时 exit 1 并提示差异。
- 全量测试不回归。

---

## E. 版本号三处同步的扩展（sync-version · 低风险）

### 背景与现状
- `scripts/dev/sync_version.py` 已同步 `pyproject.toml` + `package.json` + README badge 三处版本号。
- SKILL.md frontmatter 的 `version:` 由 `sync_skill_test_versions.py` 独立同步到测试常量。

### 详细描述
随 D 一同做：确认 sync-version 与 sync-skill-test-versions 两份变更在提交时都能被 pre-commit 捕获（前者变更静态文件、后者变更测试常量），避免重复打包 UI。无新增工作，仅验收。

### 适配场景
- 发版流程（SemVer bump）时。

### 验收标准
- 一次 bump 版本号后 `git status` 恰好出现预期三处同步 + 测试常量同步，无遗漏。

---

## F. 网络/真实行情域冒烟（列表外，需外部环境）

### 背景与现状
- 网络相关能力（真实行情抓取、降级链路、`--run-network` 全量）依赖外部 API，本地冒烟只覆盖离线部分。
- watchdog 600s 超时、CircuitBreaker、RateLimiter 的集成行为强依赖真实网络时延。

### 详细描述
给出运行步骤（非自动任务）：
1. `python3 -m pytest tests/ --run-network -x -q`（全量含网络）。
2. `./tests/smoke_test.sh`（端到端冒烟，验证 install.sh symlink 全链路）。
3. `python3 scripts/monitor.py`（数据源健康检查 + 缓存管理）。

### 适配场景
- 每次发版前、或网络域代码（fetchers/ 27 模块）有结构性改动时。
- 数据源上游（腾讯/东方财富/新浪）口径调整时。

### 验收标准
- 三条命令全部通过；若有降级路径告警，需明确是"预期降级"还是"新回归"。

---

## G. 观看清单（watch · 暂缓）

| 项 | 触发条件 | 说明 |
| --- | --- | --- |
| akshare 挂起的 watchdog 超时 | `STOCK_SCREENER_DEADLINE` 默认 600s 用户反馈不够，或有新挂起场景 | 已接入，仅需按反馈调参 |
| 根目录 `data/` namespace 遮蔽 | 任何向仓库根新增无 `__init__.py` 目录（如未来 `reports/` 扩展） | 与任务 A 强相关；改结构前后跑一次 mypy expert 层 |
| experts 人设扩表 | 从 16 份继续扩 | 同步更新 experts/yaml + registry + 本表 |

---

## 优先级总结

| 优先级 | 任务 | 预估成本 | 决策 |
| --- | --- | --- | --- |
| P0 | A experts/ mypy 入库 | 0.5h | ✅ 已完成（2026-08-13，29 文件全绿 + MYPYPATH 坑已文档化） |
| P1 | D CI↔pre-commit 同步自校验 | 2-4h | ✅ 已完成（2026-08-13，sync_ci_precommit.py --check 双端挂载） |
| P1 | B coverage ≥80%（结构性前置） | 分阶段 | 🚧 进行中（2026-08-13：CI 新增两 coverage step——全仓 .coveragerc 阈值 21% + 核心目录报告；补 technical 62 条测试 75.1%→89.9% 达标；核心 10 目录基线 55.3%） |
| P2 | E 版本同步验收 | 0.5h | 随 D 顺带 |
| P2 | F 网络域冒烟 | 0.5h | 发版前例行 |
| P3 | C lockfile | — | 维持不引入，触发条件见上 |
| — | G watch | — | 触发式跟进 |
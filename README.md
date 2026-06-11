# stock-analyzer-skill

> **A 股投资的 12 个专业分析师，常驻你的 Claude Code。**
> 五层分析框架 + 8 人专家圆桌 + 多数据源自动故障转移，零配置即可使用。

![Version](https://img.shields.io/badge/version-1.3.2-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Zero Deps](https://img.shields.io/badge/python_deps-stdlib_only-lightgrey)

---

## 这是什么？

一个 Claude Code 插件包，把 12 个 A 股分析能力封装成 `/xxx` 斜杠命令。
不写代码也能用——**说一句 `/stock 贵州茅台`，就能拿到 5 层专业分析**。

**适合谁用**：

- 📈 散户/个人投资者：日常看行情、复盘、盯持仓
- 🎓 投资学习者：跟着 8 位投资专家的人设理解多空博弈
- 🛠 量化爱好者：用脚本能力二次开发、组合到自己的工作流

**不适合谁用**：

- ❌ 寻找"代码选股圣杯"的自动化交易者（本包不保证收益）
- ❌ 需要实时 tick 级行情的 HFT 场景（数据源最小粒度为分钟级）

---

## 🚀 5 分钟上手

### ① 安装插件（任选一种）

```bash
# 推荐：Claude Code Plugin
claude plugins marketplace add . && claude plugins install stock-analyzer
```

### ② 初始化股票池（一次即可）

```text
/stock-init
```

> **零配置可用**：内置预置默认股票池，无需 token 即可使用。联网时自动获取最新数据，失败自动 fallback。

### ③ 跑第一个命令

```text
/stock sh600989 quick    →  3 分钟快评（基本面+估值+技术面）
/stock sh600989         →  完整五层分析
/stock sh600989 debate  →  8 人专家圆桌多空辩论
```

---

## 🎯 4 个典型场景

不知道从哪个命令开始？挑一个最贴近你当前问题的：

| 场景 | 命令链 | 你会得到什么 |
| --- | --- | --- |
| 🥇 **自上而下选股** | `/market` → `/sector 资源` → `/screener --strategy quality_value` → `/stock` | 从市场状态到具体标的的完整决策链 |
| 🥈 **诊断持仓** | `/portfolio` → `/stock 持仓股 debate` | 健康度 + 风险预警 + 多空辩论结论 |
| 🥉 **挖掘板块机会** | `/market` → `/sector 医药 compare` | 板块轮动位置 + 核心标的横向对比 |
| 🏅 **深度研究个股** | `/stock 贵州茅台 debate` → `/financial-analyst` → `/technical` | 八方观点 + 财务建模 + 技术买卖点 |

> 🌟 **特色功能**：`/stock <代码> debate` 召集 **8 位投资专家**（巴菲特/林奇/索罗斯/段永平/徐翔/赵老哥/炒股养家/作手新一）从各自框架独立打分，由 `decide.md` 汇总投票，是本包最独特的卖点。详见 [experts/README.md](experts/README.md)。
>
> 💡 12 个 skill 的完整衔接流程见 [`workflow.md`](workflow.md)。

---

## 📋 12 个 Skill 速查

| 类别 | Skill | 命令 | 解决什么问题 |
| --- | --- | --- | --- |
| **决策** | [stock](skills/stock/SKILL.md) | `/stock <代码>` | 单股五层分析（基本面/估值/技术/板块/风险收益比） |
| **🌟 专家** | [stock-debate](skills/stock/SKILL.md) | `/stock <代码> debate` | **8 位投资专家多空圆桌辩论**（长线 4 + 短线 4） |
| **环境** | [market](skills/market/SKILL.md) | `/market` | 大盘快评/完整复盘/盘中分时 |
| **环境** | [sector](skills/sector/SKILL.md) | `/sector <板块>` | 板块全景/标的对比/板块内筛选 |
| **选股** | [screener](skills/screener/SKILL.md) | `/screener` | 5 种策略 × 5 因子维度批量选股 |
| **组合** | [portfolio](skills/portfolio/SKILL.md) | `/portfolio` | 持仓健康/调仓再平衡/对比 |
| **组合** | [monitor](skills/monitor/SKILL.md) | `/monitor start` | 盘中异动监控 + Bark/企微/钉钉推送 |
| **技术** | [technical](skills/technical/SKILL.md) | `/technical <代码>` | 均线/MACD/KDJ/BOLL/缠论/本土战法 |
| **验证** | [backtest](skills/backtest/SKILL.md) | `/backtest` | 5 种策略历史胜率+收益验证 |
| **数据** | [stock-init](skills/stock-init/SKILL.md) | `/stock-init` | 初始化/刷新股票池（零配置） |
| **研究** | [financial-analyst](skills/financial-analyst/SKILL.md) | `/financial-analyst <任务>` | 财务建模/预测/场景分析 |
| **研究** | [investment-researcher](skills/investment-researcher/SKILL.md) | `/investment-researcher <任务>` | 市场研究/尽调/估值 |
| **辅助** | [help](skills/help/SKILL.md) | `/help` | 显示所有 skills 和使用说明 |

**股票代码格式**：`sh600519`（沪）/ `sz000858`（深）/ `600519`（自动推断）/ `贵州茅台`（按名称模糊匹配）

---

## 📦 安装

### 方式一：Claude Code Plugin（推荐）

```bash
# 在项目根目录执行一行命令
claude plugins marketplace add . && claude plugins install stock-analyzer
```

✅ 自动注册到 Claude Code，重启后立即可用。

### 方式二：npm 全局安装

```bash
npm install -g stock-analyzer-skill
```

### 方式三：手动软链（传统）

```bash
git clone <repo> && cd stock-analyzer-skill
./install.sh   # 在 ~/.claude/skills/ 下创建 symlink
```

> ⚠️ 手动方式需重启 Claude Code 生效。

### 验证安装

```bash
claude skills list | grep stock     # 看到 12 个 stock-* 即成功
/help                                # 在 Claude Code 内查看命令清单
```

---

## 🏗️ 项目架构（开发者视角）

```text
scripts/
├── business/      # 业务逻辑层（stock_analysis / screening_service）
├── common/        # 基础设施（HTTP、缓存、熔断器、异常体系）
├── config/        # 外部化配置（YAML：评分/数据源/行业阈值）
├── data/          # 数据类型 + 磁盘缓存 + 股票池
├── fetchers/      # 9+ 数据源适配器（腾讯/东财/新浪/雪球/同花顺/AkShare/…）
├── strategies/    # 5 种选股策略 + 因子库
├── technical/     # 技术指标（MACD/KDJ/BOLL/RSI/均线/缠论/本土战法）
├── monitor/       # 实时监控 + 多通道通知
├── portfolio/     # 持仓管理
└── *.py           # 顶层 CLI 入口（SKILL.md 直接调用）
```

**核心特性**：

- 🪶 **零 Python 外部依赖**：仅 `urllib` + `json` + `pathlib` + `yaml`
- 🔁 **多数据源故障转移**：单个 API 挂掉自动切换到下一家（集成熔断器）
- 📦 **三层架构**：API 层 → 业务层 → 数据层，职责清晰易扩展
- ⚙️ **配置外部化**：行业阈值/评分权重/数据端点全部 YAML，零改代码调参
- 🧪 **测试覆盖**：单元测试 + 元数据测试 + 端到端冒烟测试

详见 [开发者指南](docs/developer-guide.md) 和 [产品架构](docs/product-architecture.md)。

---

## 📚 文档导航

| 你的角色 | 推荐先读 | 之后 |
| --- | --- | --- |
| **新用户** | [快速入门](docs/quick-start.md) | [使用者指南](docs/user-guide.md) |
| **投资者** | [投资方法论](methodology.md) | [8 人专家档案库](experts/README.md) |
| **二次开发者** | [开发者指南](docs/developer-guide.md) | [API 参考](docs/api-reference.md) |
| **贡献者** | [贡献指南](CONTRIBUTING.md) | [变更日志](CHANGELOG.md) |

---

## ❓ 常见问题

**Q：股票池没初始化会怎样？**
使用 `/stock`、`/screener`、`/sector` 时如果股票池未初始化，系统会自动触发或提示先跑 `/stock-init`。

**Q：可以离线使用吗？**
可以。`/stock-init default` 走预置数据，零网络请求。联网后再 `/stock-init force` 刷新。

**Q：数据源挂了怎么办？**
内置熔断器 + 多源故障转移：腾讯 → 东财 → 新浪 → 雪球 → 同花顺 → AkShare → …，单源失败不影响整体。

**Q：分析结果能直接拿去交易吗？**
❌ 不能。所有输出仅供研究框架参考，不构成投资建议。投资有风险，决策需谨慎。

**Q：如何自定义持仓？**

```bash
cp scripts/data/portfolio_example.json scripts/data/portfolio.json
# 编辑 portfolio.json 的 codes 字段
/portfolio    # 自动读取 portfolio.json
```

---

## ⚠️ 已知限制

- 实时数据依赖外部 API 稳定性，变更时改 `scripts/fetchers/` 端点即可
- 预置股票池为静态快照，全市场最新数据需联网刷新
- 多因子权重基于经验设定，未经大规模历史回测验证
- 资金面数据（融资融券/股东户数）每日更新，受交易所披露节奏限制

---

## 🤝 贡献与反馈

提交规范详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
Issue / PR / 建议 → [GitHub Repo](https://github.com/CurtisTong/stock-analyzer-skill)。

---

## 📜 许可

MIT License © curtis

---

**版本**：v1.3.2（2026-06-10） · **最后更新**：见 [CHANGELOG.md](CHANGELOG.md)

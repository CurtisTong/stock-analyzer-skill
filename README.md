# stock-analyzer-skill

独立的股票分析 skill 包，提供 8 个股票分析相关 skill + 完整方法论 + 工具脚本。当前同时保留 Codex 可发现的 `.agents/skills/` 和 Claude Code 可安装的 `.claude/skills/` 两套入口。

## 包含的 Skill

| Skill | 命令 | 用途 | 模式 |
|-------|------|------|------|
| **stock** | `/stock <代码或名称> [quick\|full\|debate]` | 单股分析 | 五层框架 + 8人专家圆桌 |
| **market** | `/market [full\|quick\|intraday]` | 大盘复盘 | 指数+板块+风格+资金 |
| **sector** | `/sector <板块> [overview\|compare\|stock]` | 板块分析 | 标的对比+多空博弈 |
| **portfolio** | `/portfolio [health\|rebalance\|compare]` | 持仓健康检查 | 涨跌+支撑+风险预警 |
| **screener** | `/screener [--sector 板块] [--strategy 策略]` | 选股策略系统 | 多因子筛选+硬过滤+候选池 |
| **technical** | `/technical <代码> [quick\|full]` | 纯技术分析 | 均线+MACD/KDJ/BOLL+缠论+本土战法 |
| **financial-analyst** | `/financial-analyst <任务>` | 财务分析 agent | 建模+预测+场景分析 |
| **investment-researcher** | `/investment-researcher <任务>` | 投资研究 agent | 市场研究+尽调+估值 |

## 目录结构

```
stock-analyzer-skill/
├── README.md                       # 本文件
├── workflow.md                     # 8 个 skill 的协作流程
├── methodology.md                  # 完整投资方法论（5层框架、8人圆桌、凯利公式等）
├── install.sh                      # 一键注册到 ~/.claude/skills/
├── .agents/skills/                 # Codex workspace skill 源
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── screener/SKILL.md
│   ├── technical/SKILL.md
│   ├── financial-analyst/SKILL.md
│   └── investment-researcher/SKILL.md
├── .claude/skills/                 # Claude Code skill 源（与 .agents 同步）
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── screener/SKILL.md
│   ├── technical/SKILL.md
│   ├── financial-analyst/SKILL.md
│   └── investment-researcher/SKILL.md
├── scripts/                        # 工具脚本（Python stdlib only）
│   ├── common.py                   # 编码转换、字段映射、HTTP
│   ├── quote.py                    # 腾讯实时行情
│   ├── finance.py                  # 东财财务数据
│   ├── kline.py                    # 新浪 K线
│   ├── announcements.py            # 东财公告/研报
│   ├── screener.py                 # A股多因子选股器
│   ├── technical.py                # 纯技术分析
│   ├── classifier.py               # 个股类型分类
│   ├── chan.py                     # 缠论结构
│   └── patterns_local.py           # A股本土战法形态
├── data/                           # 静态参考数据
│   ├── sector_etf.csv              # 板块 ETF 清单
│   ├── sector_stocks.json          # 板块核心标的库
│   └── portfolio_example.json      # 持仓配置示例
└── tests/
    └── smoke_test.sh               # 端到端冒烟测试
```

## 安装

```bash
cd ~/Documents/curtis/stock-analyzer-skill
./install.sh
```

`install.sh` 会在 `~/.claude/skills/` 下创建 8 个扁平 symlink，指向本包的 `.claude/skills/` 目录。重新启动 Claude Code 即可识别。

Codex 会从 workspace 的 `.agents/skills/` 读取 skill；如需修改 skill，保持 `.agents/skills/` 与 `.claude/skills/` 内容一致。

## 验证

```bash
./tests/smoke_test.sh
```

应输出 `N 通过, 0 失败`。

## 数据源

- **腾讯** `qt.gtimg.cn`：实时行情、PE/PB/市值（GBK 编码，scripts/ 自动处理）
- **东方财富** `emweb.securities.eastmoney.com`：财务摘要（type=0/1/2/3/4）
- **新浪** `money.finance.sina.com.cn`：K线（5/15/30/240 分钟）
- **东方财富** `np-anotice-stock.eastmoney.com`：`company 公告`
- **东方财富** `reportapi.eastmoney.com`：券商研报

所有数据 API 在国内直连，无须代理。

## 使用示例

### 快速个股分析
```
/stock sh600989
```
返回：基本面+估值+技术面 3 分钟快评。

### 大盘快评
```
/market quick
```
返回：主要指数涨跌+最强最弱板块+一句话结论。

### 持仓健康检查
```
/portfolio
```
读取 `data/portfolio_example.json`（可复制为 `portfolio.json` 自定义持仓）。

### 多因子选股
```
/screener --sector 资源 --strategy quality_value --top 5
```
返回：硬过滤结果 + 多因子评分 + 候选池 + 跟踪条件。

### 技术面确认
```
/technical sh600989 --quick
```
返回：趋势、量价、支撑阻力、技术触发和失效条件。

### 完整五层 + 专家辩论
```
/stock sh600989 debate
```
返回：五层分析 + 8人圆桌多空辩论 + 最终折中方案。

## 自定义持仓

```bash
cp data/portfolio_example.json data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
```

`/portfolio` 命令默认读取 `data/portfolio.json`（或 `data/portfolio_example.json` 作为回退）。

## 方法论

完整投资方法论见 [`methodology.md`](methodology.md)：

- §1 数据源
- §2 五层分析框架（ROE/PE/PEG/技术面/风险收益比）
- §3 8 人专家圆桌（巴菲特/林奇/索罗斯/段永平 + 徐翔/赵老哥/炒股养家/作手新一）
- §4 仓位管理（凯利公式 + 仓位分级）
- §5 决策流程
- §6 选股策略系统
- §7 数据获取工具详解
- §8 快捷启动命令
- §9 关键经验

8 个 skill 的衔接流程见 [`workflow.md`](workflow.md)：市场 → 板块 → 选股 → 个股 → 技术 → 组合，也支持持仓再平衡和深度研究两条工作流。

## 解耦特性

✅ **零项目依赖**：不引用任何业务项目内文件（`src/`、`data_provider/`、`AGENTS.md` 等）
✅ **零外部 Python 库**：只用 stdlib（`urllib` + `json` + `pathlib`）
✅ **单源真理**：方法论、数据、脚本各自集中在一处
✅ **可移植**：可打包为 git 仓库或 npm 包分发

## 贡献与 Git 规范

提交信息、分支命名、Tag 版本号等约定详见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
一句话：标题与正文使用中文，type 沿用 Conventional Commits（`feat` / `fix` / `docs` / `refactor` / `chore` 等），分支统一 `<type>/<短描述>` 格式。

## 卸载

```bash
rm -f ~/.claude/skills/stock ~/.claude/skills/market ~/.claude/skills/sector ~/.claude/skills/portfolio ~/.claude/skills/screener ~/.claude/skills/technical ~/.claude/skills/financial-analyst ~/.claude/skills/investment-researcher
```

## 已知限制

- 实时数据依赖外部 API 端点稳定性；如遇变更，修改 `scripts/common.py` 中端点即可
- portfolio skill 默认读取 `data/portfolio_example.json` 作为示例，实际使用前需自定义
- 部分 API（如东财公告）可能有反爬限制，已加超时和重试

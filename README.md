# stock-analyzer-skill

独立的 Claude Code skill 包，提供 6 个股票分析相关 skill + 完整方法论 + 工具脚本。

## 包含的 Skill

| Skill | 命令 | 用途 | 模式 |
|-------|------|------|------|
| **stock** | `/stock <代码或名称> [quick\|full\|debate]` | 单股分析 | 五层框架 + 8人专家圆桌 |
| **market** | `/market [full\|quick\|intraday]` | 大盘复盘 | 指数+板块+风格+资金 |
| **sector** | `/sector <板块> [overview\|compare\|stock]` | 板块分析 | 标的对比+多空博弈 |
| **portfolio** | `/portfolio [health\|rebalance\|compare]` | 持仓健康检查 | 涨跌+支撑+风险预警 |
| **financial-analyst** | `/financial-analyst <任务>` | 财务分析 agent | 建模+预测+场景分析 |
| **investment-researcher** | `/investment-researcher <任务>` | 投资研究 agent | 市场研究+尽调+估值 |

## 目录结构

```
stock-analyzer-skill/
├── README.md                       # 本文件
├── methodology.md                  # 完整投资方法论（5层框架、8人圆桌、凯利公式等）
├── install.sh                      # 一键注册到 ~/.claude/skills/
├── .claude/skills/                 # 6 个 skill 源
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── financial-analyst/SKILL.md
│   └── investment-researcher/SKILL.md
├── scripts/                        # 工具脚本（Python stdlib only）
│   ├── common.py                   # 编码转换、字段映射、HTTP
│   ├── quote.py                    # 腾讯实时行情
│   ├── finance.py                  # 东财财务数据
│   ├── kline.py                    # 新浪 K线
│   └── announcements.py            # 东财公告/研报
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

`install.sh` 会在 `~/.claude/skills/stock-analyzer/` 下创建 6 个 symlink，指向本包的 `.claude/skills/` 目录。重新启动 Claude Code 即可识别。

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
- §6 数据获取工具详解
- §7 快捷启动命令
- §8 关键经验

## 解耦特性

✅ **零项目依赖**：不引用任何项目内文件（`src/`、`data_provider/`、`AGENTS.md` 等）
✅ **零外部 Python 库**：只用 stdlib（`urllib` + `json` + `pathlib`）
✅ **单源真理**：方法论、数据、脚本各自集中在一处
✅ **可移植**：可打包为 git 仓库或 npm 包分发

## 卸载

```bash
rm -rf ~/.claude/skills/stock-analyzer
```

## 已知限制

- 实时数据依赖外部 API 端点稳定性；如遇变更，修改 `scripts/common.py` 中端点即可
- portfolio skill 默认读取 `data/portfolio_example.json` 作为示例，实际使用前需自定义
- 部分 API（如东财公告）可能有反爬限制，已加超时和重试

# 项目使用说明文档实现计划

> **致代理工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用 checkbox（`- [ ]`）语法进行跟踪。

**目标：** 为开发者、使用者、投资分析师编写 5 个文档（quick-start.md、user-guide.md、developer-guide.md、methodology.md、api-reference.md）

**架构：** 多文档拆分，按职责组织：快速入门、使用者指南、开发者指南、方法论详解、API 参考。每个文档独立完整，可单独阅读。

**技术栈：** Markdown 文档

---

## 文件结构

```
docs/
├── quick-start.md          # 快速入门（5分钟）
├── user-guide.md           # 使用者指南
├── developer-guide.md      # 开发者指南
├── methodology.md          # 投资方法论
└── api-reference.md        # API 参考
```

---

## 任务 1：创建 docs 目录结构

**文件：**

- 创建：`docs/` 目录

- [ ] **步骤 1：创建 docs 目录**

```bash
mkdir -p docs
```

- [ ] **步骤 2：验证目录创建**

```bash
ls -la docs/
```

预期：目录存在，无报错
失败：目录不存在或权限错误

- [ ] **步骤 3：提交**

```bash
git add docs/
git commit -m "docs: 创建 docs 目录结构"
```

---

## 任务 2：编写 quick-start.md

**文件：**

- 创建：`docs/quick-start.md`

- [ ] **步骤 1：编写快速入门文档**

````markdown
# 快速入门

5 分钟内跑通第一个技能。

## 前置条件

- Python 3.x
- Claude Code 环境

## 安装

```bash
cd ~/Documents/curtis/stock-analyzer-skill
./install.sh
```
````

`install.sh` 会在 `~/.claude/skills/` 下创建 8 个扁平 symlink，指向本包的 `.claude/skills/` 目录。

重启 Claude Code 即可识别。

## 验证安装

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

## 第一个命令

```
/stock sh600989 quick
```

返回：基本面+估值+技术面 3 分钟快评。

## 常见问题

### 权限问题

```bash
chmod +x install.sh
```

### Python 版本问题

确认 python3 可用：

```bash
python3 --version
```

### 网络问题

确认能访问国内 API：

```bash
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8 | head -1
```

应返回包含"宝丰能源"的行情数据。

````

- [ ] **步骤 2：验证文档内容**

```bash
head -50 docs/quick-start.md
````

预期：文档包含前置条件、安装、验证、第一个命令、常见问题
失败：文件不存在或内容缺失

- [ ] **步骤 3：提交**

```bash
git add docs/quick-start.md
git commit -m "docs: 添加快速入门文档"
```

---

## 任务 3：编写 user-guide.md

**文件：**

- 创建：`docs/user-guide.md`

- [ ] **步骤 1：编写使用者指南文档**

```markdown
# 使用者指南

掌握所有 8 个技能的用法。

## 技能概览

| Skill                 | 命令                                          | 用途           | 模式                             |
| --------------------- | --------------------------------------------- | -------------- | -------------------------------- |
| stock                 | `/stock <代码或名称> [quick\|full\|debate]`   | 单股分析       | 五层框架 + 8人专家圆桌           |
| market                | `/market [full\|quick\|intraday]`             | 大盘复盘       | 指数+板块+风格+资金              |
| sector                | `/sector <板块> [overview\|compare\|stock]`   | 板块分析       | 标的对比+多空博弈                |
| portfolio             | `/portfolio [health\|rebalance\|compare]`     | 持仓健康检查   | 涨跌+支撑+风险预警               |
| screener              | `/screener [--sector 板块] [--strategy 策略]` | 选股策略系统   | 多因子筛选+硬过滤+候选池         |
| technical             | `/technical <代码> [quick\|full]`             | 纯技术分析     | 均线+MACD/KDJ/BOLL+缠论+本土战法 |
| financial-analyst     | `/financial-analyst <任务>`                   | 财务分析 agent | 建模+预测+场景分析               |
| investment-researcher | `/investment-researcher <任务>`               | 投资研究 agent | 市场研究+尽调+估值               |

## 单股分析 (/stock)

命令格式：`/stock <代码或名称> [quick|full|debate]`

### quick 模式（3 分钟快评）
```

/stock sh600989 quick

```

返回：基本面+估值+技术面快速评估。

### full 模式（五层分析）

```

/stock sh600989 full

```

返回：五层分析（基本面/估值/技术面/板块/风险收益比）。

### debate 模式（专家辩论）

```

/stock sh600989 debate

```

返回：五层分析 + 8人圆桌多空辩论 + 最终折中方案。

## 大盘复盘 (/market)

命令格式：`/market [full|quick|intraday]`

### full 模式（完整复盘）

```

/market full

```

返回：主要指数+板块+风格+资金流向完整分析。

### quick 模式（快评）

```

/market quick

```

返回：主要指数涨跌+最强最弱板块+一句话结论。

### intraday 模式（盘中分时）

```

/market intraday

```

返回：盘中分时复盘。

## 板块分析 (/sector)

命令格式：`/sector <板块> [overview|compare|stock]`

### overview 模式（板块全景）

```

/sector 资源 overview

```

返回：板块全景分析。

### compare 模式（核心标的对比）

```

/sector 资源 compare

```

返回：核心标的横向对比。

### stock 模式（板块内个股筛选）

```

/sector 资源 stock

````

返回：板块内个股筛选。

## 持仓管理 (/portfolio)

命令格式：`/portfolio [health|rebalance|compare]`

### 自定义持仓

```bash
cp data/portfolio_example.json data/portfolio.json
# 编辑 portfolio.json，修改 codes 字段
````

### health 模式（健康检查）

```
/portfolio health
```

返回：持仓实时涨跌、仓位/板块集中度、风险预警。

### rebalance 模式（调仓再平衡）

```
/portfolio rebalance
```

返回：调仓建议、再平衡方案。

### compare 模式（持仓对比）

```
/portfolio compare
```

返回：持仓标的对比分析。

## 多因子选股 (/screener)

命令格式：`/screener [--sector 板块] [--strategy 策略]`

### 5 种策略

| 策略            | 市场环境          | 说明     |
| --------------- | ----------------- | -------- |
| balanced        | 震荡/方向不明     | 均衡精选 |
| quality_value   | 价值修复/防守     | 质量价值 |
| growth_momentum | 进攻行情/主线题材 | 成长动量 |
| defensive       | 缩量弱市/避险     | 防守低波 |
| turning_point   | 超跌修复/拐点     | 拐点修复 |

### 参数说明

- `--sector <板块>`：板块名称
- `--strategy <策略>`：策略名称
- `--top <N>`：返回前 N 个候选
- `--codes <代码>`：自定义股票池（逗号分隔）
- `--exclude-loss`：剔除亏损股
- `--json`：JSON 格式输出

### 使用示例

```
/screener --sector 资源 --strategy quality_value --top 5
```

返回：硬过滤结果 + 多因子评分 + 候选池 + 跟踪条件。

## 纯技术分析 (/technical)

命令格式：`/technical <代码> [quick|full]`

### quick 模式

```
/technical sh600989 quick
```

返回：趋势、量价、支撑阻力、技术触发和失效条件。

### full 模式

```
/technical sh600989 full
```

返回：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）。

## 财务分析 (/financial-analyst)

命令格式：`/financial-analyst <任务>`

用途：建模、预测、场景分析。

```
/financial-analyst 分析宝丰能源的财务质量
```

## 投资研究 (/investment-researcher)

命令格式：`/investment-researcher <任务>`

用途：市场研究、尽调、估值。

```
/investment-researcher 宝丰能源投资价值研究
```

## 组合使用场景

### 自上而下选股

`market` → `sector` → `screener` → `stock` → `technical` → `portfolio`

1. `market` 给出市场状态：进攻、均衡、防守
2. `sector` 找强弱板块和主题位置
3. `screener` 生成候选池和剔除原因
4. `stock` 对候选股做五层分析
5. `technical` 给买入触发、失效位、支撑阻力
6. `portfolio` 决定是否纳入持仓、替换谁、仓位多少

### 自下而上验证

`stock` → `financial-analyst` → `sector` → `technical` → `portfolio`

适合用户已经给定个股。先判断公司质量和估值，再看板块是否配合，最后确认技术触发。

### 持仓再平衡

`portfolio` → `market` → `technical` → `screener` → `stock`

1. 先找组合风险，再确认市场风格
2. 对弱势持仓跑 `technical` 判破位
3. 用 `screener` 找替代候选，再用 `stock` 精筛

### 深度研究报告

`investment-researcher` 作为总控，按需调用：

- `market`：宏观市场和风格
- `sector`：行业景气和竞争格局
- `financial-analyst`：财务质量、预测、场景
- `stock`：投资结论和风险收益比
- `technical`：交易窗口和失效条件

## 常见问题

### 数据源是否稳定？

数据源依赖外部 API 端点稳定性。如遇变更，修改 `scripts/common.py` 中端点即可。

### 如何处理 API 变更？

1. 检查 `scripts/common.py` 中的端点配置
2. 更新端点 URL
3. 验证数据格式是否变化
4. 更新字段映射

### 如何自定义选股策略？

当前策略权重在 `scripts/screener.py` 中定义。如需自定义：

1. 修改策略权重配置
2. 添加新因子定义
3. 更新评分逻辑

````

- [ ] **步骤 2：验证文档内容**

```bash
grep -c "##" docs/user-guide.md
````

预期：包含 10+ 个二级标题
失败：标题数量不足或文件不存在

- [ ] **步骤 3：提交**

```bash
git add docs/user-guide.md
git commit -m "docs: 添加使用者指南文档"
```

---

## 任务 4：编写 developer-guide.md

**文件：**

- 创建：`docs/developer-guide.md`

- [ ] **步骤 1：编写开发者指南文档**

```markdown
# 开发者指南

理解项目结构并能扩展开发。

## 项目结构详解
```

stock-analyzer-skill/
├── README.md # 项目说明
├── workflow.md # 8 个 skill 的协作流程
├── methodology.md # 完整投资方法论
├── install.sh # 一键注册到 ~/.claude/skills/
├── .agents/skills/ # Codex workspace skill 源
│ ├── stock/SKILL.md
│ ├── market/SKILL.md
│ ├── sector/SKILL.md
│ ├── portfolio/SKILL.md
│ ├── screener/SKILL.md
│ ├── technical/SKILL.md
│ ├── financial-analyst/SKILL.md
│ └── investment-researcher/SKILL.md
├── .claude/skills/ # Claude Code skill 源（与 .agents 同步）
├── scripts/ # 工具脚本（Python stdlib only）
│ ├── common.py # 编码转换、字段映射、HTTP
│ ├── quote.py # 腾讯实时行情
│ ├── finance.py # 东财财务数据
│ ├── kline.py # 新浪 K线
│ ├── announcements.py # 东财公告/研报
│ ├── screener.py # A股多因子选股器
│ ├── technical.py # 纯技术分析
│ ├── classifier.py # 个股类型分类
│ ├── chan.py # 缠论结构
│ └── patterns_local.py # A股本土战法形态
├── data/ # 静态参考数据
│ ├── sector_etf.csv # 板块 ETF 清单
│ ├── sector_stocks.json # 板块核心标的库
│ └── portfolio_example.json # 持仓配置示例
└── tests/
└── smoke_test.sh # 端到端冒烟测试

````

## 脚本模块说明

### common.py - 编码转换、字段映射、HTTP 工具

提供通用工具函数：
- GBK 编码转换
- HTTP 请求封装
- 字段映射配置

### quote.py - 腾讯实时行情

从 `qt.gtimg.cn` 获取实时行情数据。

用法：
```bash
python3 scripts/quote.py sh600989
````

### finance.py - 东财财务数据

从 `emweb.securities.eastmoney.com` 获取财务摘要。

用法：

```bash
python3 scripts/finance.py SH600989
```

### kline.py - 新浪 K 线

从 `money.finance.sina.com.cn` 获取 K 线数据。

用法：

```bash
python3 scripts/kline.py sh600989 240 30
```

### screener.py - 多因子选股器

A 股多因子选股系统。

用法：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析引擎

纯技术分析，包含均线、MACD、KDJ、BOLL、缠论、本土战法。

用法：

```bash
python3 scripts/technical.py sh600989 full
```

### chan.py - 缠论结构

缠论分析：笔-线段-中枢-买卖点-背驰。

### patterns_local.py - A 股本土战法形态

本土战法形态识别：三阴一阳、老鸭头、美人肩等。

### classifier.py - 个股类型分类

A 股个股类型分类器。

## 数据源架构

### 腾讯 qt.gtimg.cn

- 用途：实时行情、PE/PB/市值
- 编码：GBK（需 iconv 转换）
- 限制：批量查询最多约 15 只/次

### 东方财富 emweb.securities.eastmoney.com

- 用途：财务摘要
- 格式：JSON
- 参数：code 必须大写 SH/SZ

### 新浪 money.finance.sina.com.cn

- 用途：K 线数据
- 周期：5/15/30/240 分钟
- 格式：JSON

### 东方财富 np-anotice-stock.eastmoney.com

- 用途：公告查询

### 东方财富 reportapi.eastmoney.com

- 用途：券商研报

## Skill 注册机制

### .claude/skills/ vs .agents/skills/

- `.claude/skills/`：Claude Code 读取的 skill 源
- `.agents/skills/`：Codex workspace 读取的 skill 源
- 两者内容需保持一致

### symlink 机制

`install.sh` 创建扁平 symlink 到 `~/.claude/skills/`：

```bash
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/stock ~/.claude/skills/stock
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/market ~/.claude/skills/market
# ... 共 8 个
```

### SKILL.md 格式

每个 skill 的 `SKILL.md` 包含：

- name：技能名称
- description：触发条件和用途
- 指令：详细的使用说明

## 扩展开发指南

### 添加新数据源

1. 在 `scripts/` 下创建新模块
2. 遵循 `common.py` 的 HTTP 工具模式
3. 处理编码和错误
4. 更新 `api-reference.md`

### 添加新因子

1. 在 `screener.py` 中添加因子定义
2. 更新权重配置
3. 添加评分逻辑
4. 更新 `methodology.md`

### 添加新技能

1. 创建 `.claude/skills/<name>/SKILL.md`
2. 更新 `install.sh`
3. 同步到 `.agents/skills/`
4. 更新 `user-guide.md`

## 测试与验证

### 端到端冒烟测试

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

### 手动测试流程

1. 运行单个脚本验证数据获取
2. 运行 skill 命令验证功能
3. 检查输出格式和内容

## 贡献流程

### Git 规范

- 提交信息：Conventional Commits（`feat` / `fix` / `docs` / `refactor` / `chore`）
- 标题与正文使用中文
- 分支命名：`<type>/<短描述>`

### 示例

```bash
git commit -m "feat: 添加新数据源"
git commit -m "fix: 修复编码问题"
git commit -m "docs: 更新 API 文档"
```

````

- [ ] **步骤 2：验证文档内容**

```bash
grep -c "##" docs/developer-guide.md
````

预期：包含 10+ 个二级标题
失败：标题数量不足或文件不存在

- [ ] **步骤 3：提交**

```bash
git add docs/developer-guide.md
git commit -m "docs: 添加开发者指南文档"
```

---

## 任务 5：编写 methodology.md

**文件：**

- 创建：`docs/methodology.md`

- [ ] **步骤 1：编写方法论文档**

```markdown
# 投资方法论

完整投资分析框架，面向投资分析师。

## 数据源详解

### 腾讯实时行情字段映射

| 字段位 | 含义       | 示例        |
| ------ | ---------- | ----------- |
| 1      | 市场代码   | 1=沪, 51=深 |
| 2      | 代码       | 600989      |
| 3      | 名称       | 宝丰能源    |
| 4      | 当前价     | 24.59       |
| 5      | 昨收       | 24.92       |
| 33     | 涨跌幅%    | -0.49       |
| 37     | 成交量(手) | 547985      |
| 38     | 成交额(万) | 134521      |
| 39     | 换手率%    | 0.75        |
| 40     | PE(动)     | 14.34       |

### 东财财务数据字段映射

| 字段               | 含义            | 示例值 |
| ------------------ | --------------- | ------ |
| EPSJB              | 每股收益        | 0.5    |
| ROEJQ              | ROE(加权)       | 7.28   |
| TOTALOPERATEREVETZ | 营收同比增长%   | 22.9   |
| PARENTNETPROFITTZ  | 净利润同比增长% | 50.2   |
| XSMLL              | 毛利率%         | 37.4   |
| XSJLL              | 净利率%         | 27.7   |
| ZCFZL              | 资产负债率%     | 44.9   |
| BPS                | 每股净资产      | 7.11   |
| MGJYXJJE           | 每股经营现金流  | 0.76   |

### 新浪 K 线参数

| 参数    | 含义       | 取值                |
| ------- | ---------- | ------------------- |
| symbol  | 股票代码   | sh600989 / sz000807 |
| scale   | 周期(分钟) | 5/15/30/240         |
| ma      | 均线       | no=不显示           |
| datalen | 数据条数   | 10/15/30/48         |

### API 限制与注意事项

- 腾讯：批量查询最多约 15 只/次，GBK 编码需转换
- 东财：code 参数必须大写 SH/SZ
- 新浪：symbol 需 sh/sz 前缀

## 五层分析框架

### 第 1 层：基本面筛选

- ROE > 15%（优秀）, > 20%（顶级）
- 净利增速 > 20%（成长）, > 50%（高速）
- 毛利率 > 30%（有壁垒）
- 负债率 < 60%（健康）
- 经营现金流/EPS > 1（利润含金量高）

### 第 2 层：估值评估

- PE 绝对值 vs 行业对比
- PEG = PE / 净利增速（<1 低估, 1-2 合理, >2 偏贵）
- PE/ROE（<3 为好）
- 历史估值分位

### 第 3 层：技术面确认

- 30 日 K 线趋势（上升/横盘/下降）
- 关键支撑/阻力位
- 成交量变化（放量/缩量）
- 5 分钟分时形态（出货/吸筹/震荡）

### 第 4 层：板块与风格分析

- 板块轮动节奏
- 大小盘分化程度
- 市场风格（成长 vs 价值、进攻 vs 防御）
- 资金流向

### 第 5 层：风险收益比计算

- 情景分析（牛市/基准/震荡/悲观/极端）
- 概率加权期望收益
- 凯利公式：f = p - (1-p)/b
- 止损/止盈位设定

## 8 人专家圆桌

### 长线 4 人（价值发现）

| 专家      | 风格      | 核心逻辑                                 |
| --------- | --------- | ---------------------------------------- |
| 巴菲特    | 价值投资  | 好生意+好价格+长期持有，偏好高 ROE 低 PE |
| 彼得·林奇 | 成长投资  | PEG<1 增速消化估值，偏好高增速合理 PE    |
| 索罗斯    | 宏观/趋势 | 趋势确认+反身性，技术面+资金面           |
| 段永平    | 逆向投资  | 好公司+安全边际，低估值+护城河           |

### 短线 4 人（时机把握）

| 专家     | 风格       | 核心逻辑                        |
| -------- | ---------- | ------------------------------- |
| 徐翔     | 涨停板战法 | 龙头+量价配合，打板追涨         |
| 赵老哥   | 趋势龙头   | 趋势确认+持仓周期，波段操作     |
| 炒股养家 | 情绪流     | 情绪周期+板块轮动，情绪拐点买卖 |
| 作手新一 | 强势股低吸 | 回调到支撑位低吸，分批建仓      |

### 讨论流程

1. 基本面数据呈现 → 共识
2. 多空辩论 → 正方 vs 反方
3. 操作方案对比 → 不同风格方案
4. 投票汇总 → 多数决+少数保留
5. 最终建议 → 折中方案+风险预案

## 仓位管理

### 凯利公式
```

最优仓位 f = p - (1-p)/b
p = 胜率, b = 赔率(期望收益/最大风险)
调整后最优仓位 ≈ f × 0.5（安全系数）

```

### 仓位分级

| 仓位 | 含义 | 适用场景 |
| --- |
| 0% | 不碰 | 基本面差/估值过高 |
| 3% | 试探仓 | 等回调/方向不明 |
| 5% | 标准仓 | 确认买入信号 |
| 8% | 重仓 | 强烈看好+低位 |
| 10-15% | 核心仓 | 最强标的+安全边际充足 |

### 止损铁律

- 个股：跌破关键支撑位收盘确认即止损
- 组合：单日亏损>3% 减仓
- 板块：板块趋势转空减仓

## 选股策略系统

### A 股市场约束

- 主板、创业板、科创板、北交所、ETF 不同波动制度
- T+1 交易制度
- 涨跌停限制
- ST/退市风险过滤

### 股票池构建

| 股票池 | 用途 | 数据来源 |
| --- |
| 内置板块池 | 快速筛主题/行业 | `data/sector_stocks.json` |
| ETF 映射池 | 判断板块强弱 | `data/sector_etf.csv` |
| 用户自定义池 | 精筛自选或持仓 | `--codes` 或持仓 JSON |

### 硬过滤规则

| 过滤项 | 默认规则 | 理由 |
| --- |
| ST/退市风险 | 名称含 ST 剔除 | 风险收益结构失真 |
| 成交额 | 低于 5000 万剔除 | 避免冲击成本和流动性陷阱 |
| 总市值 | 低于 40 亿剔除 | 避免壳、小票极端波动 |
| 盈利 | 可选剔除 EPS<=0 | 质量/价值策略必须盈利约束 |
| 涨跌停 | 降低动量分 | 当日可交易性差 |

### 多因子评分

| 因子 | 权重桶 | 指标 |
| --- |
| 质量 | quality | ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS |
| 估值 | valuation | PE、PB、PEG、PE/ROE |
| 动量 | momentum | 20 日收益、MA10/MA20、量能比、换手率 |
| 流动性 | liquidity | 成交额、总市值、换手适中程度 |

### 5 种策略权重

| 策略 | 市场环境 | 质量 | 估值 | 动量 | 流动性 |
| --- | --- | --- | --- |
| balanced | 震荡/方向不明 | 32% | 25% | 23% | 20% |
| quality_value | 价值修复/防守 | 42% | 32% | 10% | 16% |
| growth_momentum | 进攻行情/主线题材 | 26% | 12% | 42% | 20% |
| defensive | 缩量弱市/避险 | 38% | 34% | 8% | 20% |
| turning_point | 超跌修复/拐点 | 24% | 24% | 36% | 16% |

## 决策流程与 Skill 协作

### 标准决策流程

```

研究标的 → 基本面筛选(ROE/增速/毛利)
→ 估值评估(PE/PEG)
→ 技术面确认(支撑/趋势)
→ 板块分析(轮动/风格)
→ 专家讨论(多空辩论)
→ 风险收益比计算
→ 仓位决策(凯利公式)
→ 建仓节奏(分批)
→ 持续跟踪(止损/止盈)

```

### Skill 协作流程

| 场景 | 推荐链路 |
| --- | --- |
| 自上而下找机会 | `market` → `sector` → `screener` → `stock` → `technical` → `portfolio` |
| 已有个股做验证 | `stock` → `financial-analyst` → `sector` → `technical` → `portfolio` |
| 持仓再平衡 | `portfolio` → `market` → `technical` → `screener` → `stock` |
| 深度研究报告 | `investment-researcher` 总控，按需调用其他 skill |

交接时至少保留：市场状态、板块观点、候选池、基本面评级、技术触发、仓位计划、置信度。

## 关键经验（9 条铁律）

1. 不追高：PE>100 时风险极大
2. 板块轮动极快：不追轮动，持有核心仓位
3. 关键支撑位需多次测试确认，不赌单次
4. 仓位管理比选股重要
5. 现金是最好的期权：震荡市中 30% 现金是优势
6. 高赔率≠无风险：仍需止损纪律
7. 防御仓位（黄金/低估值金融）是组合压舱石
8. 科技仓位不能为零，至少 5-8%
```

- [ ] **步骤 2：验证文档内容**

```bash
grep -c "##" docs/methodology.md
```

预期：包含 10+ 个二级标题
失败：标题数量不足或文件不存在

- [ ] **步骤 3：提交**

```bash
git add docs/methodology.md
git commit -m "docs: 添加投资方法论文档"
```

---

## 任务 6：编写 api-reference.md

**文件：**

- 创建：`docs/api-reference.md`

- [ ] **步骤 1：编写 API 参考文档**

````markdown
# API 参考

脚本命令行参数和数据源快速查阅。

## 脚本命令行参数

### quote.py - 实时行情查询

```bash
python3 scripts/quote.py <code>
```
````

示例：

```bash
python3 scripts/quote.py sh600989
```

### finance.py - 财务数据查询

```bash
python3 scripts/finance.py <code>
```

示例：

```bash
python3 scripts/finance.py SH600989
```

注意：code 参数必须大写 SH/SZ。

### kline.py - K 线数据查询

```bash
python3 scripts/kline.py <code> [scale] [datalen]
```

示例：

```bash
python3 scripts/kline.py sh600989 240 30
```

参数：

- code：股票代码（sh600989 / sz000807）
- scale：周期（5/15/30/240 分钟）
- datalen：数据条数（10/15/30/48）

### screener.py - 多因子选股

```bash
python3 scripts/screener.py [options]
```

选项：

- `--strategy <策略>`：balanced/quality_value/growth_momentum/defensive/turning_point
- `--sector <板块>`：板块名称
- `--top <N>`：返回前 N 个候选
- `--codes <代码>`：自定义股票池（逗号分隔）
- `--exclude-loss`：剔除亏损股
- `--json`：JSON 格式输出

示例：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析

```bash
python3 scripts/technical.py <code> [mode]
```

示例：

```bash
python3 scripts/technical.py sh600989 full
```

模式：

- quick：趋势、量价、支撑阻力
- full：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）

### announcements.py - 公告/研报查询

```bash
python3 scripts/announcements.py <code>
```

示例：

```bash
python3 scripts/announcements.py SH600989
```

## 数据源 API

### 腾讯实时行情字段映射

字段按 `~` 分隔，从 0 开始：

| 字段位 | 含义       | 示例        |
| ------ | ---------- | ----------- |
| 1      | 市场代码   | 1=沪, 51=深 |
| 2      | 代码       | 600989      |
| 3      | 名称       | 宝丰能源    |
| 4      | 当前价     | 24.59       |
| 5      | 昨收       | 24.92       |
| 33     | 涨跌幅%    | -0.49       |
| 37     | 成交量(手) | 547985      |
| 38     | 成交额(万) | 134521      |
| 39     | 换手率%    | 0.75        |
| 40     | PE(动)     | 14.34       |

### 东财财务数据字段映射

| 字段               | 含义            | 示例值 |
| ------------------ | --------------- | ------ |
| EPSJB              | 每股收益        | 0.5    |
| ROEJQ              | ROE(加权)       | 7.28   |
| TOTALOPERATEREVETZ | 营收同比增长%   | 22.9   |
| PARENTNETPROFITTZ  | 净利润同比增长% | 50.2   |
| XSMLL              | 毛利率%         | 37.4   |
| XSJLL              | 净利率%         | 27.7   |
| ZCFZL              | 资产负债率%     | 44.9   |
| BPS                | 每股净资产      | 7.11   |
| MGJYXJJE           | 每股经营现金流  | 0.76   |

注意：

- `WEIGHTAVG_ROE`、`GROSSPROFITINRATIO`、`NETPROFITRATIO` 返回 None，不要用
- 正确字段是 `ROEJQ`、`XSMLL`、`XSJLL`

### 新浪 K 线参数

| 参数    | 含义       | 取值                |
| ------- | ---------- | ------------------- |
| symbol  | 股票代码   | sh600989 / sz000807 |
| scale   | 周期(分钟) | 5/15/30/240         |
| ma      | 均线       | no=不显示           |
| datalen | 数据条数   | 10/15/30/48         |

## 输出格式说明

### 文本格式

默认人类可读格式，适合直接阅读。

### JSON 格式

使用 `--json` 参数获取 JSON 格式输出，适合程序处理。

## 错误码与常见问题

### 中文乱码

原因：GBK 编码未转换
解决：加 `iconv -f GBK -t UTF-8`

### 财务字段返回 None

原因：字段名错误
解决：用 ROEJQ 不用 WEIGHTAVG_ROE

### JSON 解析失败

原因：返回空或格式错误
解决：加 `2>/dev/null` + 判断 `d['data']`

### K 线数据为空

原因：symbol 格式错误
解决：检查 sh/sz 前缀

### 批量查询部分失败

原因：超过 API 限制
解决：分批查询，每批≤15 只

````

- [ ] **步骤 2：验证文档内容**

```bash
grep -c "##" docs/api-reference.md
````

预期：包含 5+ 个二级标题
失败：标题数量不足或文件不存在

- [ ] **步骤 3：提交**

```bash
git add docs/api-reference.md
git commit -m "docs: 添加 API 参考文档"
```

---

## 任务 7：更新 README.md 添加文档链接

**文件：**

- 修改：`README.md`

- [ ] **步骤 1：读取当前 README.md**

```bash
head -30 README.md
```

预期：看到现有内容
失败：文件不存在

- [ ] **步骤 2：在 README.md 中添加文档链接**

在 README.md 的"方法论"部分后添加：

```markdown
## 文档

- [快速入门](docs/quick-start.md) - 5 分钟上手
- [使用者指南](docs/user-guide.md) - 8 个技能详细用法
- [开发者指南](docs/developer-guide.md) - 项目结构与扩展开发
- [投资方法论](docs/methodology.md) - 五层框架、专家圆桌、仓位管理
- [API 参考](docs/api-reference.md) - 脚本命令行与数据源
```

- [ ] **步骤 3：验证修改**

```bash
grep -c "文档" README.md
```

预期：包含"文档"标题和 5 个链接
失败：链接缺失或格式错误

- [ ] **步骤 4：提交**

```bash
git add README.md
git commit -m "docs: 在 README 中添加文档链接"
```

---

## 任务 8：验证所有文档

**文件：**

- 验证：`docs/*.md`

- [ ] **步骤 1：验证所有文档存在**

```bash
ls -la docs/
```

预期：5 个文档文件存在
失败：文件缺失

- [ ] **步骤 2：验证文档内容完整性**

```bash
for f in docs/*.md; do echo "=== $f ==="; grep -c "##" "$f"; done
```

预期：每个文档包含多个二级标题
失败：标题数量为 0 或文件为空

- [ ] **步骤 3：验证链接有效性**

```bash
grep -o "\[.*\](.*)" README.md | grep "docs/"
```

预期：显示 5 个文档链接
失败：链接缺失

- [ ] **步骤 4：最终提交**

```bash
git add docs/
git commit -m "docs: 完成项目使用说明文档"
```

---

## 自审

### 1. 规格覆盖

- ✓ quick-start.md：安装、验证、第一个命令、常见问题
- ✓ user-guide.md：8 个技能用法、组合场景、持仓配置、常见问题
- ✓ developer-guide.md：项目结构、脚本模块、数据源、扩展开发、贡献流程
- ✓ methodology.md：数据源、五层框架、专家圆桌、仓位管理、选股策略、决策流程
- ✓ api-reference.md：脚本命令行、数据源 API、输出格式、错误处理

### 2. 占位符扫描

- ✓ 无 TBD/TODO
- ✓ 无"稍后实现"
- ✓ 所有步骤都有具体命令和预期输出

### 3. 类型一致性

- ✓ 文档名称一致：quick-start.md、user-guide.md、developer-guide.md、methodology.md、api-reference.md
- ✓ 目录结构一致：docs/
- ✓ 链接路径一致：docs/xxx.md

---

## 执行交接

计划完成并保存到 `docs/superpowers/plans/2026-06-05-project-documentation.md`。两种执行选项：

**1. 子代理驱动（推荐）** - 我为每个任务分派一个新的子代理，任务间审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行带检查点

选择哪种方式？

# 项目使用说明文档设计

**日期**：2026-06-05
**状态**：待批准
**目标受众**：开发者、使用者、投资分析师

---

## 1. 背景与目标

### 1.1 背景

stock-analyzer-skill 是一个独立的股票分析 skill 包，提供 8 个股票分析相关技能、完整方法论和工具脚本。当前项目有 README.md，但内容较为集中，缺乏针对不同受众的详细指南。

### 1.2 目标

为三类目标受众提供专门的文档：

- **使用者**：快速上手并熟练使用 8 个技能
- **开发者**：理解项目结构并能扩展开发
- **投资分析师**：深入理解分析框架和方法论

### 1.3 成功标准

- 使用者能在 5 分钟内完成安装并运行第一个技能
- 开发者能在 30 分钟内理解项目结构并开始扩展
- 投资分析师能完整理解五层分析框架和专家圆桌机制

---

## 2. 文档结构

### 2.1 目录结构

```
docs/
├── quick-start.md          # 快速入门（5分钟）
├── user-guide.md           # 使用者指南
├── developer-guide.md      # 开发者指南
├── methodology.md          # 投资方法论
└── api-reference.md        # API 参考
```

### 2.2 文档职责

| 文档               | 目标受众      | 职责                                             |
| ------------------ | ------------- | ------------------------------------------------ |
| quick-start.md     | 所有人        | 安装、验证、5 分钟上手示例                       |
| user-guide.md      | 使用者        | 技能用法、组合场景、持仓配置、常见问题           |
| developer-guide.md | 开发者        | 项目结构、脚本原理、数据源、扩展开发、贡献指南   |
| methodology.md     | 投资分析师    | 五层框架、专家圆桌、仓位管理、选股策略、关键经验 |
| api-reference.md   | 开发者+分析师 | 脚本命令行、字段映射、数据源 API                 |

---

## 3. 文档详细设计

### 3.1 quick-start.md

**目标**：5 分钟内让用户跑通第一个技能

**内容大纲**：

1. **前置条件**
   - Python 3.x
   - Claude Code 环境

2. **安装步骤**

   ```bash
   cd ~/Documents/curtis/stock-analyzer-skill
   ./install.sh
   ```

   - 说明 install.sh 的作用：创建 symlink 到 ~/.claude/skills/
   - 重启 Claude Code

3. **验证安装**

   ```bash
   ./tests/smoke_test.sh
   ```

   - 预期输出：N 通过, 0 失败

4. **第一个命令**

   ```
   /stock sh600989 quick
   ```

   - 预期输出：基本面+估值+技术面 3 分钟快评

5. **常见安装问题**
   - 权限问题：`chmod +x install.sh`
   - Python 版本问题：确认 python3 可用
   - 网络问题：确认能访问国内 API

---

### 3.2 user-guide.md

**目标**：让使用者掌握所有技能的用法

**内容大纲**：

1. **技能概览**
   - 8 个技能的表格：名称、命令、用途、模式

2. **单股分析 (/stock)**
   - 命令格式：`/stock <代码或名称> [quick|full|debate]`
   - 三种模式详解：
     - quick：3 分钟快评（基本面+估值+技术面）
     - full：五层分析（基本面/估值/技术面/板块/风险收益比）
     - debate：8 人专家圆桌辩论
   - 输出解读
   - 使用示例

3. **大盘复盘 (/market)**
   - 命令格式：`/market [full|quick|intraday]`
   - 三种模式详解：
     - full：完整复盘（指数+板块+风格+资金）
     - quick：快评（主要指数+最强最弱板块+一句话结论）
     - intraday：盘中分时复盘
   - 输出解读
   - 使用示例

4. **板块分析 (/sector)**
   - 命令格式：`/sector <板块> [overview|compare|stock]`
   - 三种模式详解：
     - overview：板块全景
     - compare：核心标的横向对比
     - stock：板块内个股筛选
   - 输出解读
   - 使用示例

5. **持仓管理 (/portfolio)**
   - 命令格式：`/portfolio [health|rebalance|compare]`
   - 三种模式详解：
     - health：持仓健康检查
     - rebalance：调仓再平衡
     - compare：持仓标的对比
   - 自定义持仓配置：
     ```bash
     cp data/portfolio_example.json data/portfolio.json
     # 编辑 portfolio.json
     ```
   - 输出解读
   - 使用示例

6. **多因子选股 (/screener)**
   - 命令格式：`/screener [--sector 板块] [--strategy 策略]`
   - 5 种策略详解：
     - balanced：均衡精选（震荡市）
     - quality_value：质量价值（价值修复/防守）
     - growth_momentum：成长动量（进攻行情）
     - defensive：防守低波（缩量弱市）
     - turning_point：拐点修复（超跌修复）
   - 参数说明：--sector, --strategy, --top, --codes, --exclude-loss, --json
   - 输出解读：候选排名、剔除原因、市场适配、交易计划
   - 使用示例

7. **纯技术分析 (/technical)**
   - 命令格式：`/technical <代码> [quick|full]`
   - 两种模式详解：
     - quick：趋势、量价、支撑阻力
     - full：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）
   - 输出解读
   - 使用示例

8. **财务分析 (/financial-analyst)**
   - 命令格式：`/financial-analyst <任务>`
   - 用途：建模、预测、场景分析
   - 使用示例

9. **投资研究 (/investment-researcher)**
   - 命令格式：`/investment-researcher <任务>`
   - 用途：市场研究、尽调、估值
   - 使用示例

10. **组合使用场景**
    - 自上而下选股流程：market → sector → screener → stock → technical → portfolio
    - 自下而上验证流程：stock → financial-analyst → sector → technical → portfolio
    - 持仓再平衡流程：portfolio → market → technical → screener → stock
    - 深度研究报告：investment-researcher 总控，按需调用其他 skill

11. **常见问题与解答**
    - 数据源是否稳定？
    - 如何处理 API 变更？
    - 如何自定义选股策略？

---

### 3.3 developer-guide.md

**目标**：让开发者理解项目结构并能扩展

**内容大纲**：

1. **项目结构详解**

   ```
   stock-analyzer-skill/
   ├── README.md
   ├── workflow.md
   ├── methodology.md
   ├── install.sh
   ├── .agents/skills/         # Codex workspace skill 源
   ├── .claude/skills/         # Claude Code skill 源
   ├── scripts/                # 工具脚本
   ├── data/                   # 静态参考数据
   └── tests/
   ```

2. **脚本模块说明**
   - `common.py` - 编码转换、字段映射、HTTP 工具
   - `quote.py` - 腾讯实时行情
   - `finance.py` - 东财财务数据
   - `kline.py` - 新浪 K 线
   - `screener.py` - 多因子选股器
   - `technical.py` - 技术分析引擎
   - `chan.py` - 缠论结构
   - `patterns_local.py` - 本土战法形态
   - `classifier.py` - 个股类型分类

3. **数据源架构**
   - 腾讯 qt.gtimg.cn：实时行情、PE/PB/市值（GBK 编码）
   - 东方财富 emweb.securities.eastmoney.com：财务摘要
   - 新浪 money.finance.sina.com.cn：K 线数据
   - 东方财富 np-anotice-stock.eastmoney.com：公告
   - 东方财富 reportapi.eastmoney.com：研报

4. **Skill 注册机制**
   - `.claude/skills/` vs `.agents/skills/` 的区别
   - symlink 机制：install.sh 创建扁平 symlink 到 ~/.claude/skills/
   - SKILL.md 格式说明

5. **扩展开发指南**
   - 添加新数据源：
     1. 在 scripts/ 下创建新模块
     2. 遵循 common.py 的 HTTP 工具模式
     3. 处理编码和错误
   - 添加新因子：
     1. 在 screener.py 中添加因子定义
     2. 更新权重配置
     3. 添加评分逻辑
   - 添加新技能：
     1. 创建 .claude/skills/<name>/SKILL.md
     2. 更新 install.sh
     3. 同步到 .agents/skills/

6. **测试与验证**
   - 端到端冒烟测试：tests/smoke_test.sh
   - 手动测试流程

7. **贡献流程**
   - Git 规范：Conventional Commits
   - 分支命名：`<type>/<短描述>`
   - 提交信息：中文标题与正文

---

### 3.4 methodology.md

**目标**：让投资分析师理解完整分析框架

**内容大纲**：

1. **数据源详解**
   - 腾讯实时行情字段映射
   - 东财财务数据字段映射
   - 新浪 K 线参数说明
   - API 限制与注意事项

2. **五层分析框架**
   - 第 1 层：基本面筛选
     - ROE > 15%（优秀）, > 20%（顶级）
     - 净利增速 > 20%（成长）, > 50%（高速）
     - 毛利率 > 30%（有壁垒）
     - 负债率 < 60%（健康）
     - 经营现金流/EPS > 1（利润含金量高）

   - 第 2 层：估值评估
     - PE 绝对值 vs 行业对比
     - PEG = PE / 净利增速（<1 低估, 1-2 合理, >2 偏贵）
     - PE/ROE（<3 为好）
     - 历史估值分位

   - 第 3 层：技术面确认
     - 30 日 K 线趋势（上升/横盘/下降）
     - 关键支撑/阻力位
     - 成交量变化（放量/缩量）
     - 5 分钟分时形态（出货/吸筹/震荡）

   - 第 4 层：板块与风格分析
     - 板块轮动节奏
     - 大小盘分化程度
     - 市场风格（成长 vs 价值、进攻 vs 防御）
     - 资金流向

   - 第 5 层：风险收益比计算
     - 情景分析（牛市/基准/震荡/悲观/极端）
     - 概率加权期望收益
     - 凯利公式：f = p - (1-p)/b
     - 止损/止盈位设定

3. **8 人专家圆桌**
   - 长线 4 人（价值发现）：
     - 巴菲特：价值投资（好生意+好价格+长期持有）
     - 彼得·林奇：成长投资（PEG<1 增速消化估值）
     - 索罗斯：宏观/趋势（趋势确认+反身性）
     - 段永平：逆向投资（好公司+安全边际）

   - 短线 4 人（时机把握）：
     - 徐翔：涨停板战法（龙头+量价配合）
     - 赵老哥：趋势龙头（趋势确认+持仓周期）
     - 炒股养家：情绪流（情绪周期+板块轮动）
     - 作手新一：强势股低吸（回调到支撑位低吸）

   - 讨论流程：
     1. 基本面数据呈现 → 共识
     2. 多空辩论 → 正方 vs 反方
     3. 操作方案对比 → 不同风格方案
     4. 投票汇总 → 多数决+少数保留
     5. 最终建议 → 折中方案+风险预案

4. **仓位管理**
   - 凯利公式推导：

     ```
     最优仓位 f = p - (1-p)/b
     p = 胜率, b = 赔率(期望收益/最大风险)
     调整后最优仓位 ≈ f × 0.5（安全系数）
     ```

   - 仓位分级：
     | 仓位 | 含义 | 适用场景 |
     |------|------|---------|
     | 0% | 不碰 | 基本面差/估值过高 |
     | 3% | 试探仓 | 等回调/方向不明 |
     | 5% | 标准仓 | 确认买入信号 |
     | 8% | 重仓 | 强烈看好+低位 |
     | 10-15% | 核心仓 | 最强标的+安全边际充足 |

   - 止损铁律：
     - 个股：跌破关键支撑位收盘确认即止损
     - 组合：单日亏损>3% 减仓
     - 板块：板块趋势转空减仓

5. **选股策略系统**
   - A 股市场约束：
     - 主板、创业板、科创板、北交所、ETF 不同波动制度
     - T+1 交易制度
     - 涨跌停限制
     - ST/退市风险过滤

   - 股票池构建：
     - 内置板块池：data/sector_stocks.json
     - ETF 映射池：data/sector_etf.csv
     - 用户自定义池：--codes 或持仓 JSON

   - 硬过滤规则：
     - ST/退市风险：名称含 ST 剔除
     - 成交额：低于 5000 万剔除
     - 总市值：低于 40 亿剔除
     - 盈利：可选剔除 EPS<=0
     - 涨跌停：降低动量分

   - 多因子评分：
     | 因子 | 权重桶 | 指标 |
     |------|--------|------|
     | 质量 | quality | ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS |
     | 估值 | valuation | PE、PB、PEG、PE/ROE |
     | 动量 | momentum | 20 日收益、MA10/MA20、量能比、换手率 |
     | 流动性 | liquidity | 成交额、总市值、换手适中程度 |

   - 5 种策略权重：
     | 策略 | 市场环境 | 质量 | 估值 | 动量 | 流动性 |
     |------|----------|------|------|------|--------|
     | balanced | 震荡/方向不明 | 32% | 25% | 23% | 20% |
     | quality_value | 价值修复/防守 | 42% | 32% | 10% | 16% |
     | growth_momentum | 进攻行情/主线题材 | 26% | 12% | 42% | 20% |
     | defensive | 缩量弱市/避险 | 38% | 34% | 8% | 20% |
     | turning_point | 超跌修复/拐点 | 24% | 24% | 36% | 16% |

6. **决策流程与 Skill 协作**
   - 标准决策流程：

     ```
     研究标的 → 基本面筛选 → 估值评估 → 技术面确认 → 板块分析 → 专家讨论 → 风险收益比计算 → 仓位决策 → 建仓节奏 → 持续跟踪
     ```

   - Skill 协作流程（详见 workflow.md）：
     - 自上而下选股：market → sector → screener → stock → technical → portfolio
     - 自下而上验证：stock → financial-analyst → sector → technical → portfolio
     - 持仓再平衡：portfolio → market → technical → screener → stock
     - 深度研究报告：investment-researcher 总控

7. **关键经验（9 条铁律）**
   1. 不追高：PE>100 时风险极大
   2. 板块轮动极快：不追轮动，持有核心仓位
   3. 关键支撑位需多次测试确认，不赌单次
   4. 仓位管理比选股重要
   5. 现金是最好的期权：震荡市中 30% 现金是优势
   6. 高赔率≠无风险：仍需止损纪律
   7. 防御仓位（黄金/低估值金融）是组合压舱石
   8. 科技仓位不能为零，至少 5-8%

---

### 3.5 api-reference.md

**目标**：提供脚本和数据源的快速查阅

**内容大纲**：

1. **脚本命令行参数**
   - `quote.py` - 实时行情查询

     ```bash
     python3 scripts/quote.py <code>
     # 示例：python3 scripts/quote.py sh600989
     ```

   - `finance.py` - 财务数据查询

     ```bash
     python3 scripts/finance.py <code>
     # 示例：python3 scripts/finance.py SH600989
     ```

   - `kline.py` - K 线数据查询

     ```bash
     python3 scripts/kline.py <code> [scale] [datalen]
     # 示例：python3 scripts/kline.py sh600989 240 30
     ```

   - `screener.py` - 多因子选股

     ```bash
     python3 scripts/screener.py [options]
     # 选项：
     #   --strategy <策略>  balanced/quality_value/growth_momentum/defensive/turning_point
     #   --sector <板块>    板块名称
     #   --top <N>          返回前 N 个候选
     #   --codes <代码>     自定义股票池（逗号分隔）
     #   --exclude-loss     剔除亏损股
     #   --json             JSON 格式输出
     ```

   - `technical.py` - 技术分析

     ```bash
     python3 scripts/technical.py <code> [mode]
     # 示例：python3 scripts/technical.py sh600989 full
     ```

   - `announcements.py` - 公告/研报查询
     ```bash
     python3 scripts/announcements.py <code>
     # 示例：python3 scripts/announcements.py SH600989
     ```

2. **数据源 API**
   - 腾讯实时行情字段映射（~分隔，从 0 开始）：
     | 字段位 | 含义 | 示例 |
     |--------|------|------|
     | 1 | 市场代码 | 1=沪, 51=深 |
     | 2 | 代码 | 600989 |
     | 3 | 名称 | 宝丰能源 |
     | 4 | 当前价 | 24.59 |
     | 5 | 昨收 | 24.92 |
     | 33 | 涨跌幅% | -0.49 |
     | 37 | 成交量(手) | 547985 |
     | 38 | 成交额(万) | 134521 |
     | 39 | 换手率% | 0.75 |
     | 40 | PE(动) | 14.34 |

   - 东财财务数据字段映射：
     | 字段 | 含义 | 示例值 |
     |------|------|--------|
     | EPSJB | 每股收益 | 0.5 |
     | ROEJQ | ROE(加权) | 7.28 |
     | TOTALOPERATEREVETZ | 营收同比增长% | 22.9 |
     | PARENTNETPROFITTZ | 净利润同比增长% | 50.2 |
     | XSMLL | 毛利率% | 37.4 |
     | XSJLL | 净利率% | 27.7 |
     | ZCFZL | 资产负债率% | 44.9 |
     | BPS | 每股净资产 | 7.11 |
     | MGJYXJJE | 每股经营现金流 | 0.76 |

   - 新浪 K 线参数：
     | 参数 | 含义 | 取值 |
     |------|------|------|
     | symbol | 股票代码 | sh600989 / sz000807 |
     | scale | 周期(分钟) | 5/15/30/240 |
     | ma | 均线 | no=不显示 |
     | datalen | 数据条数 | 10/15/30/48 |

3. **输出格式说明**
   - 文本格式：默认人类可读格式
   - JSON 格式：使用 --json 参数

4. **错误码与常见问题**
   - 中文乱码：GBK 编码未转换
   - 财务字段返回 None：字段名错误
   - JSON 解析失败：返回空或格式错误
   - K 线数据为空：symbol 格式错误
   - 批量查询部分失败：超过 API 限制

---

## 4. 文档维护

### 4.1 更新策略

- 代码变更时同步更新相关文档
- 新增技能时更新 user-guide.md 和 api-reference.md
- 新增脚本时更新 developer-guide.md 和 api-reference.md
- 方法论变更时更新 methodology.md

### 4.2 版本控制

- 文档与代码同仓库管理
- 重大变更时更新 README.md 中的版本说明

---

## 5. 待办事项

- [ ] 编写 quick-start.md
- [ ] 编写 user-guide.md
- [ ] 编写 developer-guide.md
- [ ] 编写 methodology.md
- [ ] 编写 api-reference.md
- [ ] 更新 README.md 添加文档链接
- [ ] 验证所有文档中的命令和示例

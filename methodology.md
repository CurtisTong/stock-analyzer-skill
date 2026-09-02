---
name: stock-analyzer-methodology
description: 投资分析完整方法论——五层框架、专家讨论模式、数据源、仓位管理、决策流程
source: 抽离自 ~/.claude/memory/investment-methodology.md
version: 1.22.1
---

# 投资分析方法论

## 一、数据源

### 实时行情（腾讯）

```
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8
```

字段: 3=名称, 4=现价, 33=涨跌幅, 40=PE, 37=成交量, 39=换手率

### 财务数据（东方财富）

```
curl -s "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=SH600989"
```

JSON结构: `response['data'][0]`
关键字段: EPSJB(每股收益), ROEJQ(加权ROE), TOTALOPERATEREVETZ(营收增速), PARENTNETPROFITTZ(净利增速), XSMLL(毛利率), XSJLL(净利率), ZCFZL(负债率), BPS(每股净资产), MGJYXJJE(每股经营现金流)

### K线数据（新浪财经）

日K: `scale=240`, 5分钟: `scale=5`, 15分钟: `scale=15`

```
curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600989&scale=240&ma=no&datalen=30"
```

### 板块ETF

510050(上证50), 510300(沪深300), 510500(中证500), 512010(医药), 512480(半导体), 512690(白酒), 512800(银行), 513120(港股创新药), 518880(黄金), 515030(新能源车)

### 市场情绪数据源（短线策略依赖）

短线专家（徐翔/赵老哥/养家/作手新一/题材龙头/情绪技术复合）的核心指标依赖市场整体情绪数据，统一由以下接口提供：

| 指标                | 数据源                             | 调用方式                                                        | 主要使用专家             |
| :------------------ | :--------------------------------- | :-------------------------------------------------------------- | :----------------------- |
| 涨停家数 / 跌停家数 | 东方财富 push2（板块行情聚合）     | `scripts/technical/sentiment.py` 或 `scripts/market_breadth.py` | 养家、徐翔、情绪技术复合 |
| 炸板率（触板未封）  | 东方财富 push2 + 龙虎榜            | `scripts/technical/sentiment.py`                                | 养家、题材龙头           |
| 昨涨停今日溢价      | 东方财富 push2 历史行情 + 集合竞价 | `scripts/technical/sentiment.py`                                | 养家、作手新一           |
| 两市成交额          | 上交所/深交所每日成交统计          | `scripts/quote.py` (上证指数 + 深证指数)                        | 索罗斯、风险管理         |
| 北向资金净流入      | 东方财富 push2 北向资金接口        | `scripts/fetchers/eastmoney_flow.py::NorthboundFlowFetcher`     | 索罗斯、机构派           |
| 板块涨跌停共振      | 东方财富板块列表 + 个股聚合        | `scripts/market_breadth.py`                                     | 题材龙头、赵老哥         |

> **数据完整性约束**：若市场情绪数据缺失（API 失败/未订阅），短线专家评分应回退至 `experts/scoring/_utils.py:score_from_dimensions` 的中性默认值（50.0），并在 `experts/decide.md` 输出中标注"情绪数据缺失"。该规则防止"伪 API"在生产 debate 中给出虚假高分。

## 二、五层分析框架

### 第1层：基本面筛选

- ROE > 15%（优秀）, > 20%（顶级）
- 净利增速 > 20%（成长）, > 50%（高速）
- 毛利率 > 30%（有壁垒）
- 负债率 < 60%（健康）
- 经营现金流/EPS > 1（利润含金量高）

### 第2层：估值评估

- PE绝对值 vs 行业对比
- PEG = PE / 净利增速（<1低估, 1-2合理, >2偏贵）
- PE/ROE（<3为好）
- 历史估值分位

### 第3层：技术面确认

- 30日K线趋势（上升/横盘/下降）
- 关键支撑/阻力位
- 成交量变化（放量/缩量）
- 5分钟分时形态（出货/吸筹/震荡）

### 第4层：板块与风格分析

- 板块轮动节奏
- 大小盘分化程度
- 市场风格（成长vs价值、进攻vs防御）
- 资金流向

### 第5层：风险收益比计算

- 情景分析（牛市/基准/震荡/悲观/极端）
- 概率加权期望收益
- 凯利公式：f = p - (1-p)/b（p=胜率, b=赔率）
- 止损/止盈位设定

### 第6层：行业差异化阈值（sector_specialist 视角）

> **重要**：上述第 1-2 层的统一阈值（ROE>15%、PE 估值未分行业）适用于全市场初筛。若启用 [experts/sector_specialist.md](experts/sector_specialist.md)，需按子行业差异化：

| 行业类                 | ROE 门槛                          | 毛利率门槛 | PE 分位                                    | 增速门槛   | 其他                                   |
| :--------------------- | :-------------------------------- | :--------- | :----------------------------------------- | :--------- | :------------------------------------- |
| 消费（食品/家电/医药） | ≥ 15%                             | ≥ 40%      | < 历史 5 年 40% 分位                       | 营收 ≥ 10% | 品牌/渠道护城河                        |
| 科技（半导体/软件/AI） | ≥ 10%                             | ≥ 30%      | < 历史 5 年 60% 分位                       | 营收 ≥ 30% | 研发占比 ≥ 10%                         |
| 医药（创新药/CXO）     | ≥ 12%                             | ≥ 50%      | < 历史 5 年 50% 分位                       | 营收 ≥ 20% | CXO 在手订单 ≥ 2 年营收                |
| 周期（有色/化工/煤炭） | ≥ 行业 70% 分位                   | —          | < 历史 5 年 50% 分位                       | —          | 商品价格历史 50-80% 分位 + 股息率 ≥ 4% |
| 金融（银行/券商/保险） | 银行 ≥ 10% / 券商 ≥ 行业 70% 分位 | —          | 银行 PB < 0.7（国有大行）/ < 1.0（股份行） | —          | 不良率（银行）/ 净资产规模（券商）     |

> 配置文件：`scripts/data/industry_thresholds.json` 与 `experts/yaml/industry_thresholds.yaml` 同步。sector_specialist 通过 `experts/scoring/sector_specialist.py` 应用本表阈值。

## 三、专家讨论模式（16 份专家人设：8 active + 8 legacy）

> 完整档案见 [experts/README.md](experts/README.md)，每位专家独立成文（1200-1500 字深度档）。

### 长线（legacy active=False + active）

| 专家      | 风格      | 核心逻辑                              | 档案                                         |  状态  |
| --------- | --------- | ------------------------------------- | -------------------------------------------- | :----: |
| 巴菲特    | 价值投资  | 好生意+好价格+长期持有，偏好高ROE低PE | [buffett.md](experts/buffett.md)             | legacy |
| 段永平    | 逆向投资  | 好公司+安全边际，低估值+护城河        | [duan_yongping.md](experts/duan_yongping.md) | legacy |
| 彼得·林奇 | 成长投资  | PEG<1增速消化估值，偏好高增速合理PE   | [lynch.md](experts/lynch.md)                 | active |
| 索罗斯    | 宏观/趋势 | 趋势确认+反身性，技术面+资金面        | [soros.md](experts/soros.md)                 | active |

> legacy 2 人（buffett / duan_yongping）已合并入 `value_anchor` 合并型专家；active 2 人（lynch / soros）保留独立 ID 不合并。

### 短线（legacy active=False）

| 专家     | 风格       | 核心逻辑                        | 档案                                           |  状态  |
| -------- | ---------- | ------------------------------- | ---------------------------------------------- | :----: |
| 徐翔     | 涨停板战法 | 龙头+量价配合，打板追涨         | [xu_xiang.md](experts/xu_xiang.md)             | legacy |
| 赵老哥   | 趋势龙头   | 趋势确认+持仓周期，波段操作     | [zhao_laoge.md](experts/zhao_laoge.md)         | legacy |
| 炒股养家 | 情绪流     | 情绪周期+板块轮动，情绪拐点买卖 | [chaogu_yangjia.md](experts/chaogu_yangjia.md) | legacy |
| 作手新一 | 强势股低吸 | 回调到支撑位低吸，分批建仓      | [zuoshou_xinyi.md](experts/zuoshou_xinyi.md)   | legacy |

> legacy 4 人已合并入 `topic_leader`（徐翔+赵老哥）与 `emotion_tech`（养家+作手新一）。

### v2.1.0 + v2.2.0 + v2.4.0 扩展 8 人（active=True，补盲区）

| 专家         | 风格              | 核心逻辑                            | 档案                                                 | 引入版本 |
| ------------ | ----------------- | ----------------------------------- | ---------------------------------------------------- | :------: |
| 题材龙头     | 题材龙头（合并）  | 徐翔 0.5 + 赵老哥 0.5               | [topic_leader.md](experts/topic_leader.md)           |  v2.1.0  |
| 情绪技术复合 | 情绪+技术（合并） | 养家 0.5 + 作手新一 0.5             | [emotion_tech.md](experts/emotion_tech.md)           |  v2.1.0  |
| 行业专家     | 行业特异性        | 行业景气+竞争格局+行业 PE 分位      | [sector_specialist.md](experts/sector_specialist.md) |  v2.1.0  |
| 风险管理     | 二阶思维+周期位置 | Howard Marks 周期位置+风险预算      | [risk_manager.md](experts/risk_manager.md)           |  v2.1.0  |
| 动量派       | 系统化趋势跟踪    | 利弗莫尔关键转折 + 海龟交易法则     | [momentum_trader.md](experts/momentum_trader.md)     |  v2.2.0  |
| 价值机构锚   | 价值+机构（合并） | value_anchor + institution 合并     | [value_institution.md](experts/value_institution.md) |  v2.4.0  |

> v2.4.0 将 `value_anchor`（巴菲特 0.55 + 段永平 0.45）与 `institution`（高瓴/红杉框架）合并为 `value_institution`，两者转为 legacy。

> 完整权重与 veto 条件见 `experts/yaml/*.yaml`；与本表对齐的代码实现见 `experts/scoring/<name>.py`。

### 讨论流程

1. 基本面数据呈现 -> 共识
2. 多空辩论 -> 正方vs反方
3. 操作方案对比 -> 不同风格方案
4. 投票汇总 -> 多数决+少数保留
5. 最终建议 -> 折中方案+风险预案

### 分数口径

专家评分系统严格遵循统一公式，确保 `dim_scores`（原始分）与 `breakdown`（贡献值）之间无歧义：

```
最终得分 = Σ ( 原始分 × 权重 )
breakdown[dim] = dim_scores[dim] × (weight / 100)
```

- **原始分**（`dim_scores`）：各维度 0-100 百分制，由专家 `score()` 函数按 `experts/yaml/*.yaml` 定义的阈值分支计算。
- **权重**（`weights`）：各维度在总分中的占比（百分制，如估值 22.5 表示 22.5%），定义于 `experts/yaml/*.yaml`。
- **贡献值**（`breakdown`）：原始分 × 权重，即该维度对总分的实际贡献。

**展示规范**：debate 报告展示维度拆分时，必须同时输出三元组 `原始分 × 权重 = 贡献值`。例如价值机构锚的估值维度：`33 × 22.5% = 7.42`，而非仅展示 7.42 或 33。

**禁用表述**：不得使用"反向加分""反向指标"等模糊词汇。低分仅代表"不符合本专家体系投资标准"，不构成对未来价格走势的反向预测。`experts/formatter.py` 会在渲染层检测 `reason` 字段是否含数据引用、是否出现禁用表述，违规时追加警告标记。

**模型边界**：本体系对强周期资产的盈利能力评估存在结构性局限（单期增速无法区分"周期顶部高增速"与"成长性高增速"）。强周期股的低分应解读为"不符合本体系标准"，而非"价格将下跌"。

## 四、仓位管理

### 凯利公式

```
最优仓位 f = p - (1-p)/b
p = 胜率, b = 赔率(期望收益/最大风险)
调整后最优仓位 ≈ f × 0.5（安全系数）
```

### 仓位分级

| 仓位   | 含义   | 适用场景              |
| ------ | ------ | --------------------- |
| 0%     | 不碰   | 基本面差/估值过高     |
| 3%     | 试探仓 | 等回调/方向不明       |
| 5%     | 标准仓 | 确认买入信号          |
| 8%     | 重仓   | 强烈看好+低位         |
| 10-15% | 核心仓 | 最强标的+安全边际充足 |

### 集中度控制

> **权威来源**：[experts/risk_manager.md](experts/risk_manager.md) §四 仓位与止损（active=True，v2.1.0 起）。本表与 risk_manager 对齐。

| 约束项             | 上限     | 理由                        |                      权威                       |
| ------------------ | -------- | --------------------------- | :---------------------------------------------: |
| 单只个股           | 15%      | 避免单一标的黑天鹅          |           methodology + risk_manager            |
| 单一行业           | 30%      | 避免行业系统性风险          |           methodology + risk_manager            |
| 前 3 大持仓        | 50%      | 保持适度分散                | **risk_manager**（methodology 旧值 45% 已对齐） |
| 前 5 大持仓        | 70%      | 集中度上限                  |    risk_manager（methodology 缺失，已补齐）     |
| 总仓位（牛市）     | 80-90%   | 现金 10-20%（保留加仓空间） |                  risk_manager                   |
| 总仓位（震荡）     | 70%      | 现金 30%（均衡）            |           methodology + risk_manager            |
| 总仓位（熊市）     | ≤ 50%    | 现金 50%+（保留抄底空间）   |           methodology + risk_manager            |
| 总仓位（极度恐慌） | ≤ 30-40% | 现金 60-70%（极致逆向）     |                  risk_manager                   |

### 止损铁律

- 个股：跌破关键支撑位收盘确认即止损
- 组合：单日亏损>3%减仓
- 板块：板块趋势转空减仓
- 时间止损：短线 5 个交易日无预期表现减仓 50%，中线 20 个交易日重新评估

### 加仓规则

- 浮盈 > 10% 且趋势确认（MA 多头 + 量价配合）：可加仓
- 每次加仓不超过原仓位的 50%
- 单只总仓位不超过 30%（含加仓）
- 加仓必须有新资金来源或减持其他标的

### 极端情景预案

- 个股连续 2 个跌停：次日集合竞价挂跌停价卖出
- 组合单周亏损 > 10%：强制减仓至 50% 以下
- 全市场跌停 > 1000 家：暂停所有新开仓，等待流动性恢复

## 五、决策流程

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

完整协作关系见 `workflow.md`。常用路径：

| 场景           | 推荐链路                                                               |
| -------------- | ---------------------------------------------------------------------- |
| 自上而下找机会 | `market` → `sector` → `screener` → `stock` → `technical` → `portfolio` |
| 已有个股做验证 | `stock` → `research` → `sector` → `technical` → `portfolio`   |
| 持仓再平衡     | `portfolio` → `market` → `technical` → `screener` → `stock`            |
| 深度研究报告   | `research` 总控，按需调用其他 skill                       |

交接时至少保留：市场状态、板块观点、候选池、基本面评级、技术触发、仓位计划、置信度。

## 六、选股策略系统

选股系统不是“找一只马上买的股票”，而是生成可跟踪候选池。流程必须固定：股票池 → 硬过滤 → 多因子评分 → 策略权重 → 市场适配 → 买点触发。

### 1. A 股市场约束

- 先识别市场板块：主板、创业板、科创板、北交所、ETF。不同板块波动制度不同，不能用同一套追涨风险假设。
- 普通 A 股交易以 T+1 为主，短线策略必须考虑隔夜风险和次日无法立即卖出的限制。
- 涨跌停附近的标的只进入观察池，不做机械追入；高分但流动性不足同样剔除。
- ST、退市风险、长期停牌、成交额过低、市值过小、财务亏损标的优先硬过滤。

### 2. 股票池构建

| 股票池       | 用途             | 数据来源                                      |
| ------------ | ---------------- | --------------------------------------------- |
| 内置板块池   | 快速筛主题/行业  | `scripts/data/sector_stocks.json`（动态更新） |
| 预置默认池   | 离线可用，零配置 | `scripts/data/sector_stocks.default.json`     |
| ETF 映射池   | 判断板块强弱     | `scripts/data/sector_etf.csv`                 |
| 用户自定义池 | 精筛自选或持仓   | `--codes` 或持仓 JSON                         |
| 全市场池     | 后续扩展         | 需接入完整 A 股列表                           |

**数据源优先级：** 东方财富 API → 预置默认数据（自动 fallback）

### 3. 硬过滤

| 过滤项      | 默认规则         | 理由                      |
| ----------- | ---------------- | ------------------------- |
| ST/退市风险 | 名称含 ST 剔除   | 风险收益结构失真          |
| 成交额      | 低于 5000 万剔除 | 避免冲击成本和流动性陷阱  |
| 总市值      | 低于 40 亿剔除   | 避免壳、小票极端波动      |
| 盈利        | 可选剔除 EPS<=0  | 质量/价值策略必须盈利约束 |
| 涨跌停      | 降低动量分       | 当日可交易性差            |

### 4. 多因子评分

| 因子   | 权重桶     | 指标                                                    | 解释                   |
| ------ | ---------- | ------------------------------------------------------- | ---------------------- |
| 质量   | quality    | ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS | 好公司与盈利质量       |
| 估值   | valuation  | PE、PB、PEG、PE/ROE                                     | 安全边际和估值消化能力 |
| 动量   | momentum   | 20日收益、MA10/MA20、量能比、换手率                     | 市场是否开始认可       |
| 流动性 | liquidity  | 成交额、总市值、换手适中程度                            | 能否交易、能否退出     |
| 波动率 | volatility | 历史收益率标准差（低波动得高分）                        | A股低波动异象          |

### 5. 策略权重（九因子模型）

> **注**：表中仅列 7 个核心因子权重；`event`（事件因子：财报/解禁/分红/违规）与 `analyst`（分析师预期：一致预期净利润/目标价空间）为 2026 新增维度，默认权重 0%（占位），可通过 `scripts/strategies/registry.py` 调节。

| 策略                | 市场环境          | 质量 | 估值 | 动量 | 流动性 | 波动率 | 股息 | 筹码 |
| ------------------- | ----------------- | ---- | ---- | ---- | ------ | ------ | ---- | ---- |
| balanced            | 震荡/方向不明     | 30%  | 20%  | 15%  | 5%     | 15%    | 5%   | 10%  |
| quality_value       | 价值修复/防守     | 30%  | 35%  | 5%   | 5%     | 10%    | 10%  | 5%   |
| growth_momentum     | 进攻行情/主线题材 | 20%  | 20%  | 30%  | 10%    | 5%     | 5%   | 10%  |
| defensive           | 缩量弱市/避险     | 22%  | 20%  | 5%   | 3%     | 20%    | 10%  | 20%  |
| turning_point       | 超跌修复/拐点     | 20%  | 20%  | 15%  | 10%    | 15%    | 10%  | 10%  |
| ma_volume_momentum  | MA10/MA21 金叉 + 量价共振 | 15% | 15% | 30% | 10% | 10% | 5% | 15% |

### 6. 输出标准

选股结果必须同时给出：

- 候选排名：总分 + 九因子分。
- 剔除原因：让”为什么没选”可审计。
- 市场适配：当前更适合进攻、均衡还是防守。
- 交易计划：买入触发、失效条件、止损/降仓、仓位上限。
- 后续跟踪：需要复核的财报、公告、板块 ETF、关键均线或支撑位。

### 7. 脚本入口

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

## 七、数据获取与开发工具

> 数据源 API 字段说明见 [`docs/api-reference.md`](docs/api-reference.md)；代码结构与模块用法见 [`docs/developer-guide.md`](docs/developer-guide.md)；测试框架见 [`tests/FRAMEWORK.md`](tests/FRAMEWORK.md)。本章 v1.1.0 版本内容已迁移至上述文档，避免多处维护漂移。

## 八、快捷启动命令

| 命令                                        | 用途     | 模式                                          |
| ------------------------------------------- | -------- | --------------------------------------------- |
| `/stock <标的> [quick\|full\|debate]`       | 个股分析 | quick=3分钟, full=五层, debate=专家辩论       |
| `/portfolio [health\|rebalance\|compare]`   | 持仓检查 | health=健康检查, rebalance=调仓, compare=对比 |
| `/market [full\|quick\|intraday]`           | 大盘复盘 | full=完整, quick=快评, intraday=分时          |
| `/sector <板块> [overview\|compare\|stock]` | 板块分析 | overview=全景, compare=对比, stock=个股       |

## 九、关键经验

1. 不追高：PE>100时风险极大——**本条指估值层"追高"，非指打板瞬间买入**。徐翔/赵老哥打板是"涨停瞬间封板后的封单博弈"，区别于高位追涨；短线策略（涨停基因+板块共振+流通市值 30-200 亿）的具体规则见 [experts/xu_xiang.md](experts/xu_xiang.md) §决策逻辑。
2. 板块轮动极快：不追轮动，持有核心仓位
3. 关键支撑位需多次测试确认，不赌单次
4. 仓位管理比选股重要
5. 现金是最好的期权：震荡市中30%现金是优势（与 [experts/risk_manager.md](experts/risk_manager.md) §四 一致）
6. 高赔率≠无风险：仍需止损纪律
7. 防御仓位（黄金/低估值金融）是组合压舱石
8. 科技仓位不能为零，至少5-8%
9. **冰点二元语义**（养家）：冰点既是"情绪退潮极端"（触发 [experts/vote_engine.py](experts/vote_engine.py) 中短线组 ×0.7 降权），也是"机会起爆点"（不降权 + 标注"冰点机会"）；权威定义见 [experts/chaogu_yangjia.md](experts/chaogu_yangjia.md) §决策逻辑（冰点判定），其余文件交叉引用此定义。

## 十、案例复盘

> 案例复盘汇总见 [`data/reports/202506_Stock_Analysis_Summary.md`](data/reports/202506_Stock_Analysis_Summary.md)（含 7 只个股分析、评级排序、风险识别模式、后续跟踪）。本章原为 2026年6月时效性内容，已移至 reports 归档，避免「今日市场特征」类信息常驻方法论文档。

## 十一、测试框架

> 测试框架详见 [`tests/FRAMEWORK.md`](tests/FRAMEWORK.md)（目录结构、6 个 pytest 标记、fixtures 清单、respx 网络替身、覆盖率门禁、CI 编排）。

# 开源股票分析项目深度调研 × 功能优化校准报告

> 日期：2026-10-29 · 版本基线：v1.23.1 · 分支：`fix/experts-calibration-path`
> 方法：4 路并行调研（LLM 多 Agent / A 股工具 / 量化回测 / 一体化平台），GitHub 实时核对 star 与 2026 活跃度；本项目侧逐项 grep 源码核实，不采信文档口径。

---

## 一、调研范围

共调研 30+ 开源项目，按与本项目的相关度分四类：

| 类别 | 重点项目（star · 2026 活跃度） |
| --- | --- |
| LLM 多 Agent 投研 | TradingAgents（117.9k · 活跃）、ai-hedge-fund（64.3k · v2 重构）、TradingAgents-CN（32.7k · A 股适配）、AI-Trader（23k）、ai-berkshire（16.9k · Claude Code skill 同赛道）、FinRobot（8.3k） |
| A 股工具 | InStock（14.9k）、a-stock-data（11.2k · skill 形态 15 层 87 端点）、daily_stock_analysis（67.2k · 推送最全）、vibe-astock（短线情绪复盘）、Sequoia-X（8.3k 形态策略）、czsc（6.5k 缠论权威）、adata（5.3k） |
| 量化回测/因子 | Qlib（49.8k）、vnpy（46.1k）、nautilus_trader（31k）、Lean（22.3k）、backtrader（23.6k · 停更）、rqalpha（6.8k · A 股严谨性最强）、vectorbt（9.6k）、PyPortfolioOpt（6.1k）、Riskfolio-Lib（4.6k） |
| 一体化平台 | OpenBB（74.8k · V5 大版本，官方把 Claude Code skill 当一等公民）、Freqtrade（56.1k）、Jesse（8.7k · 内置 MCP）、ghostfolio（9.6k） |

**赛道判断**：OpenBB 官方在 2026 版本中提供 `install_skill` 工具直接把 SKILL.md 写入 Claude Code / Codex 的 skill 目录；Jesse 文档直接写 "Connect Claude Code"。本项目「LLM skill + Python CLI」形态与市场主流演进方向一致，赛道正确。

---

## 二、本项目现状核实（事实清单）

调研结论建立在对源码的逐项核实上，与 README/文档口径的差异已标注：

- ✅ **专家校准**：`experts/calibration.py` 有 record/verify/report/真实价格回调/长短分组校准/胜率卡片；**统一 30 天验证窗口**（无按专家区分）。
- ✅ **回测引擎**（`backtest/engine.py`，697 行）：佣金 0.025%（双向）+ 印花税 0.1%（卖出）+ 滑点 0.1%（双向）；涨跌停（±10%/±20%）与停牌（volume=0）**跳过处理**；quality 因子 90 天披露延迟防前瞻；walk-forward OOS。
- ✅ **数据域已覆盖**：龙虎榜+席位、限售解禁、股权质押、商誉、两融、股东户数、分红、公告、研报、一致预期、筹码分布、题材概念、涨停池/炸板/连板、事件日历（`fetchers/lhb/`、`fetchers/event/`、`chip.py`、`events.py` 等）。
- ✅ **因子库实际 15 个模块**（quality/valuation/valuation_ext/momentum/liquidity/volatility/dividend/chip/event/analyst/capacity/cyclical/dealer/dupont/dcf）——**多于文档口径的「9 因子」**。
- ✅ **形态策略 8 个**（底部首板/断板/老鸭头/量价/美人尖/三阴/双针/涨停）；缠论 8 模块（分型/笔/线段/中枢/背驰/买点/面积/合并）。
- ⚠️ **`/monitor` skill 已于 v1.17.0 移除**（监控能力下放 portfolio-web），但用户全局 AGENTS.md 仍列有 `/monitor`，且本机 `~/.claude/skills/monitor{,.md}` 为失效软链（install.sh 自检重跑可清）。
- ❌ **零覆盖数据域**（grep 全量 0 命中）：大宗交易、可转债、逐笔成交/集合竞价、涨停原因归因+封板质量、互动易/舆情热榜、机构调研、股票回购、打新日历。

---

## 三、五维校准矩阵

### 维度 1：专家圆桌 / 多 Agent 决策

对标 ai-hedge-fund v2（确定性信号混合 + 记分卡 + 硬限额）、TradingAgents（辩论冲突消解 + 反思记忆）、TradingAgents-CN（三场景反思 + 按 agent 隔离记忆）。

| # | 机制 | 对标来源 | 本项目现状 | 校准建议 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| 1.1 | **按专家 horizon 结算** | ai-hedge-fund：巴菲特 252 交易日、PEAD 数周，各模型自声明 horizon | 统一 30 天窗口——用错误时间窗评价长线专家（林奇/价值机构会被 30 天噪声误伤） | 长线专家 120 交易日、短线专家 5-10 交易日、行业专家 60 交易日，verify 按 expert→horizon 分桶到期 | **P0** |
| 1.2 | **记分卡强制携带样本数** | ai-hedge-fund scorecard：hit_rate/slugging/IC 均值+t 统计，样本不足返回 None；区分 n_abstained/n_pending | 胜率卡片无样本数下限提示，小样本胜率会被过度解读 | 胜率卡片每格加 `n=xx`；n<10 显示「样本不足」；分离弃权与未结算 | **P0** |
| 1.3 | **slugging（赔率）口径** | 赢时均涨幅 / 输时均跌幅 | 只有方向胜率 | 校准报告加 slugging 与平均收益差，比胜率更抗噪声 | P1 |
| 1.4 | **弃权票显式化** | TradingAgents：解析不出返回 REVIEW 哨兵而非 Hold，「读不出来的决策不是持有」 | 投票只有 买入/观望/回避 | decide.md 增加「无法判定/数据不足」第四态，不计入投票基数；debate 输出 consensus_view + dissenting_opinions | P1 |
| 1.5 | **冲突消解措辞** | TradingAgents prompt：「冲突本身不是 Hold 的理由；证据更强一侧必须站过去，只在证据均衡时 Hold」 | decide.md 有加权规则，无显式反和稀泥条款 | decide.md 增补该裁决纪律（一行 prompt 成本，直接改善「各打五十大板」倾向） | P1 |
| 1.6 | **风险官「只否决不表决」** | ai-hedge-fund：LLM 只出 conviction，仓位由确定性代码 `max_position_pct` 钳制 + ClampEvent 审计留痕 | 风控官是 8 票之一 | 保留投票，另加确定性钳制层：组合集中度/单票上限由 portfolio 代码硬约束并留审计记录 | P2 |
| 1.7 | **分层反思记忆** | TradingAgents-CN：交易复盘/分析报告/辩论三类教训分开存、按 agent 隔离、结构化 JSON、检索后注入 | calibration 只存分数，无「为什么错」的结构化教训 | 校准 JSON 加 `lessons` 字段（reasoning/improvement/summary），debate 时注入该专家近 3 条教训 | P2 |

**不做**：TradingAgents 式多轮 LLM 辩论（token 成本高、收益存疑）。保持单轮投票 + 结构化分歧记录，把算力投给校准——这正是本项目已选对的路。

### 维度 2：数据域覆盖

对标 a-stock-data（15 层 87 端点 34 源）、InStock、TradingAgents-astock。

| # | 项 | 校准建议 | 优先级 |
| --- | --- | --- | --- |
| 2.1 | **大宗交易**（成交价量/买卖营业部/溢价率） | 东财 datacenter 单一 base URL 即可，fetcher 接入成本低；对机构动向分析有直接价值 | **P0** |
| 2.2 | **涨停原因归因 + 封板质量**（涨停原因/封板资金/板型：换手板一字板 T 字板/回封标记） | 同花顺涨停揭秘 + 东财四池；现有 zt_pool 有池无因，是短线情绪闭环的入口 | **P0** |
| 2.3 | **可转债**（转股价/溢价率/双低值） | 事件日历域自然延伸；T+0 标的池扩展 | P1 |
| 2.4 | **逐笔成交/集合竞价**（竞价异动、开盘抢筹） | 盘中监控（portfolio-web 推送）的信号源升级 | P1 |
| 2.5 | 互动易/舆情热榜、机构调研、回购方案、打新日历 | events.py 域扩展，按需 | P2 |
| 2.6 | **pytdx 优先级下调** | 2026-09 通达信公开服务器行情命令已失效（a-stock-data #52 记录），mootdx 已移末位——本项目 pytdx（优先级 9）同样暴露，建议排到腾讯/官方源之后并加探活 | **P0** |
| 2.7 | 交易所官方备胎 | 沪深官方龙虎榜/两融接口做兜底源；a-stock-data 防封铁律（批量逐股 sleep）可借鉴进 screener | P2 |

**已覆盖勿重复投入**：龙虎榜、解禁、质押、商誉、两融、股东户数、筹码、题材概念——这块本项目与最强对标基本齐平。

### 维度 3：选股 / 形态 / 情绪

对标 InStock（61 形态 + 11 策略）、Sequoia-X（6 形态策略）、vibe-astock（短线情绪闭环）、UZI-Skill（证据门控）。

| # | 项 | 校准建议 | 优先级 |
| --- | --- | --- | --- |
| 3.1 | **经典 K 线形态库** | 补 10-15 个最高频形态：吞没、锤子、射击之星、早晨/黄昏之星、乌云盖顶、曙光初现、孕线、三只乌鸦（InStock 61 种清单可参考，注意其 Apache-2.0 署名）；与现有 8 个本土战法互补而非替换 | P1 |
| 3.2 | **情绪指标组** | 赚钱效应（涨跌停比/中位数涨幅）、晋级率（连板晋级）、连板天梯、题材 5 日轮动 → 直接喂 screener 做第 16 个因子 `sentiment`；短线阵营 3 位专家辩论时引用 | P1 |
| 3.3 | **形态型策略扩充** | 海龟突破/高窄旗形/回踩年线/停机坪/无大幅回撤——InStock 11 策略中已验证的形态型，迁入 patterns/（6 策略 → 8-10） | P2 |
| 3.4 | **证据门控** | UZI 核心纪律：数据缺失不得伪装成 0 分。**已核实**：打分层 `compute_weighted_score` 缺 key 填中性 50（合理）；但归一化路径 `compute_weighted_score_with_norm` 先跑 `normalize_factors_batch`（`p.get(k, 0)` 缺值填 0 → 排到该因子最低分位），打分层的 50 兜底在此路径不触发——批量选股时缺值股被系统性打低分（analyst/event 等常缺因子占比高的策略受影响最大）。修复：归一化层缺值改中性 50 或剔除该因子并重归一权重 | **P0（已核实缺陷）** |

**领先项**：零依赖（仅 stdlib+PyYAML）在所有对标中唯一（Ashare 名为零依赖实际依赖 pandas）；缠论 8 模块自研覆盖度优于多数对标（czsc 220+ 信号函数属重型武器，不必追）。

### 维度 4：回测严谨性

对标 qlib（PIT + limit_threshold + volume_threshold）、rqalpha（A 股拒单/部分成交最完整）、vectorbt（deflated Sharpe）、Freqtrade（protections）。

| # | 项 | 本项目现状 | 校准建议 | 优先级 |
| --- | --- | --- | --- | --- |
| 4.1 | **最低佣金 5 元** | 无 | 小额交易成本被系统性低估，engine 成本模型加 `max(fee, 5.0)`——一行改动 | **P0** |
| 4.2 | **多重检验校正** | 5 档位参数寻优后直接报最优 | 引入 deflated Sharpe Ratio（vectorbt 有公式可参考）或至少报「参数敏感性平台曲线」（相邻档位收益差），警示过拟合 | **P0** |
| 4.3 | **容量约束** | 无成交量上限 | 回测买入额 ≤ 当日成交额 × 10%，超出部分部分成交；防「小盘股满仓成交」假象 | P1 |
| 4.4 | **超额指标** | 11 项绝对收益指标 + 基准对比 | 加 excess_sharpe / alpha / beta / IR（rqalpha 口径），与基准对比从「收益差」升级为风险调整口径 | P1 |
| 4.5 | **Freqtrade 保护机制三件套** | monitor 有预警，无自动熔断 | A 股化移植进 portfolio/monitor：回撤熔断（权益曲线峰谷回撤超阈值→提示降仓）、连亏熔断（N 次止损→冷却期）、冷却期（同票 N 日不再入场） | P1 |
| 4.6 | **guards vs triggers + 信号粘连** | 无此纪律 | 写进 screener/research 判定参考：「连续多根 K 线都成立的信号=进场太晚」；guards（永不进场条件）与 triggers（此刻触发）分开 | P1 |
| 4.7 | 涨跌停「跳过」→「拒单」 | 跳过该日（近似等价，可接受） | `_is_limit_or_suspended` 用「接近 ±10%」判断存在误判边界，可改用精确涨停价比较 | P2 |
| 4.8 | PIT 财报 / 历史成分防幸存者偏差 | quality 90 天延迟 | 需要公告日+版本链数据源，成本高，依赖数据可得性 | P2 |
| 4.9 | 组合层优化（逆波动率/风险平价/BL） | 等权 | portfolio rebalance 加逆波动率加权起步；BL/求解器依赖（cvxpy）违背零依赖原则，仅按需可选装 | P2 |

**领先项**：quality 因子 90 天披露延迟 + walk-forward OOS 在同类轻量回测中已属少见；涨跌停/停牌处理已有基础版（backtrader 都没有）。

### 维度 5：产品形态 / LLM 集成

对标 OpenBB（TET 数据契约 + MCP tool discovery）、Jesse（agent rules）、Freqtrade（Telegram 语义化控制）。

| # | 项 | 校准建议 | 优先级 |
| --- | --- | --- | --- |
| 5.1 | **机器可读命令契约** | OpenBB 范式：「先 --describe 再调用」——把 command→params→schema 做成机器可读 JSON（script-catalog.md 已有受管表，缺结构化产物），LLM 少翻文档、少猜参数 | P1 |
| 5.2 | **数据血缘透明化** | 本项目 v1.19.0 已有 data_sources 透传——比 OpenBB（仅凭证缺失才换源、运行时报错不换源）**领先**；补一步：降级事件（切了哪个源/为什么/损失了什么字段）写进输出尾部血缘行 | P1 |
| 5.3 | MCP server | tool discovery 折叠 + 分类白名单，避免几十个工具撑爆上下文；本项目 30+ CLI 天然可转 | P2 |
| 5.4 | agent rules 文件 | Jesse 式：把「何时用哪个 skill、字段怎么解释」固化为规则文件（部分已有：workflow.md/output-template），查漏补缺即可 | P2 |

**领先项**：熔断器 + RateLimiter + 运行时故障转移强于 OpenBB 的凭证级 fallback，这是本项目应持续对外强调的差异化；12 skill 场景化串联（workflow.md）优于多数同类的单点工具堆叠。

---

## 四、优化路线图（按收益/成本排序）

### P0（低成本高确定性，建议 v1.24.0 落地）

1. **专家 horizon 分桶结算**：校准从统一 30 天改为按专家角色分窗（长线 120 日/短线 5-10 日/行业 60 日）——`experts/calibration.py` + verify 调度。
2. **胜率卡片样本数强制**：n<10 显示「样本不足」，分离弃权/未结算。
3. **回测最低佣金 5 元**：engine 成本模型一行。
4. **deflated Sharpe / 参数敏感性平台**：寻优报告增加过拟合警示。
5. **pytdx 优先级下调 + 探活**：数据源风险对冲。
6. **大宗交易 + 涨停原因归因两个 fetcher**：东财 datacenter/push2 单一 base URL，接入成本最低的两个新数据域。
7. **证据门控修复（已核实缺陷）**：`screening_service.normalize_factors_batch` 的 `p.get(k, 0)` 使缺值股在分位数归一化中被排到最低分位（打分层的缺值填 50 兜底在归一化路径不生效）；改为缺值填中性 50 或剔除+权重重归一。

### P1（结构性增强，v1.25-v1.26）

- 弃权票第四态 + decide.md 冲突消解纪律 + slugging 口径；
- 经典 K 线形态库（10-15 个）+ 情绪因子（赚钱效应/晋级率/连板天梯）；
- 回测容量约束 + 超额指标（excess_sharpe/alpha/beta/IR）；
- 保护机制三件套（回撤熔断/连亏熔断/冷却期）进 portfolio/monitor；
- 机器可读命令契约 JSON + 数据血缘行增强；
- 可转债 + 逐笔/竞价 fetcher。

### P2（按需投入）

- 反思记忆（分层教训注入 debate prompt）、风控官确定性钳制层；
- 形态策略扩充至 8-10、互动易/调研/回购/打新、交易所官方备胎；
- PIT 财报与历史成分（依赖数据源可得性）、组合层逆波动率起步、MCP server。

### 明确不跟进（避免过度工程）

- 多轮 LLM 辩论链（token 成本高、本项目单轮投票已验证够用）；
- czsc 220+ 信号函数全量对齐（维持 8 模块自研核心）；
- BL/求解器类组合优化作为默认依赖（违背零依赖卖点）；
- GUI 工作台（Claude Code skill 形态即产品，OpenBB/Jesse 的动作已验证该赛道）。

---

## 五、顺带发现的工程问题

1. **因子缺值当 0 的真实缺陷**（见 P0 第 7 项）：`normalize_factors_batch` 缺 key 填 0 参与分位排名，与打分层「缺值填中性 50」的设计意图冲突。
2. `~/.claude/skills/monitor{,.md}` 失效软链（v1.17.0 移除 monitor skill 的本机残留）——重跑 install.sh 自检或手动删除即可。
3. 用户全局 AGENTS.md 的 skill 表仍列有 `/monitor`，与 v1.17.0 后的实际不符，建议更新。
4. README「9 因子」口径 vs 实际 15 个因子模块，建议统一表述为「6 策略 × 15 因子模块」。

---

## 六、结论

本项目的差异化根基（零依赖、运行时多源故障转移+熔断、8 专家单轮投票+胜率校准、场景化 skill 串联）在 2026 年的开源对标中依然成立且部分领先（OpenBB 的故障转移只到凭证层、Ashare 类需 pandas）。主要差距集中在四点：**专家校准的时间窗与统计口径太粗（P0）**、**回测成本与多重检验细节（P0，均为小改动）**、**短线情绪数据域缺口（大宗/涨停归因/封板质量，P0-P1）**、**经典形态库与情绪因子（P1）**。P0 全部为低风险小改动，预计 1-2 个工作日可完成一轮校准发版。

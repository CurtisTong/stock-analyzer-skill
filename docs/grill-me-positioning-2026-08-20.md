# grill-me · 项目定位压力测试报告

> 审查对象：stock-analyzer-skill 的项目定位文档簇
> 覆盖材料：`README.md`（764 行）+ `CLAUDE.md`（173 行）+ `docs/persona.md`（197 行）+ `docs/product-architecture.md`（426 行）
> 审查日期：2026-08-20 · 当前仓库版本：v1.20.2（CHANGELOG 标 2026-08-13）
> 立场：默认怀疑。每个外宣数字均已去代码核实。

---

## 一、保留项（经 Attack 仍成立）

1. **"12 个 skill"** — 真实。`skills/` 目录 12 个子目录（8 核心 + 4 变体：stock-technical / portfolio-web / portfolio-natural / learn），SKILL.md 全部带 `version: 1.20.2` frontmatter，结构一致。
2. **"8 active + 8 legacy = 16 份专家人设"** — 真实。`experts/yaml/` 下 16 个 yaml，`experts/registry.py:70-72` 有强制断言 `total == 16 and active_count == 8`。active 8 人 = lynch / soros / value_institution / topic_leader / emotion_tech / sector_specialist / risk_manager / momentum_trader，结构与 CLAUDE.md §Experts 全表一致。
3. **"6 种内置策略"** — 真实（平衡 / 质量价值 / 成长动量 / 防守低波 / 拐点修复 / ma_volume_momentum）。`scripts/strategies/registry.py:list_strategies()` 返回 6 个；SKILL.md 与 README 都按 6 种自洽。
4. **"27 个 fetcher / 35 类查询"** — 真实（按产品架构 §2.3 自报的核对口径）。`scripts/fetchers/` 下 26 个真实数据源 .py + quote 子包内含 `_base_bulk.py`（基础工具非数据源），合 27 个；按域 query 类型合计 35。
5. **"零 Python 外部依赖（核心 8 命令仅 stdlib + PyYAML）"** — 真实。`pyproject.toml` 的 `dependencies` 仅 PyYAML；其余 akshare / yfinance / efinance / pytdx 均在 `[optional-dependencies]` 或 `optional` 自检跳过。
6. **"三段任务超时 watchdog 默认 1800s"** — 真实（`scripts/screener.py:443` argparse `default=1800`，`STOCK_SCREENER_DEADLINE` 环境变量覆盖）。
7. **"OOS 验证状态机：默认 in_sample + 升级阈值"** — 真实（`registry.py:103-127` 全部 6 个策略默认 `in_sample`；CLAUDE.md 列阈值 `n_stocks ≥ 30 + win_rate ≥ 50 + total_return > 0`）。
8. **"ma_volume_momentum 71.4% 胜率为样本内拟合"** — 真实且自爆到位（`registry.py:122-126` 注释 + 5 只股票样本说明 + `in_sample` 标注）。
9. **"3 类用户画像"** — persona.md 的散户 / 学习者 / 量化三档与 README "适合谁 / 不适合谁" 矩阵、product-architecture §1.3 目标用户表口径一致。
10. **"173+ 项行业差异化"** — 实测 `industry_thresholds.json` 覆盖 8 个主行业（产品架构 §2.4 表与 JSON 一致）。

---

## 二、风险项（按 P0 / P1 / P2 排序）

### P0 · 必须现在澄清

#### P0-1 · CLAUDE.md 顶部版本号与正文内容严重错位（文档漂移的活样本）
- **声明**：`CLAUDE.md:5` 标 `> 版本：v1.19.0 | 更新日期：2026-08-05`，但正文同一文件提及 **v1.16.0 / v1.19.0 / v1.20.1 / v1.21.0** 四个版本号；其中"v1.21.0 调整为 1800s"在 CHANGELOG 中并不存在（最新就是 v1.20.2），属幻觉或未发布版本。
- **证据**：`grep -oE "v1\.[0-9]+\.[0-9]+" CLAUDE.md` 输出 `{v1.16.0, v1.19.0, v1.20.1, v1.21.0}`；CHANGELOG.md 速览表无 v1.21.0 条目。
- **建议**：把 CLAUDE.md 顶 banner 改为 `v1.20.2 | 2026-08-13`，删去 v1.21.0 引用；若该版本在规划中请改成 [Future] 标注。一行 `sed` 修复，但留着会被新读者当事实记下来。

#### P0-2 · "12 个 skill" vs "13 个 skill" 直接打架
- **声明**：`README.md` 12 个（含 stock-help）、`docs/product-architecture.md:173` 说"📡 接口层 (13 Skills)"、`docs/product-architecture.md:320` 说"13 skill + 4 变体"。
- **证据**：`ls skills/` 实际是 12 个目录（product-architecture 自相矛盾于 §2.1 与 §6.1）。
- **建议**：删除产品架构里所有 "13" 提法，统一为 "12"；这是最显眼的一处数字不一致，会被任何"二次开发者"截图引用。

#### P0-3 · 策略数 "5" 与 "6" 双口径并存
- **声明**：`docs/product-architecture.md §2.5 五因子模型` 表只列 5 个策略（缺 ma_volume_momentum），README / SKILL.md / `registry.py:list_strategies()` 都说 6 个。
- **证据**：§2.5 表格 balance/quality_value/growth_momentum/defensive/turning_point 共 5 行；§2.5 段首却写"5 种内置策略"，但实际注册了 6 个（ma_volume_momentum 为模式策略）。
- **建议**：要么在 §2.5 表加第 6 行，要么改段首为"5 种内置策略 + 1 模式策略（ma_volume_momentum）"并把表改名"主策略"。这是 README 一致性的源头，错一处就会到处抄错。

#### P0-4 · K 线 fetcher 数 "8" 与 "9" 不一致
- **声明**：`docs/product-architecture.md:99` "K线数据 | 9 | 5+ | ..." 与同文件 §4.2 "8 个 K 线源" 自相矛盾。CLAUDE.md §三层架构 写 "27 个模块 × 7 数据域"。
- **证据**：`ls scripts/fetchers/kline/*.py | grep -v __init__` 实际是 9 个（akshare/baostock/eastmoney/efinance/pytdx/sina/tencent/tushare/yfinance）。
- **建议**：§4.2 "8 个 K 线源" 改 "9 个 K 线源"。

### P1 · 需要补定义或数字

#### P1-1 · "3 分钟拿到 5 层分析"承诺无任何 benchmark
- **声明**：README 顶部 banner 含"30 秒上手"，但 §30 秒上手小节自己写"耗时取决于数据源响应；网络差时延后"，watchdog 真触发是 1800s 后 `os._exit(2)`。
- **证据**：`scripts/perf_bench.py` 文件存在但 README/CLAUDE/persona 未引用其结果；产品架构 §5 用户交互流程示例图里 `综合评分: 68分 → 偏多` 没有耗时标注。
- **建议**：要么删掉"30 秒"修辞改成"开箱即用"，要么在 README 顶部加一行实测基准（例如 `perf_bench.py` 跑出的 median / p95 秒数）。数字宣传无支撑会被同行拿来挑刺。

#### P1-2 · "理财师"用户画像仅出现在产品架构 §1.3，persona.md 没收
- **声明**：`docs/product-architecture.md:51` 把"理财师 / 客户持仓分析 / 投资建议生成"列为目标用户之一；但 `docs/persona.md` 三档画像（散户 / 学习者 / 量化）完全没有"理财师"。
- **证据**：grep "理财师" 仅 product-architecture 命中 2 处，persona.md / user_expert.md / visual_expert.md 均未提及。
- **建议**：要么把"理财师"删了（避免做出承诺却没画像），要么补一份画像档。否则任何面向 B 端的二手介绍都会基于这个无人维护的承诺展开。

#### P1-3 · "🤖 代码选股圣杯"和"⚡ HFT"在"不适合你"表格里，但产品架构 §1.2 又写"机构级分析方法"
- **声明**：README §这是什么把"代码选股圣杯"列为 ❌；产品架构 §1.2"专业性"主张"融合缠论、16 人专家圆桌等机构级分析方法"——"机构级"与"非荐股服务"两张皮。
- **证据**：同段落"零门槛/零依赖/零配置"三个"零"加"机构级"在 §1.2 表内并排；与 §7.1 竞品对比"分析深度: 缠论+专家圆桌 vs 基础指标"暗示了 B 端能力。
- **建议**：要么把"机构级"降级为"方法论覆盖广（缠论/多因子/圆桌投票）"，避免散户工具挂"机构"标签引出过度期望。

#### P1-4 · "1007 测试" 与 "1700+" 与 "589" 三个口径同时存在
- **声明**：README §核心特性行"1017 测试"；产品架构 §6.1 表"测试 1700+"；同文件 §v1.16.0 重构段"589 个 def test_，分 5 层"。
- **证据**：`grep -rE "def test_" tests/ | wc -l` = **1720**（实测）；README 数字 1017 是过时的（v1.16.0 之前）。
- **建议**：把 README 的"1017 测试"改成 `1720` 或 `1700+`，删掉产品架构里残留的"589"（v1.16.0 之前的数字，已被 v1.16.0 重构覆盖）。三套数字共存是技术债的可视化。

#### P1-5 · portfolio-natural vs portfolio-web vs portfolio 三个 skill 共享同一脚本入口
- **声明**：README §12 skill 速查 把 portfolio / portfolio-web / portfolio-natural 列为三个独立 skill；实际 `allowed-tools` 全部含 `Bash(python3 scripts/portfolio_web.py *)`。
- **证据**：`grep "portfolio_web" skills/portfolio*/SKILL.md` 三处均出现。
- **建议**：要么在 SKILL.md 注明"portfolio-natural 是 portfolio 的 NL 触发词典，portfolio-web 是 portfolio 的 HTTP 入口"，避免用户以为有三个独立 CLI 进程——CLAUDE.md §Skill 索引表倒是注明了，README 没。

### P2 · 细节 / 一致性 / 风格

#### P2-1 · "8 位活跃专家圆桌 = 5 长线 + 3 短线"在多处文件出现，但 active 8 人里 "短线" 边界模糊
- 5 长 = value_institution / lynch / soros / sector_specialist / risk_manager；3 短 = topic_leader / emotion_tech / momentum_trader。CLAUDE.md 与 README 与产品架构一致，但 `experts/vote_engine.py:418` 注释只写"5 长线 + 3 短线"，未列名。**建议**：在该注释里加一行 `5长=value_institution/lynch/soros/sector_specialist/risk_manager; 3短=topic_leader/emotion_tech/momentum_trader`，方便后人排错时不踩坑。

#### P2-2 · "1800s watchdog 兜底"宣传与 README "3 分钟"修辞互相打脸
- README §快速上手 写"耗时取决于数据源响应；网络差时延后"，但 §核心特性 又写"集成熔断器，单源故障自动切换下家"——并未说兜底耗时。可在 README 顶部加一行"`watchdog 真超时默认 1800s`"链接到 `CLAUDE.md §项目概述`，让用户自己评估。

#### P2-3 · README §架构图 与实际目录树 有一处不一致
- README §架构图：`scripts/business/ ... scripts/common/ ... scripts/config/ ... scripts/data/ ... scripts/fetchers/ ... scripts/strategies/ ... scripts/technical/ ... scripts/monitor/ ... scripts/portfolio/`
- 实际：`scripts/` 顶层还有 `chan/` `chan.py` `chip.py` `classifier.py` `events.py` `concept.py` 等脚本没在 README 架构图里出现。
- **建议**：README §架构图仅画层级，不要逐文件；要么补一句"完整脚本列表见 `scripts/`"。

#### P2-4 · "27 个 fetcher" 在 4 个文档里出现，README/CLAUDE/产品架构各写一遍，但 _base_bulk.py 是否计入口径没说清
- 产品架构 §2.3 自报 "quote 10"，但 `ls scripts/fetchers/quote/*.py` 实测 11 个（含 _base_bulk.py）。**建议**：明确 `_base_bulk.py` 是否计入 27 个，否则每次删/加文件就要回 4 处文档同步。

#### P2-5 · docs/persona.md 数据来源"基于 D3 用户访谈 + 5 个高频用户试用实录"无出处链接
- 这是定位文档里唯一的"事实性引用"，但 D3 / 5 用户 / 试用实录都没有链接或附录。**建议**：要么补链接到原访谈纪要，要么降级为"基于内部访谈与试用观察"。

---

## 三、待澄清项（Attack 中发现的事实空白）

| # | 问题 | 为什么要问 |
|---|---|---|
| Q1 | CLAUDE.md 提到的 v1.21.0 watchdog 升级到 1800s，这条信息是来自未发布规划还是文档笔误？ | 决定它该留作 Forward-looking 引用还是直接删除。 |
| Q2 | "理财师"画像只挂在产品架构 §1.3，是 B 端未启用的占位还是有真实诉求？ | 决定要不要补 persona / user_expert 两份画像。 |
| Q3 | `tests/` 实际 1720 个测试，README "1017" 是 v1.16.0 之前的快照，产品架构"1700+"是哪一次？ | 决定哪个数字作废。 |
| Q4 | `_base_bulk.py` 是工具类（不算 fetcher）还是数据源？产品架构"quote 10"把它算进去还是排除？ | 决定 fetcher 总数是 26 还是 27。 |
| Q5 | OOS 验证 "n_stocks ≥ 30 + win_rate ≥ 50 + total_return > 0" 三个阈值的样本来源是什么？是经验还是某次回测结果？ | 决定 CLAUDE.md 该不该展开为 §strategy-validation.md 的小节。 |
| Q6 | "3 分钟拿到 5 层分析"如果删掉，没有任何 baseline；如果留，是基于哪台机器 / 哪个数据源 / 哪个交易日？ | 决定这个修辞是删还是补测试结果。 |
| Q7 | product-architecture §3.1 ASCII 图写"数据源: 财务数据 (3 数据源)"，§2.3 表写"财务数据 | 2 |"，以哪个为准？ | 财务 fetcher 实测 3 个（akshare_balance / akshare_finance / eastmoney_finance），§2.3 表里 2 是漏数。 |
| Q8 | 行情 fetcher "10"（产品架构 §2.3）vs `scripts/fetchers/quote/*.py` 实测 11 个，哪一处错了？ | 同 Q4。 |
| Q9 | README §已知限制 第 4 条说"回测财务数据存在前瞻偏差防护"，但 CLAUDE.md / 产品架构都没复述——这是只在 README 兜底还是另有 SPEC 文档？ | 决定这个安全网是单点还是设计意图。 |
| Q10 | `experts/yaml/` 下 16 个 yaml，每个文件至少 1200+ 字深度档（README §16 份专家人设），但 README 链接只指向 `experts/*.md` 而非 `experts/yaml/*.yaml`，新人点进去对不上。 | 决定 README 链接该指向哪个。 |

---

## 四、下一步行动（按优先级排，每条可一轮完成）

1. **修 CLAUDE.md 顶部 banner**：`v1.19.0 | 2026-08-05` → `v1.20.2 | 2026-08-13`，并删除/标注 v1.21.0 引用。10 分钟。
2. **删 product-architecture.md 全部 "13 Skills" 提法**，统一为 "12"（§2.1、§6.1 各 1 处）。5 分钟。
3. **product-architecture.md §2.5** 加 ma_volume_momentum 第 6 行，或改名表为"主策略"并补"模式策略"表。10 分钟。
4. **product-architecture.md §4.2** "8 个 K 线源" → "9 个 K 线源"。1 分钟。
5. **README §核心特性** "1017 测试" → "1720 项测试（v1.20.2 实测）"。1 分钟。
6. **product-architecture.md §v1.16.0 段** "589 个 def test_" 删掉或改为"v1.16.0 重构后扩至 1700+"。2 分钟。
7. **product-architecture.md §2.3 财务数据** "2" → "3"（实测 akshare_balance / akshare_finance / eastmoney_finance）。1 分钟。
8. **portfolio/portfolio-web/portfolio-natural 三个 SKILL.md** 在文件头部加一行相互引用注释："本 skill 是 portfolio 的子模块（NL 词典 / Web 入口）"。15 分钟。
9. **README §架构图** 加一句"完整脚本列表见 `scripts/`"，并把 K 线 fetcher 数从 7/8 修到 9。5 分钟。
10. **decide** 是否补 persona.md "理财师"画像档（基于 Q2 回答再决定）。

---

## 五、立场结论

**这个项目定位整体站得住，但正在被多处"小不一致"稀释可信度。** 12 skills / 16 专家 / 6 策略 / 27 fetcher / 1800s watchdog / OOS 默认 in_sample / ma_volume 71.4% 是样本内拟合 这些**核心骨架全部经得起核实**，CLAUDE.md 自爆机制（`@silent_fallback` / OOS 默认值 / 5 长 3 短注释）做得相当扎实，说明维护者对"承诺 vs 现实"这件事是有意识的。

真正的风险不在"哪里说错了"，而在"同一个数字在 4 个文档里写了 4 个版本"——`13 vs 12 skills`、`5 vs 6 策略`、`8 vs 9 kline`、`1017 vs 1700+ vs 589 tests`、`27 fetcher` 的 _base_bulk.py 是否计入没说清。**这些不是 bug，是没收回的散弹**：每修一处 README，就要在 CLAUDE.md / 产品架构 / persona.md / changelog 同步重数一次，否则下次新人 onboarding 会被这些数字绊一遍。

**项目值不值得继续？值得。** 它确实把 A 股分析封装成 12 条命令 + 多源容错的形态自洽了，且有真实 fetcher / 真实策略 / 真实 watchdog / 真实 OOS 兜底。但**接下来的发版节奏里，"数字单源化"应作为 P0**：建一个 `data/project_meta.json` 或在 `pyproject.toml` 注释里集中维护 skill 数 / fetcher 数 / 测试数 / watchdog 默认值，让 4 份文档都从这同一个事实源派生，否则这套不一致会随版本号越长越多。

—— 完 ——
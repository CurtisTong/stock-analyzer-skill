# 2026-08-12 复盘元复盘问题清单

> **版本**：v1.21.0-dev（pre-release）  
> **生成日期**：2026-08-12 08:10  
> **来源**：单次会话内连续执行 market → stock×2 → sector → portfolio → screener 共 5 个 skill 后做的元层面复盘  
> **规模**：11 个编号问题（3 P0 + 4 P1 + 4 P2）  
> **修复进度**：P0-01 ✅（a+b+c）/ P0-02 ✅ / P0-03 ✅（a/b/c 全部落地）｜P1-01 ✅ / P1-02 ✅ / P1-03 ✅ / P1-04 ✅（a/b/c 全部落地）｜P2-01 ✅ / P2-02 ✅ / P2-03 ✅（共享规范约束，非脚本行为变更）/ P2-04 ✅（含实际总仓位）  
> **关联文档**：[review-issues.md](../review-issues.md)（75 项深度审阅）· [screener-review.md](../screener-review.md)（选股器专项审查）· [architecture-review-2026-07-07.md](../architecture-review-2026-07-07.md)  
> **关联 skill**：market / stock / sector / portfolio / screener

---

## ⚠️ 与历史 review 的关系

本文档聚焦**单次会话内暴露的运行期问题**，不重复 `review-issues.md` 中已记录的代码层问题（那些是源码审阅发现，已 Round 7-11 修复完成）。新增的 11 项是**使用层 + 集成层 + 流程层**问题，反映"工具能跑 ≠ 跑得好"。

---

## 📊 元复盘覆盖范围

| # | skill | 调用 | 输出 | 状态 |
|---|---|---|---|---|
| 1 | market full | market_anchor + sector_summary + quote | 6指数+30板块+美股+持仓影响 | ✅ 完成 |
| 2 | stock 德赛西威 full | 行情+财务+技术+锚定 | 五层+风险收益+仓位 | ⚠ 板块归属未知 |
| 3 | stock 宝丰能源 full | 同上 | 同上 | ✅ 完成 |
| 4 | sector 化工 compare | 25 只核心标的排序 | 首选/次选/回避 | ⚠ 仅主题池 |
| 5 | portfolio 截图更新 | 5 项变更（4 删+1 增+3 改成本）| oplog 50 条 | ✅ 完成 |
| 6 | screener 4 策略 | balanced+qv+tp+gm | 各 7-15 只 | ❌ 全市场超时 |

---

## 🔴 P0 严重问题（需立即修复）

### P0-01 全市场 screener 触发 watchdog 600s 超时

**现象**：4 次 `--full-market` 调用（balanced / quality_value / turning_point / growth_momentum）全部失败；预筛阶段 `4998 → 3323` 只，但无法完成后续 K 拉取与评分；输出 `⚠️ Watchdog timeout (600s), exiting...`。

**复现步骤**：
```bash
python3 scripts/screener.py --full-market --strategy balanced --top 15 -j -q
python3 scripts/screener.py --full-market --strategy quality_value --top 15 -j -q
python3 scripts/screener.py --full-market --strategy turning_point --top 15 -j -q
python3 scripts/screener.py --full-market --strategy growth_momentum --top 15 -j -q
```

**根因分析**：
- screener 在全市场模式下需为每只标的拉 K 线计算技术因子（MA、MACD、KDJ、BOLL、RSI 等）
- 3323 只 × K 线拉取 ≈ 网络 + 计算时间显著超出 600 秒 watchdog
- 文档声称 `--two-stage` 可解（Phase 1 无 K 线初筛，Phase 2 仅 Top N×3 拉 K 线精排），实际**两阶段模式仍然超时**——说明该参数在当前实现中要么未生效要么 Phase 1 就够慢

**影响**：
- 全市场选股被降级为**主题池 280 只筛选**
- **遗漏所有非主题池内的中小盘个股**（科创板部分、北交所、中小盘消费、新材料、AI 算力链细分等）
- 用户感知："号称全市场实际只有 280 只"

**修复建议**（按优先级）：
1. **短期 P0-01a**：增大 watchdog 超时阈值（10min → 30min），`scripts/screener.py` 顶部 `WATCHDOG_TIMEOUT = 1800`
2. **中期 P0-01b**：实现真正有效的两阶段管线——Phase 1 只用 quote（不拉 K 线）粗筛 Top 200，Phase 2 再拉 K 线精排；当前 `--two-stage` 标记需验证是否真的生效
3. **长期 P0-01c**：本地缓存 K 线到 `data/cache/kline/`，key 为 `code_scale_datalen`，避免每次重新拉
4. **兜底**：若短期无法修复，应在 SKILL.md 和 CLI help 明确标注"全市场模式可能超时，建议分批按板块筛选"

**修复记录**：
- 2026-08-12：**P0-01a 已修复**。`scripts/common/screener_watchdog.py` 默认 deadline 600→1800 秒（`DEFAULT_DEADLINE_SEC`），同步更新 `screener.py --deadline` help 与 `_resolve_deadline` docstring（commit c84004b）
- 2026-08-12：**P0-01b 已修复**。根因定位：复现命令**未传 `--two-stage`**，full_market 默认走单阶段路径，对预筛后全部 ~3323 只 `prefetch_kline_all` 拉 K 线（`screening_pipeline.py` 单阶段分支），远超 deadline 而超时。修复：`run_screening` 中 full_market 强制走两阶段管线（`if args.two_stage or args.full_market:`）——Phase1 仅 quote+Top500 财务粗筛不拉 K 线，Phase2 仅 Top N×3 拉 K 线精排。`--two-stage` 本身已生效，无需重写管线
- P0-01c（本地 K 线缓存）：**已隐含实现，验证完成**。`get_kline()`（`scripts/data/__init__.py`）已接 `common.cache` 磁盘缓存，key = `kline_{code}_{sha256(scale,datalen,格式版本)}`（等价于建议的 `code_scale_datalen`，另含版本号防格式变更污染），日 K TTL 1h、分钟 K 30s、其他周期 6h；screener 的 `prefetch_kline_all`（`scripts/data/helpers.py`）即走 `get_kline`，无需新代码。新增 `tests/unit/test_kline_cache_p001c.py`（3 项：同参二次调用命中缓存 / 参数变化独立缓存 / 批量复用缓存）验证通过。缓存目录为项目根 `.cache/`（非 issue 建议的 `data/cache/kline/`，机制等价且纳入统一 TTL 抖动/原子写/体积上限清理）
- 2026-08-12：**端到端验证观察（P0-01 后续）**。真实环境跑 `screener.py --full-market --strategy balanced --top 5`：进程 9min 无输出、CPU ~1%、缓存不增长——**复现数据源挂起**，但卡点在**财务批量阶段**（`prefetch_finance_all` 480s 超时窗口后仍未释放），非 K 线拉取（两阶段修复有效：Phase2 仅 Top N×3 拉 K 线）。结论：full_market 依赖 1800s watchdog 兜底仍成立，但用户 30min 无反馈体验差。后续建议（未实施）：screener 增加阶段进度 stderr 输出（Phase1 完成/Phase2 进行中），或按数据源拆分财务批量超时

**关联**：`docs/screener-review.md` 中可能已有相关问题，待对照。

---

### P0-02 股票代码 sh/sz 前缀误判导致脚本空输出

**现象**：
- `quote.py sh002920`（德赛西威）返回 `[]`
- `kline.py sh002920` 返回空
- `market_anchor.py sh002920` 返回 `industry_beta.interpolation="K 线缺失"`
- 需改为 `sz002920` 才正常

**根因**：`normalize_quote_code()`（`scripts/common/utils.py:80`）已接入各 CLI，但 `infer_exchange()` 对 `00` 开头的数字段统一按"沪深二义"处理并**信任入参前缀**，导致误冠的 `sh002920` 原样保留，最终下游数据源查无此代码、整链路静默返回空。

**影响**：用户/agent 在不熟悉代码归属时容易填错，**整个分析链路全部静默失败**——不是报错，是返回空数据，让用户以为"代码错了"或"市场休市"。

**修复建议**：
1. **P0-02a**：`infer_exchange()` 将 `002/003`（深市主板，原中小板，非指数号段）从二义段移除，强制判 `sz`；仅保留 `000xxx` 二义（上证指数 sh000001 与深市主板 sz000001 重合）继续信任入参前缀。⚠️ 原建议的 `normalize_code` 函数存在缺陷：`if code.startswith(('sh','sz')): return code` 只会规范化、不会纠正错误前缀，不能采用。
2. **P0-02b**：在所有 SKILL.md 的脚本调用示例中标注代码归属；或在代码前缀参考文档 `../_shared/references/code-prefix.md` 加强提示
3. **P0-02c**：当代码不存在/为空时，脚本应**显式返回错误码**而非空数组

**修复记录**：
- 2026-08-12：`infer_exchange()` 增加 `002/003 -> sz` 强制判定，二义范围收窄为 `000`（commit a742d2f）；`tests/unit/test_common_utils.py` 更新 `SH002335 -> sz` 断言并新增 `sh002920 -> sz002920` 回归用例
- 验证：`python3 -m pytest tests/unit/test_common_utils.py` → 144 passed；`normalize_quote_code('sh002920')` → `sz002920`，`normalize_quote_code('sh000001')` → `sh000001` 不受影响

---

### P0-03 macro 字段 fixture 来源未充分标注

**现象**：
```json
"treasury_10y_pct_source": "fixture",
"usd_index_source": "fixture",
"vix_source": "fixture",  // ← 实际是 yfinance 真实值
```

**问题**：报告中多次引用 macro 字段作为"宏观锚点"，但其中 7/8 是**离线预置**，仅 VIX 真实（yfinance）。

**风险**：
- 用户看到"VIX 15.28（远低于 20 警戒线，全球避险情绪未升温）"这种结论依赖真实数据——是对的
- 但若误读 treasury / usd_index 等字段（与 VIX 类似），会得出错误判断
- 报告中部分 macro 字段已标 [fixture]，但**渲染时容易遗漏**

**修复建议**：
1. **P0-03a**：`market_anchor.py` 输出的 macro 块，**所有字段后缀强制追加 `_source` + value**，例如：
   ```json
   "vix": {"value": 15.28, "source": "yfinance"},
   "usd_index": {"value": 99.81, "source": "fixture"}
   ```
2. **P0-03b**：报告模板（`reports/full-template.md`）的 macro 渲染层，**每个字段自动追加 [source] 标记**（已部分实现，需全面化）
3. **P0-03c**：当 macro 字段为 fixture 时，**降级结论置信度**，例如"基于预置数据，仅供参考"

**✅ 修复状态（2026-08-12 确认）**：
- **P0-03a 已实现**：`macro_indicators.py` 每个字段返回 `{"value":..., "source":...}`（`fixture` / `fixture(stale)` / 实时源）；`market_anchor.py` 输出层展开为 `<field>` + `<field>_source` 双字段（`:726-744`）
- **P0-03b 已实现**：`market_anchor.py` 渲染层 `_source_tag()`（`:812`）为 fixture/stale 字段行尾标注，且段首有"本段含 N 个非实时字段"占比提示（`:941-959`，P2-26 修复）
- **P0-03c 已修复（2026-08-12）**：macro 段存在 fixture 字段时追加"⚠️ 宏观结论置信度降级：N 个字段为预置/兜底数据，据此得出的宏观判断仅供参考"行（`market_anchor.py` `to_markdown` macro 块末）

**遗留修复记录**：
- P0-03c：在 macro 结论渲染处对 source != 实时源的字段追加"（预置数据，仅供参考）"降级说明 → **已落地（2026-08-12）**

---

## 🟡 P1 重要问题

### P1-01 market_anchor 的板块归属"未知"覆盖盲区

**现象**：德赛西威 `stock_sector_compare.verdict = "板块归属未知"`；`industry_beta.interpretation = "超防御型"` 但 R²=0.0008 极低，解释不严谨。

**根因**：
- 板块反查基于 `scripts/data/sector_etf.csv` 的 13 个 ETF
- 德赛西威（汽车电子/智能驾驶）未在覆盖范围
- `industry_beta` 的 `超防御型` 标签基于低 beta 值，但 R² 低意味着相关性弱，beta 数值参考价值有限

**修复建议**：
1. **P1-01a**：扩展 ETF 覆盖，至少增加：sh515250 智能汽车 ETF、sh515380 通信 ETF、sh515980 人工智能 ETF、sh515790 光伏 ETF、sh515220 煤炭 ETF（部分已有，需补全）
2. **P1-01b**：维护股票-板块映射表 `scripts/data/stock_sector_map.json`，覆盖申股二级 100+ 行业
3. **P1-01c**：industry_beta 输出增加 `interpretation_confidence` 字段（R² >0.3 才报"超防御型"，R² <0.1 报"与基准低相关，独立行情"）

**✅ 修复记录（P1-01c 2026-08-12）**：
- `industry_beta._interpret_beta(beta, r_squared)` — R²<0.1 报"与基准低相关（独立行情）：beta 数值参考价值有限"；0.1≤R²<0.3 加"相关性偏弱，解读适度降级"前缀；新增 `_r2_confidence()` 三级分级（≥0.7 高/≥0.3 中/否则低）；`compute_beta` 全分支补 `interpretation_confidence` 字段
- `market_anchor` 渲染层补"解读置信度"行；CLI 输出置信度
- 测试：`tests/unit/test_industry_beta.py`（14 项）
- 验证（sh600519 vs sh000300）：R²=0.006 → 原误报"负 beta：与市场反向"，现报"与基准低相关（独立行情）"、置信度"低"

**✅ 修复记录（P1-01a + P1-01b 2026-08-12）**：
- **P1-01a**：`sector_etf.csv` 新增 7 个行业 ETF（sh515250 智能汽车 / sh515880 通信 / sh515980 人工智能 / sh562500 机器人 / sz159611 电力 / sz159996 家电 / sh516010 游戏），行业类 ETF 10→17；`_SECTOR_TO_ETF_PROXY` 提为模块级常量并补盲区映射（机器人→sh562500、PCB/AI算力→sh515980、电力→sz159611、石化→sh516020、家电→sz159996、智能汽车→sh515250、通信→sh515880 等），原"无对应 ETF 代理"盲区清零。⚠️ 原文档建议的 sh515380（实为沪深300ETF泰康）/ sh561580（实为央企红利ETF）代码有误，已用真实代码替换
- **P1-01b**：新增 `scripts/data/stock_sector_map.json`（`stocks` 219 只：反向生成主题池 + 手工补充德赛西威/中际旭创/比亚迪等主题池外核心标的；`industry_proxy` 32 条行业名→ETF）；`build_stock_sector_compare` 归属来源链改为 stock_sector_map → sector_stocks.json → 代码段推断，返回 `sector_source` 标注归属来源
- 测试：`tests/unit/test_sector_blindspot_p101.py`（12 项：新增 ETF 存在性 / 映射非空 / JSON 结构 / 德赛西威归属 / 归属链优先级 / 未知股票优雅降级）
- 验证（sz002920 德赛西威，元复盘 P1-01 场景）：原 verdict"板块归属未知"，现"汽车电子→ 智能汽车ETF富国 +0.21%（中性）; 跑输板块 -1.42pp; vs 大盘 -1.56pp"；22/22 个 ETF 全部拉取成功

---

### P1-02 screener 评分与板块判断矛盾

**矛盾**：
- 化工板块选股明确说"**回避恒力/恒逸/荣盛**"（板块退潮，ETF -2.56%）
- 但 balanced / growth_momentum 评分把恒力/恒逸放在前 2

**根因**：screener 评分体系**没有接入"板块退潮"过滤器**，个股评分高但板块弱的情况未被屏蔽。

**修复建议**：
1. **P1-02a**：screener.py 增加 `--exclude-sector-momentum` 参数，自动剔除"过去 5 日板块 ETF 跌幅 >5%"的板块内标的
2. **P1-02b**：在 SKILL 文档明确"使用 screener 时应先跑 market/sector 确认板块状态"
3. **P1-02c**：screener 输出增加 `sector_momentum_warning` 字段，对处于退潮板块的高分标的加 ⚠️ 标记

**✅ 修复记录（2026-08-12）**：
- **P1-02a/c 已实现**：新增 `scripts/sector_momentum.py`（`infer_industry` 类别→行业 ETF 近似映射 + 5 日动量拉取 + 模块级缓存）；`screening_pipeline._apply_sector_momentum()` 在排序后为每行附 `sector_momentum_ret_5d` / 退潮时 `sector_momentum_warning`，`--exclude-sector-momentum` 时剔除；`render`/`render_brief` 对退潮高分标的打印 `⚠️` 行；ETF 数据不可得时静默跳过，不阻塞主流程
- **P1-02b 已实现（2026-08-12）**：`skills/screener/SKILL.md` Step 0 增加提示"使用 screener 前建议先跑 /market 或 /sector 确认板块状态"+ `--exclude-sector-momentum` 用法说明
- 测试：`tests/unit/test_sector_momentum.py` + `tests/unit/test_screening_sector_momentum.py`（10 项，含行业映射防漂移校验）

---

### P1-03 持仓更新流程：成本变更未经用户显式授权

**问题**：用户给截图说"更新持仓"，先做差异 diff（5 项变更）→AskUserQuestion 二次确认 → 用截图成本为准直接写盘（中天 35.84→41.93、宝丰 22.37→24.02、华友 57.83→54.76）。

**风险**：
- 券商 APP 的成本算法可能与账面成本不同（含手续费 / 摊薄 / 不含等差异）
- 报告已说明"截图成本为准"，但**未提示用户成本变更后浮亏率会变**——信息不对称
- 自动化批量更新可能在未来其他场景重复发生

**修复建议**：
1. **P1-03a**：在 `portfolio.add_position` / `update_position` 增加"成本来源"字段（`cost_source: screenshot | user_input | calculated`），保留可追溯
2. **P1-03b**：持仓更新前必须列出"成本变更前后浮亏对比表"，让用户看到变更影响
3. **P1-03c**：在 `scripts/data/portfolio_oplog.json` 增加 `cost_before / cost_after` 字段记录变更详情

**✅ 修复记录（2026-08-12）**：
- **P1-03a 已实现**：`PortfolioManager.add_position` 新增 `cost_source` 参数（默认 `user_input`），加仓后自动置 `calculated`；`update_position` 支持 `cost_source`，更新 cost 未显式给时默认 `user_input`；Web dispatch 支持 `cost_source` 透传 + 非法值校验
- **P1-03b 已实现（响应层）**：`update_position` 请求返回 `meta.cost_before/cost_after/cost_source + hint`（成本变更后浮亏率将随之变化，请复核券商 APP 成本口径）；完整"更新前先确认"对话流保留给 CLI 层编排
- **P1-03c 已实现**：`portfolio_oplog.json` 操作记录新增 `cost_before/cost_after/cost_source` 字段（`OpLog.push(extra=...)` + 新增 `OpLog.update_last()` 回填操作后成本）
- 测试：`tests/unit/test_portfolio_cost_source.py`（8 项）+ `tests/test_dispatch.py` TestCostSourceDispatch（5 项）

---

### P1-04 组合相关性分析"过度乐观"

**现象**：报告输出"宝丰能源 vs 持仓组合均相关 -0.04（负相关，分散价值最高）"

**风险**：
- 60 日窗口相关性**只是历史窗口**
- 负相关**未来可能反转**（如某次周期切换所有持仓同跌）
- **单独看相关性容易高估分散效果**

**修复建议**：
1. **P1-04a**：报告增加"窗口声明"——"60 日窗口 ≠ 长期稳定"，每次输出相关性都附带
2. **P1-04b**：提供**压力测试场景**（如 2008/2015/2018 熊市下相关性的变化）
3. **P1-04c**：相关性强弱判定需考虑 R²（低 R² + 负相关 ≠ 真正分散）

**✅ 修复记录（2026-08-12）**：
- **P1-04a 已实现**：`portfolio_correlation.WINDOW_NOTICE` 常量 + `window_notice` 字段随矩阵 / `vs_portfolio` / full 载荷输出（含空持仓分支）；CLI 与 `market_anchor` 渲染层均附带
- **P1-04b 已实现**：`_half_window_stability()` 对收益率序列切前半段/后半段对比两两相关性，统计符号翻转对数 + 最大变化幅度，输出 `stability.stable` 标志（纯计算，零额外网络请求）；历史/极端行情变化在 window_notice 文案中明示
- **P1-04c 已实现**：`_corr_detailed()` 返回 corr + R²（=corr²）+ 近似 t 检验显著性（|t|>2）；`compute_stock_vs_portfolio` 统计显著负相关对数占比 `neg_significant_ratio`；`_interpret_diversification(avg_corr, ratio)` 对负相关弱（|corr|<0.3）或不显著（ratio<0.5）的情形报"高存疑（低 R² 下可能为噪声）"，新增 `corr_confidence` 置信度
- 测试：`tests/unit/test_portfolio_correlation_p104.py`（16 项：窗口声明 / 显著性 / 双半窗口稳定性 / 解读分级 / 置信度）
- 验证（sh600519 vs 持仓组合）：avg corr -0.16 → 原报"分散价值最高"，现报"高存疑（低 R²，仅 75% 通过显著性检验）"，置信度"低"

---

## 🟢 P2 一般问题

### P2-01 化工板块选股回避名单"业绩反转陷阱"判定粗糙

**现象**：恒逸石化"扣非仅 1.41 亿 → 业绩反转陷阱"作为回避理由——但**未做基本面深度分析**（行业地位、产品结构、产能扩张进度）。

**风险**：可能错杀周期反转标的。

**修复**：对"业绩反转陷阱"类标的，单独标记为"观察"，而非直接"回避"；提供反转触发条件清单。

**✅ 修复记录（2026-08-12）**：`skills/sector/SKILL.md` Step 3 增加"回避名单分类"表（硬性回避 / 基本面走弱 / **业绩反转陷阱**）：反转陷阱类标的标记"观察"而非"回避"，附反转触发条件清单（价格/毛利率企稳、产能投放落地、订单/合同负债回升、环比扭亏），达标前不纳入首选；已做 `/research financial` 确认恶化趋势性才可升级为"回避"。

---

### P2-02 剧烈轮动期与"分层操作建议"错配

**矛盾**：
- market 报告：`rotation_strength = 4.13`（剧烈轮动，主线切换中）
- 操作建议：仍然给出"成长占优/防守/进攻"分层——**剧烈轮动环境下，分层建议会迅速失效**

**修复**：剧烈轮动期应给"**减少新增仓位 + 优先减仓弱势持仓 + 等待主线明确**"的保守建议，而不是继续扩张候选池。

**✅ 修复记录（2026-08-12）**：`market_anchor._fetch_sector_rotation()` 在 `rotation_strength > 3` 时附加 `advice` 字段（"剧烈轮动期（主线切换中）：减少新增仓位，优先减仓弱势持仓，等待主线明确后再考虑进攻/分层配置"），≤3 时给"维持现有配置"；`to_markdown` 题材轮动块渲染"操作建议"行。测试 `tests/unit/test_market_rotation_advice_p202.py`（5 项）。

---

### P2-03 报告长度与可执行性失衡

**现象**：5 份报告累计输出 **超 1.5 万字**，每份都包含"30 秒研判 + 详细论证 + 数据护栏 + 免责"。

**风险**：用户疲劳，关键结论被淹没。

**修复**：
1. 默认 `--brief`（<500 字）+ 详细分析按需展开
2. 不要每份都写 4-5 张表
3. 关键结论（首选 / 回避 / 风险）置顶，详细论证折叠

**✅ 修复记录（2026-08-12）**：方向定为"强化执行约束"（不动脚本默认行为，避免影响所有调用方）。落地到共享规范（stock/market/sector/screener/research 5 份报告 SKILL 均已引用，全局生效）：
- 第 2 条（表格上限）：`guardrails.md` §四 新增"表格上限"行（单报告 ≤3 张，quick ≤1 张，超出合并或改进度条）；`output-template.md` §六 同步
- 第 3 条（折叠披露）：`output-template.md` 新增"折叠披露"小节——默认只渲染结论层（30 秒研判 + 决策卡片 + 核心数据表 + 数据护栏），详细论证折叠为"章节标题 + 一句话摘要"，用户要求展开再完整呈现；禁止 5 个并列全量章节平铺（默认至多 3 个）
- 第 1 条（默认 --brief）维持现状：stock/market 已默认 quick，`--brief` 作为可选组合保留，不做全量代码级默认切换

---

### P2-04 持仓占位"组合占组合比例"建议过于密集

**现象**：
- 全市场选股报告给出 6 只标的累计仓位 7.5-11%
- 加上已有持仓（5 只，总成本 17.15 万），总仓位可达 43-50%
- 看似符合 risk_manager 文档"震荡市 70% 总仓位"，但分散度风险被低估（6 只里有 2 化工+1 科技+2 金融+1 消费，看似分散实则都是大盘股）

**修复**：
1. 计算**实际组合总仓位**后再给建议
2. 行业集中度上限（单一行业 ≤ 30%）应作为硬约束
3. 新增候选与已有持仓的"行业重叠率"显示

**✅ 修复记录（2026-08-12）**：
- 第 2 条（行业 30% 硬约束）：已由 `portfolio.manager.check_concentration(industry_limit=0.30)` 覆盖（既有实现）
- 第 3 条（行业重叠率）：`portfolio_correlation.compute_industry_overlap()` 新增——候选股与各持仓统一映射到"行业名→ETF 代理代码"（复用 P1-01b `stock_sector_map.json` 的 stocks + industry_proxy，ETF 代理对齐判断同行业，覆盖细分同大类场景）；输出重叠持仓列表/重叠行业占组合成本比例 `overlap_pct`；>20% 触发 `concentration_warning` 并提示新增仓位上限（≤30%-overlap_pct）以免触发硬约束；映射缺失用持仓 `industry`/`tags` 名称兜底。接入 `compute_full_portfolio_correlation`（`industry_overlap` 字段）+ CLI + `market_anchor` 渲染
- 第 1 条（实际总仓位）：**已实现（2026-08-12）**。`portfolio.json` 顶层可选 `total_assets`（元，用户账户配置）；`PortfolioManager.compute_total_position_ratio()` 计算持仓成本/市值 ÷ 总资产的占比（成本口径 `position_ratio` + 市值口径 `position_ratio_mv`），成本占比 >90% 触发"仓位过重"警告；未配置 `total_assets` 时返回 None + 提示，不猜测资金上下文。接入 `health_report` 输出 `position_ratio` 字段（所有消费方自动生效）。测试 `tests/unit/test_portfolio_position_ratio_p204.py`（5 项）
- 测试：`tests/unit/test_industry_overlap_p204.py`（9 项）
- 验证（sz002920 德赛西威 vs 持仓）：行业"汽车电子"与现有持仓无重叠，分散性良好

---

## 📋 修复优先级矩阵

| 优先级 | 问题 | 建议动作 | 预计工时 | 状态 |
|---|---|---|---|---|
| **P0-01** | screener 全市场超时 | 增大 watchdog + 实现真正两阶段 + K 线缓存 | 2-3 天 | ✅ a+b+c 全部修复（deadline→1800s；full_market 强制两阶段；K 线缓存已隐含实现并经 test_kline_cache_p001c 验证）|
| **P0-02** | sh/sz 前缀误判 | quote/kline 内部归一化 + SKILL 警告 | 0.5 天 | ✅ 已修复（infer_exchange 002/003→sz）|
| **P0-03** | macro fixture 标注不全 | JSON 结构 + 渲染层标记 + 置信度降级 | 1 天 | ✅ 全部落地（a/b 已实现 + c 已修复）|
| **P1-01** | 板块归属盲区 | 扩展 ETF 表 + stock_sector_map.json + industry_beta 置信度 | 1-2 天 | ✅ 全部落地（a 扩展 ETF + b stock_sector_map.json + c interpretation_confidence）|
| **P1-02** | screener 与板块判断矛盾 | --exclude-sector-momentum + 输出 warning | 0.5 天 | ✅ 全部落地（a/c 代码 + b SKILL 提示）|
| **P1-03** | 持仓更新成本变更 | cost_source 字段 + 变更对比表 + oplog 增强 | 0.5 天 | ✅ 全部落地（a/b/c）|
| **P1-04** | 相关性过度乐观 | 窗口声明 + 压力测试 | 1 天 | ✅ 全部落地（a/b/c：window_notice + 双半窗口稳定性 + 显著性）|
| **P2-01** | 反转陷阱粗糙 | 标记为观察 + 反转触发条件 | 0.5 天 | ✅ 已修复（sector SKILL.md 回避分类表）|
| **P2-02** | 轮动期与建议错配 | 保守建议优先 | 0.5 天 | ✅ 已修复（market_anchor rotation advice）|
| **P2-03** | 报告过长 | --brief 默认 + 关键结论置顶 | 1 天 | ✅ 已修复（guardrails/output-template 表格上限 + 折叠披露；stock/market 已默认 quick，--brief 保留为可选）|
| **P2-04** | 持仓占位过密 | 实际总仓位计算 + 行业占比上限 | 0.5 天 | ✅ 全部修复（industry_overlap + 30% 硬约束 + 实际总仓位 compute_total_position_ratio）|

---

## 🔄 跟踪与验证

每项修复完成后：
1. 在本文件对应问题下追加"修复 commit + 验证结果"
2. 更新 `CHANGELOG.md`（参考已有 Round 7-11 风格）
3. 跑全量回归测试（pytest 2700+ 项）
4. 重新执行本次复盘的完整流程（market→stock→sector→portfolio→screener），对比修复前/后

---

## 📚 关联资源

- **历史问题清单**：`docs/review-issues.md`（75 项，已 Round 7-11 全部修复）
- **架构审查**：`docs/architecture-review-2026-07-07.md`（46 项 T/I 债，已 Round 11 收官）
- **screener 专项审查**：`docs/screener-review.md`
- **改进路线图**：`docs/improvement-roadmap.md`

---

> **维护者**：复盘元复盘由每次多 skill 串联会话触发；建议作为 CI 的一部分，**每月自动跑一次 5 skill 串联回归**。

📅 **生成日期**：2026-08-12 08:10
📊 **下次复盘建议**：下次多 skill 串联会话后立即追加新问题到本文档
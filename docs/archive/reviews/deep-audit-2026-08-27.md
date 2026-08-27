# market / sector / portfolio 模块深度审查报告（2026-08-27）

> **审查时间**：2026-08-27
> **审查对象**：`scripts/market_anchor.py`、`scripts/market_breadth.py`、`scripts/sector_etf_strength.py`、`scripts/sector_summary.py`、`scripts/sector.py`、`scripts/sector_momentum.py`、`scripts/portfolio/`（manager/crud/analytics/brinson/oplog）、`experts/market_detector.py`
> **方法**：3 个并行 Explore agent 逻辑层审查 + 合成数据实测验证（最小复现确认）
> **流程**：延续 2026-08-27 技术模块审查模式（找集成死代码/指标边界/降级路径/条件恒假分支）
> **相关文档**：[technical-module-review-2026-08-27.md](technical-module-review-2026-08-27.md)

---

## 一、一句话结论

> 🚨 **三个模块都存在"输出与事实相反或永远不可达"级别的功能失效**：题材轮动"位次上升/下降"榜单方向完全颠倒（且渲染层二次取反）；market regime 4/6 分支（牛市/熊市/冰点/亢奋）因硬编码字段永远不可达；非交易日（周末/节假日）必现"退潮"误报；portfolio 的 risk_summary 是死集成（import 不存在的函数）、归因报告是占位假数据、top5 集中度约束从未执行。声明层审查（横切审查）看不到这些问题——**逻辑层审查是独立且必要的维度**。

---

## 二、P0（崩溃/核心功能失效）

| # | 问题 | 证据 | 修复 |
|---|---|---|---|
| P0-1 | **sector_summary 降级被 AttributeError 击穿**：东财 `data=null` 时 `diff.get("diff")` 崩溃，except 元组不含 AttributeError → CLI 直接 traceback 而非降级 | `sector_summary.py:139,167-175` | 空 dict 守卫 + except 扩展（已修） |
| P0-2 | **portfolio undo 浅拷贝污染**（Agent 报告）→ **实测推翻**：`_push_oplog` 在操作前调用且 push 同步序列化，快照正确 | `manager.py:462` + 实测 | 不修（误报） |

## 三、P1（逻辑错误/功能失效）

| # | 问题 | 证据 | 修复 |
|---|---|---|---|
| P1-1 | **轮动位次上升/下降名单方向完全颠倒**：`rank_delta = rank_nd - rank_1d`（正=上升）但 risers 取负值，fallers 取正值；渲染层 `+{-r[2]}` 二次取反 | `sector_etf_strength.py:509-518` + `market_anchor.py:1137,1141` | 排序方向 + 渲染符号修正（实测验证） |
| P1-2 | **regime 4/6 分支不可达**：`new_high_low_ratio` 硬编码 1.0、`pe_percentile` 50、`margin_ratio` 0 → 牛市（需 >1.5）/熊市（<0.5）/冰点（<0.2）/亢奋（>90 且 >10）永不触发 | `market_anchor.py:81,134-135` vs `market_detector.py:103-136` | new_high_low_ratio 用涨跌家数比近似；亢奋标注数据降级不可达 |
| P1-3 | **非交易日误报"退潮"（中置信）**：akshare `stock_zt_pool_em` 非交易日返回空 DataFrame（非异常）→ 全 0 无降级标记 → breadth 判"退潮" | `sentiment.py:94-122` + `market_breadth.py:105-109,205-207` | akshare 空池走东财兜底 + breadth 全零视为降级 |
| P1-4 | **to_markdown vs_portfolio=None 崩溃**：`vp.get("corr_confidence")` 无 None 守卫 → AttributeError | `market_anchor.py:1111-1116` | 加守卫（修） |
| P1-5 | **quotes_missing 判定过宽**：dict 非空即视为"有行情"，缺报价持仓按 0 市值计入 totals | `manager.py:817` | 任一持仓缺报价即缺失（修） |
| P1-6 | **cost=0 虚假盈利**：行级 pnl=全部市值且 pnl_pct=+0.00%，与 totals 矛盾，违反 SKILL guardrail | `manager.py:841-849` | 行级 pnl/pnl_pct 置 None（修） |
| P1-7 | **risk_summary 死集成**：import 不存在的 `compute_portfolio_var/format_var_report`，恒走 ImportError 分支 | `analytics.py:78-83` | 改用真实 `position_var_summary`（修） |
| P1-8 | **归因报告占位假数据**：组合收益硬编码 0、基准 5%——输出"选股效应恒为负"误导 | `brinson.py:207,233-234` | note 字段如实标注降级（修） |
| P1-9 | **top5_limit 死参数**：SKILL 声称"前5大≤70%"但 check_concentration 从不检查 | `manager.py:771` | 补 top5 检查（修） |
| P1-10 | **sector_summary ths NaN 崩溃**：`int(float('nan') or 0)` → ValueError | `sector_summary.py:64-65` | `_finite` 防护（修） |
| P1-11 | **sector 前缀遮蔽**："300" 先于 "300750" → 宁德时代误判科技 | `sector.py:57-97` | 按前缀长度降序（修） |

## 四、P2（边界/一致性）

- **3 只 ETF 时强势==弱势**（`sector_etf_strength.py:596-597`）——数据不足时 top3/bottom3 重叠
- **regime_confidence 在降级字段追加前冻结**（`market_anchor.py:613`）
- **"regime" not in degraded 恒真**（死条件，`market_anchor.py:623`）
- **情绪降级输出方向性结论**（全零数据判"偏弱"而非"未知"）
- **多时间框架死分支**（ret_5d 的 else、atr None 分支）
- **北向"综合方向"末端分支同值**
- **sector_momentum ret_5d 标签在 days≠5 时错位** → 已修（动态标签）
- **轮动阈值 2.5/3/3 三处不一致** → 已修（统一 ≥2.5）
- **portfolio**：tag/untag 不写 oplog（已修）、CRUD 入参校验缺失（已修）、watch 舍入边界（已修）、update_watch 无法清空目标价、undo 不回滚 trade_log、停牌 pnl 矛盾（已修）、brinson tags[0] 不滤状态标签
- **SKILL 死声明**：portfolio compare 未实现（已标注）、market 北向 guardrail 过时（已更新）、sector 轮动位置无工具产出（已注明）

## 五、验证无问题项（防误报）

- 除零防护（advance_ratio/up_ratio/ATR/stdev 全有守卫）
- ETF 数据不足 3 只不崩溃
- detect_market_state 缺数据 fail-safe（防御型）一致
- 降级标记透传链（breadth → anchor markdown）一致
- 北向空数据降级（direction=unknown + degraded）
- 数据时效三档、宏观 fixture 标注
- portfolio 空组合/单标的/全 0 市值 health_report 不崩溃
- 加权平均成本 + cost_source 自动置 calculated
- 相关性模块短序列/零方差返回 None
- Brinson 公式数学正确（问题仅在占位数据）

## 六、立场结论

**market/sector/portfolio 值得继续，但"输出方向颠倒 + 条件不可达 + 占位假数据"三类问题会让用户拿到与事实相反的结论**——本轮已修复全部 P0/P1（除 1 个实测推翻的误报），剩余 P2 为边界项与设计分歧。建议下轮优先：update_watch 目标价清空、undo 回滚 trade_log、brinson 真实收益接入（需 K 线上期价）。
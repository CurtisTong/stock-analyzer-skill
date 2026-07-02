# 全模块代码审查报告（2026-07-02）

> 技术专家团队对 13 个模块（~3 万行 Python）逐个深度审查的汇总。
> 共发现 **Critical 14 / High 35 / Medium 41 / Low 30+** 项问题。
> 每个模块由独立 code-reviewer agent 审查，覆盖正确性、健壮性、性能、安全、架构、可维护性六维。

---

## 一、审查总览

| 模块 | 行数 | Critical | High | Medium | 健康度 | 核心风险 |
|------|------|----------|------|--------|--------|----------|
| common（基础设施） | 2725 | 1 | 4 | 8 | 7/10 | SSRF 防御缺失、输入校验宽松、4xx 误熔断 |
| fetchers（数据源） | 2630 | 2 | 6 | 7 | 6/10 | **6 kline fetcher 缺 source 致 volume 差 100 倍**、北向资金索引对齐 bug |
| data（类型缓存） | 1100 | 2 | 4 | 5 | 6/10 | **缓存键未归一化**、零值缓存穿透 |
| technical（技术分析） | 3305 | 1 | 3 | 5 | 7/10 | **MACD 背离索引错位 25 根**、volume IndexError |
| business（业务逻辑） | 896 | 2 | 4 | 5 | 5/10 | **net_profit_cagr_3y 字段不存在致 PEG 逻辑失效**、涨跌停误过滤 |
| strategies（策略） | 3211 | 3 | 5 | 6 | 6/10 | Phase 2 chip 网络浪费、过拟合警示缺失、backtest chip 签名错 |
| portfolio（持仓） | 3645 | 2 | 5 | 8 | 5/10 | **并发写丢失（单例未 reload）**、前后端契约断裂、集中度口径错 |
| monitor（监控） | 2073 | 2 | 5 | 6 | 6/10 | **去重竞态致重复推送**、global 线程不安全、无重试 |
| backtest（回测） | 1215 | 3 | 4 | 5 | 4/10 | **信息比率时间错位**、multi_stock 字段失配全零、夏普年化错 |
| chan+顶层脚本 | 5698 | 5 | 9 | 11 | 4/10 | **缠论 5 项算法错误**（线段/中枢/背驰/买卖点）、死代码 |
| experts（专家系统） | — | 1 | 3 | 3 | 6/10 | **短线 2看空+1看多误判中性**、buffett_sub_score 路径失效 |
| config+dev | 1359 | 0 | 2 | 6 | 8/10 | 正则误改嵌套 version、parse/sync 宽容度不一致 |

---

## 二、Critical 问题清单（14 项，必须修复）

### 数据正确性（影响投资判断，最高优先级）

1. **[fetchers/C2]** 6 个 kline fetcher（efinance/akshare/baostock/tushare/yfinance/pytdx）缺 `source` 字段，volume 归一化被跳过 → **跨源切换成交量差 100 倍**，量比/放量分析全部失真。
2. **[fetchers/C1]** `eastmoney_flow.py` 北向资金沪深股通按索引对齐，天数不一致时数据丢失/错位，无日期校验。
3. **[data/C1]** `get_quote/get_kline/get_finance` 缓存键不归一化 code（`SH600989` vs `sh600989` 生成不同键）→ 缓存未命中 + 数据不一致 + 空间浪费。
4. **[data/C2]** `get_finance` 零值缓存穿透：fetch 返回空列表不写 zero_key，对无数据股票每次触发网络请求。
5. **[technical/C1]** `macd.py:73` MACD 背离检测价格窗口与 DIF 窗口错位 25 根 K 线 → 背离误判/漏判，反转信号不可信。
6. **[business/C1]** `net_profit_cagr_3y` 字段在 FinanceRecord 不存在 → `growth` 恒为 0，PEG 永远回退单期增速，3 年 CAGR 意图从未生效（valuation.py/dcf.py 同样问题）。
7. **[business/C2]** 涨跌停硬过滤用预警宽松阈值（主板 9.5%）而非精确阈值（10.0%）→ 涨 9.5%-9.99% 可交易股票被误排除，伤害短线/动量策略。
8. **[strategies/C3]** `backtest_report.py` 输出 `✅ 策略表现良好` 无过拟合警示 → 71.4% 胜率（样本内拟合）被误读为实盘可用。

### 资金与并发安全

9. **[portfolio/C1]** PortfolioManager 单例 CRUD 走 `save()` 而非 `atomic_update`，写前不 reload → 外部进程改 portfolio.json 后被陈旧内存态覆盖，**持仓数据丢失**。
10. **[monitor/C1]** `_check_throttle` 检查与更新分离为两个临界区 → 并发 send 同一 throttle_key 时去重失效，**用户被重复轰炸**。
11. **[monitor/C2]** 失败发送不更新 throttle_log/daily_count → 通道持续故障时形成无效重试循环。

### 回测可信度

12. **[backtest/C1]** 信息比率用 `all_daily_returns`（多期拼接）与 `benchmark_returns`（连续 N 天）按 `min_len` 对齐，时间区间错开数周到数月 → 数值无意义。
13. **[backtest/C2]** `multi_stock_backtest.py` 读取 `total_return/annual_return/sharpe/...` 但 `simulate_strategy` 不返回这些字段 → **报告全为零**，外样本验证脚本输出无效。
14. **[backtest/C3]** 夏普比率 holding_days 退化路径：小样本 stdev 高估 + 非独立期收益用 `periods_per_year**0.5` 年化数学不成立。

### 缠论算法（5 项，严重影响该模块可信度）

- **[chan/C1]** 线段划分未用特征序列，违反缠论标准。
- **[chan/C2]** 中枢缺 GG/DD 字段，三买/三卖判断不准。
- **[chan/C3]** 背驰检测笔 idx（merged 坐标系）与 dea_offset（closes 坐标系）混乱，面积计算可能错位。
- **[chan/C4]** 一买/一卖不检查背驰结果，违反缠论定义（无背驰非一买）。
- **[chan/C5]** 笔合并规则不完整，同方向连续分型未正确处理。

### 投票裁决

- **[experts/C1]** `aggregate_group_votes` 分支顺序：均势分歧分支在看空多数分支之前 → 短线 2看空+1看多被误判为"中性"而非"看空"，与 decide.md §七冲突。

---

## 三、High 问题清单（35 项，本迭代强烈建议修复）

### 跨模块系统性问题（字段缺失系列）

- **[business/H2]** `TOTALOPERATEREVE` 字段不存在 → 财务类退市风险预警（营收<1亿+亏损）**永不触发**，静默失效的安全检查。
- **[strategies/H1]** `backtest/engine.py` 调用 `chip_score_dynamic(hist_quote, fin, industry)` 传 3 参，但签名只收 1 参 → TypeError 被 except 吞掉，回测中 chip 因子永远为 0，defensive/turning_point 回测失真。
- **[experts/H1]** `buffett_sub_score` 仅 `score_with_reasoning` 注入，`score_expert_precise`（SKILL.md 推荐路径）走 `score()` 不含此字段 → 巴菲特否决权在推荐路径静默失效。
- **[experts/H2]** 9 专家无 `group` 字段时被静默丢弃，回退 50/50 → 整轮辩论退化为恒定 50 分中性输出。

### 数据正确性

- **[common/H1]** `normalize_code` 用 `len>=8` 宽松校验，接受 `sh1234567890` 超长非法代码。
- **[common/H2]** `http_get` 4xx 抛 `requests.HTTPError` 被 manager 当网络故障计入熔断 → 404 误熔断数据源。
- **[common/H3]** `cache.put` flock 在 close 后释放、replace 在锁外 → 多进程 last-write-wins 风险。
- **[common/H4]** `validate_date` 只校验正则不校验有效性，`2024-13-45` 返回 True。
- **[data/H1]** `get_margin_summary` 假设数据降序但未验证排序。
- **[technical/H2]** `volume.py:82` len=3-5 且连续缩量时 IndexError。
- **[technical/H3]** `candlestick.py:82` 锤子线上影线对阴线不正确（应用 `max(close,open)`）。
- **[portfolio/H1]** 交易统计 JS 读 `total_pnl/win_rate*100/avg_hold_days`，Python 返 `total_profit/win_rate(已%)/avg_profit` → 交易面板胜率显示 6000% 或全"—"。
- **[portfolio/H3]** `check_concentration` 用成本×数量而非市值 → 大涨后集中度预警漏报。
- **[backtest/H1]** `_calc_daily_returns` 从 `j=i` 起算含信号日日内波动，与 `entry_price=bars[i].close` 错位一天。
- **[backtest/H2]** 止损用收盘价判断+收盘价成交 → 乐观偏差，触发频率低估、收益高估。
- **[backtest/H4]** 股票池为静态现存股票，幸存者偏差（短周期影响小，长周期高估收益）。
- **[chan/H1-H9]** 缠论包含方向判断滞后、snapshots diff 无 --json、calibration_sync pull 覆盖致数据丢失、双针探底分母错（÷3 应 ÷2）、classifier 死代码致蓝筹误用流通市值、chan.py 缺异常处理等。

### 性能与安全

- **[strategies/C1/H3]** Phase 2 调 `chip_score_dynamic`（3 次网络请求）后立即 `pop` 丢弃 → 批量选股每候选股浪费 3 次请求。
- **[portfolio/C2]** 0.0.0.0 绑定 + Token 即鉴权 + 无 TLS → 公网部署 token 可被同网段嗅探。
- **[monitor/H1]** `_LOG_MAX_SIZE/FILES` 用 global，多实例共享且默认参数绑定时机易错。
- **[monitor/H2]** Bark/企微/钉钉通道单次 HTTP 无重试，网络抖动漏推。
- **[monitor/H4]** `alert_engine` 单例 `_nm/_pm` check-then-init 无锁，并发创建多实例致去重失效。
- **[monitor/H5]** 持续性信号（MACD 金叉可持数日）level-triggered，调度间隔>15min 时重复推送。
- **[experts/H3]** `veto_results` 原地修改调用方 expert_results dict，污染原始评分不可回溯。

---

## 四、优化计划

按"影响面 × 紧迫度"分四个阶段。每个修复项标注：**[模块/编号]** + 文件 + 改动量。

### 阶段一：P0 数据正确性 hotfix（1-2 天，阻塞发布）

> 这些直接影响投资判断或资金安全，未修复不可用于实盘。

| # | 修复项 | 文件 | 改动量 |
|---|--------|------|--------|
| 1 | **[fetchers/C2]** 6 kline fetcher 补 `source` 字段 + 单位归一化 | efinance/akshare/baostock/tushare/yfinance/pytdx_kline.py | 小（每文件 1-2 行） |
| 2 | **[fetchers/C1]** 北向资金改按 date dict 合并 | eastmoney_flow.py:52-57 | 中 |
| 3 | **[data/C1]** 三个 `get_*` 入口归一化 code | data/__init__.py:64,115,138 | 小 |
| 4 | **[data/C2]** fetch 返回空也写 zero_key | data/__init__.py:154-165 | 小 |
| 5 | **[technical/C1]** MACD 背离索引对齐（offset=25，closes[offset:offset+lookback]） | macd.py:73 | 小 |
| 6 | **[business/C1]** 移除 `net_profit_cagr_3y` 引用或新增字段+填充 | stock_analysis.py:212 + valuation.py:81 + dcf.py:87 | 中 |
| 7 | **[business/C2]** 涨跌停硬过滤改用精确阈值 | screening_service.py:398-401 | 小 |
| 8 | **[experts/C1]** 看空多数分支前移或均势分支加 `< majority` 约束 | vote_engine.py:550-558 | 小 |
| 9 | **[portfolio/C1]** CRUD 写路径统一走 `atomic_update`（锁内 reload-改-写） | manager.py + web/app.py | 中 |
| 10 | **[monitor/C1+C2]** throttle 检查+标记合并为原子操作，失败也更新去重窗口 | manager.py:194-222,320-323 | 中 |
| 11 | **[backtest/C2]** `run_one_strategy` 改调 `run_backtest` + 字段名映射 | multi_stock_backtest.py:202-303 | 中 |
| 12 | **[backtest/C1]** 信息比率改用每期收益 vs 基准同期持有期收益 | metrics.py:132-141 | 中 |

### 阶段二：P1 高价值修复（3-5 天，本迭代内）

| # | 修复项 | 文件 |
|---|--------|------|
| 13 | **[strategies/H1]** backtest engine chip 调用改 `_chip_score(code)` 或提供适配签名 | backtest/engine.py:17,186 |
| 14 | **[strategies/C1]** Phase 2 跳过 chip 因子（exclude_keys 或 network 标记） | screening_service.py:441-453 + factors/__init__.py |
| 15 | **[strategies/C3]** backtest_report 总结段强制插过拟合警示 | patterns/backtest_report.py:283-298 |
| 16 | **[business/H2]** 补营收字段或移除退市预警检查（避免虚假安全感） | screening_service.py:342-345 + types.py + parsers.py |
| 17 | **[experts/H1]** `value_anchor.score()` 也输出 `buffett_sub_score` | scoring/value_anchor.py:43 |
| 18 | **[experts/H2]** 9 人无 group 的 fallback（按 6+3 切分） | vote_engine.py:360-366 |
| 19 | **[experts/H3]** veto_results 入口浅拷贝 `[dict(r) for r in ...]` | vote_engine.py:346-353 |
| 20 | **[portfolio/H1]** 交易统计前后端契约对齐 | templates.py:580-587 ↔ trade_log.py:194-252 |
| 21 | **[portfolio/H3]** check_concentration 用市值（接受 quotes 参数） | manager.py:453,463,496 |
| 22 | **[portfolio/C2]** 公网绑定时强制 TLS/不在 stdout 打印 token | web/app.py:564-579 |
| 23 | **[monitor/H2]** 通知通道加 2-3 次指数退避重试 | channels/bark.py、wechat.py、dingtalk.py |
| 24 | **[monitor/H4]** alert_engine 单例初始化加锁 | alert_engine.py:30-58 |
| 25 | **[monitor/H5]** 持续性信号改 edge-triggered（持久化 notified_state） | alert_engine.py:467-564 |
| 26 | **[backtest/H1]** `_calc_daily_returns` 从 `j=i+1` 起算 | engine.py:219,283-289 |
| 27 | **[backtest/H2]** 止损用 `low` 判断 + 保守成交价 | engine.py:307-327 |
| 28 | **[backtest/C3]** 夏普统一用 `all_daily_returns`，不足则报样本不足 | metrics.py:78-86 |
| 29 | **[technical/H2]** volume.py 循环条件改 `min(len, 6)` + guard | volume.py:82-84 |
| 30 | **[technical/H3]** candlestick 锤子线复用 `_body_shadow` | candlestick.py:82 |
| 31 | **[common/H1-H4]** normalize_code 严格校验、validate_date 用 strptime、4xx 抛 DataError 子类、cache.put 持锁 replace | validators.py、http.py、cache.py |
| 32 | **[fetchers/H1-H2]** 3 quote fetcher 补 source、统一 circulating_cap | efinance/akshare/tushare_quote.py |

### 阶段三：P2 缠论专项 + 健壮性（1-2 周）

> 缠论模块 5 个 Critical 是系统性算法问题，需决策：**重构为标准缠论** 还是 **标注为非标准实现**。

| # | 修复项 | 决策 |
|---|--------|------|
| 33 | **[chan/C1-C5]** 缠论算法 | 方案 A：实现特征序列线段 + 中枢 GG/DD + 背驰索引统一坐标系 + 一买依赖背驰。方案 B：docstring + SKILL.md 明确标注"非标准缠论，仅供学习"。**建议先 B 后 A** |
| 34 | **[chan/H1-H9]** snapshots --json、calibration_sync 三向合并、双针探底分母、classifier 死代码、chan.py 异常处理 | 逐项修复 |
| 35 | **[data/H1-H4]** margin 排序验证、holders 样本要求、cache.clear missing_ok、data/cache.py 去 sys.modules hack | 逐项修复 |
| 36 | **[strategies/H2-H5]** event default_weight=0、normalize 批次过滤、chip institution clamp、dividend fin=None 容错 | 逐项修复 |

### 阶段四：P3 技术债与一致性（持续）

- common：SSRF scheme 白名单、export_to_csv filename 清洗、compute_volume_ratio base/recent 重叠、version.py 纳入同步
- technical：sentiment 重复请求、scoring KDJ 钝化权重、long_term ROE 双重计分、trend 整数关口
- portfolio：file_lock TOCTOU、_rate_limit_history 无上限、update_position vs add_position 语义
- monitor：throttle_key 用 md5 避免截断碰撞、alert_engine 用 dev.clock、health.py 去重 monitor.py
- config/dev：sync_version 正则改 json.load/dump、parse/sync pattern 宽容度统一、ConfigLoader 加锁、safe_get 缩窄 except
- 全局：统一 sys.path.insert 模式、清理死代码（多处 `to_float(...)` 未赋值）

---

## 五、横向主题（跨模块共性）

1. **字段契约脱节**（最严重）：`FinanceRecord` 定义的字段 ↔ fetcher 填充 ↔ business/factors 消费三方脱节，导致 `net_profit_cagr_3y`、`TOTALOPERATEREVE`、`revenue` 等静默失效。**建议建立字段映射单一真实来源（single source of truth）**，data 层定义 → fetcher 映射 → business 消费自动对齐校验。

2. **异常吞没掩盖 bug**：多处 `except Exception: pass` 或降级为 50，把字段缺失/签名错误/网络失败静默掉（backtest chip、dividend fin=None、退市预警）。**建议 except 至少 logger.warning 记录被降级的原因**。

3. **缓存键与归一化**：data 层缓存键不归一化、fetcher code 格式不统一，是缓存失效与数据不一致的根源。

4. **并发与单例**：portfolio 单例、monitor alert_engine 单例、ConfigLoader 类级缓存都缺线程安全，web 服务场景下竞态。

5. **过拟合与回测可信度**：模式策略胜率未充分警示、回测指标计算多处错误（信息比率/夏普/daily_returns 对齐），回测结果可信度受损。

6. **缠论非标准**：5 项核心算法与缠论定义不一致，需明确是"学习版"还是"实盘版"。

---

## 六、模块健康度排名

| 排名 | 模块 | 健康度 | 一句话评价 |
|------|------|--------|------------|
| 1 | config+dev | 8/10 | YAML 安全、同步幂等，仅正则边界瑕疵 |
| 2 | common | 7/10 | 基石扎实，安全防御与输入校验需加强 |
| 3 | technical | 7/10 | 核心公式正确（与通达信一致），背离索引需修 |
| 4 | fetchers | 6/10 | 架构好，但字段一致性是重灾区 |
| 5 | data | 6/10 | 缓存设计有亮点，键归一化是关键缺口 |
| 6 | strategies | 6/10 | 注册表机制优秀，过拟合警示与 chip 签名需修 |
| 7 | experts | 6/10 | 近期修复方向对，分支顺序与 buffett 路径需修 |
| 8 | monitor | 6/10 | 通道抽象清晰，去重竞态是核心缺陷 |
| 9 | business | 5/10 | 评分骨架对，字段缺失致多处静默失效 |
| 10 | portfolio | 5/10 | 安全基线好，并发写丢失是结构性风险 |
| 11 | backtest | 4/10 | 前视控制好，但指标计算多处错误，可信度受损 |
| 12 | chan+脚本 | 4/10 | 缠论非标准，顶层脚本参数校验不一 |

---

## 七、建议执行顺序

1. **立即**：阶段一 P0（12 项数据正确性 hotfix）——阻塞实盘使用
2. **本迭代**：阶段二 P1（20 项高价值修复）+ 补充对应回归测试（短线 2看空+1看多、9人无 group、缓存键归一化、MACD 背离索引、backtest 字段映射）
3. **下迭代**：阶段三 P2 缠论决策 + 健壮性
4. **持续**：阶段四 P3 技术债

> 各模块详细审查报告（含每项文件:行号、问题描述、修复代码建议）见各 code-reviewer agent 输出，本报告为汇总索引。

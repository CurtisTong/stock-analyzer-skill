# 定时任务调度设计（P0）

> 版本：v0.1（P0 基础设施）｜建立日期：2026-11-20

## 1. 为什么是「launchd 一条心跳 + runner 判槽」

本机没有 crontab、没有项目级 LaunchAgent，所有「定时」原本挂在 DSH 会话的
schedule 上。但 DSH 的 schedule 不能当钟用，实测与源码证据：

| 事实 | 证据 |
|---|---|
| 只补「最近一次」漏跑的 occurrence | DSH 工具描述原文：`each recurring task contributes only its latest missed occurrence` |
| 可能重复交付 | 同上：`Delivery can repeat after a crash` |
| 应用不运行则没有调度 | 调度在 Host 进程内；`~/.dsh/storages/schedule.json` 只是持久化状态 |
| 交付会唤醒 cold session | 每次触发生成 model 调用，有 token 成本 |

而 macOS `launchd` 的 `StartCalendarInterval` **在睡眠/关机期间错过的时点不会补跑**。
所以「每个时点一条 launchd」= N 份补跑逻辑。

**定稿形态**：launchd 只装 1 个心跳，runner 自己判断该跑什么。

```xml
<!-- ~/Library/LaunchAgents/com.curtis.stock-scheduler.plist -->
<key>ProgramArguments</key>
<array>
  <string>/Users/curtis/.dsh/bot/workspace/stock-team/.venv/bin/python</string>
  <string>/Users/curtis/.dsh/bot/workspace/stock-team/stock-analyzer/scripts/dev/scheduled_task.py</string>
  <string>--tick</string>
</array>
<key>StartInterval</key><integer>300</integer>
<key>RunAtLoad</key><true/>
<key>StandardOutPath</key><string>/tmp/stock-scheduler.log</string>
<key>StandardErrorPath</key><string>/tmp/stock-scheduler.err</string>
```

睡眠/关机错过的时间，唤醒后下一次 tick（≤5 分钟）自然补上；重复 tick 由幂等键吃掉。

## 2. 三层防护（缺一不可）

1. **`is_trading_day(d)` 前置**
   **禁止**用 `is_trading_hours()`：后者判「此刻是否在盘中」，08:45 / 15:05 / 18:30
   一律返回 `False`，拿它当前置会把盘前盘后任务静默跳过且不报错。
2. **幂等键 + 单实例锁**
   幂等键 `{date}__{task}__{slot}` → `scripts/data/.run/*.json`，`status=ok` 才算完成；
   锁用 `fcntl.flock` 非阻塞。锁防「同时」，幂等键防「先后重复」，只做一层都会被绕过。
3. **数据就绪断言（两层）**
   - **runner 层**：canary 抽样（3–5 只大票）判「整体是否就绪」，未就绪 exit 2 且
     **不写完成标记**，下个 tick 重试；
   - **screener 层（P1）**：每只实际用到的票断言末根日期 == 目标交易日，不等标
     `degraded` **但不剔除**，输出计数；**stale 比例 > 20% 整批 exit 2**。

   > ⚠️ **明文约束：跑批正确性禁止复用 `technical/core.py:stale_trading_days()`
   > 当门槛。** 它的 docstring 写明是 `SKILL guardrail：数据 stale（>3 个交易日）
   > 必须警告用户`——阈值 3 天是为「提示用户」设的，1 天滞后它会放行，正好放过
   > 2026-11-18 那次 sina 缓存停在 T-1、用旧 K 线算均线与 ATR 的事故。
   > 半年后不要图省事把它拿回来用。

**缓存陷阱（2026-11-20 源码核对）**：`get_kline()` 命中缓存时不比对末根日期，
`kline_240m` TTL 为 3600s；`--no-cache` 在仓库里是**空开关**（只有声明、零消费）。
因此：

- runner 的 canary 探针**必须 `use_cache=False`**（3 只票，成本可忽略），否则
  「未就绪」会一直成立到 TTL 过期；
- 选股槽必须让 `get_kline()` 支持 `require_date`（命中缓存但末根日期不符 → 穿透重拉），
  而不是指望加 `--no-cache`；
- **重跑成本自动收敛**：`require_date` 形态下，已就绪的票在重试时命中缓存校验直接返回，
  只有未就绪的票真正发请求。所以 16:00–19:00 每 15 分钟整批重跑是安全的，不需要维护
  「待重试清单」；
- 15:05 收盘快照与 16:30 选股共用同一份 K 线缓存，两条槽必须串起来设计，
  否则快照会把盘中不完整的当日 K 线喂给选股。

个别票 stale 只记日志不阻塞：全池 284 只里总有停牌、退市、新股，「一只不齐就全场停」
会变成天天误报，最后告警被关掉——那比静默算错更糟。

## 3. 告警时点：判「仍未开始跑」，不判「未跑完」

18:50 数据就绪 → 18:50 开跑 → 19:25 结束，是正常长任务。若按「19:00 未完成」告警，
会天天误报。因此：

- 19:00（各槽 `deadline`）检查的是状态里**有没有 `started_at`**；
- 任务成功/失败/超时只从幂等键的 exit code 读，**不与就绪告警共用一个时点**。

## 4. 次日兜底

上一交易日的槽没跑成 → 次日 08:00 窗口内（`backfill_at`，到 08:45 前）对该交易日重跑一次，
带 `TARGET_DATE=上一交易日`。补跑出的清单**必须在标题与正文标明「T 日收盘口径」**，
不得与当日盘前风偏混排；执行顺序固定 **08:00 补跑 → 08:45 盘前**，不并行。

## 5. 退出码与可见性

| 退出码 | 含义 | 后续动作 |
|---|---|---|
| 0 | 成功 / 已跳过 / 未到点 | 无 |
| 2 | 数据未就绪 | 不写完成标记，下个 tick 重试，deadline 后告警 |
| 3 | 执行失败 | 写 `failed`，推微信告警（P1 接线） |

状态文件 `scripts/data/.run/<key>.json` 保留 `status / exit / started_at / finished_at /
canary / data_date`，失败现场可回看。目录已进 `.gitignore`。

`--no-cache` 曾经是**空开关**（只在 `common/cli_base.py` 声明、零处消费，加了照样命中
缓存）；2026-11-20 已让 `scripts/kline.py` 真正传 `use_cache=False`。照旧笔记用之前先确认。

`degraded` **必须写成日志字段**，不许变成「习惯性缺省」——例如美股指数当前无源
（yfinance 429、雪球 400），要显式记 `degraded: ["us_index"]`，等源补上才去掉标注。

## 6. 槽位表（P1 接入计划，一个槽一个 commit）

| 时点 | 任务 | 谁 | 槽位 | 备注 |
|---|---|---|---|---|
| 07:20 | 隔夜外盘 | 宏观 | 3min | 美股指数当前 degraded |
| 08:00 | 上一交易日兜底 | runner | 5min | 必须早于 08:45 |
| 08:45 | 盘前风偏 | 宏观 | 5min | |
| 09:30 | 跳空检查 + breadth | 操盘/宏观 | 5min | quote 带不出宽度，需单独调 `market_breadth.py` |
| 14:30 | 尾盘决策 + breadth | 操盘/宏观 | 5min | |
| 15:05 | **收盘快照（合并 job）** | 宏观+研判 | 5min | 指数+宽度+ETF ≈1.9s，一次取数两方消费 |
| 15:10 | 止损复核 | 操盘 | 10min | 与条件单判定分开，口径不同 |
| 16:00→19:00 | 探测式选股 | 策略 | 35min | 末根日期齐才跑 |
| 17:00 / 17:30 | OOS 回测 / 因子 IC | 策略 | 15 / 5min | 落文件不推送 |
| 18:30 | 盘后复盘 | 宏观 | 10min | |

## 7. 分期

- **P0（本提交）**：`is_trading_day()`、runner、幂等+锁、退出码与日志、本文件。
  **不接任何业务槽位**，空跑一天只打日志（`--push` 默认关）。
- **P1**：按上表逐槽接入，先接 15:05 收盘快照（最便宜、依赖最少）。
- 前提：`scripts/data/portfolio.json` 尚未就绪，09:30 / 14:30 / 15:10 目前只能跑
  条件单，不得写依赖持仓的逻辑。

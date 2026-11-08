---
name: portfolio-web
description: 持仓 Web 录入与查询服务。触发词：持仓 web、portfolio web、启动 Web 录入、查持仓 API。从 portfolio 拆分：仅负责 Web 服务子功能。
version: 1.33.0
model: glm-5.2
allowed-tools: Bash(python3 scripts/portfolio_web.py *) Bash(curl -X POST http://127.0.0.1:8765/api/positions *) Bash(lsof -i:8765 *) Read(./scripts/data/portfolio.json) Read(./scripts/config/notification.yaml) Read(./skills/_shared/references/*.md)
---

# Portfolio Web Service

持仓 Web 录入子服务。本文档从 `/portfolio` 拆分，仅覆盖 Web 相关操作。

> 本 skill 是 `/portfolio` 的 **Web HTTP API 子模块**（`scripts/portfolio_web.py` 监听 :8765），非独立 CLI 进程；持仓 CRUD 主流程见 [`/portfolio`](./../portfolio/SKILL.md)，NL → 命令映射见 [`/portfolio-natural`](./../portfolio-natural/SKILL.md)。

## Usage

```text
/portfolio-web                             # 启动 Web 服务（默认 127.0.0.1:8765）
/portfolio-web --port 9000                 # 指定端口
/portfolio-web --no-open                   # 启动后不自动打开浏览器（默认自动打开）
/portfolio-web --no-notify                 # 启动时不推送通知
/portfolio-web --virtual                   # 启动虚拟持仓模式（portfolio_virtual.json）
```

## API 端点

所有端点需 Bearer 认证（除 `/api/health`）：

- `POST /api/positions` - 创建/更新持仓
- `GET /api/positions` - 查询当前持仓
- `GET /api/positions/<code>` - 查询单只持仓
- `GET /api/trades` - 查询交易日志
- `GET /api/health` - 健康检查（免认证）
- `DELETE` 一律 405——**删除持仓无 HTTP 端点**，须经 `/portfolio remove` CLI

完整 CRUD 操作见 [`/portfolio`](../portfolio/SKILL.md)。

## 鉴权（Bearer Token）

curl / 脚本调用必须带 `Authorization: Bearer <token>`，token 位于
`~/.config/stock-analyzer/portfolio_web.token`（首启自动生成，0600 权限）：

```bash
TOKEN=$(cat ~/.config/stock-analyzer/portfolio_web.token)
curl -X POST http://127.0.0.1:8765/api/positions \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"code":"sh600989","name":"宝丰能源","cost":18.5,"quantity":1000}'
```

页面导航可用 `?token=<token>` query 参数；同源浏览器请求放行 Origin
（跨站 Origin 拒绝 403，公网绑定 `--allow-public-bind` 时 Origin 退位、
全程仍强制 Bearer）。

## Instructions

使用中文输出。Web 服务依赖 `scripts/data/portfolio.json` 中的持仓数据。
同时只允许一个实例占用端口（`lsof -i:8765`）。

输出遵循统一模板：首行为服务状态，尾行为端口 + 数据时间戳。详见 `../_shared/references/output-template.md`。

## Guardrails

- 持仓数据修改须走 `PortfolioManager` API，不要直接编辑 JSON
- 并发写入冲突时使用锁机制（详见 `scripts/portfolio/manager.py`）
- `--virtual` 模式数据存 `portfolio_virtual.json`，不污染主仓
- 删除持仓走 `/portfolio remove` CLI（HTTP 无 DELETE 端点，DELETE 请求恒 405）

## 推送通知配置

Web 服务在持仓 CRUD（加仓/减仓/清仓等）时会通过 `NotificationManager` 异步推送通知。
配置位于 `scripts/config/notification.yaml`，支持 3 个通道：

| 通道 | 启用方式 | 必填字段 |
|------|---------|---------|
| Bark | `bark.enabled: true` | `bark.key`（Bark 推送 Key，iOS 设备上 Bark App 获取） |
| 企业微信 | `wechat_work.enabled: true` | `wechat_work.key`（群机器人 Webhook Key） |
| 钉钉 | `dingtalk.enabled: true` | `dingtalk.token` + `dingtalk.secret`（加签模式） |

> `notification.yaml` 的 `rules:` 段当前无消费方（盘中规则预警能力未接线），
> 仅 `channels/throttle/logging` 三段生效；配置 `webhook.enabled` 亦无效（无此通道）。

未配置任何通道时，`/portfolio-web` 启动时会输出 `⚠ 未配置通道`，但服务正常运行。
`--no-notify` 参数完全跳过通知推送（不读 yaml、不实例化 manager）。

频率控制：`throttle.dedup_window`（默认 15 分钟）+ `throttle.daily_limit`（默认 20 条/天）+
`throttle.quiet_hours`（默认 `15:05-09:25` 非交易时段静默——**静默期内所有持仓 CRUD 推送被丢弃**，
早盘录入若未收到通知属预期行为，可按需改小窗口）。
紧急消息（`urgent=True`）绕过每日上限但仍受去重窗口限制。

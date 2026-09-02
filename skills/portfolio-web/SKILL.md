---
name: portfolio-web
description: 持仓 Web 录入与查询服务。触发词：持仓 web、portfolio web、启动 Web 录入、查持仓 API。从 portfolio 拆分：仅负责 Web 服务子功能。
version: 1.22.1
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

- `POST /api/positions` - 创建/更新持仓
- `GET /api/positions` - 查询当前持仓
- `DELETE /api/positions/<code>` - 删除持仓

完整 CRUD 操作见 [`/portfolio`](../portfolio/SKILL.md)。

## Instructions

使用中文输出。Web 服务依赖 `scripts/data/portfolio.json` 中的持仓数据。
同时只允许一个实例占用端口（`lsof -i:8765`）。

输出遵循统一模板：首行为服务状态，尾行为端口 + 数据时间戳。详见 `../_shared/references/output-template.md`。

## Guardrails

- 持仓数据修改须走 `PortfolioManager` API，不要直接编辑 JSON
- 并发写入冲突时使用锁机制（详见 `scripts/portfolio/manager.py`）
- `--virtual` 模式数据存 `portfolio_virtual.json`，不污染主仓
- 删除前必须二次确认（DELETE 返回 405）

## 推送通知配置

Web 服务在持仓 CRUD（加仓/减仓/清仓等）时会通过 `NotificationManager` 异步推送通知。
配置位于 `scripts/config/notification.yaml`，支持 4 个通道：

| 通道 | 启用方式 | 必填字段 |
|------|---------|---------|
| Bark | `bark.enabled: true` | `bark.key`（Bark 推送 Key，iOS 设备上 Bark App 获取） |
| 企业微信 | `wechat_work.enabled: true` | `wechat_work.key`（群机器人 Webhook Key） |
| 钉钉 | `dingtalk.enabled: true` | `dingtalk.token` + `dingtalk.secret`（加签模式） |
| 自定义 Webhook | `webhook.enabled: true` | `webhook.url`（HTTPS 强校验，拒绝私有 IP 防 SSRF） |

未配置任何通道时，`/portfolio web` 启动时会输出 `⚠ 未配置通道`，但服务正常运行。
`--no-notify` 参数完全跳过通知推送（不读 yaml、不实例化 manager）。

频率控制：`throttle.dedup_window`（默认 15 分钟）+ `throttle.daily_limit`（默认 20 条/天）。
紧急消息（`urgent=True`）绕过每日上限但仍受去重窗口限制。

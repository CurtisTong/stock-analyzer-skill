---
name: portfolio-web
description: 持仓 Web 录入与查询服务。触发词：持仓 web、portfolio web、启动 Web 录入、查持仓 API。从 portfolio 拆分：仅负责 Web 服务子功能。
version: 1.12.0
model: sonnet
allowed-tools: Bash(python3 scripts/portfolio_web.py *) Bash(curl -X POST http://127.0.0.1:8765/api/positions *) Bash(lsof -i:8765 *) Read(./scripts/data/portfolio.json) Read(./scripts/config/notification.yaml) Read(./skills/_shared/references/*.md)
---

# Portfolio Web Service

持仓 Web 录入子服务。本文档从 `/portfolio` 拆分，仅覆盖 Web 相关操作。

## Usage

```text
/portfolio-web                             # 启动 Web 服务（默认 127.0.0.1:8765）
/portfolio-web --port 9000                 # 指定端口
/portfolio-web --open                      # 启动后自动打开浏览器
/portfolio-web --no-notify                 # 启动时不推送通知
/portfolio-web --no-monitor                # 禁用后台策略监控
/portfolio-web --virtual                   # 启动虚拟持仓模式（portfolio_virtual.json）
/portfolio-web --stop                      # 停止后台运行的 Web 服务
/portfolio-web --status                    # 查看 Web 服务运行状态
```

## API 端点

- `POST /api/positions` - 创建/更新持仓
- `GET /api/positions` - 查询当前持仓
- `DELETE /api/positions/<code>` - 删除持仓

完整 CRUD 操作见 [`/portfolio`](../portfolio/SKILL.md)。

## Instructions

使用中文输出。Web 服务依赖 `scripts/data/portfolio.json` 中的持仓数据。
启动后默认启用后台策略监控（`--no-monitor` 关闭）。同时只允许一个实例占用端口（`lsof -i:8765`）。

输出遵循统一模板：首行为服务状态，尾行为端口 + 数据时间戳。详见 `../_shared/references/output-template.md`。

## Guardrails

- 持仓数据修改须走 `PortfolioManager` API，不要直接编辑 JSON
- 并发写入冲突时使用锁机制（详见 `scripts/portfolio/manager.py`）
- `--virtual` 模式数据存 `portfolio_virtual.json`，不污染主仓
- 删除前必须二次确认（DELETE 返回 405）

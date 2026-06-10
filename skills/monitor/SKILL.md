---
name: monitor
description: A 股盘中监控与消息推送 skill。支持持仓异动监控、价格预警、技术信号推送、市场环境预警，通过 Bark/企业微信/钉钉等通道推送通知。用于持仓实时盯盘（盘中定时任务），非交易时段静默。
version: 1.3.1
model: sonnet
allowed-tools: Bash(python3 scripts/*) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/data/portfolio.json) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/scripts/config/notification.yaml) Read(//Users/curtis/Documents/curtis/stock-analyzer-skill/skills/**)
---

# Monitor

盘中监控与消息推送——持仓异动实时预警。

## Usage

```text
/monitor [操作] [参数...]
```

| 操作     | 说明          | 示例              |
| -------- | ------------- | ----------------- |
| `start`  | 启动盘中监控  | `/monitor start`  |
| `stop`   | 停止监控      | `/monitor stop`   |
| `status` | 查看监控状态  | `/monitor status` |
| `test`   | 测试推送通道  | `/monitor test`   |
| `config` | 查看/修改配置 | `/monitor config` |
| `log`    | 查看推送日志  | `/monitor log`    |

### 自然语言

- "启动盘中监控"
- "测试一下推送"
- "看看最近推了什么消息"
- "下午开会别推了"（静默模式）
- "恢复推送"

## Instructions

使用中文输出。监控依赖 `data/portfolio.json` 中的持仓数据。

### 初始化

```python
import sys; sys.path.insert(0, "scripts")
from monitor import NotificationManager
from portfolio import PortfolioManager

nm = NotificationManager()
pm = PortfolioManager()
```

### 推送通道

配置文件: `scripts/config/notification.yaml`

支持通道:

- **Bark** (iOS): 免费、自托管、API 极简
- **企业微信机器人**: 国内用户习惯、群聊支持
- **钉钉机器人**: 国内普及率高
- **Webhook**: 通用，可接入任何系统

通道实现: `scripts/monitor/channels/`

### 推送规则

| 类型     | 触发条件         | 默认阈值   |
| -------- | ---------------- | ---------- |
| 价格预警 | 涨跌幅超阈值     | ±3%        |
| 价格预警 | 触及支撑/压力位  | -          |
| 价格预警 | 涨跌停附近       | 距涨停 <1% |
| 技术信号 | MACD 金叉/死叉   | -          |
| 技术信号 | 均线突破         | 20/60 日线 |
| 技术信号 | 放量异动         | 量比 >2.0  |
| 持仓风险 | 风险状态变更     | -          |
| 持仓风险 | 连续跑输板块     | 2 天       |
| 市场环境 | 大盘涨跌幅       | ±2%        |
| 市场环境 | 北向资金大幅流动 | ±50 亿     |

### 频率控制

- 同类消息 15 分钟去重
- 每日推送上限 20 条
- 非交易时段（15:05-09:25）静默

### 推送消息格式

```
标题: 🔴 宝丰能源 触及支撑位
内容: 现价 17.80 (-3.2%)，已跌破 20 日支撑 18.10
      建议关注是否有效跌破，考虑减仓
      —— 持仓 1000 股 | 浮亏 -700 (-3.8%)
```

## Guardrails

- 非交易时段（15:05-09:25）静默，不推送任何消息
- 同类消息 15 分钟去重，避免信息轰炸
- 紧急预警（破位/止损）可通过 `urgent=True` 绕过每日上限（但仍受去重窗口限制）
- 无活跃通道时返回 `reason: "no_channels"`，不丢消息
- 推送失败时记录日志（含错误详情），不阻塞监控循环
- 不支持并发写入持仓数据，多进程场景需串行化

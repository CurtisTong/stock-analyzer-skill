# 快速入门

5 分钟内跑通第一个技能。

> 💡 **新手？** 先看 [README.md](../README.md) 5 行上手；本指南是 5 分钟跑通第一个技能。

## 前置条件

- **Python 3.11+**（`pyproject.toml` `requires-python = ">=3.11"`）
- Claude Code、Codex 或 DeepSeek Harness 环境之一
- **会开终端、能跑 `install.sh`**——不需要写代码，但这不是"点开即用"的 App

> 30 秒判断：如果你不想碰终端，这里不适合你（见[定位说明](positioning.md)）。想继续的话，下面三步就能看到第一个结果。

## 安装

DeepSeek Harness 用户跳到「方式三」；Claude Code / Codex 用户两种方式等价（底层都是创建 symlink）。

### 方式一：Claude Code Plugin

在项目根目录（含 `.claude-plugin/`）：

```bash
claude plugins marketplace add . && claude plugins install stock-analyzer
```

### 方式二：install.sh（git clone）

```bash
cd stock-analyzer-skill
./install.sh
```

`install.sh` 会在 `~/.claude/skills/`、`~/.codex/skills/` 下创建 12 个 symlink，在项目级 `.claude/skills/`、`.codex/skills/`、`.dsh/skills/` 下创建指向 `../../skills/stock` 这样的链接（每个技能名一条）并校验完整性。

重启 Claude Code / Codex 即可识别。

### 方式三：DeepSeek Harness（无需安装）

在 DSH 中打开仓库即可：项目根 `.dsh/skills/` 已随仓库追踪，12 条入口指向 `skills/` 权威源；DSH 会话会自动发现技能，无需 `install.sh` 或重启。`/backtest` 保留源 frontmatter 的 `disable-model-invocation: true`，不会出现在模型自动选择目录里，但用户显式输入 `/backtest` 仍可调用。

## 验证安装

先跑一条**不需要任何 AI 代理**的自检命令，30 秒确认数据链路通了：

```bash
python3 scripts/quote.py sh600989
```

真实输出（宝丰能源，数值随行情变化）：

```text
> 数据完整性：ok 1/1 只报价 · 数据源 未记录 · 2026-11-22T08:47
代码         名称               现价     涨跌%      PE    换手%      市值亿
------------------------------------------------------------
sh600989   宝丰能源          20.29     0.0     8.9   0.53  1487.94
```

再跑项目冒烟测试：

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

## 初始化股票池（零配置）

首次使用前，初始化股票池：

```bash
/screener init
```

**零配置可用**：这里指股票池数据内置预置快照，无需任何 token 或 API 密钥；但终端环境（`install.sh`）仍需准备，见[定位说明](positioning.md)。

> **跳过初始化会怎样？** 使用 `/stock`、`/screener`、`/sector` 等命令时，如果股票池未初始化，系统会自动触发初始化或提示先运行 `/screener init`。

如需联网获取最新数据：

```bash
/screener init force
```

如需离线模式（不访问 API）：

```bash
/screener init default
```

## 第一个命令

```bash
/stock sh600519 quick
```

返回：基本面 + 估值 + 技术面 3 分钟快评。输出结构如下（**以下为项目 demo 的合成演示输出，数值随行情变化，结构稳定**）：

```text
🎯 🟢 贵州茅台（sh600519）现价 1392.05（+2.81%）｜综合评分 42.1（中性）｜谨慎回避
────────────────────────────────────
【基本面】ROE 24.5%（行业Top）│ 毛利率 91.5% │ 净利YoY -0%
【估值】PE 22.1 │ 近5年估值分位 23%
【技术面】MA 多头排列 │ MACD 0 │ RSI 70 │ KDJ超买区(J=98)
【风险收益】观察上沿 ~1480 │ 观察下沿 ~1320（非目标价/止损位）
────────────────────────────────────
📊 数据时间戳: 2026-10-31T12:27 | 数据源: 行情[tencent], K线[sina], 财务[eastmoney]
📜 本输出为量化研判参考，不构成投资建议，据此操作风险自负
```

> 📖 看不懂 PE / ROE / 夏普？[`methodology.md`](../methodology.md) 术语速查，或在 Claude Code 里用 `/learn` 随时提问。

**下一步**：想看完整论证用 `/stock sh600519 full`；想每天固定看，把[两个日常入口](../README.md#-两个日常入口)用成习惯。

## v1.7.0 新增能力（可选体验）

按需体验，不需要也能用：

| 能力             | 命令                                                           | 适用场景                                 |
| ---------------- | -------------------------------------------------------------- | ---------------------------------------- |
| 专家圆桌决策     | `/stock sh600989 debate`                                       | 想看 8 位 active 专家辩论 + 最终方向 + 仓位建议 |
| 单组辩论         | `/stock sh600989 debate 长线` 或 `/stock sh600989 debate 短线` | 只想听某一阵营的观点                     |
| 美股参考（盘中） | `/market full` 自动拉美股收盘                                  | 隔夜美股大跌时评估 A 股开盘情绪          |
| 全市场股票池     | `/screener init full-market` 一次性拉 ~5000 只 A 股            | 想做全市场扫描，不被默认 20 只限死       |
| 校准报告查看     | `python3 scripts/calibration.py report`                        | 看历史专家准确率 + 当前校准因子          |

## 常见问题

### 权限问题

```bash
chmod +x install.sh
```

### Python 版本问题

确认 python3 可用：

```bash
python3 --version
```

### 网络问题 / 数据源挂了

```text
【症状】命令长时间无输出；或某些字段显示 N/A、提示"数据缺失"；curl 无返回。
【根因】多为上游 API 临时限频或本地网络/DNS 异常——这是工具侧的数据源问题，不是你操作错了。
【下一步】
 ① 等 60 秒再跑一次，熔断器会在这段时间自行恢复；
 ② 用预置快照兜底：python3 scripts/init_pool.py --default；
 ③ 看各源状态：python3 scripts/monitor.py --sources；
 ④ 确认能访问国内 API：curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8 | head -1
    （应返回包含"宝丰能源"的行情数据）；
 ⑤ 持续失败请带命令与报错原文到 GitHub issue 上报。
```

### 股票代码写错了

```text
【症状】返回"未找到标的"、空数据，或查出来的不是你想看的公司。
【根因】代码前缀写错（sh/sz 混用）或用了有歧义的股票简称。
【下一步】用带交易所前缀的代码最稳：sh600519（沪）、sz000858（深）；
 纯数字 600519 会自动推断；简称"贵州茅台"在多个相似名时可能错配。
 不确定时先跑 python3 scripts/quote.py sh600519 验证代码能否查到。
```

### 如何获取最新股票池数据？

默认使用预置数据（离线可用）。如需最新数据，运行 `/screener init force` 强制联网刷新。

### smoke_test 报错怎么办？

```bash
# 确保在项目根目录运行
cd stock-analyzer-skill
./tests/smoke_test.sh

# 如果仍有问题，检查 Python 版本
python3 --version  # 需要 3.11+
```

### Claude Code 不识别 skills？

1. 确认已重启 Claude Code
2. 运行 `claude skills list` 查看已安装的 skills
3. 如果使用手动安装，检查 symlink 是否正确：`ls -la ~/.claude/skills/`

### DeepSeek Harness 不显示 skills？

1. 确认打开的工作区是仓库根目录（含 `.git`）——DSH 以最近的 `.git` 祖先为项目根
2. 检查入口：`ls -la .dsh/skills/`，应有 12 条指向 `../../skills/stock` 这类路径的链接（每个技能名一条）
3. 校验契约：`python3 -m unittest tests.contracts.test_dsh_skill_support -v`
4. 若链接被误删，重跑 `./install.sh` 即可恢复

## ⚠️ 免责声明

本工具仅供学习和研究参考，不构成任何投资建议。所有分析结果基于公开数据和量化模型，
存在局限性和偏差。投资有风险，决策需谨慎，请结合自身判断和专业顾问意见。

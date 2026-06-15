# 快速入门

5 分钟内跑通第一个技能。

## 前置条件

- Python 3.x
- Claude Code 环境

## 安装

### 方式一：Claude Code Plugin（推荐）

```bash
claude plugins marketplace add . && claude plugins install stock-analyzer
```

### 方式二：手动安装

```bash
cd ~/Documents/curtis/stock-analyzer-skill
./install.sh
```

`install.sh` 会在 `~/.claude/skills/` 下创建 11 个 symlink，指向本包的 `skills/` 目录。

重启 Claude Code 即可识别。

## 验证安装

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

## 初始化股票池（零配置）

首次使用前，初始化股票池：

```
/stock-init
```

**零配置可用**：脚本内置预置默认股票池数据，无需任何 token 或 API 密钥即可使用。

> **跳过初始化会怎样？** 使用 `/stock`、`/screener`、`/sector` 等命令时，如果股票池未初始化，系统会自动触发初始化或提示先运行 `/stock-init`。

如需联网获取最新数据：

```
/stock-init force
```

如需离线模式（不访问 API）：

```
/stock-init default
```

## 第一个命令

```
/stock sh600989 quick
```

返回：基本面+估值+技术面 3 分钟快评。

## v1.7.0 新增能力（可选体验）

按需体验，不需要也能用：

| 能力             | 命令                                                           | 适用场景                                |
| ---------------- | -------------------------------------------------------------- | --------------------------------------- |
| 专家圆桌决策     | `/stock sh600989 debate`                                       | 想看 8 位专家辩论 + 最终方向 + 仓位建议 |
| 单组辩论         | `/stock sh600989 debate 长线` 或 `/stock sh600989 debate 短线` | 只想听某一阵营的观点                    |
| 美股参考（盘中） | `/market full` 自动拉美股收盘                                  | 隔夜美股大跌时评估 A 股开盘情绪         |
| 全市场股票池     | `/stock-init full-market` 一次性拉 ~5000 只 A 股               | 想做全市场扫描，不被默认 20 只限死      |
| 校准报告查看     | `python3 scripts/calibration.py report`                        | 看历史专家准确率 + 当前校准因子         |

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

### 网络问题

确认能访问国内 API：

```bash
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8 | head -1
```

应返回包含"宝丰能源"的行情数据。

### 如何获取最新股票池数据？

默认使用预置数据（离线可用）。如需最新数据，运行 `/stock-init force` 强制联网刷新。

### smoke_test 报错怎么办？

```bash
# 确保在项目根目录运行
cd ~/Documents/curtis/stock-analyzer-skill
./tests/smoke_test.sh

# 如果仍有问题，检查 Python 版本
python3 --version  # 需要 3.9+
```

### Claude Code 不识别 skills？

1. 确认已重启 Claude Code
2. 运行 `claude skills list` 查看已安装的 skills
3. 如果使用手动安装，检查 symlink 是否正确：`ls -la ~/.claude/skills/`

## ⚠️ 免责声明

本工具仅供学习和研究参考，不构成任何投资建议。所有分析结果基于公开数据和量化模型，
存在局限性和偏差。投资有风险，决策需谨慎，请结合自身判断和专业顾问意见。

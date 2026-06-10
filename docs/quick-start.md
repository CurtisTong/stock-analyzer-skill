# 快速入门

5 分钟内跑通第一个技能。

## 前置条件

- Python 3.x
- Claude Code 环境

## 安装

```bash
cd ~/Documents/curtis/stock-analyzer-skill
./install.sh
```

`install.sh` 会在 `~/.claude/skills/` 下创建 8 个扁平 symlink，指向本包的 `.claude/skills/` 目录。

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

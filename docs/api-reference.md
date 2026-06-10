# API 参考

脚本命令行参数和数据源快速查阅。

## 脚本命令行参数

### init_pool.py - 初始化股票池

```bash
python3 scripts/init_pool.py [--force] [--top N] [--default]
```

参数：

- `--force` / `-f`：强制重新初始化（忽略已有数据）
- `--top` / `-n <N>`：每板块取 Top N（默认 20）
- `--default` / `-d`：使用预置默认数据（不访问 API，离线可用）

示例：

```bash
python3 scripts/init_pool.py                    # 检测并初始化
python3 scripts/init_pool.py --force            # 强制重新初始化
python3 scripts/init_pool.py --top 30           # 每板块取 Top 30
python3 scripts/init_pool.py --default          # 离线模式
```

特性：

- 零配置可用：内置预置默认股票池数据，无需 token
- 自动 fallback：API 失败时自动使用预置数据
- 无 token 时自动尝试免费访问 API

### refresh_pool.py - 刷新股票池

```bash
python3 scripts/refresh_pool.py [--sector 板块] [--top N] [--sort 排序] [--dry-run] [--diff] [--default]
```

参数：

- `--sector` / `-s <板块>`：只刷新指定板块
- `--top` / `-n <N>`：每板块取 Top N（默认 20）
- `--sort <排序>`：amount/cap/pe/turnover（默认 amount）
- `--dry-run`：只打印不写入
- `--diff`：对比当前池显示变更
- `--default`：使用预置默认数据初始化（不访问 API）

示例：

```bash
python3 scripts/refresh_pool.py                 # 刷新全部板块
python3 scripts/refresh_pool.py --sector 机器人  # 只刷新指定板块
python3 scripts/refresh_pool.py --diff          # 显示变更
python3 scripts/refresh_pool.py --default       # 离线模式
```

### quote.py - 实时行情查询

```bash
python3 scripts/quote.py <code|@文件> [-j]
```

参数：

- `<code|@文件>`：股票代码（支持逗号分隔批量），或 `@文件路径` 从文件读取代码列表
- `-j`：JSON 格式输出

示例：

```bash
python3 scripts/quote.py sh600989
python3 scripts/quote.py sh600989,sz000807,sh518880    # 批量查询
python3 scripts/quote.py @data/watchlist.txt             # 从文件读取
python3 scripts/quote.py sh600989 -j                    # JSON 输出
```

### finance.py - 财务数据查询

```bash
python3 scripts/finance.py <code> [-c <codes>] [-j]
```

参数：

- `<code>`：股票代码（必须大写 SH/SZ，如 SH600989）
- `-c <codes>`：逗号分隔的批量代码列表
- `-j`：JSON 格式输出

示例：

```bash
python3 scripts/finance.py SH600989
python3 scripts/finance.py -c SH600989,SZ000807         # 批量查询
python3 scripts/finance.py SH600989 -j                  # JSON 输出
```

### kline.py - K 线数据查询

```bash
python3 scripts/kline.py <code> [scale] [datalen] [-j]
```

参数：

- `<code>`：股票代码（sh600989 / sz000807）
- `[scale]`：周期，默认 240（5/15/30/240 分钟）
- `[datalen]`：数据条数，默认 30（10/15/30/48）
- `-j`：JSON 格式输出

示例：

```bash
python3 scripts/kline.py sh600989 240 30
python3 scripts/kline.py sh600989 5 48                  # 5分钟K线
python3 scripts/kline.py sh600989 240 30 -j             # JSON 输出
```

### screener.py - 多因子选股

```bash
python3 scripts/screener.py [options]
```

选项：

- `--strategy <策略>`：balanced/quality_value/growth_momentum/defensive/turning_point（默认 balanced）
- `--sector <板块>`：板块名称，支持模糊匹配
- `--top <N>`：返回前 N 个候选（默认 10）
- `--codes <代码>`：自定义股票池（逗号分隔），优先于 --sector
- `--min-amount <万>`：最低成交额，单位万元（默认 5000）
- `--min-cap <亿>`：最低总市值，单位亿元（默认 40）
- `--exclude-loss`：剔除 EPS<=0 标的
- `--json` / `-j`：JSON 格式输出

示例：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析

```bash
python3 scripts/technical.py <code> [--quick] [--classify] [--no-chan] [--scale N] [--datalen N] [--market-index CODE] [--json]
```

参数：

- `<code>`：证券代码（如 sh600989）
- `--quick` / `-q`：快速摘要模式（趋势、量价、支撑阻力）
- `--classify`：启用个股分类+缠论+本土战法+市场环境自适应
- `--no-chan`：跳过缠论分析（仅与 --classify 配合）
- `--scale` / `-s <N>`：K线周期（240=日K, 60=60分钟, 30=30分钟, 15=15分钟, 5=5分钟，默认 240）
- `--datalen <N>`：K线数量（默认 250）
- `--market-index <CODE>`：市场环境参考指数（如 sh000001）
- `--json` / `-j`：JSON 格式输出

示例：

```bash
python3 scripts/technical.py sh600989                    # 完整分析
python3 scripts/technical.py sh600989 --quick            # 快速模式
python3 scripts/technical.py sh600989 --classify         # 分类+缠论+战法
python3 scripts/technical.py sh600989 --classify --no-chan  # 跳过缠论
python3 scripts/technical.py sh600989 --scale 60         # 60分钟K线
```

### announcements.py - 公告/研报查询

```bash
python3 scripts/announcements.py <code> [reports] [-j]
```

参数：

- `<code>`：股票代码（如 600989，不需要 sh/sz 前缀）
- `[reports]`：传入 `reports` 时查研报，默认查公告
- `-j`：JSON 格式输出

示例：

```bash
python3 scripts/announcements.py 600989                  # 查公告
python3 scripts/announcements.py 600989 reports          # 查研报
python3 scripts/announcements.py 600989 -j              # JSON 输出
```

示例：

```bash
python3 scripts/announcements.py SH600989
```

## 数据源 API

### 腾讯实时行情字段映射

字段按 `~` 分隔，从 1 开始：

| 字段位 | 含义       | 示例        |
| ------ | ---------- | ----------- |
| 1      | 市场代码   | 1=沪, 51=深 |
| 2      | 名称       | 宝丰能源    |
| 3      | 代码       | 600989      |
| 4      | 当前价     | 24.59       |
| 5      | 昨收       | 24.92       |
| 33     | 涨跌幅%    | -0.49       |
| 37     | 成交量(手) | 547985      |
| 38     | 成交额(万) | 134521      |
| 39     | 换手率%    | 0.75        |
| 40     | PE(动)     | 14.34       |

### 东财财务数据字段映射

| 字段               | 含义            | 示例值 |
| ------------------ | --------------- | ------ |
| EPSJB              | 每股收益        | 0.5    |
| ROEJQ              | ROE(加权)       | 7.28   |
| TOTALOPERATEREVETZ | 营收同比增长%   | 22.9   |
| PARENTNETPROFITTZ  | 净利润同比增长% | 50.2   |
| XSMLL              | 毛利率%         | 37.4   |
| XSJLL              | 净利率%         | 27.7   |
| ZCFZL              | 资产负债率%     | 44.9   |
| BPS                | 每股净资产      | 7.11   |
| MGJYXJJE           | 每股经营现金流  | 0.76   |

注意：

- `WEIGHTAVG_ROE`、`GROSSPROFITINRATIO`、`NETPROFITRATIO` 返回 None，不要用
- 正确字段是 `ROEJQ`、`XSMLL`、`XSJLL`

### 新浪 K 线参数

| 参数    | 含义       | 取值                |
| ------- | ---------- | ------------------- |
| symbol  | 股票代码   | sh600989 / sz000807 |
| scale   | 周期(分钟) | 5/15/30/240         |
| ma      | 均线       | no=不显示           |
| datalen | 数据条数   | 10/15/30/48         |

## 输出格式说明

### 文本格式

默认人类可读格式，适合直接阅读。

### JSON 格式

使用 `--json` 参数获取 JSON 格式输出，适合程序处理。

## 错误码与常见问题

### 中文乱码

原因：GBK 编码未转换
解决：加 `iconv -f GBK -t UTF-8`

### 财务字段返回 None

原因：字段名错误
解决：用 ROEJQ 不用 WEIGHTAVG_ROE

### JSON 解析失败

原因：返回空或格式错误
解决：加 `2>/dev/null` + 判断 `d['data']`

### K 线数据为空

原因：symbol 格式错误
解决：检查 sh/sz 前缀

### 批量查询部分失败

原因：超过 API 限制
解决：分批查询，每批<=15 只

# API 参考

脚本命令行参数和数据源快速查阅。

## 脚本命令行参数

### quote.py - 实时行情查询

```bash
python3 scripts/quote.py <code>
```

示例：

```bash
python3 scripts/quote.py sh600989
```

### finance.py - 财务数据查询

```bash
python3 scripts/finance.py <code>
```

示例：

```bash
python3 scripts/finance.py SH600989
```

注意：code 参数必须大写 SH/SZ。

### kline.py - K 线数据查询

```bash
python3 scripts/kline.py <code> [scale] [datalen]
```

示例：

```bash
python3 scripts/kline.py sh600989 240 30
```

参数：

- code：股票代码（sh600989 / sz000807）
- scale：周期（5/15/30/240 分钟）
- datalen：数据条数（10/15/30/48）

### screener.py - 多因子选股

```bash
python3 scripts/screener.py [options]
```

选项：

- `--strategy <策略>`：balanced/quality_value/growth_momentum/defensive/turning_point
- `--sector <板块>`：板块名称
- `--top <N>`：返回前 N 个候选
- `--codes <代码>`：自定义股票池（逗号分隔）
- `--exclude-loss`：剔除亏损股
- `--json`：JSON 格式输出

示例：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析

```bash
python3 scripts/technical.py <code> [mode]
```

示例：

```bash
python3 scripts/technical.py sh600989 full
```

模式：

- quick：趋势、量价、支撑阻力
- full：完整技术分析（均线/MACD/KDJ/BOLL/缠论/本土战法）

### announcements.py - 公告/研报查询

```bash
python3 scripts/announcements.py <code>
```

示例：

```bash
python3 scripts/announcements.py SH600989
```

## 数据源 API

### 腾讯实时行情字段映射

字段按 `~` 分隔，从 0 开始：

| 字段位 | 含义       | 示例        |
| ------ | ---------- | ----------- |
| 1      | 市场代码   | 1=沪, 51=深 |
| 2      | 代码       | 600989      |
| 3      | 名称       | 宝丰能源    |
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

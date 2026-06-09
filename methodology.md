---
name: stock-analyzer-methodology
description: 投资分析完整方法论——五层框架、专家讨论模式、数据源、仓位管理、决策流程
source: 抽离自 ~/.claude/memory/investment-methodology.md
version: 1.0
---

# 投资分析方法论

## 一、数据源

### 实时行情（腾讯）
```
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8
```
字段: 3=名称, 4=现价, 33=涨跌幅, 40=PE, 37=成交量, 39=换手率

### 财务数据（东方财富）
```
curl -s "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=SH600989"
```
JSON结构: `response['data'][0]`
关键字段: EPSJB(每股收益), ROEJQ(加权ROE), TOTALOPERATEREVETZ(营收增速), PARENTNETPROFITTZ(净利增速), XSMLL(毛利率), XSJLL(净利率), ZCFZL(负债率), BPS(每股净资产), MGJYXJJE(每股经营现金流)

### K线数据（新浪财经）
日K: `scale=240`, 5分钟: `scale=5`, 15分钟: `scale=15`
```
curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600989&scale=240&ma=no&datalen=30"
```

### 板块ETF
510050(上证50), 510300(沪深300), 510500(中证500), 512010(医药), 512480(半导体), 512690(白酒), 512800(银行), 513120(港股创新药), 518880(黄金), 515030(新能源车)

## 二、五层分析框架

### 第1层：基本面筛选
- ROE > 15%（优秀）, > 20%（顶级）
- 净利增速 > 20%（成长）, > 50%（高速）
- 毛利率 > 30%（有壁垒）
- 负债率 < 60%（健康）
- 经营现金流/EPS > 1（利润含金量高）

### 第2层：估值评估
- PE绝对值 vs 行业对比
- PEG = PE / 净利增速（<1低估, 1-2合理, >2偏贵）
- PE/ROE（<3为好）
- 历史估值分位

### 第3层：技术面确认
- 30日K线趋势（上升/横盘/下降）
- 关键支撑/阻力位
- 成交量变化（放量/缩量）
- 5分钟分时形态（出货/吸筹/震荡）

### 第4层：板块与风格分析
- 板块轮动节奏
- 大小盘分化程度
- 市场风格（成长vs价值、进攻vs防御）
- 资金流向

### 第5层：风险收益比计算
- 情景分析（牛市/基准/震荡/悲观/极端）
- 概率加权期望收益
- 凯利公式：f = p - (1-p)/b（p=胜率, b=赔率）
- 止损/止盈位设定

## 三、专家讨论模式（8人圆桌）

> 完整档案见 [experts/README.md](experts/README.md)，每位专家独立成文（1200-1500 字深度档）。

### 长线4人（价值发现）
| 专家 | 风格 | 核心逻辑 | 档案 |
|------|------|---------|------|
| 巴菲特 | 价值投资 | 好生意+好价格+长期持有，偏好高ROE低PE | [buffett.md](experts/buffett.md) |
| 彼得·林奇 | 成长投资 | PEG<1增速消化估值，偏好高增速合理PE | [lynch.md](experts/lynch.md) |
| 索罗斯 | 宏观/趋势 | 趋势确认+反身性，技术面+资金面 | [soros.md](experts/soros.md) |
| 段永平 | 逆向投资 | 好公司+安全边际，低估值+护城河 | [duan_yongping.md](experts/duan_yongping.md) |

### 短线4人（时机把握）
| 专家 | 风格 | 核心逻辑 | 档案 |
|------|------|---------|------|
| 徐翔 | 涨停板战法 | 龙头+量价配合，打板追涨 | [xu_xiang.md](experts/xu_xiang.md) |
| 赵老哥 | 趋势龙头 | 趋势确认+持仓周期，波段操作 | [zhao_laoge.md](experts/zhao_laoge.md) |
| 炒股养家 | 情绪流 | 情绪周期+板块轮动，情绪拐点买卖 | [chaogu_yangjia.md](experts/chaogu_yangjia.md) |
| 作手新一 | 强势股低吸 | 回调到支撑位低吸，分批建仓 | [zuoshou_xinyi.md](experts/zuoshou_xinyi.md) |

### 讨论流程
1. 基本面数据呈现 → 共识
2. 多空辩论 → 正方vs反方
3. 操作方案对比 → 不同风格方案
4. 投票汇总 → 多数决+少数保留
5. 最终建议 → 折中方案+风险预案

## 四、仓位管理

### 凯利公式
```
最优仓位 f = p - (1-p)/b
p = 胜率, b = 赔率(期望收益/最大风险)
调整后最优仓位 ≈ f × 0.5（安全系数）
```

### 仓位分级
| 仓位 | 含义 | 适用场景 |
|------|------|---------|
| 0% | 不碰 | 基本面差/估值过高 |
| 3% | 试探仓 | 等回调/方向不明 |
| 5% | 标准仓 | 确认买入信号 |
| 8% | 重仓 | 强烈看好+低位 |
| 10-15% | 核心仓 | 最强标的+安全边际充足 |

### 集中度控制

| 约束项 | 上限 | 理由 |
| ------ | ---- | ---- |
| 单只个股 | 15% | 避免单一标的黑天鹅 |
| 单一行业 | 30% | 避免行业系统性风险 |
| 前 3 大持仓 | 45% | 保持适度分散 |
| 总仓位（牛市） | 90% | 保留 10% 现金应对波动 |
| 总仓位（震荡） | 70% | 保留 30% 现金 |
| 总仓位（熊市） | 50% | 保留 50% 现金 |

### 止损铁律
- 个股：跌破关键支撑位收盘确认即止损
- 组合：单日亏损>3%减仓
- 板块：板块趋势转空减仓
- 时间止损：短线 5 个交易日无预期表现减仓 50%，中线 20 个交易日重新评估

### 加仓规则
- 浮盈 > 10% 且趋势确认（MA 多头 + 量价配合）：可加仓
- 每次加仓不超过原仓位的 50%
- 单只总仓位不超过 30%（含加仓）
- 加仓必须有新资金来源或减持其他标的

### 极端情景预案
- 个股连续 2 个跌停：次日集合竞价挂跌停价卖出
- 组合单周亏损 > 10%：强制减仓至 50% 以下
- 全市场跌停 > 1000 家：暂停所有新开仓，等待流动性恢复

## 五、决策流程

```
研究标的 → 基本面筛选(ROE/增速/毛利)
         → 估值评估(PE/PEG)
         → 技术面确认(支撑/趋势)
         → 板块分析(轮动/风格)
         → 专家讨论(多空辩论)
         → 风险收益比计算
         → 仓位决策(凯利公式)
         → 建仓节奏(分批)
         → 持续跟踪(止损/止盈)
```

### Skill 协作流程

完整协作关系见 `workflow.md`。常用路径：

| 场景 | 推荐链路 |
|------|----------|
| 自上而下找机会 | `market` → `sector` → `screener` → `stock` → `technical` → `portfolio` |
| 已有个股做验证 | `stock` → `financial-analyst` → `sector` → `technical` → `portfolio` |
| 持仓再平衡 | `portfolio` → `market` → `technical` → `screener` → `stock` |
| 深度研究报告 | `investment-researcher` 总控，按需调用其他 skill |

交接时至少保留：市场状态、板块观点、候选池、基本面评级、技术触发、仓位计划、置信度。

## 六、选股策略系统

选股系统不是“找一只马上买的股票”，而是生成可跟踪候选池。流程必须固定：股票池 → 硬过滤 → 多因子评分 → 策略权重 → 市场适配 → 买点触发。

### 1. A 股市场约束

- 先识别市场板块：主板、创业板、科创板、北交所、ETF。不同板块波动制度不同，不能用同一套追涨风险假设。
- 普通 A 股交易以 T+1 为主，短线策略必须考虑隔夜风险和次日无法立即卖出的限制。
- 涨跌停附近的标的只进入观察池，不做机械追入；高分但流动性不足同样剔除。
- ST、退市风险、长期停牌、成交额过低、市值过小、财务亏损标的优先硬过滤。

### 2. 股票池构建

| 股票池 | 用途 | 数据来源 |
|--------|------|----------|
| 内置板块池 | 快速筛主题/行业 | `data/sector_stocks.json` |
| ETF 映射池 | 判断板块强弱 | `data/sector_etf.csv` |
| 用户自定义池 | 精筛自选或持仓 | `--codes` 或持仓 JSON |
| 全市场池 | 后续扩展 | 需接入完整 A 股列表 |

### 3. 硬过滤

| 过滤项 | 默认规则 | 理由 |
|--------|----------|------|
| ST/退市风险 | 名称含 ST 剔除 | 风险收益结构失真 |
| 成交额 | 低于 5000 万剔除 | 避免冲击成本和流动性陷阱 |
| 总市值 | 低于 40 亿剔除 | 避免壳、小票极端波动 |
| 盈利 | 可选剔除 EPS<=0 | 质量/价值策略必须盈利约束 |
| 涨跌停 | 降低动量分 | 当日可交易性差 |

### 4. 多因子评分

| 因子 | 权重桶 | 指标 | 解释 |
|------|--------|------|------|
| 质量 | quality | ROE、净利增速、营收增速、毛利率、负债率、经营现金流/EPS | 好公司与盈利质量 |
| 估值 | valuation | PE、PB、PEG、PE/ROE | 安全边际和估值消化能力 |
| 动量 | momentum | 20日收益、MA10/MA20、量能比、换手率 | 市场是否开始认可 |
| 流动性 | liquidity | 成交额、总市值、换手适中程度 | 能否交易、能否退出 |
| 波动率 | volatility | 历史收益率标准差（低波动得高分） | A股低波动异象 |

### 5. 策略权重（五因子模型）

| 策略 | 市场环境 | 质量 | 估值 | 动量 | 流动性 | 波动率 |
|------|----------|------|------|------|--------|--------|
| balanced | 震荡/方向不明 | 25% | 20% | 20% | 15% | 20% |
| quality_value | 价值修复/防守 | 35% | 30% | 5% | 12% | 18% |
| growth_momentum | 进攻行情/主线题材 | 18% | 15% | 35% | 12% | 20% |
| defensive | 缩量弱市/避险 | 25% | 22% | 8% | 12% | 33% |
| turning_point | 超跌修复/拐点 | 18% | 18% | 32% | 14% | 18% |

### 6. 输出标准

选股结果必须同时给出：

- 候选排名：总分 + 五因子分。
- 剔除原因：让”为什么没选”可审计。
- 市场适配：当前更适合进攻、均衡还是防守。
- 交易计划：买入触发、失效条件、止损/降仓、仓位上限。
- 后续跟踪：需要复核的财报、公告、板块 ETF、关键均线或支撑位。

### 7. 脚本入口

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

## 七、数据获取工具详解（v1.1.0）

### 1. 代码结构总览

```
scripts/
├── __init__.py           # 入口
├── common/               # 公共工具包（v1.1.0 新增）
│   ├── __init__.py       # 主模块（缓存、HTTP、编码转换）
│   ├── validators.py     # 输入验证器
│   └── exceptions/       # 统一异常类
│       └── __init__.py
├── config/               # 配置加载器（v1.1.0 新增）
│   ├── __init__.py
│   ├── loader.py
│   ├── data_source.yaml
│   ├── industry_thresholds.yaml
│   ├── limits.yaml
│   └── scoring.yaml
├── data/                 # 数据层
├── strategies/           # 选股策略
└── technical/            # 技术分析
```

### 2. Common 模块详解

#### 2.1 缓存与 HTTP

```python
from common import (
    cache_get, cache_set, cache_cleanup,
    http_get, http_get_cached,
    CACHE_DIR,
)

# 带缓存的 HTTP 请求（默认 6 小时 TTL）
data = http_get_cached("https://qt.gtimg.cn/q=sh600989")

# 直接 HTTP 请求
data = http_get(url, timeout=10)
```

#### 2.2 股票代码标准化

```python
from common import normalize_quote_code, normalize_finance_code, plain_code

# 标准化为 sh/sz 前缀格式
quote_code = normalize_quote_code("600989")  # → "sh600989"
finance_code = normalize_finance_code("600989")  # → "sh600989"
plain = plain_code("sh600989")  # → "600989"
```

#### 2.3 输入验证器

```python
from common.validators import (
    validate_code, normalize_code, validate_codes,
    validate_date, validate_date_range,
    validate_positive, validate_in_range,
    ValidationError,
)

# 验证单个代码
if validate_code("sh600989"):
    code = normalize_code("600989")  # → "sh600989"

# 批量验证
codes = validate_codes(["600989", "000807", "300476"])

# 日期验证
validate_date_range("2024-01-01", "2024-12-31")

# 数值验证
validate_positive(10.5, "price", min_value=0)
validate_in_range(15.0, "pe", 0, 1000)
```

#### 2.4 统一异常类

```python
from common.exceptions import (
    StockAnalyzerError, DataError, NetworkError,
    RateLimitError, ParseError, DataUnavailableError,
    BusinessError, ValidationError, StrategyError,
    InsufficientDataError, ConfigurationError,
)

try:
    result = http_get(url)
except RateLimitError as e:
    print(f"触发速率限制: {e.retry_after}秒后重试")
except NetworkError as e:
    print(f"网络错误: {e.url}, {e.message}")
except ValidationError as e:
    print(f"校验失败: {e.field} = {e.value_str}, {e.message}")
```

### 3. Config 模块详解

```python
from config import get_limit_config, get_scoring_config, load_industry_thresholds

# 获取限制配置
st_prefixes = get_limit_config("st_prefixes", ["ST", "*ST"])
min_amount = get_limit_config("min_amount.创业板", 3000)

# 获取评分配置
quality_weights = get_scoring_config("weights.quality")
valuation_weights = get_scoring_config("weights.valuation")

# 获取行业阈值
thresholds = load_industry_thresholds()
```

**配置文件说明：**

| 文件 | 用途 |
|------|------|
| `limits.yaml` | ST 前缀、最低成交额、最低市值、涨跌停限制 |
| `scoring.yaml` | 多因子评分权重、因子阈值 |
| `industry_thresholds.yaml` | 各行业 ROE/PE/增速阈值 |
| `data_source.yaml` | API 端点配置、缓存 TTL |

### 4. 数据层使用

```python
from data import get_quote, get_quotes, get_kline, get_finance

# 单只行情
quote = get_quote("sh600989")
print(quote.price, quote.pe, quote.change_pct)

# 批量行情
quotes = get_quotes(["sh600989", "sz000807"])

# K线数据
bars = get_kline("sh600989", scale=240, datalen=30)  # 日K
bars = get_kline("sh600989", scale=5, datalen=100)   # 5分钟

# 财务数据
records = get_finance("sh600989")
fin = records[0]  # 最新一期
print(fin.ROEJQ, fin.EPSJB, fin.PARENTNETPROFITTZ)
```

### 5. 腾讯实时行情 — 批量查询

**单只查询：**
```bash
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8
```

**批量查询（最多约15只/次）：**
```bash
curl -s "https://qt.gtimg.cn/q=sh600989,sz000807,sh518880,sh603993" | iconv -f GBK -t UTF-8
```

**编码注意：** 返回GBK编码，必须用 `iconv -f GBK -t UTF-8` 转码。

**代码前缀规则：**
- `sh` = 上海（60xxxx, 68xxxx）
- `sz` = 深圳（00xxxx, 30xxxx）

**字段解析（按~分隔，从0开始）：**
| 字段位 | 含义 | 示例 |
|--------|------|------|
| 1 | 市场代码 | 1=沪, 51=深 |
| 2 | 代码 | 600989 |
| 3 | 名称 | 宝丰能源 |
| 4 | 当前价 | 24.59 |
| 5 | 昨收 | 24.92 |
| 33 | 涨跌幅% | -0.49 |
| 37 | 成交量(手) | 547985 |
| 38 | 成交额(万) | 134521 |
| 39 | 换手率% | 0.75 |
| 40 | PE(动) | 14.34 |

**提取脚本模式：**
```bash
curl -s "https://qt.gtimg.cn/q=sh600989" | iconv -f GBK -t UTF-8 | tr ';' '\n' | while read line; do
  name=$(echo "$line" | cut -d'~' -f3)
  price=$(echo "$line" | cut -d'~' -f4)
  change=$(echo "$line" | cut -d'~' -f33)
  pe=$(echo "$line" | cut -d'~' -f40)
  echo "$name | $price | 涨跌:${change}% | PE:$pe"
done
```

### 2. 东方财富财务数据 — JSON解析

**请求：**
```bash
curl -s "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=SH600989"
```

**注意：** `code` 参数必须大写 `SH`/`SZ`。

**JSON结构：**
```json
{
  "data": [
    {"EPSJB": 0.5, "ROEJQ": 7.28, "TOTALOPERATEREVETZ": 22.9, ...},
    {"EPSJB": 1.56, "ROEJQ": 24.84, ...},
    ...
  ]
}
```

**关键字段名（必须用这些，不是WEIGHTAVG_ROE等）：**
| 字段 | 含义 | 示例值 |
|------|------|--------|
| EPSJB | 每股收益 | 0.5 |
| ROEJQ | ROE(加权) | 7.28 |
| TOTALOPERATEREVETZ | 营收同比增长% | 22.9 |
| PARENTNETPROFITTZ | 净利润同比增长% | 50.2 |
| XSMLL | 毛利率% | 37.4 |
| XSJLL | 净利率% | 27.7 |
| ZCFZL | 资产负债率% | 44.9 |
| BPS | 每股净资产 | 7.11 |
| MGJYXJJE | 每股经营现金流 | 0.76 |

**解析脚本（多季度）：**
```bash
curl -s "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=SH600989" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d and 'data' in d and d['data']:
    for r in d['data'][:4]:
        print(f\"EPS: {r.get('EPSJB')}, ROE: {r.get('ROEJQ')}, 营收增长: {r.get('TOTALOPERATEREVETZ')}, 净利增长: {r.get('PARENTNETPROFITTZ')}\")
        print(f\"毛利率: {r.get('XSMLL')}, 净利率: {r.get('XSJLL')}, 负债率: {r.get('ZCFZL')}\")
        print()
" 2>/dev/null
```

**已知坑：**
- `WEIGHTAVG_ROE`、`GROSSPROFITINRATIO`、`NETPROFITRATIO` 返回 None — 不要用
- 正确字段是 `ROEJQ`、`XSMLL`、`XSJLL`
- `data` 是数组，取 `[0]` 是最新一期，`[:4]` 是最近4期

### 3. 新浪K线数据 — 多周期

**请求：**
```bash
curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600989&scale=240&ma=no&datalen=30"
```

**参数：**
| 参数 | 含义 | 取值 |
|------|------|------|
| symbol | 股票代码 | sh600989 / sz000807 |
| scale | 周期(分钟) | 5=5分钟, 15=15分钟, 30=30分钟, 240=日K |
| ma | 均线 | no=不显示 |
| datalen | 数据条数 | 10/15/30/48 |

**JSON结构：**
```json
[
  {"day": "2026-05-29", "open": "24.60", "high": "24.70", "low": "24.00", "close": "24.00", "volume": "69178677"},
  ...
]
```

**解析脚本：**
```bash
curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600989&scale=240&ma=no&datalen=30" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for d in data[-10:]:
    print(f\"{d['day']} | O:{d['open']} H:{d['high']} L:{d['low']} C:{d['close']} V:{d['volume']}\")
" 2>/dev/null
```

**5分钟分时用途：**
- 分析日内走势（出货/吸筹/震荡）
- 识别支撑/阻力位
- 判断资金行为（放量杀跌/缩量横盘）

**日K用途：**
- 判断中期趋势
- 识别支撑/阻力位
- 成交量分析

### 4. 批量操作模板

**批量获取财务数据：**
```bash
for code in "SH600989" "SZ000807" "SH603993"; do
  echo "=== $code ==="
  curl -s "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=$code" | python3 -c "
import json,sys
d=json.load(sys.stdin)
if d and 'data' in d and d['data']:
    r=d['data'][0]
    print(f\"EPS: {r.get('EPSJB')}, ROE: {r.get('ROEJQ')}, 营收增长: {r.get('TOTALOPERATEREVETZ')}, 净利增长: {r.get('PARENTNETPROFITTZ')}\")
" 2>/dev/null
done
```

**批量K线对比：**
```bash
for sym in "sh600989" "sz000807" "sh603993"; do
  echo "=== $sym ==="
  curl -s "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=$sym&scale=240&ma=no&datalen=10" | python3 -c "
import json,sys
data=json.load(sys.stdin)
for d in data[-5:]:
    print(f\"{d['day']} | O:{d['open']} H:{d['high']} L:{d['low']} C:{d['close']} V:{d['volume']}\")
" 2>/dev/null
done
```

**行情+解析一步到位：**
```bash
curl -s "https://qt.gtimg.cn/q=sh600989,sz000807" | iconv -f GBK -t UTF-8 | tr ';' '\n' | while read line; do
  if [ -n "$line" ]; then
    name=$(echo "$line" | cut -d'~' -f3)
    price=$(echo "$line" | cut -d'~' -f4)
    change=$(echo "$line" | cut -d'~' -f33)
    pe=$(echo "$line" | cut -d'~' -f40)
    echo "$name | $price | 涨跌:${change}% | PE:$pe"
  fi
done
```

### 5. 工具选择决策树

```
需要什么数据？
├─ 实时行情/PE/涨跌 → 腾讯API（最快，支持批量）
├─ 财务指标(ROE/增速/毛利) → 东方财富API（JSON，需解析）
├─ K线走势/分时图 → 新浪API（支持多周期）
├─ 板块对比 → 腾讯API + ETF代码
└─ 综合分析 → 三种API组合使用
```

### 6. 常见错误与解决

| 错误 | 原因 | 解决 |
|------|------|------|
| 中文乱码 | GBK编码未转换 | 加 `iconv -f GBK -t UTF-8` |
| 财务字段返回None | 字段名错误 | 用 ROEJQ 不用 WEIGHTAVG_ROE |
| JSON解析失败 | 返回空或格式错误 | 加 `2>/dev/null` + 判断 `d['data']` |
| K线数据为空 | symbol格式错误 | 检查 sh/sz 前缀 |
| 批量查询部分失败 | 超过API限制 | 分批查询，每批≤15只 |

## 八、快捷启动命令

| 命令 | 用途 | 模式 |
|------|------|------|
| `/stock <标的> [quick\|full\|debate]` | 个股分析 | quick=3分钟, full=五层, debate=专家辩论 |
| `/portfolio [health\|rebalance\|compare]` | 持仓检查 | health=健康检查, rebalance=调仓, compare=对比 |
| `/market [full\|quick\|intraday]` | 大盘复盘 | full=完整, quick=快评, intraday=分时 |
| `/sector <板块> [overview\|compare\|stock]` | 板块分析 | overview=全景, compare=对比, stock=个股 |

## 九、关键经验

1. 不追高：PE>100时风险极大
2. 板块轮动极快：不追轮动，持有核心仓位
3. 关键支撑位需多次测试确认，不赌单次
4. 仓位管理比选股重要
5. 现金是最好的期权：震荡市中30%现金是优势
6. 高赔率≠无风险：仍需止损纪律
7. 防御仓位（黄金/低估值金融）是组合压舱石
8. 科技仓位不能为零，至少5-8%

## 十、近期案例复盘总结（2026年6月）

> 完整案例汇总见 `data/reports/202506_Stock_Analysis_Summary.md`

### 10.1 本次分析股票概览

| 股票 | 代码 | 评级 | 置信度 | PE | Q1净利增速 | 今日涨跌 |
|------|------|------|--------|-----|-----------|----------|
| 云铝股份 | 000807 | Buy | 80% | 10.7 | +269% | -3.04% |
| 宝丰能源 | 600989 | Buy | 78% | 13.8 | +50% | +0.73% |
| 洛阳钼业 | 603993 | Buy | 75% | 15.0 | +97% | -7.15% |
| 华友钴业 | 603799 | Hold | 65% | 12.1 | +99% | -6.49% |
| 海尔智家 | 600690 | Hold | 65% | 10.1 | -15% | -0.69% |
| 贵研铂业 | 600459 | Hold | 55% | 29.8 | +9% | -3.64% |
| 中兴通讯 | 000063 | **Sell** | 55% | 39.4 | **-47%** | -5.93% |

### 10.2 成功案例特征

**Buy 评级的共同特征**：
1. **高ROE**：ROE > 15%（云铝19.7%、宝丰24.8%、洛阳26.6%）
2. **高增长**：Q1净利增速 > 50%（云铝269%、洛阳97%、华友99%）
3. **低估值**：PE < 15x，PE/ROE < 3
4. **技术面偏多**：技术评分 > 60，买入信号共振

**案例1：云铝股份**
- 核心逻辑：Q1净利暴增269%，PE仅10.7x，负债率17.7%极安全
- 技术面：双针探底+老鸭头形态
- 结论：Buy，置信度80%，目标价32元

**案例2：宝丰能源**
- 核心逻辑：ROE 25%顶级，PEG仅0.17严重低估
- 技术面：三阴一阳+缠论底背驰
- 结论：Buy，置信度78%，目标价26元

**案例3：洛阳钼业**
- 核心逻辑：铜金双极战略，Q1净利+97%
- 技术面：MACD底背离+老鸭头
- 结论：Buy，置信度75%，目标价20元

### 10.3 失败案例警示

**Sell/Hold 评级的共同特征**：
1. **业绩下滑**：Q1净利负增长（中兴-47%、海尔-15%）
2. **高估值陷阱**：PE > 30 且无高增长支撑（中兴PE 39x）
3. **技术面极弱**：MACD死叉、均线空头排列
4. **负债率过高**： > 60%（华友63.6%、贵研64.9%）

**案例：中兴通讯**
- 问题：PE 39x严重高估，Q1净利-47%下滑，ROE仅7.6%
- 技术面：今日放量大跌-5.93%，MACD死叉
- 结论：Sell，置信度55%，建议回避

### 10.4 选股核心逻辑总结

| 优先级 | 指标 | 阈值 | 权重 |
|--------|------|------|------|
| 1 | ROE | >15%优秀，>20%顶级 | 25% |
| 2 | 净利增速 | >20%成长，>50%高速 | 25% |
| 3 | PE/ROE | <3低估，<1极度低估 | 20% |
| 4 | 技术面 | 评分>60，买入信号共振 | 15% |
| 5 | 负债率 | <60%健康，<50%优秀 | 10% |
| 6 | 毛利率 | >30%有壁垒 | 5% |

### 10.5 风险识别模式库

| 风险类型 | 识别信号 | 典型案例 | 应对策略 |
|----------|----------|----------|----------|
| 业绩暴降 | Q1/Q2增速转负 | 中兴(-47%) | 立即卖出 |
| 估值泡沫 | PE>30 且 增速<20% | 中兴(PE 39x) | 回避 |
| 技术破位 | MACD死叉+放量下跌 | 华友钴业 | 止损 |
| 负债过高 | 负债率>60% | 华友(63.6%) | 降低仓位 |
| 周期陷阱 | 低价但无成长 | 贵研铂业 | 观察 |
| 趋势向下 | 均线空头排列 | 中兴通讯 | 观望 |

### 10.6 今日市场特征（2026-06-08）

- **大盘**：沪深300ETF -2.15%，偏弱震荡
- **板块**：有色/能源/AI板块领跌
- **情绪**：7只分析股6只下跌，仅宝丰能源微涨
- **结论**：市场处于调整期，控制仓位，防守为主

### 10.7 输出格式标准化

深度分析报告必须包含以下核心章节（详见 `skills/stock/SKILL.md` Step 3.1）：

1. **一句话结论**：核心判断 + 置信度
2. **五层分析**：基本面/估值/技术面/板块/风险收益比
3. **同业对比**：与行业竞争对手关键指标对比
4. **8人专家圆桌**：8位专家评分 + 分组汇总 + 信心指数
5. **投资建议**：评级 + 仓位 + 止损止盈 + 跟踪条件
6. **核心矛盾**：主要风险点和转折信号

## 十一、测试框架（v1.1.0）

### 1. Pytest 配置

```bash
# 运行所有测试（跳过网络测试）
pytest

# 运行包含网络测试
pytest --run-network

# 运行特定标记的测试
pytest -m unit
pytest -m "not slow"
```

**可用标记：**

| 标记 | 说明 |
|------|------|
| `unit` | 单元测试 |
| `integration` | 集成测试 |
| `e2e` | 端到端测试 |
| `network` | 需要网络的测试（默认跳过） |
| `slow` | 慢速测试 |

### 2. 测试数据 fixtures

```python
import pytest
from conftest import (
    SAMPLE_KLINE,
    SAMPLE_QUOTE,
    sample_finance_data,
    mock_http_get,
)

# 使用标准K线数据
def test_ema_trend(SAMPLE_KLINE):
    closes = [bar["close"] for bar in SAMPLE_KLINE]
    ...

# 使用标准行情数据
def test_quota_fields(SAMPLE_QUOTE):
    assert SAMPLE_QUOTE["pe"] > 0
```

### 3. Mock 网络请求

```python
from unittest.mock import patch

@patch("common.http_get")
def test_with_mock(mock_get):
    mock_get.return_value = b'...'
    result = get_quote("sh600989")
    ...
```

---

> **版本说明**：v1.1.0 新增 common 包、config 包、增强测试框架。

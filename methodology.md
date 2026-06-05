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

### 止损铁律
- 个股：跌破关键支撑位收盘确认即止损
- 组合：单日亏损>3%减仓
- 板块：板块趋势转空减仓

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
| 动量 | momentum | 20 日收益、MA10/MA20、量能比、换手率 | 市场是否开始认可 |
| 流动性 | liquidity | 成交额、总市值、换手适中程度 | 能否交易、能否退出 |

### 5. 策略权重

| 策略 | 市场环境 | 质量 | 估值 | 动量 | 流动性 |
|------|----------|------|------|------|--------|
| balanced | 震荡/方向不明 | 32% | 25% | 23% | 20% |
| quality_value | 价值修复/防守 | 42% | 32% | 10% | 16% |
| growth_momentum | 进攻行情/主线题材 | 26% | 12% | 42% | 20% |
| defensive | 缩量弱市/避险 | 38% | 34% | 8% | 20% |
| turning_point | 超跌修复/拐点 | 24% | 24% | 36% | 16% |

### 6. 输出标准

选股结果必须同时给出：

- 候选排名：总分 + 四因子分。
- 剔除原因：让“为什么没选”可审计。
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

## 七、数据获取工具详解

### 1. 腾讯实时行情 — 批量查询

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

# 开发者指南

理解项目结构并能扩展开发。

## 项目结构详解

```
stock-analyzer-skill/
├── README.md                       # 项目说明
├── workflow.md                     # 8 个 skill 的协作流程
├── methodology.md                  # 完整投资方法论
├── install.sh                      # 一键注册到 ~/.claude/skills/
├── .agents/skills/                 # Codex workspace skill 源
│   ├── stock/SKILL.md
│   ├── market/SKILL.md
│   ├── sector/SKILL.md
│   ├── portfolio/SKILL.md
│   ├── screener/SKILL.md
│   ├── technical/SKILL.md
│   ├── financial-analyst/SKILL.md
│   └── investment-researcher/SKILL.md
├── .claude/skills/                 # Claude Code skill 源（与 .agents 同步）
├── scripts/                        # 工具脚本（Python stdlib only）
│   ├── common.py                   # 编码转换、字段映射、HTTP
│   ├── quote.py                    # 腾讯实时行情
│   ├── finance.py                  # 东财财务数据
│   ├── kline.py                    # 新浪 K线
│   ├── announcements.py            # 东财公告/研报
│   ├── screener.py                 # A股多因子选股器
│   ├── technical.py                # 纯技术分析
│   ├── classifier.py               # 个股类型分类
│   ├── chan.py                     # 缠论结构
│   └── patterns_local.py           # A股本土战法形态
├── data/                           # 静态参考数据
│   ├── sector_etf.csv              # 板块 ETF 清单
│   ├── sector_stocks.json          # 板块核心标的库
│   └── portfolio_example.json      # 持仓配置示例
└── tests/
    └── smoke_test.sh               # 端到端冒烟测试
```

## 脚本模块说明

### common.py - 编码转换、字段映射、HTTP 工具

提供通用工具函数：

- GBK 编码转换
- HTTP 请求封装
- 字段映射配置

### quote.py - 腾讯实时行情

从 `qt.gtimg.cn` 获取实时行情数据。

用法：

```bash
python3 scripts/quote.py sh600989
```

### finance.py - 东财财务数据

从 `emweb.securities.eastmoney.com` 获取财务摘要。

用法：

```bash
python3 scripts/finance.py SH600989
```

### kline.py - 新浪 K 线

从 `money.finance.sina.com.cn` 获取 K 线数据。

用法：

```bash
python3 scripts/kline.py sh600989 240 30
```

### screener.py - 多因子选股器

A 股多因子选股系统。

用法：

```bash
python3 scripts/screener.py --strategy balanced --top 10
python3 scripts/screener.py --sector 资源 --strategy quality_value --top 5
python3 scripts/screener.py --codes sh600989,sz000807,300476 --strategy growth_momentum
python3 scripts/screener.py --strategy defensive --exclude-loss --json
```

### technical.py - 技术分析引擎

纯技术分析，包含均线、MACD、KDJ、BOLL、缠论、本土战法。

用法：

```bash
python3 scripts/technical.py sh600989 full
```

### chan.py - 缠论结构

缠论分析：笔-线段-中枢-买卖点-背驰。

### patterns_local.py - A 股本土战法形态

本土战法形态识别：三阴一阳、老鸭头、美人肩等。

### classifier.py - 个股类型分类

A 股个股类型分类器。

## 数据源架构

### 腾讯 qt.gtimg.cn

- 用途：实时行情、PE/PB/市值
- 编码：GBK（需 iconv 转换）
- 限制：批量查询最多约 15 只/次

### 东方财富 emweb.securities.eastmoney.com

- 用途：财务摘要
- 格式：JSON
- 参数：code 必须大写 SH/SZ

### 新浪 money.finance.sina.com.cn

- 用途：K 线数据
- 周期：5/15/30/240 分钟
- 格式：JSON

### 东方财富 np-anotice-stock.eastmoney.com

- 用途：公告查询

### 东方财富 reportapi.eastmoney.com

- 用途：券商研报

## Skill 注册机制

### .claude/skills/ vs .agents/skills/

- `.claude/skills/`：Claude Code 读取的 skill 源
- `.agents/skills/`：Codex workspace 读取的 skill 源
- 两者内容需保持一致

### symlink 机制

`install.sh` 创建扁平 symlink 到 `~/.claude/skills/`：

```bash
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/stock ~/.claude/skills/stock
ln -sf ~/Documents/curtis/stock-analyzer-skill/.claude/skills/market ~/.claude/skills/market
# ... 共 8 个
```

### SKILL.md 格式

每个 skill 的 `SKILL.md` 包含：

- name：技能名称
- description：触发条件和用途
- 指令：详细的使用说明

## 扩展开发指南

### 添加新数据源

1. 在 `scripts/` 下创建新模块
2. 遵循 `common.py` 的 HTTP 工具模式
3. 处理编码和错误
4. 更新 `api-reference.md`

### 添加新因子

1. 在 `screener.py` 中添加因子定义
2. 更新权重配置
3. 添加评分逻辑
4. 更新 `methodology.md`

### 添加新技能

1. 创建 `.claude/skills/<name>/SKILL.md`
2. 更新 `install.sh`
3. 同步到 `.agents/skills/`
4. 更新 `user-guide.md`

## 测试与验证

### 端到端冒烟测试

```bash
./tests/smoke_test.sh
```

预期输出：`N 通过, 0 失败`

### 手动测试流程

1. 运行单个脚本验证数据获取
2. 运行 skill 命令验证功能
3. 检查输出格式和内容

## 贡献流程

### Git 规范

- 提交信息：Conventional Commits（`feat` / `fix` / `docs` / `refactor` / `chore`）
- 标题与正文使用中文
- 分支命名：`<type>/<短描述>`

### 示例

```bash
git commit -m "feat: 添加新数据源"
git commit -m "fix: 修复编码问题"
git commit -m "docs: 更新 API 文档"
```

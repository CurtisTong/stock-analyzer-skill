# Skill Output Contracts

跨 Skill 输出的 JSON Schema 契约。本目录为机器可读的事实源（Single Source of Truth），
所有 SKILL.md 的"输出格式"段应引用此处的 schema，而非重复定义字段。

## 文件清单

| Schema | 用途 | 输出方 | 消费方 |
|---|---|---|---|
| `stock.schema.json` | 个股五层分析完整输出 | `/stock full` / `/stock debate` | `/portfolio` / `/research` |
| `market.schema.json` | 大盘复盘输出 | `/market` | `/portfolio` / `/research` |
| `sector.schema.json` | 板块分析输出 | `/sector` | `/portfolio` / `/research` |
| `portfolio.schema.json` | 持仓健康/调仓输出 | `/portfolio` | `/monitor` |
| `debate.schema.json` | 8 人专家圆桌输出 | `/stock debate` | `/portfolio` |

## 使用方式

### SKILL.md 引用

```markdown
## 输出格式

输出符合 [`skills/_shared/contracts/stock.schema.json`](./stock.schema.json)，
首行为一句话结论，尾行为数据时间戳 + 数据源。详见 `_shared/references/output-template.md`。
```

### Python 校验

```python
import json
import jsonschema

with open("skills/_shared/contracts/stock.schema.json") as f:
    schema = json.load(f)

with open("output.json") as f:
    data = json.load(f)

jsonschema.validate(data, schema)
```

### CLI 校验

```bash
python3 scripts/dev/validate_contracts.py
```

## 维护规则

- 新增/修改字段必须先改 schema，再改 SKILL.md 描述
- 所有 `$ref` 必须闭合（`validate_contracts.py` 会校验）
- `enum` 值的变更必须在 CHANGELOG 记录

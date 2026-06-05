#!/usr/bin/env bash
# 端到端冒烟测试：7 个脚本 + 3 个 API 端点 + 8 个 skill + 可选 symlink
set -e

PKG_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$PKG_ROOT/scripts"
GLOBAL_NS="$HOME/.claude/skills"
AGENTS_SKILLS="$PKG_ROOT/.agents/skills"
CLAUDE_SKILLS="$PKG_ROOT/.claude/skills"

pass=0
fail=0

ok() { echo "  ✓ $1"; pass=$((pass+1)); }
ko() { echo "  ✗ $1"; fail=$((fail+1)); }

echo "==> 1. scripts/ 完整性"
for f in common.py quote.py finance.py kline.py announcements.py screener.py technical.py; do
  if [ -x "$SCRIPTS/$f" ]; then
    ok "$f 可执行"
  else
    ko "$f 缺失或无执行权限"
  fi
done

echo "==> 2. API 端点可达性"
for url in \
  "https://qt.gtimg.cn/q=sh600989" \
  "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=SH600989" \
  "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=sh600989&scale=240&ma=no&datalen=5"; do
  if curl -s -m 8 -o /dev/null -w "%{http_code}" "$url" | grep -q "200"; then
    ok "$(echo $url | cut -d/ -f3)"
  else
    ko "$(echo $url | cut -d/ -f3) 不可达"
  fi
done

echo "==> 3. scripts/ 实际运行"
cd "$SCRIPTS"
output=$(python3 quote.py sh600989 2>&1 || true)
if echo "$output" | grep -q "宝丰能源"; then
  ok "quote.py 输出含 宝丰能源"
else
  ko "quote.py 输出异常: $output"
fi

output=$(python3 finance.py SH600989 2>&1 || true)
if echo "$output" | grep -q "ROE"; then
  ok "finance.py 输出含 ROE"
else
  ko "finance.py 输出异常: $output"
fi

output=$(python3 kline.py sh600989 240 3 2>&1 || true)
if echo "$output" | grep -q "2026"; then
  ok "kline.py 输出含 2026 日期"
else
  ko "kline.py 输出异常: $output"
fi

output=$(python3 announcements.py 600989 2>&1 || true)
if echo "$output" | grep -qE "公告|宝丰能源"; then
  ok "announcements.py 输出含公告"
else
  ko "announcements.py 输出异常: $output"
fi

output=$(python3 screener.py --sector 资源 --top 3 2>&1 || true)
if echo "$output" | grep -q "策略:"; then
  ok "screener.py 输出含策略"
else
  ko "screener.py 输出异常: $output"
fi

output=$(python3 technical.py sh600989 --quick 2>&1 || true)
if echo "$output" | grep -qE "评分|MACD|均线"; then
  ok "technical.py 输出含技术指标"
else
  ko "technical.py 输出异常: $output"
fi

echo "==> 4. 8 个本地 skill 定义"
for s in stock market sector portfolio screener financial-analyst investment-researcher technical; do
  if [ -f "$AGENTS_SKILLS/$s/SKILL.md" ] && grep -q "^---$" "$AGENTS_SKILLS/$s/SKILL.md"; then
    ok ".agents/$s 含 frontmatter"
  else
    ko ".agents/$s 缺 SKILL.md 或 frontmatter"
  fi
  if [ -f "$CLAUDE_SKILLS/$s/SKILL.md" ] && cmp -s "$AGENTS_SKILLS/$s/SKILL.md" "$CLAUDE_SKILLS/$s/SKILL.md"; then
    ok ".claude/$s 与 .agents 同步"
  else
    ko ".claude/$s 与 .agents 不一致"
  fi
done

echo "==> 5. 8 个 symlink 已注册（未安装时可失败）"
for s in stock market sector portfolio screener financial-analyst investment-researcher technical; do
  if [ -L "$GLOBAL_NS/$s" ] && [ -e "$GLOBAL_NS/$s" ]; then
    ok "$s 链接有效"
  else
    echo "  - $s 未注册到 ~/.claude/skills/，运行 ./install.sh 后应存在"
  fi
done

echo "==> 6. SKILL.md 内容含核心说明"
for s in stock market sector portfolio screener technical; do
  if grep -qE "Usage|scripts/" "$CLAUDE_SKILLS/$s/SKILL.md"; then
    ok "$s/SKILL.md 含 Usage"
  else
    ko "$s/SKILL.md 缺 Usage"
  fi
done
for s in financial-analyst investment-researcher; do
  if grep -q "scripts/" "$CLAUDE_SKILLS/$s/SKILL.md"; then
    ok "$s/SKILL.md 已引用 scripts/"
  else
    ko "$s/SKILL.md 未引用 scripts/（未解耦）"
  fi
done

echo
echo "==> 总结: $pass 通过, $fail 失败"
[ $fail -eq 0 ]

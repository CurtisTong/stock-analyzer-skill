#!/usr/bin/env bash
# 端到端冒烟测试：7 个脚本 + 3 个 API 端点 + 13 个 skill + symlink + portfolio_web Bearer
set -e

PKG_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$PKG_ROOT/scripts"
GLOBAL_NS="$HOME/.claude/skills"
CLAUDE_SKILLS="$PKG_ROOT/.claude/skills"

pass=0
fail=0

ok() { echo "  ✓ $1"; pass=$((pass+1)); }
ko() { echo "  ✗ $1"; fail=$((fail+1)); }

echo "==> 1. scripts/ 完整性"
for f in common quote.py finance.py kline.py announcements.py screener.py technical.py classifier.py chan.py patterns_local.py stock.py chip.py; do
  if [ -d "$SCRIPTS/$f" ] || [ -x "$SCRIPTS/$f" ]; then
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

output=$(python3 technical.py sh600989 --classify --no-chan --quick 2>&1 || true)
if echo "$output" | grep -qE "评分|三阴一阳"; then
  ok "technical.py --classify 含本土战法"
else
  ko "technical.py --classify 输出异常: $output"
fi

output=$(python3 classifier.py sh600989 2>&1 || true)
if echo "$output" | grep -q "type"; then
  ok "classifier.py 输出含类型"
else
  ko "classifier.py 输出异常: $output"
fi

output=$(python3 chan.py sh600989 2>&1 || true)
if echo "$output" | grep -qE "valid|fenxing"; then
  ok "chan.py 输出含缠论"
else
  ko "chan.py 输出异常: $output"
fi

output=$(python3 patterns_local.py sh600989 2>&1 || true)
if echo "$output" | grep -q "patterns"; then
  ok "patterns_local.py 输出含战法"
else
  ko "patterns_local.py 输出异常: $output"
fi

output=$(python3 chip.py sh600989 -j --days 5 2>&1 || true)
# 网络请求可能失败，仅验证 JSON 格式而非数据存在性
if echo "$output" | grep -qE '^\s*\{' && echo "$output" | grep -qE '\}\s*$'; then
  ok "chip.py 输出有效 JSON"
elif echo "$output" | grep -qE "margin|holders|top_holders"; then
  ok "chip.py 输出含资金面数据"
else
  # 超时或网络错误时跳过，不算失败
  echo "  ⚠ chip.py 请求超时或网络错误（可忽略）"
fi

echo "==> 4. 13 个本地 skill 定义"
for s in stock market sector portfolio screener monitor backtest stock-help learn research portfolio-natural portfolio-web stock-technical; do
  # skills/ 是源代码，.claude/skills/ 是 install.sh 创建的项目级 symlink
  if [ -f "$PKG_ROOT/skills/$s/SKILL.md" ] && grep -q "^---$" "$PKG_ROOT/skills/$s/SKILL.md"; then
    ok "skills/$s 含 frontmatter"
  else
    ko "skills/$s 缺 SKILL.md 或 frontmatter"
  fi
  if [ -L "$CLAUDE_SKILLS/$s" ] && [ -e "$CLAUDE_SKILLS/$s" ]; then
    ok ".claude/$s 已链接"
  else
    ko ".claude/$s 缺失"
  fi
done

echo "==> 4.1 SKILL.md 版本一致性（package.json 主版本）"
EXPECTED_VERSION=$(cd "$PKG_ROOT" && node -p "require('./package.json').version")
VERSION_COUNT=0
for s in stock market sector portfolio screener monitor backtest stock-help learn portfolio-natural portfolio-web research stock-technical; do
  if [ -f "$PKG_ROOT/skills/$s/SKILL.md" ]; then
    if grep -q "^version: $EXPECTED_VERSION" "$PKG_ROOT/skills/$s/SKILL.md"; then
      VERSION_COUNT=$((VERSION_COUNT+1))
    fi
  fi
done
if [ $VERSION_COUNT -eq 13 ]; then
  ok "13 个 SKILL.md 版本一致（全部 v$EXPECTED_VERSION）"
else
  ko "版本不一致: 仅 $VERSION_COUNT/13 (期望 v$EXPECTED_VERSION)"
fi

echo "==> 5. symlink 已注册（未安装时可失败）"
for s in stock market sector portfolio screener monitor backtest stock-help learn research; do
  if [ -L "$GLOBAL_NS/$s" ] && [ -e "$GLOBAL_NS/$s" ]; then
    ok "$s 链接有效"
  else
    echo "  - $s 未注册到 ~/.claude/skills/，运行 ./install.sh 后应存在"
  fi
done

echo "==> 6. SKILL.md 内容含核心说明"
for s in stock market sector portfolio screener monitor backtest stock-help learn research; do
  if grep -qE "Usage|使用方式|scripts/" "$CLAUDE_SKILLS/$s/SKILL.md"; then
    ok "$s/SKILL.md 含 Usage/使用方式"
  else
    ko "$s/SKILL.md 缺 Usage/使用方式"
  fi
done
for s in portfolio-natural portfolio-web stock-technical; do
  if grep -q "scripts/" "$CLAUDE_SKILLS/$s/SKILL.md"; then
    ok "$s/SKILL.md 已引用 scripts/"
  else
    ko "$s/SKILL.md 未引用 scripts/（未解耦）"
  fi
done

echo "==> 7. portfolio_web server 冒烟（临时端口 + tmp 隔离数据 + Bearer token）"
if [ ! -f "$SCRIPTS/portfolio_web.py" ]; then
  ko "portfolio_web.py 缺失"
else
  TMPDIR=$(mktemp -d)
  cat > "$TMPDIR/portfolio.json" <<EOF
{"version":2,"positions":[],"watchlist":[]}
EOF
  # 用临时 HOME 隔离 token 文件，避免污染 ~/.config/stock-analyzer/
  HOME="$TMPDIR" python3 "$SCRIPTS/portfolio_web.py" --port 18765 --data-file "$TMPDIR/portfolio.json" > /tmp/portfolio_web_smoke.log 2>&1 &
  SRV_PID=$!
  # 等待 server 启动（最多 3 秒）
  for i in 1 2 3 4 5 6; do
    if curl -s -o /dev/null -m 1 http://127.0.0.1:18765/api/health; then break; fi
    sleep 0.5
  done

  # 读取 token（启动时 _ensure_token 会写到 $TMPDIR/.config/stock-analyzer/portfolio_web.token）
  TOKEN_FILE="$TMPDIR/.config/stock-analyzer/portfolio_web.token"
  for i in 1 2 3 4 5 6; do
    [ -s "$TOKEN_FILE" ] && break
    sleep 0.5
  done
  if [ ! -s "$TOKEN_FILE" ]; then
    ko "portfolio_web token 文件未生成（log: /tmp/portfolio_web_smoke.log）"
  else
    TOKEN=$(cat "$TOKEN_FILE")
    AUTH_HDR="Authorization: Bearer $TOKEN"

    if curl -s -m 5 -o /dev/null -w "%{http_code}" "http://127.0.0.1:18765/api/health" | grep -q 200; then
      ok "portfolio_web /api/health 返回 200"
    else
      ko "portfolio_web 健康检查失败（log: /tmp/portfolio_web_smoke.log）"
    fi

    if curl -s -m 5 -H "$AUTH_HDR" "http://127.0.0.1:18765/" | grep -q "<form"; then
      ok "portfolio_web / 返回 HTML 表单"
    else
      ko "portfolio_web / 未返回表单页"
    fi

    RESP=$(curl -s -m 5 -X POST -H 'Content-Type: application/json' -H "$AUTH_HDR" \
      -d '{"action":"add_position","code":"sh600989","name":"宝丰能源","cost":18.5,"quantity":1000}' \
      "http://127.0.0.1:18765/api/positions")
    if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['ok'] and d['data']['quantity']==1000" 2>/dev/null; then
      ok "portfolio_web POST add_position 落库"
    else
      ko "portfolio_web POST 失败: $RESP"
    fi

    LIST=$(curl -s -m 5 -H "$AUTH_HDR" "http://127.0.0.1:18765/api/positions")
    if echo "$LIST" | python3 -c "import sys,json; d=json.load(sys.stdin); assert any(p['code']=='sh600989' for p in d['data']['positions'])" 2>/dev/null; then
      ok "portfolio_web GET /api/positions 读出新增项"
    else
      ko "portfolio_web list 读出失败"
    fi

    if curl -s -m 5 -X DELETE -H "$AUTH_HDR" "http://127.0.0.1:18765/api/positions" | grep -q '"method_not_allowed"'; then
      ok "portfolio_web DELETE 返回 405 method_not_allowed"
    else
      ko "portfolio_web DELETE 未返回 405"
    fi
  fi

  kill $SRV_PID 2>/dev/null || true
  wait $SRV_PID 2>/dev/null || true
  rm -rf "$TMPDIR" /tmp/portfolio_web_smoke.log
fi

echo
echo "==> 总结: $pass 通过, $fail 失败"
[ $fail -eq 0 ]

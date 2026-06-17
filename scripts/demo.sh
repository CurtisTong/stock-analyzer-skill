#!/usr/bin/env bash
# Sprint 12 / C7: README 30s demo 脚本（C7 plan）
#
# 目的：提供一个可重放的命令序列，演示 stock-analyzer-skill 的核心能力。
# 使用方法：
#   bash scripts/demo.sh            # 实际执行
#   bash scripts/demo.sh --dry-run  # 仅打印命令
#
# 录制 GIF 推荐工具：terminalizer / asciinema / vhs

set -e

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

run() {
  local desc="$1"
  shift
  echo ""
  echo "──── $desc ────"
  echo "\$ $*"
  if [[ "$DRY_RUN" == "false" ]]; then
    "$@"
  fi
}

cd "$(dirname "$0")/.."

run "1) 初始化股票池（约 10s）" \
  python3 scripts/init_pool.py --default

run "2) 选股：均衡策略筛 5 只（约 5s）" \
  python3 scripts/screener.py --strategy balanced --codes sh600519,sh600989,sh601318,sh600036,sh600276 --top 5

run "3) 单股快速分析（约 8s）" \
  python3 scripts/stock.py sh600519 quick

run "4) 回测：5 策略对比 60 天（约 30s）" \
  python3 scripts/backtest.py --all --days 60 --benchmark sh000300

run "5) 优化策略权重（约 1m）" \
  python3 scripts/backtest.py --optimize --strategy growth_momentum --days 60

run "6) 月度校准记录（保存到 strategy_performance.json）" \
  python3 scripts/strategy_performance.py record --days 30 --codes sh600519,sh600989

run "7) 跨策略对比夏普比率" \
  python3 scripts/strategy_performance.py compare --metric sharpe_ratio

run "8) 大盘快评（约 3s）" \
  python3 scripts/market.py quick 2>/dev/null || echo "(market skill 需 Claude Code 触发)"

run "9) 选股快照保存（review#16）" \
  python3 scripts/screener.py --strategy turning_point --codes sh600519,sh600989 --snapshot

run "10) 列出最近快照" \
  python3 scripts/snapshots.py list --limit 5

echo ""
echo "──── 演示完成（约 2-3 分钟） ────"

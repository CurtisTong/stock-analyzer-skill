#!/usr/bin/env bash
# 卸载 stock-analyzer-skill：一键清除 install.sh / npm / plugin 安装的全部痕迹
#
# 覆盖（与 install.sh 一一对应）：
#   1. 项目级 .claude/skills + .codex/skills（随仓库删除即可，这里也顺手清）
#   2. 全局 ~/.claude/skills + ~/.codex/skills（12 个软链）
#   3. npm 全局包 stock-analyzer-skill
#   4. Claude plugin marketplace 注册（README 推荐路径）
#   5. 仓库内运行缓存 .cache/（14882 条目可能占数百 MB）
#
# 用法: ./uninstall.sh            （普通模式：只删软链 + 提示）
#       ./uninstall.sh --all      （完整模式：+ npm / plugin / 缓存，逐项确认）

set -e
PKG_ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-normal}"

SKILLS=(stock stock-technical stock-help market sector portfolio portfolio-web portfolio-natural screener backtest research learn)

echo "==> 1/4 清理全局 skill 软链"
GLOBAL_DIRS=("$HOME/.claude/skills" "$HOME/.codex/skills")
for dir in "${GLOBAL_DIRS[@]}"; do
  [ -d "$dir" ] || { echo "  跳过 $dir（不存在）"; continue; }
  for s in "${SKILLS[@]}"; do
    if [ -L "$dir/$s" ]; then
      rm -f "$dir/$s"
      echo "  ✓ 删除 $dir/$s"
    fi
  done
  echo "  ✓ $dir 清理完成"
done

echo
echo "==> 2/4 清理项目级软链（.claude/.codex 目录内）"
for local_dir in "$PKG_ROOT/.claude/skills" "$PKG_ROOT/.codex/skills"; do
  if [ -d "$local_dir" ]; then
    rm -rf "$local_dir"
    echo "  ✓ 删除 $local_dir"
  fi
done

echo
echo "==> 3/4 清理 Claude plugin marketplace 注册"
if command -v claude >/dev/null 2>&1; then
  claude plugins marketplace remove "$PKG_ROOT" >/dev/null 2>&1 && echo "  ✓ 移除 marketplace: $PKG_ROOT" \
    || echo "  - 未找到该 marketplace 注册（跳过）"
else
  echo "  - claude CLI 不存在，跳过（如有 plugin 注册请手动执行 claude plugins marketplace remove）"
fi

echo
echo "==> 4/4 完成"
echo ""
echo "✓ 卸载完成！"

if [ "$MODE" = "--all" ]; then
  echo ""
  echo "==> 扩展清理（--all）"

  echo "==> 卸载 npm 全局包"
  if npm ls -g stock-analyzer-skill >/dev/null 2>&1 || npm ls -g @stock-analyzer/skill >/dev/null 2>&1; then
    read -r -p "  确认卸载 npm 全局包 stock-analyzer-skill? [y/N] " ans
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      npm uninstall -g stock-analyzer-skill 2>/dev/null || npm uninstall -g @stock-analyzer/skill 2>/dev/null
      echo "  ✓ npm 全局包已卸载"
    else
      echo "  跳过"
    fi
  else
    echo "  - 未安装 npm 全局包（跳过）"
  fi

  echo ""
  echo "==> 清理仓库运行缓存（.cache/）"
  if [ -d "$PKG_ROOT/.cache" ]; then
    size=$(du -sh "$PKG_ROOT/.cache" 2>/dev/null | awk '{print $1}')
    read -r -p "  确认删除 $PKG_ROOT/.cache（$size）? [y/N] " ans
    if [[ "$ans" == "y" || "$ans" == "Y" ]]; then
      rm -rf "$PKG_ROOT/.cache"
      echo "  ✓ 缓存已清理"
    else
      echo "  跳过"
    fi
  else
    echo "  - 无缓存目录（跳过）"
  fi

  echo ""
  echo "✅ --all 扩展清理完成"
fi

echo ""
echo "📌 提示：项目目录删除后技能即 100% 移除。"
echo "   仓库位置: $PKG_ROOT"
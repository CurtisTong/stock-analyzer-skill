#!/usr/bin/env bash
# install.sh 集成测试
#
# 验证：
#   1. install.sh 存在且可执行
#   2. 关键字符串（12 个 skill 名、ln -s 软链）存在
#   3. 软链创建后目录结构正确

set -e

PKG_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INSTALL_SH="$PKG_ROOT/install.sh"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

# ─────────────────────────────────────────────────────────────
# 静态检查
# ─────────────────────────────────────────────────────────────

echo "== 静态检查：install.sh 文件与可执行 =="
test -f "$INSTALL_SH" || { echo "✗ install.sh 不存在"; exit 1; }
test -x "$INSTALL_SH" || chmod +x "$INSTALL_SH"
echo "  ✓ install.sh 存在且可执行"

echo
echo "== 静态检查：13 个 skill 全部在 SKILLS 数组 =="
EXPECTED_SKILLS=(stock stock-technical market sector portfolio portfolio-web portfolio-natural screener monitor backtest research learn stock-help)
for s in "${EXPECTED_SKILLS[@]}"; do
  grep -qE "(^|[ \"=(])${s}([ \"=)]|$)" "$INSTALL_SH" || { echo "✗ 缺少 skill: $s"; exit 1; }
done
echo "  ✓ 13 个 skill 全部声明"

echo
echo "== 静态检查：使用 ln -s 软链 =="
LN_COUNT=$(grep -c "ln -s" "$INSTALL_SH")
test "$LN_COUNT" -ge 4 || { echo "✗ ln -s 数量 $LN_COUNT（应 ≥ 4）"; exit 1; }
echo "  ✓ 软链调用 $LN_COUNT 处"

echo
echo "== 静态检查：使用 rm 清理 =="
RM_COUNT=$(grep -cE "rm -[rf]+ " "$INSTALL_SH")
test "$RM_COUNT" -ge 4 || { echo "✗ rm 调用 $RM_COUNT 处（应 ≥ 4）"; exit 1; }
echo "  ✓ 清理调用 $RM_COUNT 处"

echo
echo "== 静态检查：不使用 cp -r（应已改为 ln -s）=="
if grep -q "cp -r.*SRC_SKILLS" "$INSTALL_SH"; then
  echo "✗ 仍使用 cp -r 同步 skill"
  exit 1
fi
echo "  ✓ 已改用 ln -s 软链"

# ─────────────────────────────────────────────────────────────
# 动态验证：模拟 install 到临时 HOME
# ─────────────────────────────────────────────────────────────

echo
echo "== 动态验证：模拟 install 到临时 HOME =="
export HOME="$TMP_HOME"
mkdir -p "$TMP_HOME/.claude/skills"
mkdir -p "$TMP_HOME/.codex/skills"
mkdir -p "$PKG_ROOT/.claude/skills"
mkdir -p "$PKG_ROOT/.codex/skills"

# 运行 install.sh（会创建软链 + 调用 init_pool.py 初始化数据）
# init_pool.py 幂等可重入，不会破坏现有数据
"$INSTALL_SH" >/dev/null 2>&1 || { echo "✗ install.sh 执行失败"; exit 1; }
echo "  ✓ install.sh 执行成功"

# 验证项目级软链
echo
echo "== 动态验证：项目级 .claude/skills/ 软链 =="
PROJECT_CLAUDE="$PKG_ROOT/.claude/skills"
for s in "${EXPECTED_SKILLS[@]}"; do
  test -L "$PROJECT_CLAUDE/$s" || { echo "✗ $PROJECT_CLAUDE/$s 不是软链"; exit 1; }
done
echo "  ✓ 12 个项目级软链创建"

# 验证全局软链（install.sh 改 ln -s 后应全是软链）
echo
echo "== 动态验证：全局 ~/.claude/skills/ 软链 =="
GLOBAL_CLAUDE="$TMP_HOME/.claude/skills"
for s in "${EXPECTED_SKILLS[@]}"; do
  test -L "$GLOBAL_CLAUDE/$s" || { echo "✗ $GLOBAL_CLAUDE/$s 不是软链"; exit 1; }
done
echo "  ✓ 12 个全局软链创建（cp -r → ln -s 已生效）"

# 验证软链目标
echo
echo "== 动态验证：软链指向真实源 =="
for s in "${EXPECTED_SKILLS[@]}"; do
  TARGET=$(readlink "$GLOBAL_CLAUDE/$s")
  test -d "$TARGET" || { echo "✗ $GLOBAL_CLAUDE/$s 指向不存在目录 $TARGET"; exit 1; }
done
echo "  ✓ 软链目标全部存在"

echo
echo "═══════════════════════════════════════════════════════════════"
echo "✓ install.sh 集成测试全部通过"
echo "═══════════════════════════════════════════════════════════════"

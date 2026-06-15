#!/usr/bin/env bash
# release.sh - 一键发布脚本
# 用法: ./scripts/dev/release.sh <version>
# 示例: ./scripts/dev/release.sh 1.10.0

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印函数
info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# 检查参数
if [ $# -ne 1 ]; then
    echo "用法: $0 <version>"
    echo "示例: $0 1.10.0"
    exit 1
fi

VERSION="$1"

# 验证版本号格式 (semver)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    error "版本号格式错误: $VERSION (应为 X.Y.Z)"
fi

TAG="v${VERSION}"

# 切换到项目根目录
cd "$(dirname "$0")/../.."
PROJECT_ROOT=$(pwd)

info "项目根目录: $PROJECT_ROOT"
info "目标版本: $VERSION"

# 检查工作目录是否干净（忽略版本文件变更）
DIRTY_FILES=$(git status --porcelain | grep -v "package.json\|plugin.json\|marketplace.json\|SKILL.md\|README.md\|test_skill_metadata.py" || true)
if [ -n "$DIRTY_FILES" ]; then
    error "工作目录不干净，请先提交或暂存更改:\n$DIRTY_FILES"
fi

# 检查是否在 main 分支
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    warn "当前分支是 $CURRENT_BRANCH，建议切换到 main 分支"
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 检查 tag 是否已存在
if git tag -l "$TAG" | grep -q "$TAG"; then
    error "Tag $TAG 已存在"
fi

# 获取当前版本
CURRENT_VERSION=$(node -p "require('./package.json').version")
info "当前版本: $CURRENT_VERSION"

# 更新 package.json 版本
info "更新 package.json 版本..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/\"version\": \"$CURRENT_VERSION\"/\"version\": \"$VERSION\"/" package.json
else
    sed -i "s/\"version\": \"$CURRENT_VERSION\"/\"version\": \"$VERSION\"/" package.json
fi

# 使用 sync_version.py 同步所有其他文件
info "同步版本到所有文件..."
python3 scripts/dev/sync_version.py --version "$VERSION"

# 检查 CHANGELOG.md 是否有对应版本
if ! grep -q "## \[$VERSION\]" CHANGELOG.md; then
    warn "CHANGELOG.md 中没有找到版本 $VERSION 的记录"
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        # 回滚更改
        git checkout -- package.json .claude-plugin/ skills/ README.md tests/
        exit 1
    fi
fi

# 提交版本更改
info "提交版本更改..."
git add package.json .claude-plugin/ skills/ README.md tests/test_skill_metadata.py
git commit -m "chore: bump version to $VERSION"

# 创建 tag
info "创建 tag $TAG..."
git tag -a "$TAG" -m "Release $TAG"

# 推送
info "推送到远程..."
git push origin "$CURRENT_BRANCH"
git push origin "$TAG"

info "✅ 发布完成！"
info "GitHub Actions 将自动创建 Release 并发布到 npm"
info "查看: https://github.com/CurtisTong/stock-analyzer-skill/releases/tag/$TAG"

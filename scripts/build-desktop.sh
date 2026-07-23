#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")/../apps/desktop-core"

cargo tauri build "$@"

# 删除多余的 .app 副本（Tauri 构建后 target/release/bundle/macos/ 下会生成一份，
# DMG 安装包也已包含，保留 DMG 即可）
BUNDLE_DIR="target/release/bundle/macos"
if [ -d "$BUNDLE_DIR/iBreeze.app" ]; then
    rm -rf "$BUNDLE_DIR/iBreeze.app"
    echo "cleaned: $BUNDLE_DIR/iBreeze.app"
fi
#!/usr/bin/env bash
set -Eeuo pipefail
test "${1:-}" = "--confirm-delete-all-local-profiles"
project_root="$(git rev-parse --show-toplevel)"
test "$(pwd -P)" = "$project_root"
test -f "$project_root/apps/desktop-core/Cargo.toml"
test -f "$project_root/sidecar/pyproject.toml"

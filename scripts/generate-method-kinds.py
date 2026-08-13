#!/usr/bin/env python3
"""Generate method-kind lookups from the canonical registry for all four ends.

Reads packages/rpc-schema/registry.v1.json and writes TypeScript/Rust/Python
method-kind tables so that no end holds a manually-maintained READ/WRITE list.

Usage:
    python3 scripts/generate-method-kinds.py [--check]

The IBREEZE_OUTPUT_ROOT env var can redirect generated output to a temp
directory.  --check always reads existing files from the real workspace at
ROOT, never from IBREEZE_OUTPUT_ROOT.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_PATH = ROOT / "packages" / "rpc-schema" / "registry.v1.json"


def _output_root() -> Path:
    """Return user-specified output root or default workspace root."""
    env = os.environ.get("IBREEZE_OUTPUT_ROOT")
    return Path(env) if env else ROOT


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        reg = json.load(f)
    return reg["methods"]


def generate_ts(methods: list[dict]) -> str:
    read_set = [m["method"] for m in methods if m["kind"] == "read"]
    write_set = [m["method"] for m in methods if m["kind"] == "write"]
    lines = [
        "// DO NOT EDIT MANUALLY",
        "// Generated from packages/rpc-schema/registry.v1.json",
        "//",
        f"// {len(methods)} total methods ({len(read_set)} read, {len(write_set)} write)",
        "",
        "const READ_METHODS: ReadonlySet<string> = new Set([",
    ]
    for m in sorted(read_set):
        lines.append(f"    '{m}',")
    lines.extend([
        "]);",
        "",
        "const WRITE_METHODS: ReadonlySet<string> = new Set([",
    ])
    for m in sorted(write_set):
        lines.append(f"    '{m}',")
    lines.extend([
        "]);",
        "",
        "export function isReadOperation(operationId: string): boolean {",
        "    return READ_METHODS.has(operationId);",
        "}",
        "",
        "export function isWriteOperation(operationId: string): boolean {",
        "    return WRITE_METHODS.has(operationId);",
        "}",
        "",
    ])
    return "\n".join(lines)


def generate_rust(methods: list[dict]) -> str:
    read_set = sorted(m["method"] for m in methods if m["kind"] == "read")
    write_set = sorted(m["method"] for m in methods if m["kind"] == "write")
    sidecar_read = sorted(
        m["method"] for m in methods if m["owner"] == "sidecar" and m["kind"] == "read"
    )
    sidecar_write = sorted(
        m["method"] for m in methods if m["owner"] == "sidecar" and m["kind"] == "write"
    )
    rust_core_read = sorted(
        m["method"] for m in methods if m["owner"] == "rust_core" and m["kind"] == "read"
    )
    rust_core_write = sorted(
        m["method"] for m in methods if m["owner"] == "rust_core" and m["kind"] == "write"
    )

    lines = [
        "// DO NOT EDIT MANUALLY",
        "// Generated from packages/rpc-schema/registry.v1.json",
        "//",
        f"// {len(methods)} total methods ({len(read_set)} read, {len(write_set)} write)",
        f"// {len(sidecar_read)} sidecar reads, {len(sidecar_write)} sidecar writes",
        "",
        "/// Returns `true` when the method is a read (idempotent, safe to retry without idempotency key).",
        "/// Returns `None` when the method is not in the registry.",
        "pub fn method_is_read(method: &str) -> Option<bool> {",
        "    if method_matches(method, READ_METHODS) {",
        "        Some(true)",
        "    } else if method_matches(method, WRITE_METHODS) {",
        "        Some(false)",
        "    } else {",
        "        None",
        "    }",
        "}",
        "",
        "/// Returns `Some(false)` for Rust-core reads, `Some(true)` for Rust-core writes,",
        "/// and `None` for methods owned by another process or unknown methods.",
        "pub fn rust_core_method_kind(method: &str) -> Option<bool> {",
        "    if method_matches(method, RUST_CORE_READ_METHODS) {",
        "        Some(false)",
        "    } else if method_matches(method, RUST_CORE_WRITE_METHODS) {",
        "        Some(true)",
        "    } else {",
        "        None",
        "    }",
        "}",
        "",
        "/// Returns `true` when the method is a write (requires idempotency key).",
        "/// Returns `None` when the method is not in the registry.",
        "pub fn method_is_write(method: &str) -> Option<bool> {",
        "    if method_matches(method, WRITE_METHODS) {",
        "        Some(true)",
        "    } else if method_matches(method, READ_METHODS) {",
        "        Some(false)",
        "    } else {",
        "        None",
        "    }",
        "}",
        "",
        "/// Returns `Some(false)` for sidecar-owned reads, `Some(true)` for sidecar-owned writes,",
        "/// `None` for methods not owned by the sidecar (rust_core, unknown, etc.).",
        "pub fn sidecar_method_kind(method: &str) -> Option<bool> {",
        "    if method_matches(method, SIDECAR_READ_METHODS) {",
        "        Some(false)",
        "    } else if method_matches(method, SIDECAR_WRITE_METHODS) {",
        "        Some(true)",
        "    } else {",
        "        None",
        "    }",
        "}",
        "",
    ]
    lines.extend([
        "const READ_METHODS: &[&str] = &[",
    ])
    for m in read_set:
        lines.append(f"    \"{m}\",")
    lines.extend([
        "];",
        "",
        "const WRITE_METHODS: &[&str] = &[",
    ])
    for m in write_set:
        lines.append(f"    \"{m}\",")
    lines.extend([
        "];",
        "",
        "const SIDECAR_READ_METHODS: &[&str] = &[",
    ])
    for m in sidecar_read:
        lines.append(f"    \"{m}\",")
    lines.extend([
        "];",
        "",
        "const SIDECAR_WRITE_METHODS: &[&str] = &[",
    ])
    for m in sidecar_write:
        lines.append(f"    \"{m}\",")
    lines.extend([
        "];",
        "",
    ])
    if len(rust_core_read) <= 2:
        values = ", ".join(f'"{method}"' for method in rust_core_read)
        lines.append(f"const RUST_CORE_READ_METHODS: &[&str] = &[{values}];")
    else:
        lines.append("const RUST_CORE_READ_METHODS: &[&str] = &[")
        lines.extend(f'    "{m}",' for m in rust_core_read)
        lines.append("];" )
    lines.append("")
    lines.extend([
        "const RUST_CORE_WRITE_METHODS: &[&str] = &[",
    ])
    for m in rust_core_write:
        lines.append(f"    \"{m}\",")
    lines.extend([
        "];",
        "",
        "fn method_matches(method: &str, table: &[&str]) -> bool {",
        "    table.binary_search(&method).is_ok()",
        "}",
        "",
        "#[cfg(test)]",
        "mod tests {",
        "    use super::*;",
        "",
        "    #[test]",
        "    fn test_method_kinds_known() {",
        '        assert!(method_is_read("company.list").unwrap());',
        '        assert!(!method_is_read("company.create").unwrap());',
        '        assert!(method_is_write("company.create").unwrap());',
        '        assert!(!method_is_write("company.list").unwrap());',
        "    }",
        "",
        "    #[test]",
        "    fn test_method_kinds_unknown() {",
        '        assert!(method_is_read("nonexistent.method").is_none());',
        '        assert!(method_is_write("nonexistent.method").is_none());',
        "    }",
        "",
        "    #[test]",
        "    fn test_sidecar_method_kind_known() {",
        '        assert!(!sidecar_method_kind("company.list").expect("sidecar read"));',
        '        assert!(sidecar_method_kind("company.create").expect("sidecar write"));',
        "    }",
        "",
        "    #[test]",
        "    fn test_sidecar_method_kind_rejects_rust_core() {",
        '        assert!(sidecar_method_kind("auth.login").is_none());',
        '        assert!(sidecar_method_kind("backend.validateOrigin").is_none());',
        "    }",
        "",
        "    #[test]",
        "    fn test_rust_core_method_kind_known() {",
        '        assert!(!rust_core_method_kind("auth.listOfflineProfiles").expect("rust core read"));',
        '        assert!(rust_core_method_kind("auth.login").expect("rust core write"));',
        '        assert!(rust_core_method_kind("backend.validateOrigin").expect("rust core write"));',
        "    }",
        "",
        "    #[test]",
        "    fn test_sidecar_method_kind_unknown() {",
        '        assert!(sidecar_method_kind("nonexistent.method").is_none());',
        "    }",
        "}",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    methods = load_registry()
    do_check = "--check" in sys.argv

    ts_content = generate_ts(methods)
    rust_content = generate_rust(methods)

    ts_rel = Path("apps/desktop/src/generated/rpc/method_kinds.ts")
    rs_rel = Path("apps/desktop-core/src/rpc/generated_method_kinds.rs")

    if do_check:
        ts_path = ROOT / ts_rel
        rs_path = ROOT / rs_rel
        status = 0
        existing = ts_path.read_text() if ts_path.exists() else ""
        if existing != ts_content:
            print(f"DRIFT: {ts_rel} would change")
            status = 1
        existing = rs_path.read_text() if rs_path.exists() else ""
        if existing != rust_content:
            print(f"DRIFT: {rs_rel} would change")
            status = 1
        sys.exit(status)
    else:
        out_root = _output_root()
        ts_path = out_root / ts_rel
        rs_path = out_root / rs_rel
        ts_path.parent.mkdir(parents=True, exist_ok=True)
        rs_path.parent.mkdir(parents=True, exist_ok=True)
        ts_path.write_text(ts_content)
        print(f"Wrote {ts_path} ({len(ts_content)} bytes)")
        rs_path.write_text(rust_content)
        print(f"Wrote {rs_path} ({len(rust_content)} bytes)")


if __name__ == "__main__":
    main()

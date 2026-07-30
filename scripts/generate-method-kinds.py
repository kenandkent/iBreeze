#!/usr/bin/env python3
"""Generate method-kind lookups from the canonical registry for all four ends.

Reads packages/rpc-schema/registry.v1.json and writes TypeScript/Rust/Python
method-kind tables so that no end holds a manually-maintained READ/WRITE list.

Usage:
    python3 scripts/generate-method-kinds.py [--check]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

REGISTRY_PATH = ROOT / "packages" / "rpc-schema" / "registry.v1.json"

TS_OUTPUT = ROOT / "apps" / "desktop" / "src" / "generated" / "rpc" / "method_kinds.ts"
RUST_OUTPUT = (
    ROOT / "apps" / "desktop-core" / "src" / "rpc" / "generated_method_kinds.rs"
)


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
    lines = [
        "// DO NOT EDIT MANUALLY",
        "// Generated from packages/rpc-schema/registry.v1.json",
        "//",
        f"// {len(methods)} total methods ({len(read_set)} read, {len(write_set)} write)",
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
        "}",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    methods = load_registry()
    do_check = "--check" in sys.argv

    # TypeScript
    ts_content = generate_ts(methods)
    if do_check:
        existing = TS_OUTPUT.read_text() if TS_OUTPUT.exists() else ""
        if existing != ts_content:
            print(f"DRIFT: {TS_OUTPUT} would change")
            sys.exit(1)
    else:
        TS_OUTPUT.write_text(ts_content)
        print(f"Wrote {TS_OUTPUT} ({len(ts_content)} bytes)")

    # Rust
    rust_content = generate_rust(methods)
    if do_check:
        existing = RUST_OUTPUT.read_text() if RUST_OUTPUT.exists() else ""
        if existing != rust_content:
            print(f"DRIFT: {RUST_OUTPUT} would change")
            sys.exit(1)
    else:
        RUST_OUTPUT.write_text(rust_content)
        print(f"Wrote {RUST_OUTPUT} ({len(rust_content)} bytes)")


if __name__ == "__main__":
    main()

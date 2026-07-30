#!/usr/bin/env python3
"""Sync hand-maintained method lists from contract registry.

This script reads the canonical RPC registry and updates:
1. Python: sidecar/ibreeze/rpc_server.py - READ_METHODS and self.methods
2. Rust: apps/desktop-core/src/commands.rs - sidecar_method_kind function
3. TypeScript: apps/desktop/src/shared/rpcClient.ts - READ_OPERATIONS

Usage:
    python scripts/sync_contract_registry.py
    python scripts/sync_contract_registry.py --check  # Check-only mode for CI
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).parent.parent
REGISTRY_PATH = ROOT_DIR / "packages" / "rpc-schema" / "registry.v1.json"
OWNERSHIP_PATH = ROOT_DIR / "packages" / "rpc-schema" / "ownership.v1.json"
PYTHON_SERVER_PATH = ROOT_DIR / "sidecar" / "ibreeze" / "rpc_server.py"
RUST_COMMANDS_PATH = ROOT_DIR / "apps" / "desktop-core" / "src" / "commands.rs"
TS_RPC_CLIENT_PATH = ROOT_DIR / "apps" / "desktop" / "src" / "shared" / "rpcClient.ts"


def load_registry() -> list[dict]:
    """Load the RPC registry and return all sidecar-owned methods.
    
    Uses ownership.v1.json as the source of truth for which methods are
    sidecar-owned, since registry.v1.json may have incorrect ownership.
    """
    with open(REGISTRY_PATH) as f:
        registry = json.load(f)
    
    with open(OWNERSHIP_PATH) as f:
        ownership = json.load(f)
    
    sidecar_methods_list = ownership.get("sidecar", [])
    all_methods = {m["method"]: m for m in registry.get("methods", [])}
    
    sidecar_methods = []
    for method_name in sidecar_methods_list:
        if method_name in all_methods:
            sidecar_methods.append(all_methods[method_name])
    
    return sidecar_methods


def generate_python_read_methods(methods: list[dict]) -> str:
    """Generate the READ_METHODS frozenset for Python."""
    read_methods = sorted(m["method"] for m in methods if m["kind"] == "read")
    
    lines = ['READ_METHODS = frozenset(', '    {']
    for method in read_methods:
        lines.append(f'        "{method}",')
    lines.append('    }')
    lines.append(')')
    
    return "\n".join(lines)


def generate_python_methods_dict(methods: list[dict]) -> str:
    """Generate the self.methods dictionary for Python.
    
    This is a validation function that ensures all methods in the registry
    have corresponding handlers in the self.methods dictionary.
    """
    # This is a placeholder - the actual self.methods dictionary
    # is manually maintained with specific handler mappings
    return ""


def generate_python_methods_dict(methods: list[dict]) -> str:
    """Generate the self.methods dictionary for Python."""
    lines = []
    
    # Group methods by namespace
    namespaces: dict[str, list[dict]] = {}
    for m in methods:
        namespace = m["method"].split(".")[0]
        if namespace not in namespaces:
            namespaces[namespace] = []
        namespaces[namespace].append(m)
    
    for namespace in sorted(namespaces.keys()):
        ns_methods = namespaces[namespace]
        lines.append(f"            # {namespace.capitalize()}")
        for m in sorted(ns_methods, key=lambda x: x["method"]):
            method_name = m["method"]
            # Convert method name to Python handler name
            # e.g., "company.create" -> "_company_create"
            parts = method_name.split(".")
            if len(parts) == 2:
                handler_name = f"_{parts[0]}_{parts[1]}"
            else:
                handler_name = f"_{method_name.replace('.', '_')}"
            lines.append(f'            "{method_name}": self.{handler_name},')
        lines.append("")
    
    return "\n".join(lines)


def generate_rust_sidecar_method_kind(methods: list[dict]) -> str:
    """Generate the sidecar_method_kind function for Rust."""
    write_methods = sorted(m["method"] for m in methods if m["kind"] == "write")
    read_methods = sorted(m["method"] for m in methods if m["kind"] == "read")
    
    # Build match arms with proper Rust syntax (leading |)
    write_lines = []
    for i, method in enumerate(write_methods):
        prefix = "        " if i == 0 else "            | "
        write_lines.append(f'{prefix}"{method}"')
    
    read_lines = []
    for i, method in enumerate(read_methods):
        prefix = "        " if i == 0 else "            | "
        read_lines.append(f'{prefix}"{method}"')
    
    write_match = "\n".join(write_lines)
    read_match = "\n".join(read_lines)
    
    return f'''fn sidecar_method_kind(method: &str) -> Result<bool, AppError> {{
    let write = matches!(
        method,
{write_match}
    );
    let read = matches!(
        method,
{read_match}
    );
    if write {{
        Ok(true)
    }} else if read {{
        Ok(false)
    }} else {{
        Err(AppError::Validation("METHOD_NOT_ALLOWED".to_owned()))
    }}
}}'''


def generate_typescript_read_operations(methods: list[dict]) -> str:
    """Generate the READ_OPERATIONS Set for TypeScript."""
    read_methods = sorted(m["method"] for m in methods if m["kind"] == "read")
    
    lines = ["const READ_OPERATIONS = new Set(["]
    for method in read_methods:
        lines.append(f"  '{method}',")
    lines.append("]);")
    
    return "\n".join(lines)


def update_python_server(methods: list[dict]) -> tuple[bool, str]:
    """Update Python rpc_server.py with generated content."""
    content = PYTHON_SERVER_PATH.read_text()
    
    # Update READ_METHODS
    read_methods_pattern = r"READ_METHODS = frozenset\(\n\s*\{.*?\n\s*\}\n\s*\)"
    new_read_methods = generate_python_read_methods(methods)
    new_content = re.sub(read_methods_pattern, new_read_methods, content, flags=re.DOTALL)
    
    # Check if content changed
    changed = new_content != content
    if changed:
        PYTHON_SERVER_PATH.write_text(new_content)
    
    return changed, new_content


def update_rust_commands(methods: list[dict]) -> tuple[bool, str]:
    """Update Rust commands.rs with generated content."""
    content = RUST_COMMANDS_PATH.read_text()
    
    # Replace sidecar_method_kind function
    pattern = r"fn sidecar_method_kind\(method: &str\) -> Result<bool, AppError> \{.*?\n\}"
    new_function = generate_rust_sidecar_method_kind(methods)
    new_content = re.sub(pattern, new_function, content, flags=re.DOTALL)
    
    # Check if content changed
    changed = new_content != content
    if changed:
        RUST_COMMANDS_PATH.write_text(new_content)
    
    return changed, new_content


def update_typescript_client(methods: list[dict]) -> tuple[bool, str]:
    """Update TypeScript rpcClient.ts with generated content."""
    content = TS_RPC_CLIENT_PATH.read_text()
    
    # Update READ_OPERATIONS
    pattern = r"const READ_OPERATIONS = new Set\(\[.*?\]\);"
    new_operations = generate_typescript_read_operations(methods)
    new_content = re.sub(pattern, new_operations, content, flags=re.DOTALL)
    
    # Check if content changed
    changed = new_content != content
    if changed:
        TS_RPC_CLIENT_PATH.write_text(new_content)
    
    return changed, new_content


def check_consistency(methods: list[dict]) -> list[str]:
    """Check if generated content matches expected output."""
    issues = []
    
    # Check Python
    content = PYTHON_SERVER_PATH.read_text()
    read_methods_pattern = r"READ_METHODS = frozenset\(\n\s*\{.*?\n\s*\}\n\s*\)"
    match = re.search(read_methods_pattern, content, flags=re.DOTALL)
    if match:
        expected = generate_python_read_methods(methods)
        if match.group(0) != expected:
            issues.append("Python READ_METHODS is out of sync")
    
    # Check if self.methods dictionary contains all registry methods
    methods_pattern = r"self\.methods: dict\[str, Handler\] = \{.*?\n        \}"
    match = re.search(methods_pattern, content, flags=re.DOTALL)
    if match:
        # Extract method names from self.methods dictionary
        dict_content = match.group(0)
        registered_methods = set()
        for line in dict_content.split("\n"):
            line = line.strip()
            if line.startswith('"') and '":' in line:
                method_name = line.split('"')[1]
                registered_methods.add(method_name)
        
        # Check if all registry methods are in self.methods
        registry_methods = set(m["method"] for m in methods)
        missing = registry_methods - registered_methods
        if missing:
            issues.append(f"Python self.methods missing registry methods: {missing}")
    
    # Check Rust
    content = RUST_COMMANDS_PATH.read_text()
    pattern = r"fn sidecar_method_kind\(method: &str\) -> Result<bool, AppError> \{.*?\n\}"
    match = re.search(pattern, content, flags=re.DOTALL)
    if match:
        expected = generate_rust_sidecar_method_kind(methods)
        if match.group(0) != expected:
            issues.append("Rust sidecar_method_kind is out of sync")
    
    # Check TypeScript
    content = TS_RPC_CLIENT_PATH.read_text()
    pattern = r"const READ_OPERATIONS = new Set\(\[.*?\]\);"
    match = re.search(pattern, content, flags=re.DOTALL)
    if match:
        expected = generate_typescript_read_operations(methods)
        if match.group(0) != expected:
            issues.append("TypeScript READ_OPERATIONS is out of sync")
    
    return issues


def main():
    parser = argparse.ArgumentParser(description="Sync contract registry with hand-maintained lists")
    parser.add_argument("--check", action="store_true", help="Check-only mode for CI")
    args = parser.parse_args()
    
    # Load registry
    methods = load_registry()
    print(f"Loaded {len(methods)} sidecar methods from registry")
    
    if args.check:
        # Check mode for CI
        issues = check_consistency(methods)
        if issues:
            print("ERROR: Generated content is out of sync with registry:")
            for issue in issues:
                print(f"  - {issue}")
            print("\nRun 'python scripts/sync_contract_registry.py' to update.")
            sys.exit(1)
        else:
            print("✓ All generated content is in sync with registry")
            sys.exit(0)
    else:
        # Update mode
        python_changed, _ = update_python_server(methods)
        rust_changed, _ = update_rust_commands(methods)
        ts_changed, _ = update_typescript_client(methods)
        
        if python_changed:
            print("✓ Updated Python rpc_server.py")
        else:
            print("✓ Python rpc_server.py already up to date")
        
        if rust_changed:
            print("✓ Updated Rust commands.rs")
        else:
            print("✓ Rust commands.rs already up to date")
        
        if ts_changed:
            print("✓ Updated TypeScript rpcClient.ts")
        else:
            print("✓ TypeScript rpcClient.ts already up to date")
        
        if not (python_changed or rust_changed or ts_changed):
            print("\nAll files are already in sync with registry.")
        else:
            print("\nFiles updated. Please review changes and commit.")


if __name__ == "__main__":
    main()

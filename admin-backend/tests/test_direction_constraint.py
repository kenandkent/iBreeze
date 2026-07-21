"""
Direction constraint tests.
Admin Backend must NEVER import or call Sidecar (application side).
Correct direction: Sidecar → Admin Backend
Forbidden direction: Admin Backend → Sidecar
"""
import ast
import os
from pathlib import Path


APP_DIR = Path(__file__).parent.parent / "app"


def _find_python_files(directory: Path) -> list[Path]:
    """Recursively find all .py files in directory."""
    return list(directory.rglob("*.py"))


def _get_imports_and_calls(filepath: Path) -> tuple[list[str], list[str]]:
    """Extract import names and string literals from a Python file."""
    try:
        tree = ast.parse(filepath.read_text())
    except SyntaxError:
        return [], []
    
    imports = []
    strings = []
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.append(node.value)
    
    return imports, strings


class TestDirectionConstraint:
    """Admin Backend must never call Sidecar."""
    
    FORBIDDEN_IMPORT_PATTERNS = ["acos", "sidecar"]
    # Strings that indicate actual Sidecar connection / import attempts.
    # Pure descriptive messages (e.g. "managed by Sidecar") are excluded.
    FORBIDDEN_STRING_PATTERNS = [
        "/tmp/acos.sock",
        "50081",
        "acos.app",
        "acos.rpc",
        "sidecar://",
        "sidecar.sock",
        "sidecar:",
    ]
    
    def test_no_sidecar_imports(self):
        """Admin Backend app/ code must not import Sidecar modules."""
        violations = []
        for filepath in _find_python_files(APP_DIR):
            imports, _ = _get_imports_and_calls(filepath)
            for imp in imports:
                for pattern in self.FORBIDDEN_IMPORT_PATTERNS:
                    if pattern in imp.lower():
                        violations.append(f"{filepath.name}: imports '{imp}'")
        
        assert not violations, "Admin Backend imports Sidecar modules:\n" + "\n".join(violations)
    
    def test_no_sidecar_references(self):
        """Admin Backend app/ code must not reference Sidecar endpoints or sockets."""
        violations = []
        for filepath in _find_python_files(APP_DIR):
            _, strings = _get_imports_and_calls(filepath)
            for s in strings:
                for pattern in self.FORBIDDEN_STRING_PATTERNS:
                    if pattern in s.lower():
                        violations.append(f"{filepath.name}: references '{s}'")
        
        assert not violations, "Admin Backend references Sidecar:\n" + "\n".join(violations)
    
    def test_no_httpx_in_app_code(self):
        """Admin Backend app/ code must not use httpx (HTTP client) — only tests may."""
        violations = []
        for filepath in _find_python_files(APP_DIR):
            imports, _ = _get_imports_and_calls(filepath)
            if "httpx" in imports:
                violations.append(f"{filepath.name}: imports httpx")
        
        assert not violations, "Admin Backend app/ uses httpx (HTTP client):\n" + "\n".join(violations)
    
    def test_sync_module_is被动_endpoint_only(self):
        """sync module must only define REST endpoints (passive), not call external services."""
        sync_file = APP_DIR / "api" / "sync.py"
        if not sync_file.exists():
            return
        
        imports, _ = _get_imports_and_calls(sync_file)
        # sync.py should NOT import httpx, aiohttp, requests, or any HTTP client
        http_clients = ["httpx", "aiohttp", "requests"]
        violations = [imp for imp in imports if imp in http_clients]
        
        assert not violations, f"sync.py imports HTTP clients (should be passive only): {violations}"

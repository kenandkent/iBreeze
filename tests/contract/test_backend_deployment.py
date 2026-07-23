"""Tests for backend deployment and Docker Compose configuration."""
import pytest
from pathlib import Path
import json

ROOT = Path(__file__).parent.parent.parent


def test_docker_compose_exists():
    assert (ROOT / "docker-compose.yml").exists()


def test_docker_compose_uses_new_ports():
    """docker-compose.yml 必须使用 50000+ 端口。"""
    content = (ROOT / "docker-compose.yml").read_text()
    assert "51543" in content, "PostgreSQL must use port 51543"
    assert "51080" in content, "Backend API must use port 51080"


def test_dockerfile_uses_venv_uvicorn():
    """Dockerfile 必须使用 .venv 路径的 uvicorn。"""
    dockerfile = ROOT / "apps" / "backend-api" / "Dockerfile"
    content = dockerfile.read_text()
    assert ".venv/bin/uvicorn" in content, "Dockerfile must use .venv/bin/uvicorn"
    assert "51080" in content, "Dockerfile must expose port 51080"


def test_settings_py_new_port():
    """settings.py 默认数据库端口必须是 51543。"""
    settings = ROOT / "apps" / "backend-api" / "src" / "ibreeze_backend" / "settings.py"
    content = settings.read_text()
    assert "51543" in content, "settings.py must use port 51543"


def test_rust_lib_rs_new_port():
    """lib.rs sidecar_port 必须是 51890。"""
    lib_rs = ROOT / "apps" / "desktop-core" / "src" / "lib.rs"
    content = lib_rs.read_text()
    assert "51890" in content, "lib.rs must use sidecar port 51890"
    assert "51080" in content, "lib.rs must use api port 51080"


def test_rust_api_client_exists():
    """ApiClient 模块必须存在。"""
    api_client = ROOT / "apps" / "desktop-core" / "src" / "rpc" / "api_client.rs"
    assert api_client.exists(), "api_client.rs must exist"


def test_rust_api_client_has_register():
    """ApiClient 必须有 register 方法。"""
    api_client = ROOT / "apps" / "desktop-core" / "src" / "rpc" / "api_client.rs"
    content = api_client.read_text()
    assert "pub async fn register" in content, "ApiClient must have register method"
    assert "pub async fn login" in content, "ApiClient must have login method"


def test_rust_commands_has_register():
    """commands.rs 必须有 register 命令。"""
    commands = ROOT / "apps" / "desktop-core" / "src" / "commands.rs"
    content = commands.read_text()
    assert "pub async fn register" in content, "commands.rs must have register command"
    assert "api_client" in content, "commands.rs must use api_client"


def test_vite_configs_new_ports():
    """Vite 配置必须使用 50000+ 端口。"""
    desktop_vite = ROOT / "apps" / "desktop" / "vite.config.ts"
    content = desktop_vite.read_text()
    assert "51420" in content, "Desktop vite must use port 51420"

    admin_vite = ROOT / "apps" / "admin-web" / "vite.config.ts"
    content = admin_vite.read_text()
    assert "51421" in content, "Admin vite must use port 51421"
    assert "51080" in content, "Admin vite proxy must target 51080"


def test_tauri_conf_dev_url():
    """tauri.conf.json devUrl 必须使用新端口。"""
    conf = ROOT / "apps" / "desktop-core" / "tauri.conf.json"
    data = json.loads(conf.read_text())
    assert "51420" in data["build"]["devUrl"], "devUrl must use port 51420"

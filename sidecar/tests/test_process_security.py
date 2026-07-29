from __future__ import annotations

import os

from ibreeze.security.process_security import minimal_env, sanitize_command_args


def test_minimal_env_has_required_keys():
    env = minimal_env()
    assert "PATH" in env
    assert "HOME" in env
    assert "LANG" in env
    assert "TERM" in env
    assert env["LANG"] == "en_US.UTF-8"
    assert env["TERM"] == "dumb"


def test_minimal_env_path_fallback():
    path = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")
    env = minimal_env()
    assert env["PATH"] == path


def test_minimal_env_home_fallback():
    home = os.environ.get("HOME", "/tmp")
    env = minimal_env()
    assert env["HOME"] == home


def test_sanitize_command_args_passes_clean():
    result = sanitize_command_args(["codex", "--prompt", "do stuff"])
    assert result == ["codex", "--prompt", "do stuff"]


def test_sanitize_command_args_removes_forbidden():
    result = sanitize_command_args(
        ["codex", "--dangerously-skip-permissions", "--prompt", "do stuff"]
    )
    assert "--dangerously-skip-permissions" not in result
    assert "--prompt" in result


def test_sanitize_command_args_removes_multiple_forbidden():
    result = sanitize_command_args(
        ["codex", "--share", "--max-budget-usd", "100", "--prompt", "x"]
    )
    assert "--share" not in result
    assert "--max-budget-usd" not in result
    assert "--prompt" in result


def test_sanitize_command_args_empty():
    result = sanitize_command_args([])
    assert result == []

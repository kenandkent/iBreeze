"""Workspace domain service tests."""
import pytest
from ibreeze.workspace import (
    create_workspace,
    list_workspaces,
    get_workspace,
    update_workspace,
    delete_workspace,
    add_member,
    remove_member,
    list_members,
    update_config,
)
from ibreeze.schemas import (
    WorkspaceUpdate,
    WorkspaceMemberAdd,
    WorkspaceMemberRole,
    WorkspaceConfigUpdate,
)


def test_create_workspace():
    ws = create_workspace(company_id="c1", name="Test Workspace", description="A test workspace")
    assert ws.name == "Test Workspace"
    assert ws.description == "A test workspace"
    assert ws.company_id == "c1"
    assert ws.is_deleted is False
    assert ws.id is not None


def test_list_workspaces():
    create_workspace(company_id="c1", name="WS A")
    create_workspace(company_id="c1", name="WS B")
    results = list_workspaces(company_id="c1")
    names = [w.name for w in results]
    assert "WS A" in names
    assert "WS B" in names


def test_get_workspace():
    ws = create_workspace(company_id="c1", name="Get Test")
    fetched = get_workspace(ws.id)
    assert fetched.id == ws.id
    assert fetched.name == "Get Test"


def test_get_workspace_not_found():
    with pytest.raises(KeyError):
        get_workspace("nonexistent-id")


def test_update_workspace():
    ws = create_workspace(company_id="c1", name="Old Name")
    updated = update_workspace(ws.id, WorkspaceUpdate(name="New Name", description="Updated desc"))
    assert updated.name == "New Name"
    assert updated.description == "Updated desc"


def test_delete_workspace():
    ws = create_workspace(company_id="c1", name="To Delete")
    delete_workspace(ws.id)
    with pytest.raises(KeyError):
        get_workspace(ws.id)


def test_add_member():
    ws = create_workspace(company_id="c1", name="Members WS")
    member = add_member(ws.id, WorkspaceMemberAdd(user_id="u1", role=WorkspaceMemberRole.EDITOR))
    assert member.workspace_id == ws.id
    assert member.user_id == "u1"
    assert member.role == WorkspaceMemberRole.EDITOR


def test_add_member_duplicate():
    ws = create_workspace(company_id="c1", name="Dup Members")
    add_member(ws.id, WorkspaceMemberAdd(user_id="u1", role=WorkspaceMemberRole.VIEWER))
    with pytest.raises(ValueError, match="已是工作区成员"):
        add_member(ws.id, WorkspaceMemberAdd(user_id="u1", role=WorkspaceMemberRole.ADMIN))


def test_remove_member():
    ws = create_workspace(company_id="c1", name="Remove Member WS")
    add_member(ws.id, WorkspaceMemberAdd(user_id="u1", role=WorkspaceMemberRole.VIEWER))
    remove_member(ws.id, "u1")
    members = list_members(ws.id)
    assert len(members) == 0


def test_remove_member_not_found():
    ws = create_workspace(company_id="c1", name="No Member")
    with pytest.raises(KeyError):
        remove_member(ws.id, "nonexistent-user")


def test_list_members():
    ws = create_workspace(company_id="c1", name="List Members WS")
    add_member(ws.id, WorkspaceMemberAdd(user_id="u1", role=WorkspaceMemberRole.ADMIN))
    add_member(ws.id, WorkspaceMemberAdd(user_id="u2", role=WorkspaceMemberRole.EDITOR))
    members = list_members(ws.id)
    assert len(members) == 2
    user_ids = [m.user_id for m in members]
    assert "u1" in user_ids
    assert "u2" in user_ids


def test_update_workspace_config():
    ws = create_workspace(company_id="c1", name="Config WS")
    cfg = update_config(ws.id, WorkspaceConfigUpdate(key="theme", value="dark"))
    assert cfg.key == "theme"
    assert cfg.value == "dark"
    assert cfg.updated_at is not None

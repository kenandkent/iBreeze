"""Orchestration domain service tests."""
import pytest
from ibreeze.orchestration import (
    create_orchestration,
    list_orchestrations,
    get_orchestration,
    update_orchestration,
    delete_orchestration,
    add_node,
    add_edge,
    run_orchestration,
    get_run_history,
)
from ibreeze.schemas import (
    OrchestrationUpdate,
    OrchestrationNodeCreate,
    OrchestrationNodeType,
    OrchestrationEdgeCreate,
    OrchestrationStatus,
    OrchestrationRunStatus,
)


def test_create_orchestration():
    orc = create_orchestration(company_id="c1", name="Test Orc", description="An orchestration")
    assert orc.name == "Test Orc"
    assert orc.description == "An orchestration"
    assert orc.company_id == "c1"
    assert orc.status == OrchestrationStatus.DRAFT
    assert orc.version == 1
    assert orc.is_deleted is False


def test_list_orchestrations():
    create_orchestration(company_id="c1", name="Orc A")
    create_orchestration(company_id="c1", name="Orc B")
    results = list_orchestrations(company_id="c1")
    assert len(results) >= 2


def test_get_orchestration():
    orc = create_orchestration(company_id="c1", name="Get Orc")
    fetched = get_orchestration(orc.id)
    assert fetched.id == orc.id
    assert fetched.name == "Get Orc"


def test_get_orchestration_not_found():
    with pytest.raises(KeyError):
        get_orchestration("nonexistent-id")


def test_update_orchestration():
    orc = create_orchestration(company_id="c1", name="Old Orc")
    updated = update_orchestration(orc.id, OrchestrationUpdate(name="New Orc", description="Updated"))
    assert updated.name == "New Orc"
    assert updated.description == "Updated"
    assert updated.version == 2


def test_delete_orchestration():
    orc = create_orchestration(company_id="c1", name="To Delete")
    delete_orchestration(orc.id)
    with pytest.raises(KeyError):
        get_orchestration(orc.id)


def test_add_node():
    orc = create_orchestration(company_id="c1", name="Node Test")
    node = add_node(orc.id, OrchestrationNodeCreate(name="Agent 1", node_type=OrchestrationNodeType.AGENT, config={"model": "gpt-4"}))
    assert node.name == "Agent 1"
    assert node.node_type == OrchestrationNodeType.AGENT
    assert node.config == {"model": "gpt-4"}
    assert node.orchestration_id == orc.id


def test_add_edge():
    orc = create_orchestration(company_id="c1", name="Edge Test")
    node_a = add_node(orc.id, OrchestrationNodeCreate(name="Input", node_type=OrchestrationNodeType.INPUT))
    node_b = add_node(orc.id, OrchestrationNodeCreate(name="Output", node_type=OrchestrationNodeType.OUTPUT))
    edge = add_edge(orc.id, OrchestrationEdgeCreate(source_node_id=node_a.id, target_node_id=node_b.id))
    assert edge.source_node_id == node_a.id
    assert edge.target_node_id == node_b.id
    assert edge.orchestration_id == orc.id


def test_add_edge_self_loop_raises():
    orc = create_orchestration(company_id="c1", name="Self Loop")
    node = add_node(orc.id, OrchestrationNodeCreate(name="Node", node_type=OrchestrationNodeType.AGENT))
    with pytest.raises(ValueError, match="不允许自环边"):
        add_edge(orc.id, OrchestrationEdgeCreate(source_node_id=node.id, target_node_id=node.id))


def test_list_nodes():
    orc = create_orchestration(company_id="c1", name="List Nodes")
    add_node(orc.id, OrchestrationNodeCreate(name="N1", node_type=OrchestrationNodeType.AGENT))
    add_node(orc.id, OrchestrationNodeCreate(name="N2", node_type=OrchestrationNodeType.TOOL))
    full = get_orchestration(orc.id)
    assert len(full.nodes) == 2
    node_names = [n.name for n in full.nodes]
    assert "N1" in node_names
    assert "N2" in node_names


def test_list_edges():
    orc = create_orchestration(company_id="c1", name="List Edges")
    a = add_node(orc.id, OrchestrationNodeCreate(name="A", node_type=OrchestrationNodeType.INPUT))
    b = add_node(orc.id, OrchestrationNodeCreate(name="B", node_type=OrchestrationNodeType.OUTPUT))
    add_edge(orc.id, OrchestrationEdgeCreate(source_node_id=a.id, target_node_id=b.id))
    full = get_orchestration(orc.id)
    assert len(full.edges) == 1
    assert full.edges[0].source_node_id == a.id
    assert full.edges[0].target_node_id == b.id


def test_run_orchestration():
    orc = create_orchestration(company_id="c1", name="Run Test")
    run = run_orchestration(orc.id)
    assert run.orchestration_id == orc.id
    assert run.orchestration_version == orc.version
    assert run.status == OrchestrationRunStatus.PENDING
    assert run.started_at is not None
    assert run.completed_at is None


def test_get_run():
    orc = create_orchestration(company_id="c1", name="Get Run")
    run = run_orchestration(orc.id)
    history = get_run_history(orc.id)
    assert len(history) >= 1
    fetched = history[0]
    assert fetched.id == run.id
    assert fetched.status == run.status


def test_status_transitions():
    orc = create_orchestration(company_id="c1", name="Status Test")
    run = run_orchestration(orc.id)
    assert run.status == OrchestrationRunStatus.PENDING
    history = get_run_history(orc.id)
    assert history[0].status == OrchestrationRunStatus.PENDING

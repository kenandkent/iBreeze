"""ContextBuilder 测试。"""

from acos.capability.context_builder import ContextBuilder


def test_build_returns_six_sections_in_fixed_order() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={"employee_id": "emp-1", "name": "Alice", "role": "dev"},
        task_context={"task_id": "task-1", "conversation_id": "conv-1"},
        capability_snapshot={"capability_id": "cap-1", "version": 1},
        retrieved_knowledge=[],
    )
    assert len(sections) == 6
    names = [s.name for s in sections]
    assert names == ContextBuilder.FIXED_ORDER


def test_employee_identity_section() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={
            "employee_id": "emp-1",
            "name": "Alice",
            "role": "dev",
            "department_id": "dept-1",
            "company_id": "comp-1",
        },
        task_context={},
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    identity = sections[0]
    assert identity.name == "employee_identity"
    assert "emp-1" in identity.content
    assert "Alice" in identity.content
    assert "dev" in identity.content
    assert identity.order == 0


def test_workflow_context_section() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={
            "task_id": "task-42",
            "conversation_id": "conv-99",
            "workflow_step": "step-2",
        },
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    wf = sections[1]
    assert wf.name == "workflow_context"
    assert "task-42" in wf.content
    assert "conv-99" in wf.content
    assert "step-2" in wf.content


def test_capability_context_section() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={},
        capability_snapshot={
            "capability_id": "cap-7",
            "version": 3,
            "skills": [{"skill_id": "sk-1"}, {"skill_id": "sk-2"}],
        },
        retrieved_knowledge=[],
    )
    cap_section = sections[2]
    assert cap_section.name == "capability_context"
    assert "cap-7" in cap_section.content
    assert "sk-1" in cap_section.content
    assert "sk-2" in cap_section.content


def test_retrieved_knowledge_section() -> None:
    builder = ContextBuilder()
    knowledge = [
        {"knowledge_id": "k-1", "score": 0.95, "snippet": "hello world"},
        {"knowledge_id": "k-2", "score": 0.80, "snippet": "foo bar"},
    ]
    sections = builder.build(
        employee={},
        task_context={},
        capability_snapshot={},
        retrieved_knowledge=knowledge,
    )
    k_section = sections[3]
    assert k_section.name == "retrieved_knowledge"
    assert "k-1" in k_section.content
    assert "hello world" in k_section.content
    assert "k-2" in k_section.content


def test_retrieved_knowledge_empty() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={},
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    assert sections[3].content == ""


def test_runtime_variables_section() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={"runtime_variables": {"env": "prod", "debug": "true"}},
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    rv = sections[4]
    assert rv.name == "runtime_variables"
    assert "env=prod" in rv.content
    assert "debug=true" in rv.content


def test_user_input_section() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={"user_input": "帮我查一下报表"},
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    ui = sections[5]
    assert ui.name == "user_input"
    assert ui.content == "帮我查一下报表"
    assert ui.order == 5


def test_empty_inputs() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={},
        task_context={},
        capability_snapshot={},
        retrieved_knowledge=[],
    )
    assert len(sections) == 6
    for s in sections:
        assert s.name in ContextBuilder.FIXED_ORDER


def test_order_values_are_sequential() -> None:
    builder = ContextBuilder()
    sections = builder.build(
        employee={"employee_id": "e1"},
        task_context={"task_id": "t1"},
        capability_snapshot={"capability_id": "c1"},
        retrieved_knowledge=[],
    )
    orders = [s.order for s in sections]
    assert orders == [0, 1, 2, 3, 4, 5]

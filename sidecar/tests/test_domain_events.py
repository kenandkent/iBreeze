"""域事件注册表单元测试。

覆盖 H.4 域事件体系:
- DomainEventType 枚举完整性
- EVENT_REGISTRY 注册表完整性和一致性
- get_event_spec / list_event_types 查询函数
"""

from ibreeze.domain import (
    EVENT_REGISTRY,
    DomainEventType,
    get_event_spec,
    list_event_types,
)


class TestDomainEventTypeEnum:
    def test_company_events_present(self):
        assert DomainEventType.COMPANY_CREATED == "company.created"
        assert DomainEventType.COMPANY_RENAMED == "company.renamed"
        assert DomainEventType.COMPANY_UPDATED == "company.updated"
        assert DomainEventType.COMPANY_ARCHIVED == "company.archived"

    def test_department_events_present(self):
        assert DomainEventType.DEPARTMENT_CREATED == "department.created"
        assert DomainEventType.DEPARTMENT_UPDATED == "department.updated"
        assert DomainEventType.DEPARTMENT_LEADER_CHANGED == "department.leader_changed"

    def test_employee_events_present(self):
        assert DomainEventType.EMPLOYEE_CREATED == "employee.created"
        assert DomainEventType.EMPLOYEE_UPDATED == "employee.updated"
        assert DomainEventType.EMPLOYEE_STATUS_CHANGED == "employee.status_changed"
        assert DomainEventType.EMPLOYEE_TRANSFERRED == "employee.transferred"

    def test_company_task_events_present(self):
        assert DomainEventType.COMPANY_TASK_CREATED == "company_task.created"
        assert DomainEventType.COMPANY_TASK_PAUSED == "company_task.paused"
        assert DomainEventType.COMPANY_TASK_RESUMED == "company_task.resumed"
        assert DomainEventType.COMPANY_TASK_COMPLETED == "company_task.completed"
        assert DomainEventType.COMPANY_TASK_CANCELLED == "company_task.cancelled"
        assert DomainEventType.COMPANY_TASK_FAILED == "company_task.failed"

    def test_conversation_events_present(self):
        assert DomainEventType.CONVERSATION_USER_MESSAGE_SUBMITTED == "conversation.user_message_submitted"
        assert DomainEventType.CONVERSATION_EMPLOYEE_MESSAGE_SUBMITTED == "conversation.employee_message_submitted"

    def test_plan_events_present(self):
        assert DomainEventType.PLAN_GENERATED == "plan.generated"
        assert DomainEventType.PLAN_AWAITING_CONFIRMATION == "plan.awaiting_confirmation"
        assert DomainEventType.PLAN_APPROVED == "plan.approved"
        assert DomainEventType.PLAN_REJECTED == "plan.rejected"
        assert DomainEventType.PLAN_SUPERSEDED == "plan.superseded"

    def test_review_events_present(self):
        assert DomainEventType.REVIEW_ASSIGNMENT_CREATED == "review.assignment_created"
        assert DomainEventType.REVIEW_STARTED == "review.started"
        assert DomainEventType.REVIEW_SUBMITTED == "review.submitted"
        assert DomainEventType.REVIEW_ISSUE_CREATED == "review.issue_created"
        assert DomainEventType.REVIEW_ISSUE_RESOLVED == "review.issue_resolved"

    def test_agent_run_events_present(self):
        assert DomainEventType.RUN_PROBING == "run.probing"
        assert DomainEventType.RUN_STARTED == "run.started"
        assert DomainEventType.RUN_COMPLETED == "run.completed"
        assert DomainEventType.RUN_FAILED == "run.failed"
        assert DomainEventType.RUN_CANCELLED == "run.cancelled"
        assert DomainEventType.RUN_TIMED_OUT == "run.timed_out"
        assert DomainEventType.RUN_LOST == "run.lost"


class TestEventRegistry:
    def test_registry_has_all_enum_entries(self):
        for event_type in DomainEventType:
            assert event_type in EVENT_REGISTRY, f"Missing registry entry for {event_type}"

    def test_registry_count_matches_enum_count(self):
        assert len(EVENT_REGISTRY) == len(list(DomainEventType))

    def test_registry_entries_have_correct_aggregate_type(self):
        assert EVENT_REGISTRY[DomainEventType.COMPANY_CREATED].aggregate_type == "company"
        assert EVENT_REGISTRY[DomainEventType.COMPANY_TASK_PAUSED].aggregate_type == "company_task"
        assert EVENT_REGISTRY[DomainEventType.COMPANY_TASK_RESUMED].aggregate_type == "company_task"
        assert EVENT_REGISTRY[DomainEventType.EMPLOYEE_TRANSFERRED].aggregate_type == "employee"
        assert EVENT_REGISTRY[DomainEventType.RUN_STARTED].aggregate_type == "agent_run"

    def test_paused_and_resumed_have_descriptions(self):
        paused_spec = EVENT_REGISTRY[DomainEventType.COMPANY_TASK_PAUSED]
        resumed_spec = EVENT_REGISTRY[DomainEventType.COMPANY_TASK_RESUMED]
        assert paused_spec.description == "公司任务已暂停"
        assert resumed_spec.description == "公司任务已恢复"
        assert paused_spec.version == 1
        assert resumed_spec.version == 1

    def test_registry_entries_have_default_version(self):
        for spec in EVENT_REGISTRY.values():
            assert spec.version == 1


class TestQueryFunctions:
    def test_get_event_spec_known(self):
        spec = get_event_spec("company_task.paused")
        assert spec is not None
        assert spec.event_type == DomainEventType.COMPANY_TASK_PAUSED
        assert spec.aggregate_type == "company_task"

    def test_get_event_spec_known_run(self):
        spec = get_event_spec("run.started")
        assert spec is not None
        assert spec.event_type == DomainEventType.RUN_STARTED

    def test_get_event_spec_unknown_returns_none(self):
        assert get_event_spec("nonexistent.event") is None

    def test_get_event_spec_invalid_format_returns_none(self):
        assert get_event_spec("") is None
        assert get_event_spec("no_dot") is None

    def test_list_event_types_returns_all(self):
        all_events = list_event_types()
        assert len(all_events) == len(EVENT_REGISTRY)

    def test_list_event_types_filters_by_aggregate(self):
        company_task_events = list_event_types("company_task")
        for spec in company_task_events:
            assert spec.aggregate_type == "company_task"
        assert DomainEventType.COMPANY_TASK_PAUSED in [s.event_type for s in company_task_events]
        assert DomainEventType.COMPANY_TASK_RESUMED in [s.event_type for s in company_task_events]

    def test_list_event_types_company_aggregate(self):
        company_events = list_event_types("company")
        for spec in company_events:
            assert spec.aggregate_type == "company"

    def test_list_event_types_nonexistent_aggregate(self):
        result = list_event_types("nonexistent_aggregate")
        assert result == []

    def test_list_event_types_agent_run(self):
        run_events = list_event_types("agent_run")
        types = {s.event_type for s in run_events}
        assert DomainEventType.RUN_PROBING in types
        assert DomainEventType.RUN_STARTED in types
        assert DomainEventType.RUN_COMPLETED in types
        assert DomainEventType.RUN_FAILED in types
        assert DomainEventType.RUN_CANCELLED in types
        assert DomainEventType.RUN_TIMED_OUT in types
        assert DomainEventType.RUN_LOST in types

-- Preserve Plan/Department Task capability requirements across eager and
-- lazy EmployeeTask dispatch. The value is part of the immutable Run spec;
-- it is never read from mutable department/profile state during execution.
ALTER TABLE employee_task_dispatch_specs
    ADD COLUMN required_capability_tags_json TEXT NOT NULL DEFAULT '[]'
    CHECK(json_valid(required_capability_tags_json));

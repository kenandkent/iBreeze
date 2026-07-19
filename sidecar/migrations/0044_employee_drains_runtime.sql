-- 0044: employee_drains 扩展 Runtime port 绑定（Phase 7-T5）
--
-- drain token 绑定 drain/employee/run/active_turn，只走内部端口；suspend/archive
-- 只有在该职员无 held turn lease 后才按 drain_id 返回幂等 ACK。

ALTER TABLE employee_drains ADD COLUMN drain_token TEXT;
ALTER TABLE employee_drains ADD COLUMN bound_active_turn_id TEXT;
ALTER TABLE employee_drains ADD COLUMN bound_run_id TEXT;
ALTER TABLE employee_drains ADD COLUMN acked_at TEXT;

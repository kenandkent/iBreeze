-- 0061: Backend 健康探针字段 + 全局进程上限 + PV-03 公司配置

-- backends 表添加 last_health_probe_at（设计 §10.3）
ALTER TABLE backends ADD COLUMN last_health_probe_at TEXT;

-- 全局进程上限存储于 companies 表（默认 0 = 无上限）
ALTER TABLE companies ADD COLUMN global_process_limit INTEGER NOT NULL DEFAULT 0;

-- PV-03 计划验证器公司级配置（max_nodes/max_depth 可配）
ALTER TABLE companies ADD COLUMN plan_validator_config TEXT NOT NULL DEFAULT '{}';

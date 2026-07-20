-- 0062: backends 关联全局 Provider
-- 一个 Backend（执行环境）可服务于某个 Provider（能力来源），便于在 UI/运行时把
-- "在哪执行" 与 "用谁的能力" 对应起来。provider_id 可空，关联 providers 表。

ALTER TABLE backends ADD COLUMN provider_id TEXT REFERENCES providers(provider_id);

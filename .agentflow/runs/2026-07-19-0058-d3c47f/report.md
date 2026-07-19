STATUS: NEEDS_CHANGES

# 摘要

Performance-lens parallel-review of the design spec (AI公司桌面应用设计方案.md) and implementation plan (AI公司桌面应用-实施计划.md). No code exists yet; this is a pre-implementation audit.

Found 14 performance-focused issues across both documents: 3 high-severity bottlenecks that may block release gates, 5 medium-severity concerns affecting scalability and responsiveness, and 6 low-severity observations. Key areas: Permission Engine compute_scope hot-path cost, BackendScheduler lease-acquire contention, knowledge search pipeline latency, backup snapshot write barrier, and transcript buffer management.

The 21 known review issues (A-1~A-5, B-1~B-4, C-1~C-12) were verified from the performance lens. Only 2 have minor performance implications (A-4 table field completeness, B-2 RetentionCompactor); the remaining 19 are correctness/consistency issues with no direct performance impact.

# 变更文件

None

# 验证

None (pre-implementation; no code to verify)

# 产物

- report.issues.json (structured sidecar with 14 performance-lens issues)

# 问题

## P1 (High) §8.3 `compute_scope` 热路径复杂度可能超 release_gate

**Target**: Design spec §8.3, §4.5

`compute_scope` is called on every permission check (tool execution, knowledge query, workspace access). The function computes 6 branches: `company` (1 query), `visible_department_ids` (1 query + closure join), `managed_department_ids` (1 query + closure join), `visible_task_ids` (3 sub-queries: assignments, managed-department tasks, root-leader company-scope tasks + grant union), `own_employee_id` (trivial), `private_visible_employee_ids` (2 sub-queries: department closure + reporting closure). Total: ~8-10 SQLite queries per call.

§4.5 sets `permission_compute_scope_time < 10ms` as `release_gate`. With the baseline of 100 employees and deep department trees (closure table), the nested joins in `visible_department_ids` and `private_visible_employee_ids` may exceed 10ms on cold caches. The design explicitly forbids caching cross-request results (§8.3: "不引入常驻权限快照"), so every call pays the full cost.

**Recommendation**: §4.5 should either (a) relax to `observational` for v1 with `release_gate` deferred to v2 after profiling, or (b) allow a per-request in-memory memoization scope (not cross-request) within a single RPC handler. Also, §4.5 should specify that the 10ms target is measured with warm SQLite page cache (after first call in the process).

## P2 (High) §6.11 BackendScheduler lease-acquire 事务竞争

**Target**: Design spec §6.11, §4.5

The lease-acquire path is a single SQLite transaction that: (1) checks all backends' held counts vs concurrency_limit, (2) checks global held total vs global_process_limit, (3) selects the global earliest queue head, (4) creates a lease, (5) updates queue entry status. §4.5 sets `backend_slot_acquire_time < 50ms` as `release_gate`.

With the global process limit potentially up to 64 and multiple companies sharing the same Sidecar, the "check all backends' held counts" step requires scanning `backend_leases WHERE status=held GROUP BY backend_id` plus `COUNT(*)` across all backends. Under high concurrency (many tasks completing/starting simultaneously), SQLite's single-writer model means all lease acquire/release operations serialize on the write lock, creating a bottleneck.

**Recommendation**: The implementation plan P6-T1c should explicitly test the 50ms target under concurrent load (e.g., 10 simultaneous lease acquires). Consider materializing held counts in the `backends` table (updated on acquire/release) to avoid full lease table scans.

## P3 (High) §9.4 知识检索管线延迟链过长

**Target**: Design spec §9.4, §11.4

The knowledge search pipeline has 7 sequential steps: compute_scope → FTS5 query → LanceDB vector query → RRF fusion → governance_confirmed priority + time decay → token budget trim → write knowledge_access_logs. Steps 2-3 are parallelized, but step 1 (compute_scope) is blocking, and steps 4-7 are sequential in-process.

For interactive chat (session.sendMessage), this pipeline runs on every user turn that triggers knowledge retrieval. The combined latency of compute_scope (~5-10ms) + FTS5 (variable) + LanceDB (variable, depends on index size) + RRF fusion + audit write could exceed acceptable interactive latency thresholds.

§4.5 does not define an `observational` target for knowledge search end-to-end latency, which means there is no baseline measurement planned.

**Recommendation**: Add an `observational` metric `knowledge_search_e2e_time` to §4.5 (p50/p95, measured at 10K documents). The implementation plan P8-T4 should include a latency budget breakdown per pipeline step.

## P4 (Medium) §4.7 备份快照写入屏障持续时间不可控

**Target**: Design spec §4.7

The backup snapshot barrier freezes all writes while waiting for: (1) in-flight database transactions to complete, (2) active turns to reach safe checkpoints, (3) outbox deliveries to quiesce. The barrier has a bounded quiesce timeout (`SYS-BACKUP-QUIESCE-TIMEOUT`), but the timeout value is not specified in the design.

During the freeze window, all RPC write operations receive `SYS-BACKUP-IN-PROGRESS` and retry. For a user actively chatting, this could cause noticeable UI stutters. If a long-running tool execution is in progress (e.g., code generation taking 30+ seconds), the barrier wait could be substantial.

**Recommendation**: §4.7 should specify a concrete quiesce timeout (e.g., 30 seconds) and §4.5 should add an `observational` metric `backup_barrier_duration_ms` to track actual freeze window lengths.

## P5 (Medium) §11.4 `session_threads` 按 `security_context_key` 查找缺少索引设计

**Target**: Design spec §11.4, implementation plan P7-T1

`security_context_key` is a hash of 9 dimensions and is the primary lookup key for session threads. The design says "外部 UI/RPC 使用稳定的 thread_id" but the common path for `session.sendMessage` without `thread_id` (general conversation) requires: (1) compute the current 9-dim key, (2) look up the matching thread by `(employee_id, security_context_key)`, (3) if not found, create a new thread.

The design spec does not explicitly call out a composite index on `(employee_id, security_context_key)` in the ER diagram or table definitions. Without this index, the lookup degrades to a full table scan of `session_threads` per employee, which grows with the number of employees × key changes.

**Recommendation**: §15 or the ER diagram should explicitly declare `UNIQUE(employee_id, security_context_key)` or at minimum a composite index. The implementation plan P7-T1 should include this in the migration.

## P6 (Medium) §4.6 Outbox Worker 轮询间隔影响事件投递延迟

**Target**: Design spec §4.6, §5.2

The Outbox Worker polls `outbox_deliveries` for pending/failed rows. The design does not specify the polling interval. If set too high (e.g., 5s), domain events like `TaskCompleted`, `SkillPublished`, or `BackendHealthChanged` experience artificial delay before consumers process them. If set too low (e.g., 100ms), it creates unnecessary SQLite read pressure.

The Outbox is the sole delivery mechanism for 30+ named events (§5.2), and several downstream systems depend on timely delivery: knowledge extraction triggers on `TaskCompleted`, capability metrics aggregate on `TaskCompleted`/`ReviewCompleted`, and UI notifications depend on event consumption.

**Recommendation**: The implementation plan P1-T2 should specify a default polling interval (e.g., 1 second) and note that high-priority events (e.g., approval requests) should trigger immediate wake-up rather than waiting for the next poll cycle.

## P7 (Medium) §10.6 预留-结算模式的 int64 溢出检查开销

**Target**: Design spec §10.6

Every model call requires an atomic usage reservation: compute worst-case cost (input tokens × price + output tokens × price + tool fees) using int64 micros, check for overflow, write `usage_reservations`, then check total reserved vs budget limit. The computation involves: (1) reading `provider_model_prices` for the locked pricing version, (2) computing `ceil(input_tokens * input_per_1m / 1_000_000) + ceil(output_tokens * output_per_1m / 1_000_000) + tool_flat`, (3) checking int64 overflow, (4) summing all held reservations for the task+currency, (5) comparing against budget limit.

Step 4 requires `SELECT SUM(amount_micros) FROM usage_reservations WHERE task_id=? AND currency=? AND status='held'`, which runs on every model call dispatch. For tasks with many parallel workers, this becomes a contention point.

**Recommendation**: The implementation plan should consider maintaining a materialized `reserved_micros` counter on the `tasks` table (updated in the same transaction as reservation create/release), avoiding the aggregation query on hot path.

## P8 (Medium) §11.4 transcript.jsonl 无限增长风险

**Target**: Design spec §11.4

`transcript.jsonl` is append-only and grows with every conversation turn. The design says "单条超阈值落 artifact 只留引用" for individual messages, but does not specify a total size limit or truncation strategy for the file itself. The `context-summary.md` checkpoint mechanism compresses older messages, but the raw transcript continues growing.

For long-running employee sessions (e.g., a senior manager with months of history), the transcript could grow to hundreds of megabytes. Recovery from transcript requires reading the entire file to find the latest valid checkpoint, which becomes increasingly expensive.

**Recommendation**: §11.4 should define a maximum transcript size or age-based archival strategy (e.g., transcripts older than the most recent N checkpoints are pruned, with only the checkpoint retained). The implementation plan P7-T3 should include transcript size monitoring.

## P9 (Low) §11.2 Credential Broker 签名/验证开销

**Target**: Design spec §11.2

Every API Provider call requires: (1) Sidecar signs a capability (HMAC/signed token), (2) sends it to Rust Core via UDS, (3) Rust Core verifies the signature, (4) looks up Keychain credential, (5) returns plaintext, (6) Sidecar uses it for the HTTP request. Steps 2-3 involve a cross-process round-trip over UDS with cryptographic verification.

For high-throughput scenarios (many parallel workers all using API Providers), this round-trip per call adds latency. The capability has a 30-second TTL and is single-use, so there is no connection pooling benefit.

**Recommendation**: The implementation plan should note this overhead and consider whether Rust Core can pre-fetch credentials into a short-lived in-memory cache (within the 30s window) to avoid repeated Keychain lookups for the same (company, provider, slot) tuple within a single session turn.

## P10 (Low) §5.5 五类审计表写入分散增加事务开销

**Target**: Design spec §5.5

Different operations write to different audit tables: `acl_audit_log` on authorize, `knowledge_access_logs` on search/get, `org_change_audit` on org mutations, `knowledge_governance_audit` on knowledge governance, `backend_change_audit` on backend changes. Each write is in the same transaction as the business operation, but the 5 separate tables with different schemas increase migration complexity and index maintenance overhead.

For the baseline of 10K knowledge items and 100 employees, the audit tables grow linearly. The 90-day allow-detail compaction (§5.5 RetentionCompactor) only runs daily, so mid-cycle table sizes could be significant.

**Recommendation**: No action needed for v1; the current design is correct. Just noting that P11-T2 should include index EXPLAIN QUERY PLAN verification (already in P1-T5 test requirements) to confirm audit queries use indexes.

## P11 (Low) §4.5 `sidecar_restart_ready_time` 未区分 Sidecar 进程恢复与业务就绪

**Target**: Design spec §4.5

§4.5 defines `sidecar_restart_ready_time < 3s` as `release_gate` for "Sidecar 子进程崩溃后重启到能接受 RPC（不含任务恢复）". This is clear. However, the implementation plan P0-T3's DoD says "手动杀死 Sidecar 进程后，sidecar_restart_ready_time 达到 §4.5 的 release_gate 目标". The 3s budget includes: process spawn, Python interpreter startup, PyInstaller unpacking (if frozen), migration check, RPC server bind. On Apple Silicon M-series with 16GB, this should be achievable, but the implementation plan does not break down the time budget per step.

**Recommendation**: P0-T3 should include a breakdown: process spawn (~0.5s) + Python/import init (~1s) + migration check (~0.5s) + RPC bind (~0.1s) = ~2.1s, leaving ~0.9s margin. Cold PyInstaller startup could add 1-2s; the test should be run against the frozen binary, not `uv run`.

## P12 (Low) §10.1 PlanValidator PV-03 规模校验的性能影响

**Target**: Design spec §10.1.1

PV-03 enforces max_nodes=50 (configurable 1-200) and max_depth=8 (configurable 1-16). With max_nodes=200 and a dense DAG, the cycle detection (PV-02) requires O(V+E) traversal. The plan JSON is parsed and validated in-memory, which is fine for the scale limits. However, PV-13 (Backend schedulability) requires checking Backend health/lease state for each agent/review/fix/merge node, which adds per-node DB queries.

**Recommendation**: No action needed; the scale limits (max 200 nodes) keep this bounded. Just noting that PV-13 should batch Backend health lookups rather than querying per-node.

## P13 (Low) §9.5 LanceDB pre-filter 验证缺失可能引入性能退化

**Target**: Design spec §9.4, §17

§9.4 requires LanceDB to support true pre-filter (filter before similarity computation, not post-filter). §17 lists "检索预过滤验证" as a quality gate. If the chosen LanceDB version only supports post-filter, the system falls back to "先召回再过滤" which: (a) returns incorrect results (not just slow), and (b) wastes compute on computing similarity for documents that would be filtered out.

This is both a correctness and performance issue: post-filter with large corpora (10K documents) means computing cosine similarity against all vectors before filtering, whereas pre-filter reduces the search space before similarity computation.

**Recommendation**: P0-T4 or a dedicated Phase 0 spike should validate LanceDB pre-filter support early (Week 1-2), as §17 already requires it. The validation should include a benchmark comparing pre-filter vs post-filter at the 10K document scale.

## P14 (Low) §4.6 进程池大小 `global_process_limit` 计算公式需实测校准

**Target**: Design spec §4.6

§4.6 defines `global_process_limit = clamp(logical_cpu_count, 2, 16)` as default. For Apple Silicon M-series (8-12 cores on M1-M3), this yields 8-12. Each CLI Provider sub-process (e.g., Claude Code CLI) consumes significant memory (Node.js runtime). With 16GB RAM and 12 sub-processes, memory pressure could cause swapping, degrading all concurrent workers.

The design notes "显式值仅允许 1..64" but does not provide guidance on how to determine the optimal value for a given machine.

**Recommendation**: P0-T4 should include a memory profiling step: spawn N CLI sub-processes simultaneously and measure RSS, to determine the safe default for M-series machines. The implementation plan should note that the default may need to be lowered from the CPU-based calculation to a memory-based one.

# 建议

1. **Priority fix**: Add `compute_scope` performance budget to §4.5 with warm-cache assumption and consider per-request memoization (P1).
2. **Priority fix**: Add `knowledge_search_e2e_time` observational metric to §4.5 and latency budget breakdown in P8-T4 (P3).
3. **Priority fix**: Explicitly declare `(employee_id, security_context_key)` index on `session_threads` in §15/ER diagram (P5).
4. Specify backup quiesce timeout value in §4.7 (P4).
5. Specify Outbox Worker polling interval in P1-T2 (P6).
6. Consider materialized reserved_micros counter for budget hot path (P7).
7. Define transcript size limit or archival strategy in §11.4 (P8).
8. Add LanceDB pre-filter benchmark to Phase 0 validation (P13).
9. Add memory profiling to P0-T4 for process limit calibration (P14).
10. None of the 21 known review issues (A-1~A-5, B-1~B-4, C-1~C-12) have significant performance implications. A-4 (table field completeness) could affect query planning if fields are added later without index updates, and B-2 (RetentionCompactor manifests) affects compaction auditability but not performance. The remaining 19 issues are purely correctness/consistency.

"""统一错误码体系。"""

from __future__ import annotations

from typing import Final


class AcosError(Exception):
    """所有业务异常的基类。"""

    def __init__(
        self,
        code: str,
        message: str,
        cause: str = "",
        suggestion: str = "",
        trace_id: str = "",
    ) -> None:
        self.code = code
        self.message = message
        self.cause = cause
        self.suggestion = suggestion
        self.trace_id = trace_id
        super().__init__(message)

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "cause": self.cause,
            "suggestion": self.suggestion,
            "trace_id": self.trace_id,
        }


def _ec(code: str, message: str, cause: str = "", suggestion: str = "") -> dict[str, str]:
    """错误码常量工厂，返回 to_dict 友好的模板。"""
    return {"code": code, "message": message, "cause": cause, "suggestion": suggestion}


# ── ORG_* ────────────────────────────────────────────────────────────────

ORG_VALIDATION: Final[str] = "ORG-VALIDATION"
ORG_NOT_FOUND: Final[str] = "ORG-NOT-FOUND"
ORG_STATE_INVALID: Final[str] = "ORG-STATE-INVALID"
ORG_PERM_DENIED: Final[str] = "ORG-PERM-DENIED"
ORG_DEPT_CYCLE: Final[str] = "ORG-DEPT-CYCLE"
ORG_COMPANY_DISSOLVED: Final[str] = "ORG-COMPANY-DISSOLVED"

# ── CAP_* ────────────────────────────────────────────────────────────────

CAP_VALIDATION: Final[str] = "CAP-VALIDATION"
CAP_VERSION_IMMUTABLE: Final[str] = "CAP-VERSION-IMMUTABLE"
CAP_SNAPSHOT_CHECKSUM_MISMATCH: Final[str] = "CAP-SNAPSHOT-CHECKSUM-MISMATCH"
CAP_QUALITY_GATE_FAILED: Final[str] = "CAP-QUALITY-GATE-FAILED"
CAP_STATE_INVALID: Final[str] = "CAP-STATE-INVALID"

# ── ASSET_* ──────────────────────────────────────────────────────────────

ASSET_CROSS_COMPANY_REF_DENIED: Final[str] = "ASSET-CROSS-COMPANY-REF-DENIED"
TEMPLATE_CROSS_COMPANY_DENIED: Final[str] = "TEMPLATE-CROSS-COMPANY-DENIED"

# ── WF_* ─────────────────────────────────────────────────────────────────

WF_BUDGET_EXCEEDED: Final[str] = "WF-BUDGET-EXCEEDED"
WF_FIX_MAX_ROUNDS: Final[str] = "WF-FIX-MAX-ROUNDS"

# ── RT_* ─────────────────────────────────────────────────────────────────

RT_SESSION_BUSY: Final[str] = "RT-SESSION-BUSY"
RT_SESSION_STALE: Final[str] = "RT-SESSION-STALE"
RT_SESSION_READONLY: Final[str] = "RT-SESSION-READONLY"
RT_RESUME_FAILED: Final[str] = "RT-RESUME-FAILED"
RT_DRAIN_TOKEN_INVALID: Final[str] = "RT-DRAIN-TOKEN-INVALID"
RT_DRAIN_CLOSED: Final[str] = "RT-DRAIN-CLOSED"
RT_DRAIN_OPEN: Final[str] = "RT-DRAIN-OPEN"
RT_DRAIN_HELD_TURN: Final[str] = "RT-DRAIN-HELD-TURN"
RT_DRAIN_NOT_FOUND: Final[str] = "RT-DRAIN-NOT-FOUND"
RT_EMPLOYEE_NOT_ACTIVE: Final[str] = "RT-EMPLOYEE-NOT-ACTIVE"

# ── PROV_* ───────────────────────────────────────────────────────────────

PROV_UNAVAILABLE: Final[str] = "PROV-UNAVAILABLE"
PROV_AUTH_INVALID: Final[str] = "PROV-AUTH-INVALID"
PROV_BUDGET_FROZEN: Final[str] = "PROV-BUDGET-FROZEN"
PROV_PRICING_INVALID: Final[str] = "PROV-PRICING-INVALID"
PROV_PRICE_NOT_FOUND: Final[str] = "PROV-PRICE-NOT-FOUND"
PROV_PRICE_EXPIRED: Final[str] = "PROV-PRICE-EXPIRED"
PROV_PRICE_CURRENCY_CONFLICT: Final[str] = "PROV-PRICE-CURRENCY-CONFLICT"
PROV_PRICE_OVERFLOW: Final[str] = "PROV-PRICE-OVERFLOW"
PROV_PRICE_CROSS_COMPANY: Final[str] = "PROV-PRICE-CROSS-COMPANY"
PROV_MANIFEST_INVALID: Final[str] = "PROV-MANIFEST-INVALID"
PROV_VALIDATION: Final[str] = "PROV-VALIDATION"
PROV_FREEZE_NOT_FOUND: Final[str] = "PROV-FREEZE-NOT-FOUND"
PROV_FREEZE_STILL_UNSAFE: Final[str] = "PROV-FREEZE-STILL-UNSAFE"
CRED_NOT_FOUND: Final[str] = "CRED-NOT-FOUND"
CRED_SCOPE_DENIED: Final[str] = "CRED-SCOPE-DENIED"
CRED_VALIDATION: Final[str] = "CRED-VALIDATION"
RT_VALIDATION: Final[str] = "RT-VALIDATION"
RT_SESSION_NOT_FOUND: Final[str] = "RT-SESSION-NOT-FOUND"
RT_RUN_NOT_FOUND: Final[str] = "RT-RUN-NOT-FOUND"
RT_RUN_FAILED: Final[str] = "RT-RUN-FAILED"

# ── BACKEND_* ────────────────────────────────────────────────────────────

BACKEND_UNAVAILABLE: Final[str] = "BACKEND-UNAVAILABLE"
BACKEND_CAPACITY_FULL: Final[str] = "BACKEND-CAPACITY-FULL"
BACKEND_DRAINING: Final[str] = "BACKEND-DRAINING"
BACKEND_PATH_DENIED: Final[str] = "BACKEND-PATH-DENIED"
BACKEND_RECOVERY_UNSAFE: Final[str] = "BACKEND-RECOVERY-UNSAFE"
BACKEND_QUEUE_TIMEOUT: Final[str] = "BACKEND-QUEUE-TIMEOUT"
BACKEND_NOT_FOUND: Final[str] = "BACKEND-NOT-FOUND"
BACKEND_CROSS_COMPANY_DENIED: Final[str] = "BACKEND-CROSS-COMPANY-DENIED"
BACKEND_STATE_TRANSITION_INVALID: Final[str] = "BACKEND-STATE-TRANSITION-INVALID"
BACKEND_DEFAULT_CONFLICT: Final[str] = "BACKEND-DEFAULT-CONFLICT"
BACKEND_LEASE_HELD: Final[str] = "BACKEND-LEASE-HELD"
BACKEND_HEALTH_NOT_HEALTHY: Final[str] = "BACKEND-HEALTH-NOT-HEALTHY"
BACKEND_VALIDATION: Final[str] = "BACKEND-VALIDATION"
BACKEND_COMPANY_NOT_WRITABLE: Final[str] = "BACKEND-COMPANY-NOT-WRITABLE"

# ── KG_* ─────────────────────────────────────────────────────────────────

KG_EXTRACT_FAILED: Final[str] = "KG-EXTRACT-FAILED"
KG_EMBED_VERSION_MISMATCH: Final[str] = "KG-EMBED-VERSION-MISMATCH"
KG_CLOUD_CONSENT_REQUIRED: Final[str] = "KG-CLOUD-CONSENT-REQUIRED"

# ── GOV_* ────────────────────────────────────────────────────────────────

GOV_APPROVAL_REJECTED: Final[str] = "GOV-APPROVAL-REJECTED"
GOV_BUDGET_CURRENCY_INVALID: Final[str] = "GOV-BUDGET-CURRENCY-INVALID"
GOV_BUDGET_LIMIT_INVALID: Final[str] = "GOV-BUDGET-LIMIT-INVALID"
GOV_BUDGET_POLICY_INVALID: Final[str] = "GOV-BUDGET-POLICY-INVALID"
GOV_APPROVAL_NOT_FOUND: Final[str] = "GOV-APPROVAL-NOT-FOUND"
GOV_APPROVAL_STALE: Final[str] = "GOV-APPROVAL-STALE"
GOV_APPROVAL_EXPIRED: Final[str] = "GOV-APPROVAL-EXPIRED"
GOV_AUDIT_INVALID: Final[str] = "GOV-AUDIT-INVALID"
GOV_BUDGET_CROSS_COMPANY: Final[str] = "GOV-BUDGET-CROSS-COMPANY"

# ── SYS_* ────────────────────────────────────────────────────────────────

SYS_INTERNAL: Final[str] = "SYS-INTERNAL"
SYS_OPTIMISTIC_LOCK_CONFLICT: Final[str] = "SYS-OPTIMISTIC-LOCK-CONFLICT"
SYS_IDEMPOTENCY_CONFLICT: Final[str] = "SYS-IDEMPOTENCY-CONFLICT"
SYS_MIGRATION_FAILED: Final[str] = "SYS-MIGRATION-FAILED"
SYS_BACKUP_IN_PROGRESS: Final[str] = "SYS-BACKUP-IN-PROGRESS"
SYS_BACKUP_QUIESCE_TIMEOUT: Final[str] = "SYS-BACKUP-QUIESCE-TIMEOUT"
SYS_BACKUP_INCOMPATIBLE: Final[str] = "SYS-BACKUP-INCOMPATIBLE"
SYS_BACKUP_INCONSISTENT: Final[str] = "SYS-BACKUP-INCONSISTENT"
SYS_BACKUP_NOT_FOUND: Final[str] = "SYS-BACKUP-NOT-FOUND"
SYS_UPDATE_FAILED: Final[str] = "SYS-UPDATE-FAILED"
SYS_UPDATE_SIGNATURE_INVALID: Final[str] = "SYS-UPDATE-SIGNATURE-INVALID"
SYS_BOOTSTRAP_ROOT_INVALID: Final[str] = "SYS-BOOTSTRAP-ROOT-INVALID"

# ── APPR_* ──────────────────────────────────────────────────────────────

APPR_TYPE_INVALID: Final[str] = "APPR-TYPE-INVALID"
APPR_TYPE_NOT_FOUND: Final[str] = "APPR-TYPE-NOT-FOUND"
APPR_DECISION_INVALID: Final[str] = "APPR-DECISION-INVALID"
APPR_REQUEST_INVALID: Final[str] = "APPR-REQUEST-INVALID"

# ── WF_* (扩展) ──────────────────────────────────────────────────────────

WF_BUDGET_APPROVAL_PENDING: Final[str] = "WF-BUDGET-APPROVAL-PENDING"
WF_NOT_FOUND: Final[str] = "WF-NOT-FOUND"
WF_RESERVATION_NOT_FOUND: Final[str] = "WF-RESERVATION-NOT-FOUND"
WF_VALIDATION: Final[str] = "WF-VALIDATION"
WF_PLAN_CYCLE: Final[str] = "WF-PLAN-CYCLE"
WF_PLAN_VALIDATION_FAILED: Final[str] = "WF-PLAN-VALIDATION-FAILED"

# ── AUDIT_* ────────────────────────────────────────────────────────

AUDIT_VALIDATION: Final[str] = "AUDIT-VALIDATION"
INTERVENTION_NOT_FOUND: Final[str] = "INTERVENTION-NOT-FOUND"


# ── 错误码注册表 ─────────────────────────────────────────────────────────

ALL_ERROR_CODES: Final[dict[str, dict[str, str]]] = {
    ORG_VALIDATION: _ec(ORG_VALIDATION, "组织数据校验失败", suggestion="检查必填字段"),
    ORG_NOT_FOUND: _ec(ORG_NOT_FOUND, "组织不存在", suggestion="确认组织 ID"),
    ORG_STATE_INVALID: _ec(ORG_STATE_INVALID, "组织状态不合法"),
    ORG_PERM_DENIED: _ec(ORG_PERM_DENIED, "无操作权限"),
    ORG_DEPT_CYCLE: _ec(ORG_DEPT_CYCLE, "部门层级形成环路"),
    ORG_COMPANY_DISSOLVED: _ec(ORG_COMPANY_DISSOLVED, "公司已注销"),
    CAP_VALIDATION: _ec(CAP_VALIDATION, "能力定义校验失败", suggestion="检查能力 schema"),
    CAP_VERSION_IMMUTABLE: _ec(CAP_VERSION_IMMUTABLE, "已发布版本不可修改"),
    CAP_SNAPSHOT_CHECKSUM_MISMATCH: _ec(CAP_SNAPSHOT_CHECKSUM_MISMATCH, "快照校验和不匹配"),
    CAP_QUALITY_GATE_FAILED: _ec(CAP_QUALITY_GATE_FAILED, "质量门禁未通过"),
    CAP_STATE_INVALID: _ec(CAP_STATE_INVALID, "能力状态转换无效"),
    ASSET_CROSS_COMPANY_REF_DENIED: _ec(ASSET_CROSS_COMPANY_REF_DENIED, "禁止跨公司引用资产"),
    TEMPLATE_CROSS_COMPANY_DENIED: _ec(TEMPLATE_CROSS_COMPANY_DENIED, "禁止跨公司使用模板"),
    WF_BUDGET_EXCEEDED: _ec(WF_BUDGET_EXCEEDED, "工作流预算超限"),
    WF_FIX_MAX_ROUNDS: _ec(WF_FIX_MAX_ROUNDS, "修复轮次已达上限"),
    RT_SESSION_BUSY: _ec(RT_SESSION_BUSY, "会话正忙"),
    RT_SESSION_STALE: _ec(RT_SESSION_STALE, "会话已过期"),
    RT_SESSION_READONLY: _ec(RT_SESSION_READONLY, "会话为只读"),
    RT_RESUME_FAILED: _ec(RT_RESUME_FAILED, "会话恢复失败"),
    PROV_UNAVAILABLE: _ec(PROV_UNAVAILABLE, "供应商不可用"),
    PROV_AUTH_INVALID: _ec(PROV_AUTH_INVALID, "供应商认证无效"),
    PROV_BUDGET_FROZEN: _ec(PROV_BUDGET_FROZEN, "供应商预算已冻结"),
    BACKEND_UNAVAILABLE: _ec(BACKEND_UNAVAILABLE, "后端服务不可用"),
    BACKEND_CAPACITY_FULL: _ec(BACKEND_CAPACITY_FULL, "后端容量已满"),
    BACKEND_DRAINING: _ec(BACKEND_DRAINING, "后端正在排空"),
    BACKEND_PATH_DENIED: _ec(BACKEND_PATH_DENIED, "后端路径被拒绝"),
    BACKEND_RECOVERY_UNSAFE: _ec(BACKEND_RECOVERY_UNSAFE, "后端恢复不安全"),
    BACKEND_QUEUE_TIMEOUT: _ec(BACKEND_QUEUE_TIMEOUT, "后端队列超时"),
    KG_EXTRACT_FAILED: _ec(KG_EXTRACT_FAILED, "知识图谱提取失败"),
    KG_EMBED_VERSION_MISMATCH: _ec(KG_EMBED_VERSION_MISMATCH, "向量嵌入版本不匹配"),
    KG_CLOUD_CONSENT_REQUIRED: _ec(KG_CLOUD_CONSENT_REQUIRED, "需要云服务使用授权"),
    GOV_APPROVAL_REJECTED: _ec(GOV_APPROVAL_REJECTED, "治理审批被拒绝"),
    GOV_BUDGET_CURRENCY_INVALID: _ec(GOV_BUDGET_CURRENCY_INVALID, "预算币种无效"),
    GOV_BUDGET_LIMIT_INVALID: _ec(GOV_BUDGET_LIMIT_INVALID, "预算限额无效"),
    GOV_BUDGET_POLICY_INVALID: _ec(GOV_BUDGET_POLICY_INVALID, "预算策略无效"),
    SYS_INTERNAL: _ec(SYS_INTERNAL, "系统内部错误", suggestion="请联系管理员"),
    SYS_OPTIMISTIC_LOCK_CONFLICT: _ec(SYS_OPTIMISTIC_LOCK_CONFLICT, "乐观锁冲突", suggestion="请重试"),
    SYS_IDEMPOTENCY_CONFLICT: _ec(SYS_IDEMPOTENCY_CONFLICT, "幂等键冲突"),
    SYS_MIGRATION_FAILED: _ec(SYS_MIGRATION_FAILED, "数据库迁移失败"),
    SYS_BACKUP_IN_PROGRESS: _ec(SYS_BACKUP_IN_PROGRESS, "备份进行中"),
    SYS_BACKUP_QUIESCE_TIMEOUT: _ec(SYS_BACKUP_QUIESCE_TIMEOUT, "备份静默超时"),
    SYS_BACKUP_INCOMPATIBLE: _ec(SYS_BACKUP_INCOMPATIBLE, "备份版本不兼容"),
    SYS_BACKUP_INCONSISTENT: _ec(SYS_BACKUP_INCONSISTENT, "备份数据不一致"),
    SYS_BACKUP_NOT_FOUND: _ec(SYS_BACKUP_NOT_FOUND, "备份不存在"),
    SYS_UPDATE_FAILED: _ec(SYS_UPDATE_FAILED, "系统更新失败"),
    SYS_UPDATE_SIGNATURE_INVALID: _ec(SYS_UPDATE_SIGNATURE_INVALID, "更新签名校验失败"),
    SYS_BOOTSTRAP_ROOT_INVALID: _ec(SYS_BOOTSTRAP_ROOT_INVALID, "引导根节点无效"),
    BACKEND_NOT_FOUND: _ec(BACKEND_NOT_FOUND, "后端不存在"),
    BACKEND_CROSS_COMPANY_DENIED: _ec(BACKEND_CROSS_COMPANY_DENIED, "禁止跨公司访问后端"),
    BACKEND_STATE_TRANSITION_INVALID: _ec(BACKEND_STATE_TRANSITION_INVALID, "后端状态转换无效"),
    BACKEND_DEFAULT_CONFLICT: _ec(BACKEND_DEFAULT_CONFLICT, "默认后端不可 drain/archive"),
    BACKEND_LEASE_HELD: _ec(BACKEND_LEASE_HELD, "后端存在占用中的租约，禁止归档"),
    BACKEND_HEALTH_NOT_HEALTHY: _ec(BACKEND_HEALTH_NOT_HEALTHY, "后端未通过健康检查"),
    BACKEND_VALIDATION: _ec(BACKEND_VALIDATION, "后端参数校验失败"),
    BACKEND_COMPANY_NOT_WRITABLE: _ec(BACKEND_COMPANY_NOT_WRITABLE, "公司状态不可写"),
    PROV_PRICING_INVALID: _ec(PROV_PRICING_INVALID, "价格配置无效"),
    PROV_PRICE_NOT_FOUND: _ec(PROV_PRICE_NOT_FOUND, "价格版本不存在"),
    PROV_PRICE_EXPIRED: _ec(PROV_PRICE_EXPIRED, "价格版本已过期"),
    PROV_PRICE_CURRENCY_CONFLICT: _ec(PROV_PRICE_CURRENCY_CONFLICT, "价格币种冲突"),
    PROV_PRICE_OVERFLOW: _ec(PROV_PRICE_OVERFLOW, "价格溢出"),
    PROV_PRICE_CROSS_COMPANY: _ec(PROV_PRICE_CROSS_COMPANY, "禁止跨公司价格"),
    PROV_MANIFEST_INVALID: _ec(PROV_MANIFEST_INVALID, "供应商清单签名无效"),
    PROV_VALIDATION: _ec(PROV_VALIDATION, "供应商参数校验失败"),
    PROV_FREEZE_NOT_FOUND: _ec(PROV_FREEZE_NOT_FOUND, "预算冻结不存在"),
    PROV_FREEZE_STILL_UNSAFE: _ec(PROV_FREEZE_STILL_UNSAFE, "预算冻结仍未满足安全解除条件"),
    CRED_NOT_FOUND: _ec(CRED_NOT_FOUND, "凭据不存在"),
    CRED_SCOPE_DENIED: _ec(CRED_SCOPE_DENIED, "凭据作用域被拒绝"),
    CRED_VALIDATION: _ec(CRED_VALIDATION, "凭据校验失败"),
    RT_VALIDATION: _ec(RT_VALIDATION, "运行时参数校验失败"),
    RT_SESSION_NOT_FOUND: _ec(RT_SESSION_NOT_FOUND, "运行时会话不存在"),
    RT_RUN_NOT_FOUND: _ec(RT_RUN_NOT_FOUND, "运行时执行不存在"),
    RT_RUN_FAILED: _ec(RT_RUN_FAILED, "运行时执行失败"),
    RT_DRAIN_TOKEN_INVALID: _ec(RT_DRAIN_TOKEN_INVALID, "排空令牌无效"),
    RT_DRAIN_CLOSED: _ec(RT_DRAIN_CLOSED, "排空已关闭"),
    RT_DRAIN_OPEN: _ec(RT_DRAIN_OPEN, "排空已开启"),
    RT_DRAIN_HELD_TURN: _ec(RT_DRAIN_HELD_TURN, "排空存在占用中的回合"),
    RT_DRAIN_NOT_FOUND: _ec(RT_DRAIN_NOT_FOUND, "排空不存在"),
    RT_EMPLOYEE_NOT_ACTIVE: _ec(RT_EMPLOYEE_NOT_ACTIVE, "职员未处于活跃状态"),
    GOV_APPROVAL_NOT_FOUND: _ec(GOV_APPROVAL_NOT_FOUND, "审批不存在"),
    GOV_APPROVAL_STALE: _ec(GOV_APPROVAL_STALE, "审批已过期"),
    GOV_APPROVAL_EXPIRED: _ec(GOV_APPROVAL_EXPIRED, "审批已过期"),
    GOV_AUDIT_INVALID: _ec(GOV_AUDIT_INVALID, "治理审计参数无效"),
    GOV_BUDGET_CROSS_COMPANY: _ec(GOV_BUDGET_CROSS_COMPANY, "禁止跨公司预算操作"),
    APPR_TYPE_INVALID: _ec(APPR_TYPE_INVALID, "审批类型无效"),
    APPR_TYPE_NOT_FOUND: _ec(APPR_TYPE_NOT_FOUND, "审批类型不存在"),
    APPR_DECISION_INVALID: _ec(APPR_DECISION_INVALID, "审批决定无效"),
    APPR_REQUEST_INVALID: _ec(APPR_REQUEST_INVALID, "审批请求无效"),
    WF_BUDGET_APPROVAL_PENDING: _ec(WF_BUDGET_APPROVAL_PENDING, "预算修订待审批"),
    WF_NOT_FOUND: _ec(WF_NOT_FOUND, "工作流不存在"),
    WF_RESERVATION_NOT_FOUND: _ec(WF_RESERVATION_NOT_FOUND, "预算预留不存在"),
    WF_VALIDATION: _ec(WF_VALIDATION, "工作流参数校验失败"),
    WF_PLAN_CYCLE: _ec(WF_PLAN_CYCLE, "计划存在环路"),
    WF_PLAN_VALIDATION_FAILED: _ec(WF_PLAN_VALIDATION_FAILED, "计划校验未通过"),
    AUDIT_VALIDATION: _ec(AUDIT_VALIDATION, "审计查询参数校验失败", suggestion="检查 audit_type / company_id / 时间范围"),
    INTERVENTION_NOT_FOUND: _ec(INTERVENTION_NOT_FOUND, "人工干预项不存在"),
}


def create_error(
    code: str,
    message: str,
    cause: str = "",
    suggestion: str = "",
    trace_id: str = "",
) -> AcosError:
    """工厂函数，根据错误码创建 AcosError 实例。"""
    if code in ALL_ERROR_CODES:
        tpl = ALL_ERROR_CODES[code]
        message = message or tpl["message"]
        cause = cause or tpl["cause"]
        suggestion = suggestion or tpl["suggestion"]
    return AcosError(code=code, message=message, cause=cause, suggestion=suggestion, trace_id=trace_id)

"""Security utilities: encryption, redaction, RBAC, audit, path safety, skill verification, process security."""

from __future__ import annotations

from ibreeze.security.audit import list_audit_logs, log_audit
from ibreeze.security.encryption import (
    decrypt,
    derive_key,
    encrypt,
    generate_api_key,
    hash_password,
    is_bcrypt_hash,
    migrate_password,
    sha256_hex,
    verify_password,
)
from ibreeze.security.path_safety import (
    PathViolationError,
    create_write_approval,
    resolve_safe,
    validate_no_traversal,
    verify_write_approval,
)
from ibreeze.security.process_security import minimal_env, sanitize_command_args
from ibreeze.security.rbac import Role, check_permission, require_permission
from ibreeze.security.redaction import redact_dict, redact_string
from ibreeze.security.skill_verify import (
    SkillVerificationError,
    compute_package_hash,
    validate_package_paths,
    verify_skill_signature,
)

__all__ = [
    # encryption
    "derive_key",
    "encrypt",
    "decrypt",
    "hash_password",
    "verify_password",
    "generate_api_key",
    "sha256_hex",
    "is_bcrypt_hash",
    "migrate_password",
    # redaction
    "redact_string",
    "redact_dict",
    # rbac
    "Role",
    "check_permission",
    "require_permission",
    # audit
    "log_audit",
    "list_audit_logs",
    # path_safety
    "PathViolationError",
    "resolve_safe",
    "validate_no_traversal",
    "create_write_approval",
    "verify_write_approval",
    # skill_verify
    "SkillVerificationError",
    "verify_skill_signature",
    "validate_package_paths",
    "compute_package_hash",
    # process_security
    "minimal_env",
    "sanitize_command_args",
]

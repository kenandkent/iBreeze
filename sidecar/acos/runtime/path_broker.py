"""公司隔离路径校验（Phase 7-T1）。

可信应用数据根由 Rust 通过认证 bootstrap 注入；Sidecar 仅在校验过的根下拼接
会话线程路径。业务代码不拼绝对路径，Rust 不实现第二套 broker。

校验规则：
- 路径必须落在 company 专属根目录下（公司边界）。
- 禁止越根（.. 逃逸到根外）。
- 禁止 symlink 逃逸（解析后仍在根内）。
- 禁止跨公司路径穿越。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from acos.rpc.errors import AcosError, BACKEND_PATH_DENIED

# 本地错误码（沿用 BACKEND-PATH-DENIED 风格，不新增错误码表项）
_RT_PATH_DENIED: Final[str] = BACKEND_PATH_DENIED


def _normalize(path: str) -> Path:
    return Path(path).expanduser()


def resolve_session_path(
    company_root: str,
    company_id: str,
    *parts: str,
    must_exist: bool = False,
) -> Path:
    """在公司专属根下解析会话相关路径，校验不越根/不跨公司/symlink 逃逸。

    company_root 必须是已通过 bootstrap 认证的可信根；company_id 锁定根下的子目录，
    防止构造 company_id 穿越到其它公司目录。
    """
    root = _normalize(company_root)
    if not root.is_absolute():
        raise AcosError(_RT_PATH_DENIED, "company_root 必须为绝对路径", cause=company_root)

    # 目标目录 = root / company_id / <parts...>
    candidate = (root / company_id / Path(*parts)).resolve()

    # 解析后的可信根（考虑 symlink），边界锚定在 root 而非 company 子目录，
    # 防止 company_id 含 .. 逃逸到 root 之外或穿越到其它公司目录。
    resolved_root = root.resolve()

    # 越根检测
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        raise AcosError(
            _RT_PATH_DENIED,
            "路径越出可信根目录",
            cause=str(candidate),
            suggestion="路径不得包含 .. 或指向根外",
        )

    # symlink 逃逸检测：任一祖先解析前后不一致即拒绝
    _assert_no_symlink_escape(candidate, resolved_root)

    if must_exist and not candidate.exists():
        raise AcosError(_RT_PATH_DENIED, "路径不存在", cause=str(candidate))

    return candidate


def _assert_no_symlink_escape(candidate: Path, resolved_root: Path) -> None:
    """逐层校验候选路径与根之间不存在 symlink 桥接逃逸。"""
    # 检查 candidate 自身及所有祖先（直到 resolved_root 为止）是否为 symlink
    cur = candidate
    visited: set[str] = set()
    while True:
        real = cur.resolve()
        if os.path.islink(str(cur)):
            # 解析真实位置后仍需落在根内
            try:
                real.relative_to(resolved_root)
            except ValueError:
                raise AcosError(
                    _RT_PATH_DENIED,
                    "检测到 symlink 越界",
                    cause=str(cur),
                )
        if str(real) in visited:
            break
        visited.add(str(real))
        if real == resolved_root or cur == resolved_root:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent


def ensure_company_dir(company_root: str, company_id: str) -> Path:
    """创建并返回公司专属目录（0700），保证隔离边界存在。"""
    root = _normalize(company_root)
    if not root.is_absolute():
        raise AcosError(_RT_PATH_DENIED, "company_root 必须为绝对路径")
    company_dir = (root / company_id).resolve()
    resolved_root = root.resolve()
    try:
        company_dir.relative_to(resolved_root)
    except ValueError:
        raise AcosError(_RT_PATH_DENIED, "company_id 越出根目录")
    company_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    # 收紧目录权限（0700）
    os.chmod(company_dir, 0o700)
    return company_dir

"""部门闭包表测试。"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite
import pytest

from acos.organization.closure import DepartmentClosure
from acos.store.migrator import Migrator


@pytest.fixture
async def db(tmp_path: Path) -> aiosqlite.Connection:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    return conn


@pytest.fixture
def closure() -> DepartmentClosure:
    return DepartmentClosure()


COMPANY_ID = "test-company"

_DEPT_COLS = (
    "department_id, company_id, parent_department_id, name, "
    "status, created_at, updated_at, version"
)


async def _create_dept(
    conn: aiosqlite.Connection,
    dept_id: str,
    parent_id: str | None,
    name: str,
) -> None:
    await conn.execute(
        f"""INSERT INTO departments ({_DEPT_COLS})
            VALUES (?, ?, ?, ?, 'active', datetime('now'), datetime('now'), 1)""",
        (dept_id, COMPANY_ID, parent_id, name),
    )


async def _create_company_with_root(conn: aiosqlite.Connection) -> str:
    root_id = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO companies (company_id, name, status) "
        "VALUES (?, 'Test', 'active')",
        (COMPANY_ID,),
    )
    await _create_dept(conn, root_id, None, "Root")
    await conn.execute(
        """INSERT INTO department_closure
           (company_id, ancestor_department_id,
            descendant_department_id, depth)
           VALUES (?, ?, ?, 0)""",
        (COMPANY_ID, root_id, root_id),
    )
    await conn.commit()
    return root_id


async def test_add_department_root(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    dept_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO companies (company_id, name, status) "
        "VALUES (?, 'Test', 'active')",
        (COMPANY_ID,),
    )
    await _create_dept(db, dept_id, None, "Root")
    await closure.add_department(db, COMPANY_ID, dept_id, None)
    await db.commit()

    cursor = await db.execute(
        "SELECT COUNT(*) FROM department_closure "
        "WHERE company_id = ? AND descendant_department_id = ?",
        (COMPANY_ID, dept_id),
    )
    row = await cursor.fetchone()
    assert row[0] == 1


async def test_add_department_child(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    child_id = str(uuid.uuid4())
    await _create_dept(db, child_id, root_id, "Child")
    await closure.add_department(db, COMPANY_ID, child_id, root_id)
    await db.commit()

    descendants = await closure.get_descendants(db, COMPANY_ID, root_id)
    assert child_id in descendants


async def test_get_descendants(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    a_id = str(uuid.uuid4())
    await _create_dept(db, a_id, root_id, "A")
    await closure.add_department(db, COMPANY_ID, a_id, root_id)

    b_id = str(uuid.uuid4())
    await _create_dept(db, b_id, a_id, "B")
    await closure.add_department(db, COMPANY_ID, b_id, a_id)
    await db.commit()

    descendants = await closure.get_descendants(db, COMPANY_ID, root_id)
    assert a_id in descendants
    assert b_id in descendants
    assert len(descendants) == 2


async def test_get_ancestors(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    child_id = str(uuid.uuid4())
    await _create_dept(db, child_id, root_id, "Child")
    await closure.add_department(db, COMPANY_ID, child_id, root_id)
    await db.commit()

    ancestors = await closure.get_ancestors(db, COMPANY_ID, child_id)
    assert root_id in ancestors


async def test_move_subtree(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    a_id = str(uuid.uuid4())
    await _create_dept(db, a_id, root_id, "A")
    await closure.add_department(db, COMPANY_ID, a_id, root_id)

    b_id = str(uuid.uuid4())
    await _create_dept(db, b_id, a_id, "B")
    await closure.add_department(db, COMPANY_ID, b_id, a_id)

    c_id = str(uuid.uuid4())
    await _create_dept(db, c_id, root_id, "C")
    await closure.add_department(db, COMPANY_ID, c_id, root_id)
    await db.commit()

    await closure.move_subtree(db, COMPANY_ID, b_id, c_id)
    await db.commit()

    ancestors_of_b = await closure.get_ancestors(db, COMPANY_ID, b_id)
    assert c_id in ancestors_of_b
    assert a_id not in ancestors_of_b

    descendants_of_c = await closure.get_descendants(db, COMPANY_ID, c_id)
    assert b_id in descendants_of_c


async def test_move_creates_cycle_rejected(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    a_id = str(uuid.uuid4())
    await _create_dept(db, a_id, root_id, "A")
    await closure.add_department(db, COMPANY_ID, a_id, root_id)

    b_id = str(uuid.uuid4())
    await _create_dept(db, b_id, a_id, "B")
    await closure.add_department(db, COMPANY_ID, b_id, a_id)
    await db.commit()

    is_cycle = await closure.check_cycle(db, COMPANY_ID, a_id, b_id)
    assert is_cycle is True


async def test_three_level_tree(
    db: aiosqlite.Connection, closure: DepartmentClosure
) -> None:
    root_id = await _create_company_with_root(db)

    a_id = str(uuid.uuid4())
    await _create_dept(db, a_id, root_id, "A")
    await closure.add_department(db, COMPANY_ID, a_id, root_id)

    b_id = str(uuid.uuid4())
    await _create_dept(db, b_id, a_id, "B")
    await closure.add_department(db, COMPANY_ID, b_id, a_id)

    c_id = str(uuid.uuid4())
    await _create_dept(db, c_id, b_id, "C")
    await closure.add_department(db, COMPANY_ID, c_id, b_id)
    await db.commit()

    descendants = await closure.get_descendants(db, COMPANY_ID, root_id)
    assert len(descendants) == 3
    assert a_id in descendants
    assert b_id in descendants
    assert c_id in descendants

    ancestors_c = await closure.get_ancestors(db, COMPANY_ID, c_id)
    assert len(ancestors_c) == 3
    assert b_id in ancestors_c
    assert a_id in ancestors_c
    assert root_id in ancestors_c

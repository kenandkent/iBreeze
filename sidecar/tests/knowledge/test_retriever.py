"""P8-T4 混合检索安全测试：跨公司/跨部门/employee_private/task_private 零泄漏。

真实 FTS5 + 真实 LanceDB pre-filter；ACL 谓词下推到查询条件（非先查全再过滤）。
"""

from __future__ import annotations

import aiosqlite
import pytest

from tests.knowledge._helpers import (
    insert_department,
    make_employee,
    seed_company,
    setup_db,
)
from acos.knowledge.embedding import LocalEmbedding
from acos.knowledge.retriever import Retriever
from acos.knowledge.vector_store import LanceVectorStore
from acos.organization.permission_engine import PermissionEngine


def _insert_doc(db, document_id, company_id, title, content, category, visibility,
                dept=None, task=None, emp=None, gen=None):
    return db.execute(
        """INSERT INTO knowledge_documents
              (document_id, company_id, title, content, source_type, source_category,
               visibility, embedding_status, checksum, version, status,
               department_id, task_id, employee_id, generation_id)
           VALUES (?, ?, ?, ?, 'derived', ?, ?, 'pending', 'cs', 1, 'active', ?, ?, ?, ?)""",
        (document_id, company_id, title, content, category, visibility,
         dept, task, emp, gen),
    )


def _insert_fts(db, document_id, company_id, category, visibility, dept, task, emp, title, content):
    return db.execute(
        """INSERT INTO knowledge_fts
              (document_id, company_id, source_category, visibility, department_id,
               task_id, employee_id, title, content)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (document_id, company_id, category, visibility, dept, task, emp, title, content),
    )


async def _seed_docs(db_path, generation_id):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        # comp_a 的 company 级知识
        await _insert_doc(db, "da1", "comp_a", "API 规范", "RESTful API 设计规范 comp_a", "official", "company", gen=generation_id)
        await _insert_fts(db, "da1", "comp_a", "official", "company", None, None, None, "API 规范", "RESTful API 设计规范 comp_a")
        # comp_a 的 department 级知识（D1）
        await _insert_doc(db, "da2", "comp_a", "部门手册", "D1 部门内部手册内容", "official", "department", dept="D1", gen=generation_id)
        await _insert_fts(db, "da2", "comp_a", "official", "department", "D1", None, None, "部门手册", "D1 部门内部手册内容")
        # comp_a 的 employee_private（emp1 私人）
        await _insert_doc(db, "da3", "comp_a", "私人笔记", "emp1 私人笔记内容", "custom", "employee", emp="emp1", gen=generation_id)
        await _insert_fts(db, "da3", "comp_a", "custom", "employee", None, None, "emp1", "私人笔记", "emp1 私人笔记内容")
        # comp_a 的 task_private（task1）
        await _insert_doc(db, "da4", "comp_a", "任务资料", "task1 私有资料内容", "custom", "task", task="task1", gen=generation_id)
        await _insert_fts(db, "da4", "comp_a", "custom", "task", None, "task1", None, "任务资料", "task1 私有资料内容")
        # comp_b 的哨兵（绝不可泄漏到 comp_a）
        await _insert_doc(db, "db1", "comp_b", "竞品秘密", "comp_b 竞品秘密内容", "official", "company", gen=generation_id)
        await _insert_fts(db, "db1", "comp_b", "official", "company", None, None, None, "竞品秘密", "comp_b 竞品秘密内容")
        await db.commit()


@pytest.fixture
async def env(tmp_path):
    db_path = await setup_db(tmp_path)
    await seed_company(db_path, "comp_a")
    await seed_company(db_path, "comp_b")
    await insert_department(db_path, "comp_a", "D1", None)
    await insert_department(db_path, "comp_a", "D2", "D1")
    await insert_department(db_path, "comp_b", "BD1", None)
    await make_employee(db_path, "comp_a", "D1", "emp1")
    await make_employee(db_path, "comp_a", "D2", "emp2")
    await make_employee(db_path, "comp_b", "BD1", "emp_b")
    # task1 归属 D1，assignment emp1
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO tasks (task_id, company_id, department_id, created_by_employee_id, title, status, version, created_at) VALUES ('task1','comp_a','D1','emp1','任务一','running',1,datetime('now'))"
        )
        await db.execute(
            "INSERT INTO task_assignments (assignment_id, task_id, employee_id, company_id, status, created_at) VALUES ('as1','task1','emp1','comp_a','active',datetime('now'))"
        )
        await db.commit()
    gen = "g1"
    await _seed_docs(db_path, gen)
    emb = LocalEmbedding()
    vs = LanceVectorStore(db_path, emb.dim)
    # 写入向量（带真实 ACL 列）
    for cid, company, vis, dept, task, emp, text in [
        ("da1", "comp_a", "company", None, None, None, "RESTful API 设计规范 comp_a"),
        ("da2", "comp_a", "department", "D1", None, None, "D1 部门内部手册内容"),
        ("da3", "comp_a", "employee", None, None, "emp1", "emp1 私人笔记内容"),
        ("da4", "comp_a", "task", None, "task1", None, "task1 私有资料内容"),
        ("db1", "comp_b", "company", None, None, None, "comp_b 竞品秘密内容"),
    ]:
        vec = await emb.embed_text(text)
        await vs.upsert(cid, company, gen, vec,
                        {"visibility": vis, "department_id": dept or "",
                         "task_id": task or "", "employee_id": emp or "",
                         "document_id": cid, "text": text})
    yield db_path, emb, vs, gen
    vs.close()


async def test_cross_company_zero_leak(env) -> None:
    db_path, emb, vs, gen = env
    perm = PermissionEngine(db_path)
    retr = Retriever(db_path, emb, vs, perm)
    res = await retr.query_with_audit(
        operation="search", company_id="comp_a", view_as_employee_id="emp1",
        query="秘密", generation_id=gen,
    )
    ids = res["result_knowledge_ids"]
    assert "db1" not in ids
    assert all(not i.startswith("db") for i in ids)


async def test_employee_private_not_leaked_to_peer(env) -> None:
    db_path, emb, vs, gen = env
    perm = PermissionEngine(db_path)
    retr = Retriever(db_path, emb, vs, perm)
    # emp2 是 D2（D1 后代），但 emp1 的 employee_private 不应可见
    res = await retr.query_with_audit(
        operation="search", company_id="comp_a", view_as_employee_id="emp2",
        query="私人笔记", generation_id=gen,
    )
    assert "da3" not in res["result_knowledge_ids"]


async def test_task_private_visible_to_assignee(env) -> None:
    db_path, emb, vs, gen = env
    perm = PermissionEngine(db_path)
    retr = Retriever(db_path, emb, vs, perm)
    res = await retr.query_with_audit(
        operation="search", company_id="comp_a", view_as_employee_id="emp1",
        query="任务资料", generation_id=gen, task_id="task1",
    )
    assert "da4" in res["result_knowledge_ids"]


async def test_department_visibility_branch(env) -> None:
    db_path, emb, vs, gen = env
    perm = PermissionEngine(db_path)
    retr = Retriever(db_path, emb, vs, perm)
    # emp1 在 D1，可见本部门 department 知识 da2
    res = await retr.query_with_audit(
        operation="search", company_id="comp_a", view_as_employee_id="emp1",
        query="部门手册", generation_id=gen,
    )
    assert "da2" in res["result_knowledge_ids"]


async def test_access_log_matches_result(env) -> None:
    db_path, emb, vs, gen = env
    perm = PermissionEngine(db_path)
    retr = Retriever(db_path, emb, vs, perm)
    res = await retr.query_with_audit(
        operation="search", company_id="comp_a", view_as_employee_id="emp1",
        query="API 规范", generation_id=gen,
    )
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT result_knowledge_ids FROM knowledge_access_logs WHERE company_id='comp_a' ORDER BY timestamp DESC LIMIT 1"
        )
        row = await cur.fetchone()
        import json
        logged = json.loads(row["result_knowledge_ids"])
    assert logged == res["result_knowledge_ids"]

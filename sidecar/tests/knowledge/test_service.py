"""kg.* RPC 浏览/检索方法测试（文档获取越权拒绝）。"""

from __future__ import annotations

import pytest

from tests.knowledge._helpers import (
    insert_department,
    make_employee,
    seed_company,
    setup_db,
)
from acos.rpc.methods_kg import KgMethods


async def _seed_doc(db_path, company_id, doc_id, title, content, category="manual", vis="company"):
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO knowledge_documents
                  (document_id, company_id, title, content, source_type, source_category,
                   visibility, embedding_status, checksum, version, status)
               VALUES (?, ?, ?, ?, 'manual', ?, ?, 'pending', 'cs', 1, 'active')""",
            (doc_id, company_id, title, content, category, vis),
        )
        await db.commit()


async def _seed_org(db_path):
    await seed_company(db_path, "comp_a")
    await seed_company(db_path, "comp_b")
    await insert_department(db_path, "comp_a", "D1", None)
    await insert_department(db_path, "comp_b", "BD1", None)
    await make_employee(db_path, "comp_a", "D1", "emp_a")
    await make_employee(db_path, "comp_b", "BD1", "emp_b")


async def test_document_get_cross_company_denied(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await _seed_org(db_path)
    await _seed_doc(db_path, "comp_a", "doc1", "A 文档", "内容")
    methods = KgMethods(db_path)
    res = await methods._document_get({
        "company_id": "comp_b", "view_as_employee_id": "emp_b", "knowledge_id": "doc1",
    })
    assert res.get("error") == "KG-NOT-FOUND" or res.get("error")

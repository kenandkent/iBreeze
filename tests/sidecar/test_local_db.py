"""LocalDB tests — SQLite CRUD, search, compact.

Covers design spec sections:
- H.4 Local Database (WAL mode, CRUD, search, compact)
"""
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create and initialize a temporary LocalDB instance."""
    from ibreeze.local_db import LocalDB

    db_path = tmp_path / "test.db"
    local_db = LocalDB(db_path=str(db_path))
    await local_db.initialize()
    yield local_db
    await local_db.close()


class TestLocalDB:
    """LocalDB operations."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, db):
        """Tables should be created on initialize."""
        assert db._db is not None

    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": "company-1",
            "name": "Acme Corp",
            "email": "admin@acme.com",
            "phone": "+8613800138000",
            "unified_credit_code": "91110108MA01ABCDEF",
            "business_license_url": "https://example.com/license.pdf",
            "legal_rep_id_card": "110101199001011234",
            "industry": "Tech",
            "address": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        await db.insert("companies", data)

        result = await db.get_by_id("companies", "company-1")
        assert result is not None
        assert result["name"] == "Acme Corp"
        assert result["email"] == "admin@acme.com"

    @pytest.mark.asyncio
    async def test_update_by_id(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": "company-2",
            "name": "Old Name",
            "email": None,
            "phone": None,
            "unified_credit_code": None,
            "business_license_url": None,
            "legal_rep_id_card": None,
            "industry": None,
            "address": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        await db.insert("companies", data)

        updated = await db.update_by_id("companies", "company-2", {"name": "New Name"})
        assert updated is not None
        assert updated["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_delete_by_id(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": "company-3",
            "name": "To Delete",
            "email": None,
            "phone": None,
            "unified_credit_code": None,
            "business_license_url": None,
            "legal_rep_id_card": None,
            "industry": None,
            "address": None,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        await db.insert("companies", data)

        result = await db.delete_by_id("companies", "company-3")
        assert result is True

        found = await db.get_by_id("companies", "company-3")
        assert found is None

    @pytest.mark.asyncio
    async def test_list_all_with_filters(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        await db.insert("companies", {
            "id": "c1", "name": "A", "email": None, "phone": None,
            "unified_credit_code": None, "business_license_url": None,
            "legal_rep_id_card": None, "industry": None, "address": None,
            "status": "active", "created_at": now, "updated_at": now,
        })
        await db.insert("companies", {
            "id": "c2", "name": "B", "email": None, "phone": None,
            "unified_credit_code": None, "business_license_url": None,
            "legal_rep_id_card": None, "industry": None, "address": None,
            "status": "inactive", "created_at": now, "updated_at": now,
        })

        active = await db.list_all("companies", filters={"status": "active"})
        assert len(active) == 1
        assert active[0]["name"] == "A"

    @pytest.mark.asyncio
    async def test_list_all_with_pagination(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        for i in range(5):
            await db.insert("companies", {
                "id": f"c{i}", "name": f"Company {i}", "email": None,
                "phone": None, "unified_credit_code": None,
                "business_license_url": None, "legal_rep_id_card": None,
                "industry": None, "address": None, "status": "active",
                "created_at": now, "updated_at": now,
            })

        page = await db.list_all("companies", limit=2, offset=0)
        assert len(page) == 2

    @pytest.mark.asyncio
    async def test_count(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            await db.insert("companies", {
                "id": f"c{i}", "name": f"Company {i}", "email": None,
                "phone": None, "unified_credit_code": None,
                "business_license_url": None, "legal_rep_id_card": None,
                "industry": None, "address": None, "status": "active",
                "created_at": now, "updated_at": now,
            })

        total = await db.count("companies")
        assert total == 3

    @pytest.mark.asyncio
    async def test_search(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        await db.insert("companies", {
            "id": "c1", "name": "Acme Corp", "email": "admin@acme.com",
            "phone": None, "unified_credit_code": None,
            "business_license_url": None, "legal_rep_id_card": None,
            "industry": None, "address": None, "status": "active",
            "created_at": now, "updated_at": now,
        })

        results = await db.search("companies", "Acme")
        assert len(results) == 1
        assert results[0]["name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_compact(self, db):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        await db.insert("companies", {
            "id": "c1", "name": "Test", "email": None, "phone": None,
            "unified_credit_code": None, "business_license_url": None,
            "legal_rep_id_card": None, "industry": None, "address": None,
            "status": "active", "created_at": now, "updated_at": now,
        })

        await db.compact()
        count = await db.count("companies")
        assert count == 1

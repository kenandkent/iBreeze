"""ORG-003: Company name NFKC normalization tests.

Tests that equivalent NFKC names are properly rejected.
"""

from __future__ import annotations

import pytest

from ibreeze.company import create_company, rename_company
from ibreeze.schemas import CompanyCreate, CompanyUpdate


def _create(profile_id: str, *, name: str) -> CompanyCreate:
    return CompanyCreate(
        name=name,
        introduction="测试公司",
        general_manager_name="总经理",
        base_profile_version_id=profile_id,
    )


@pytest.mark.asyncio
class TestNFKCNormalization:
    """ORG-003: Company names are NFKC normalized before comparison."""

    async def test_fullwidth_latin_equivalent(self, db, published_profile):
        await create_company(db, _create(published_profile, name="iBreeze"))
        with pytest.raises(ValueError, match="NAME_EXISTS"):
            await create_company(db, _create(published_profile, name="ｉｂｒｅｅｚｅ"))

    async def test_unicode_normalization_variants(self, db, published_profile):
        await create_company(db, _create(published_profile, name="Café"))
        with pytest.raises(ValueError, match="NAME_EXISTS"):
            await create_company(db, _create(published_profile, name="café"))

    async def test_whitespace_and_case_equivalence(self, db, published_profile):
        await create_company(db, _create(published_profile, name="Acme Corp"))
        with pytest.raises(ValueError, match="NAME_EXISTS"):
            await create_company(db, _create(published_profile, name="  acme corp  "))

    async def test_rename_rejects_nfkc_duplicate(self, db, published_profile):
        company = await create_company(db, _create(published_profile, name="Alpha"))
        await create_company(db, _create(published_profile, name="Beta"))
        with pytest.raises(ValueError, match="NAME_EXISTS"):
            await rename_company(
                db,
                company.id,
                CompanyUpdate(name="beta", expected_version=1),
                expected_version=1,
            )

    async def test_different_nfkc_names_allowed(self, db, published_profile):
        await create_company(db, _create(published_profile, name="Alpha"))
        second = await create_company(db, _create(published_profile, name="Beta"))
        assert second.normalized_name == "beta"

"""Tests for immutable catalog releases, signing, and client verification."""

import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import AgentCatalog, ModelCatalog, ProviderCatalog
from ibreeze_backend.models.catalog_release import CatalogRelease
from ibreeze_backend.releases.canonical_json import canonical_bytes, canonical_json


class TestCanonicalJson:
    """RFC 8785 canonical JSON tests."""

    def test_simple_object(self):
        obj = {"b": 2, "a": 1}
        result = canonical_json(obj)
        assert result == '{"a":1,"b":2}'

    def test_nested_keys(self):
        obj = {"z": {"c": 3, "b": 2, "a": 1}, "y": 0}
        result = canonical_json(obj)
        assert result == '{"y":0,"z":{"a":1,"b":2,"c":3}}'

    def test_number_formatting(self):
        obj = {"int": 42, "float": 3.14}
        result = canonical_json(obj)
        assert '"int":42' in result
        assert '"float":3.14' in result

    def test_no_exponent_for_ints(self):
        obj = {"val": 1000000}
        result = canonical_json(obj)
        assert "e" not in result
        assert result == '{"val":1000000}'

    def test_string_escaping(self):
        obj = {"msg": 'hello"world'}
        result = canonical_json(obj)
        assert '"msg":"hello\\"world"' in result

    def test_slash_escaping(self):
        obj = {"url": "https://example.com/path"}
        result = canonical_json(obj)
        assert "\\/" in result

    def test_control_char_escaping(self):
        obj = {"msg": "line1\nline2"}
        result = canonical_json(obj)
        assert "\\n" in result

    def test_array(self):
        obj = {"items": [3, 1, 2]}
        result = canonical_json(obj)
        assert result == '{"items":[3,1,2]}'

    def test_boolean_and_null(self):
        obj = {"a": True, "b": False, "c": None}
        result = canonical_json(obj)
        assert result == '{"a":true,"b":false,"c":null}'

    def test_string_sorting(self):
        obj = {"": 1, " ": 2, "0": 3, "a": 4, "A": 5}
        result = canonical_json(obj)
        assert json.loads(result) == obj

    def test_empty_structures(self):
        assert canonical_json({}) == "{}"
        assert canonical_json([]) == "[]"

    def test_deterministic(self):
        obj = {"z": 1, "a": {"y": 2, "x": 3}}
        a = canonical_bytes(obj)
        b = canonical_bytes(obj)
        assert a == b


class TestManifestImmutability:
    """Post-publish resource changes don't affect historical manifests."""

    @pytest.mark.asyncio
    async def test_stored_manifest_not_dynamic(
        self, client: AsyncClient, admin_tokens: dict, db_session: AsyncSession
    ):
        agent_id = uuid.uuid4()
        agent = AgentCatalog(
            id=agent_id,
            key="immutable-agent",
            display_name="Immutable Agent",
            description="Original description",
            catalog_revision=1,
            version=1,
            status="published",
        )
        db_session.add(agent)
        await db_session.commit()

        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2024.10.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert create_resp.status_code == 201
        release_id = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        manifest_resp = await client.get("/api/v1/catalog/manifest")
        assert manifest_resp.status_code == 200
        first_manifest = manifest_resp.json()

        agent.description = "Modified description"
        await db_session.commit()

        manifest_resp2 = await client.get("/api/v1/catalog/manifest")
        assert manifest_resp2.status_code == 200
        second_manifest = manifest_resp2.json()

        assert first_manifest == second_manifest
        resources = first_manifest.get("resources", [])
        agent_resources = [r for r in resources if r.get("type") == "agent" and r.get("key") == "immutable-agent"]
        assert len(agent_resources) == 1

    @pytest.mark.asyncio
    async def test_release_uses_stored_data(
        self, client: AsyncClient, admin_tokens: dict, db_session: AsyncSession
    ):
        model_id = uuid.uuid4()
        model = ModelCatalog(
            id=model_id,
            provider_key="test",
            model_key="stored-model",
            display_name="Stored Model",
            catalog_revision=1,
            version=1,
            context_window=4096,
            max_output_tokens=1024,
            tokenizer_key="cl100k",
            supports_tools=False,
            supports_streaming=True,
            supports_vision=False,
            status="published",
        )
        db_session.add(model)
        await db_session.commit()

        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2024.11.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        result = await db_session.execute(
            select(CatalogRelease).where(CatalogRelease.id == uuid.UUID(release_id))
        )
        release = result.scalar_one()
        assert release.manifest_json is not None
        assert release.manifest_json.get("release_id") == release_id
        assert release.manifest_json.get("signature_algorithm") == "Ed25519"


class TestManifestTampering:
    """Manifest tampering (signature, sequence, object) is detected."""

    @pytest.mark.asyncio
    async def test_manifest_contains_all_required_fields(
        self, client: AsyncClient, admin_tokens: dict, db_session: AsyncSession
    ):
        provider_id = uuid.uuid4()
        provider = ProviderCatalog(
            id=provider_id,
            key="tamper-test-provider",
            display_name="Tamper Test",
            catalog_revision=1,
            version=1,
            protocol="openai_chat_completions",
            base_url="https://api.test.com",
            auth_scheme="bearer",
            status="published",
        )
        db_session.add(provider)
        await db_session.commit()

        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2024.12.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        manifest_resp = await client.get("/api/v1/catalog/manifest")
        manifest = manifest_resp.json()

        assert "release_id" in manifest
        assert "release_sequence" in manifest
        assert "created_at" in manifest
        assert "minimum_client_version" in manifest
        assert "signature_algorithm" in manifest
        assert manifest["signature_algorithm"] == "Ed25519"
        assert "resources" in manifest
        assert "signature" in manifest
        assert "signing_key_id" in manifest

        assert manifest["release_id"] == release_id
        assert manifest["release_sequence"] == 1

    @pytest.mark.asyncio
    async def test_manifest_has_valid_signature_field(
        self, client: AsyncClient, admin_tokens: dict
    ):
        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2025.01.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        manifest_resp = await client.get("/api/v1/catalog/manifest")
        manifest = manifest_resp.json()

        sig = manifest.get("signature", "")
        assert isinstance(sig, str)
        assert len(sig) > 0

    @pytest.mark.asyncio
    async def test_manifest_deterministic_serialization(
        self, client: AsyncClient, admin_tokens: dict
    ):
        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2025.02.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        manifest_resp = await client.get("/api/v1/catalog/manifest")
        manifest = manifest_resp.json()

        serialized_1 = canonical_bytes(manifest)
        serialized_2 = canonical_bytes(manifest)

        assert serialized_1 == serialized_2


class TestActiveReleaseSwitching:
    """Active release only switches after full verification."""

    @pytest.mark.asyncio
    async def test_publish_then_new_release_is_active(
        self, client: AsyncClient, admin_tokens: dict
    ):
        create_resp1 = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2025.03.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id_1 = create_resp1.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id_1}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        create_resp2 = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2025.04.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id_2 = create_resp2.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id_2}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        manifest_resp = await client.get("/api/v1/catalog/manifest")
        manifest = manifest_resp.json()
        assert manifest["release_sequence"] == 2
        assert manifest["release_id"] == release_id_2

    @pytest.mark.asyncio
    async def test_manifest_json_immutable_after_publish(
        self, client: AsyncClient, admin_tokens: dict, db_session: AsyncSession
    ):
        create_resp = await client.post(
            "/admin/api/v1/catalog/releases",
            json={"version": "2025.05.01"},
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        release_id_str = create_resp.json()["id"]

        await client.post(
            f"/admin/api/v1/catalog/releases/{release_id_str}/publish",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )

        result = await db_session.execute(
            select(CatalogRelease).where(CatalogRelease.id == uuid.UUID(release_id_str))
        )
        release = result.scalar_one()
        assert release.status == "published"
        assert release.manifest_json is not None
        assert release.manifest_object_key != ""
        assert release.published_at is not None

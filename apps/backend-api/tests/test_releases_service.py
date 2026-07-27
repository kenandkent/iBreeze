import base64
import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import AgentCatalog, ModelCatalog, ProviderCatalog
from ibreeze_backend.models.emergency_disable import EmergencyDisableRelease
from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.releases.bundle import (
    _freeze_agent,
    _freeze_model,
    _freeze_provider,
    _freeze_resource,
    _freeze_skill,
    _object_sha256,
    _resource_object_key,
    freeze_resources,
)
from ibreeze_backend.releases.emergency import (
    _next_sequence,
    create_emergency_disable,
    get_latest_emergency_disable,
)
from ibreeze_backend.releases.manifest import build_manifest, compute_manifest_signature, manifest_to_bytes


class TestObjectSha256:
    def test_sha256_of_bytes(self):
        data = b"hello"
        expected = hashlib.sha256(data).hexdigest()
        assert _object_sha256(data) == expected

    def test_sha256_empty(self):
        assert _object_sha256(b"") == hashlib.sha256(b"").hexdigest()


class TestResourceObjectKey:
    def test_agent_key(self):
        rid = uuid.uuid4()
        key = _resource_object_key("agent", rid, 3)
        assert key == f"catalog/releases/3/agents/{rid}.json"

    def test_model_key(self):
        rid = uuid.uuid4()
        key = _resource_object_key("model", rid, 1)
        assert key == f"catalog/releases/1/models/{rid}.json"

    def test_provider_key(self):
        rid = uuid.uuid4()
        key = _resource_object_key("provider", rid, 42)
        assert key == f"catalog/releases/42/providers/{rid}.json"

    def test_skill_key(self):
        rid = uuid.uuid4()
        key = _resource_object_key("skill", rid, 7)
        assert key == f"catalog/releases/7/skills/{rid}.json"


class TestFreezeResource:
    def test_freeze_resource_returns_expected_keys(self):
        payload = {"key": "test", "value": 123}
        result = _freeze_resource(payload)
        assert "object_key" in result
        assert "object_sha256" in result
        assert "size" in result
        assert result["object_key"] == ""
        assert isinstance(result["object_sha256"], str)
        assert result["size"] > 0

    def test_freeze_resource_deterministic(self):
        payload = {"b": 2, "a": 1}
        r1 = _freeze_resource(payload)
        r2 = _freeze_resource(payload)
        assert r1["object_sha256"] == r2["object_sha256"]
        assert r1["size"] == r2["size"]


class TestFreezeAgent:
    def test_freeze_agent_basic(self):
        agent = AgentCatalog(
            id=uuid.uuid4(),
            key="test-agent",
            display_name="Test Agent",
            description="An agent for testing",
            catalog_revision=2,
            version=3,
            status="published",
        )
        result = _freeze_agent(agent, 5)
        assert result["type"] == "agent"
        assert result["id"] == str(agent.id)
        assert result["key"] == "test-agent"
        assert result["catalog_revision"] == 2
        assert result["display_name"] == "Test Agent"
        assert result["version"] == 3
        assert "object_key" in result
        assert "object_sha256" in result
        assert "size" in result
        assert result["object_key"] == f"catalog/releases/5/agents/{agent.id}.json"

    def test_freeze_agent_object_key_format(self):
        agent = AgentCatalog(
            id=uuid.uuid4(),
            key="key-only",
            display_name="",
            description="",
            catalog_revision=1,
            version=1,
            status="published",
        )
        result = _freeze_agent(agent, 1)
        assert result["object_key"] == f"catalog/releases/1/agents/{agent.id}.json"


class TestFreezeModel:
    def test_freeze_model_basic(self):
        model = ModelCatalog(
            id=uuid.uuid4(),
            provider_key="test-provider",
            model_key="test-model",
            display_name="Test Model",
            context_window=8192,
            max_output_tokens=2048,
            tokenizer_key="cl100k",
            supports_tools=True,
            supports_streaming=True,
            supports_vision=False,
            catalog_revision=1,
            version=1,
            status="published",
        )
        result = _freeze_model(model, 2)
        assert result["type"] == "model"
        assert result["id"] == str(model.id)
        assert result["key"] == "test-provider/test-model"
        assert result["catalog_revision"] == 1
        assert result["display_name"] == "Test Model"
        assert result["version"] == 1
        assert result["object_key"] == f"catalog/releases/2/models/{model.id}.json"

    def test_freeze_model_booleans_included(self):
        model = ModelCatalog(
            id=uuid.uuid4(),
            provider_key="p",
            model_key="m",
            display_name="M",
            context_window=4096,
            max_output_tokens=1024,
            tokenizer_key="tk",
            supports_tools=False,
            supports_streaming=False,
            supports_vision=True,
            catalog_revision=1,
            version=1,
            status="published",
        )
        result = _freeze_model(model, 1)
        assert result["object_sha256"] != ""


class TestFreezeProvider:
    def test_freeze_provider_basic(self):
        provider = ProviderCatalog(
            id=uuid.uuid4(),
            key="test-provider",
            display_name="Test Provider",
            protocol="openai_chat_completions",
            base_url="https://api.test.com",
            auth_scheme="bearer",
            catalog_revision=1,
            version=2,
            status="published",
        )
        result = _freeze_provider(provider, 3)
        assert result["type"] == "provider"
        assert result["id"] == str(provider.id)
        assert result["key"] == "test-provider"
        assert result["catalog_revision"] == 1
        assert result["display_name"] == "Test Provider"
        assert result["version"] == 2
        assert result["object_key"] == f"catalog/releases/3/providers/{provider.id}.json"


class TestFreezeSkill:
    def test_freeze_skill_without_version(self):
        skill = Skill(
            id=uuid.uuid4(),
            key="test-skill",
            display_name="Test Skill",
            description="A test skill",
            catalog_revision=1,
            version=1,
            status="published",
        )
        result = _freeze_skill(skill, None, 4)
        assert result["type"] == "skill"
        assert result["id"] == str(skill.id)
        assert result["key"] == "test-skill"
        assert result["display_name"] == "Test Skill"
        assert result["catalog_revision"] == 1
        assert result["version"] == 1
        assert "content_sha256" not in result
        assert "skill_version_id" not in result
        assert "skill_version" not in result

    def test_freeze_skill_with_version(self):
        skill = Skill(
            id=uuid.uuid4(),
            key="test-skill-v",
            display_name="Test Skill V",
            description="With version",
            catalog_revision=2,
            version=3,
            status="published",
        )
        version = SkillVersion(
            id=uuid.uuid4(),
            skill_id=skill.id,
            version="1.0.0",
            manifest_json={},
            object_key="obj/key",
            object_size=100,
            object_sha256="abc",
            signature="sig",
            signing_key_id="kid",
            content_sha256="content_hash",
        )
        result = _freeze_skill(skill, version, 5)
        assert result["type"] == "skill"
        assert result["content_sha256"] == "content_hash"
        assert result["skill_version_id"] == str(version.id)
        assert result["skill_version"] == "1.0.0"

    def test_freeze_skill_key_default(self):
        skill = Skill(
            id=uuid.uuid4(),
            key="skill-key",
            display_name="SK",
            description="",
            catalog_revision=1,
            version=1,
            status="published",
        )
        result = _freeze_skill(skill, None, 10)
        assert result["object_key"] == f"catalog/releases/10/skills/{skill.id}.json"


class TestNextSequence:
    @pytest.mark.asyncio
    async def test_empty_db_returns_one(self, db_session: AsyncSession):
        seq = await _next_sequence(db_session)
        assert seq == 1

    @pytest.mark.asyncio
    async def test_returns_max_plus_one(self, db_session: AsyncSession, test_admin):
        uid = test_admin.id
        db_session.add(EmergencyDisableRelease(
            id=uuid.uuid4(),
            sequence=5,
            payload_json={"a": 1},
            payload_sha256="x",
            signature="y",
            signing_key_id="z",
            created_by=uid,
            created_at=datetime.now(UTC),
        ))
        db_session.add(EmergencyDisableRelease(
            id=uuid.uuid4(),
            sequence=3,
            payload_json={"b": 2},
            payload_sha256="x",
            signature="y",
            signing_key_id="z",
            created_by=uid,
            created_at=datetime.now(UTC),
        ))
        await db_session.flush()
        seq = await _next_sequence(db_session)
        assert seq == 6


class TestCreateEmergencyDisable:
    @pytest.mark.asyncio
    async def test_creates_record(self, db_session: AsyncSession, test_admin):
        uid = test_admin.id
        result = await create_emergency_disable(
            db_session,
            actor_user_id=uid,
            payload_json={"resource_type": "skill", "resource_id": str(uuid.uuid4())},
            payload_sha256="abc123",
            signature="signed",
            signing_key_id="kid1",
        )
        assert isinstance(result, EmergencyDisableRelease)
        assert result.sequence == 1
        assert result.payload_sha256 == "abc123"
        assert result.signature == "signed"
        assert result.signing_key_id == "kid1"
        assert result.created_by == uid
        assert result.created_at is not None

    @pytest.mark.asyncio
    async def test_increments_sequence(self, db_session: AsyncSession, test_admin):
        uid = test_admin.id
        r1 = await create_emergency_disable(
            db_session, actor_user_id=uid,
            payload_json={"x": 1}, payload_sha256="a",
            signature="s", signing_key_id="k",
        )
        r2 = await create_emergency_disable(
            db_session, actor_user_id=uid,
            payload_json={"x": 2}, payload_sha256="b",
            signature="s", signing_key_id="k",
        )
        assert r1.sequence == 1
        assert r2.sequence == 2


class TestGetLatestEmergencyDisable:
    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self, db_session: AsyncSession):
        result = await get_latest_emergency_disable(db_session)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_latest(self, db_session: AsyncSession, test_admin):
        uid = test_admin.id
        await create_emergency_disable(
            db_session, actor_user_id=uid,
            payload_json={"v": 1}, payload_sha256="a",
            signature="s", signing_key_id="k",
        )
        await create_emergency_disable(
            db_session, actor_user_id=uid,
            payload_json={"v": 2}, payload_sha256="b",
            signature="s", signing_key_id="k",
        )
        latest = await get_latest_emergency_disable(db_session)
        assert latest is not None
        assert latest.sequence == 2
        assert latest.payload_json == {"v": 2}


class TestBuildManifest:
    @pytest.mark.asyncio
    async def test_build_manifest_empty(self, db_session: AsyncSession):
        release_id = uuid.uuid4()
        manifest = await build_manifest(db_session, release_id, 1, "2025.01.01")
        assert manifest["release_id"] == str(release_id)
        assert manifest["release_sequence"] == 1
        assert manifest["minimum_client_version"] == "2025.01.01"
        assert manifest["signature_algorithm"] == "Ed25519"
        assert manifest["resources"] == []

    @pytest.mark.asyncio
    async def test_build_manifest_with_resources(self, db_session: AsyncSession):
        agent = AgentCatalog(
            id=uuid.uuid4(),
            key="manifest-agent",
            display_name="Manifest Agent",
            description="In manifest",
            catalog_revision=1,
            version=1,
            status="published",
        )
        db_session.add(agent)

        model = ModelCatalog(
            id=uuid.uuid4(),
            provider_key="mp",
            model_key="mm",
            display_name="Manifest Model",
            context_window=4096,
            max_output_tokens=1024,
            tokenizer_key="tk",
            supports_tools=False,
            supports_streaming=False,
            supports_vision=False,
            catalog_revision=1,
            version=1,
            status="published",
        )
        db_session.add(model)

        provider = ProviderCatalog(
            id=uuid.uuid4(),
            key="manifest-provider",
            display_name="Manifest Provider",
            protocol="openai_chat_completions",
            base_url="https://m.com",
            auth_scheme="bearer",
            catalog_revision=1,
            version=1,
            status="published",
        )
        db_session.add(provider)
        await db_session.flush()

        release_id = uuid.uuid4()
        manifest = await build_manifest(db_session, release_id, 2, "2025.06.01")
        assert len(manifest["resources"]) == 3
        resource_types = {r["type"] for r in manifest["resources"]}
        assert resource_types == {"agent", "model", "provider"}
        assert manifest["minimum_client_version"] == "2025.06.01"
        assert manifest["release_sequence"] == 2

    @pytest.mark.asyncio
    async def test_build_manifest_with_skill(self, db_session: AsyncSession):
        skill = Skill(
            id=uuid.uuid4(),
            key="manifest-skill",
            display_name="Manifest Skill",
            description="",
            catalog_revision=1,
            version=2,
            status="published",
        )
        db_session.add(skill)

        skill_ver = SkillVersion(
            id=uuid.uuid4(),
            skill_id=skill.id,
            version="2.0.0",
            manifest_json={},
            object_key="skills/test.json",
            object_size=200,
            object_sha256="abc123",
            signature="sig",
            signing_key_id="kid",
            content_sha256="content_hash_skill",
        )
        db_session.add(skill_ver)
        await db_session.flush()

        release_id = uuid.uuid4()
        manifest = await build_manifest(db_session, release_id, 3, "2025.07.01")
        skill_resources = [r for r in manifest["resources"] if r["type"] == "skill"]
        assert len(skill_resources) == 1
        sr = skill_resources[0]
        assert sr["key"] == "manifest-skill"
        assert sr["display_name"] == "Manifest Skill"
        assert sr["version"] == 2
        assert sr["content_sha256"] == "content_hash_skill"
        assert sr["skill_version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_created_at_default(self, db_session: AsyncSession):
        release_id = uuid.uuid4()
        manifest = await build_manifest(db_session, release_id, 1, "1.0")
        assert "created_at" in manifest
        assert manifest["created_at"].endswith("Z")

    @pytest.mark.asyncio
    async def test_created_at_custom(self, db_session: AsyncSession):
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        release_id = uuid.uuid4()
        manifest = await build_manifest(db_session, release_id, 1, "1.0", created_at=dt)
        assert manifest["created_at"] == "2025-01-15T10:30:00Z"


class TestComputeManifestSignature:
    def test_signature_is_base64(self):
        private_key = Ed25519PrivateKey.generate()
        data = b'{"hello":"world"}'
        sig = compute_manifest_signature(data, private_key)
        decoded = base64.b64decode(sig)
        assert len(decoded) == 64

    def test_signature_deterministic(self):
        private_key = Ed25519PrivateKey.generate()
        data = b"test data"
        sig1 = compute_manifest_signature(data, private_key)
        sig2 = compute_manifest_signature(data, private_key)
        assert sig1 == sig2

    def test_different_keys_produce_different_signatures(self):
        data = b"data"
        k1 = Ed25519PrivateKey.generate()
        k2 = Ed25519PrivateKey.generate()
        sig1 = compute_manifest_signature(data, k1)
        sig2 = compute_manifest_signature(data, k2)
        assert sig1 != sig2

    def test_different_data_different_signature(self):
        key = Ed25519PrivateKey.generate()
        sig1 = compute_manifest_signature(b"data1", key)
        sig2 = compute_manifest_signature(b"data2", key)
        assert sig1 != sig2

    def test_signature_verifiable(self):
        private_key = Ed25519PrivateKey.generate()
        data = b"verify me"
        sig_b64 = compute_manifest_signature(data, private_key)
        sig_bytes = base64.b64decode(sig_b64)
        public_key = private_key.public_key()
        public_key.verify(sig_bytes, data)


class TestManifestToBytes:
    def test_manifest_to_bytes_is_deterministic(self):
        m = {"z": 1, "a": 2}
        b1 = manifest_to_bytes(m)
        b2 = manifest_to_bytes(m)
        assert b1 == b2

    def test_manifest_to_bytes_canonical(self):
        m = {"b": 2, "a": 1}
        result = manifest_to_bytes(m)
        assert result == b'{"a":1,"b":2}'

    def test_manifest_to_bytes_empty(self):
        assert manifest_to_bytes({}) == b"{}"


class TestFreezeResourcesIntegration:
    @pytest.mark.asyncio
    async def test_freeze_resources_returns_all_published(self, db_session: AsyncSession):
        agent = AgentCatalog(
            id=uuid.uuid4(), key="fa-agent", display_name="FA", description="",
            catalog_revision=1, version=1, status="published",
        )
        db_session.add(agent)
        draft_agent = AgentCatalog(
            id=uuid.uuid4(), key="draft-agent", display_name="DA", description="",
            catalog_revision=1, version=1, status="draft",
        )
        db_session.add(draft_agent)
        await db_session.flush()

        resources = await freeze_resources(db_session, uuid.uuid4(), 1)
        agent_keys = [r["key"] for r in resources if r["type"] == "agent"]
        assert "fa-agent" in agent_keys
        assert "draft-agent" not in agent_keys

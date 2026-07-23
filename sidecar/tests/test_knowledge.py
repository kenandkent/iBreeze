"""Knowledge domain service tests."""
import pytest
from ibreeze.knowledge import (
    create_knowledge_entry,
    list_knowledge_entries,
    get_knowledge_entry,
    update_knowledge_entry,
    archive_knowledge_entry,
    search_knowledge_entries,
    get_knowledge_stats,
)
from ibreeze.schemas import (
    KnowledgeEntryUpdate,
    KnowledgeType,
    KnowledgeStatus,
)


def test_create_knowledge_entry():
    entry = create_knowledge_entry(title="Test FAQ", content="What is this?", type=KnowledgeType.FAQ)
    assert entry.title == "Test FAQ"
    assert entry.content == "What is this?"
    assert entry.type == KnowledgeType.FAQ
    assert entry.status == KnowledgeStatus.ACTIVE
    assert entry.version == 1
    assert entry.is_deleted is False
    assert entry.content_sha256 is not None


def test_create_knowledge_entry_with_tags():
    entry = create_knowledge_entry(
        title="Tagged Entry",
        content="Tagged content",
        type=KnowledgeType.DOC,
        tags=["guide", "setup"],
    )
    assert entry.tags == ["guide", "setup"]
    assert "guide" in entry.tags


def test_list_knowledge_entries():
    create_knowledge_entry(title="FAQ 1", content="Content 1", type=KnowledgeType.FAQ)
    create_knowledge_entry(title="DOC 1", content="Content 2", type=KnowledgeType.DOC)
    entries = list_knowledge_entries()
    assert len(entries) >= 2


def test_list_knowledge_entries_filter_by_type():
    create_knowledge_entry(title="URL Only", content="URL content", type=KnowledgeType.URL)
    urls = list_knowledge_entries(type=KnowledgeType.URL)
    assert all(e.type == KnowledgeType.URL for e in urls)


def test_get_knowledge_entry():
    entry = create_knowledge_entry(title="Get Test", content="Get content", type=KnowledgeType.FAQ)
    fetched = get_knowledge_entry(entry.id)
    assert fetched.id == entry.id
    assert fetched.title == "Get Test"


def test_get_knowledge_entry_not_found():
    with pytest.raises(KeyError):
        get_knowledge_entry("nonexistent-id")


def test_update_knowledge_entry():
    entry = create_knowledge_entry(title="Old Title", content="Old content", type=KnowledgeType.DOC)
    updated = update_knowledge_entry(entry.id, KnowledgeEntryUpdate(title="New Title"))
    assert updated.title == "New Title"
    assert updated.content == "Old content"
    assert updated.version == 1


def test_update_knowledge_entry_content_bumps_version():
    entry = create_knowledge_entry(title="Version Test", content="v1 content", type=KnowledgeType.DOC)
    updated = update_knowledge_entry(entry.id, KnowledgeEntryUpdate(content="v2 content"))
    assert updated.version == 2
    assert updated.content_sha256 != entry.content_sha256


def test_delete_knowledge_entry():
    entry = create_knowledge_entry(title="To Archive", content="Archive me", type=KnowledgeType.FAQ)
    archived = archive_knowledge_entry(entry.id)
    assert archived.status == KnowledgeStatus.ARCHIVED


def test_search_knowledge():
    create_knowledge_entry(title="Python Guide", content="Learn Python", type=KnowledgeType.DOC)
    create_knowledge_entry(title="JAVA Guide", content="Learn Java", type=KnowledgeType.DOC)
    results = search_knowledge_entries("Python")
    assert len(results) >= 1
    assert any("Python" in r.title for r in results)


def test_search_knowledge_by_content():
    create_knowledge_entry(title="Unique", content="very specific query term", type=KnowledgeType.FAQ)
    results = search_knowledge_entries("specific query")
    assert len(results) >= 1


def test_get_knowledge_stats():
    create_knowledge_entry(title="Stats FAQ", content="Stats content", type=KnowledgeType.FAQ, tags=["tag1"])
    create_knowledge_entry(title="Stats DOC", content="More stats", type=KnowledgeType.DOC, tags=["tag1", "tag2"])
    stats = get_knowledge_stats()
    assert stats.total >= 2
    assert stats.active >= 2
    assert stats.by_type.get("FAQ", 0) >= 1
    assert stats.by_type.get("DOC", 0) >= 1
    assert stats.by_tag.get("tag1", 0) >= 2


def test_create_duplicate_content_hash():
    content = "Same content different types"
    faq_entry = create_knowledge_entry(title="FAQ Version", content=content, type=KnowledgeType.FAQ)
    url_entry = create_knowledge_entry(title="URL Version", content=content, type=KnowledgeType.URL)
    assert faq_entry.content_sha256 == url_entry.content_sha256
    assert faq_entry.id != url_entry.id


def test_create_duplicate_content_same_type_raises():
    content = "Duplicate same type content"
    create_knowledge_entry(title="First", content=content, type=KnowledgeType.DOC)
    with pytest.raises(ValueError, match="内容重复"):
        create_knowledge_entry(title="Second", content=content, type=KnowledgeType.DOC)

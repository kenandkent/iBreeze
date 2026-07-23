"""Conversation domain service tests."""
import pytest
from ibreeze.conversation import (
    create_conversation,
    list_conversations,
    get_conversation,
    update_conversation,
    delete_conversation,
    archive_conversation,
    add_message,
    list_messages,
    delete_message,
    search_conversations,
)
from ibreeze.schemas import (
    ConversationCreate,
    ConversationStatus,
    ConversationUpdate,
    MessageCreate,
    MessageRole,
)


@pytest.fixture
def sample_conversation():
    """Create a sample conversation."""
    return create_conversation("company-123", title="Test Conversation")


def test_create_conversation():
    """Test creating a conversation."""
    conv = create_conversation("company-123", title="Test Conv")
    assert conv.company_id == "company-123"
    assert conv.title == "Test Conv"
    assert conv.status == ConversationStatus.ACTIVE
    assert conv.is_deleted is False


def test_list_conversations():
    """Test listing conversations."""
    create_conversation("company-123", title="Conv 1")
    create_conversation("company-123", title="Conv 2")
    convs = list_conversations("company-123")
    assert len(convs) >= 2


def test_get_conversation(sample_conversation):
    """Test getting a conversation by ID."""
    fetched = get_conversation(sample_conversation.id)
    assert fetched.id == sample_conversation.id
    assert fetched.title == "Test Conversation"


def test_get_conversation_not_found():
    """Test getting a non-existent conversation."""
    with pytest.raises(KeyError):
        get_conversation("nonexistent-id")


def test_update_conversation(sample_conversation):
    """Test updating a conversation."""
    update_data = ConversationUpdate(title="Updated Title")
    updated = update_conversation(sample_conversation.id, update_data)
    assert updated.title == "Updated Title"


def test_delete_conversation(sample_conversation):
    """Test soft deleting a conversation."""
    delete_conversation(sample_conversation.id)
    with pytest.raises(KeyError):
        get_conversation(sample_conversation.id)


def test_archive_conversation(sample_conversation):
    """Test archiving a conversation."""
    archived = archive_conversation(sample_conversation.id)
    assert archived.status == ConversationStatus.ARCHIVED


def test_update_archived_conversation_fails(sample_conversation):
    """Test that archived conversation cannot be modified."""
    archive_conversation(sample_conversation.id)
    with pytest.raises(ValueError, match="已归档的对话不可修改"):
        update_conversation(
            sample_conversation.id,
            ConversationUpdate(title="New Title"),
        )


def test_add_message(sample_conversation):
    """Test adding a message to a conversation."""
    msg = add_message(
        sample_conversation.id,
        MessageRole.USER,
        "Hello world",
    )
    assert msg.content == "Hello world"
    assert msg.role == MessageRole.USER
    assert msg.conversation_id == sample_conversation.id


def test_add_message_to_archived_conversation_fails(sample_conversation):
    """Test that message cannot be added to archived conversation."""
    archive_conversation(sample_conversation.id)
    with pytest.raises(ValueError, match="已归档的对话不可添加消息"):
        add_message(
            sample_conversation.id,
            MessageRole.USER,
            "Hello",
        )


def test_list_messages(sample_conversation):
    """Test listing messages in a conversation."""
    add_message(sample_conversation.id, MessageRole.USER, "Msg 1")
    add_message(sample_conversation.id, MessageRole.ASSISTANT, "Msg 2")
    messages = list_messages(sample_conversation.id)
    assert len(messages) == 2


def test_delete_message(sample_conversation):
    """Test soft deleting a message."""
    msg = add_message(sample_conversation.id, MessageRole.USER, "To delete")
    delete_message(msg.id)
    messages = list_messages(sample_conversation.id)
    assert len(messages) == 0


def test_search_conversations(sample_conversation):
    """Test searching conversations by title."""
    results = search_conversations("company-123", "Test Conversation")
    assert len(results) >= 1
    assert any(r.title == "Test Conversation" for r in results)


def test_search_conversations_by_message():
    """Test searching conversations by message content."""
    conv = create_conversation("company-123", title="Search Test")
    add_message(conv.id, MessageRole.USER, "Unique search term XYZ")
    results = search_conversations("company-123", "XYZ")
    assert len(results) >= 1


def test_conversation_extra_fields_forbidden():
    """Test that extra fields are forbidden."""
    from ibreeze.schemas import StrictModel
    from pydantic import ValidationError

    class TestModel(StrictModel):
        name: str

    with pytest.raises(ValidationError):
        TestModel(name="test", extra_field="not allowed")

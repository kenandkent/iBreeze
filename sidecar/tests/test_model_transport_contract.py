from ibreeze.runtime.transport import _build_provider_request


def test_anthropic_tool_schema_is_complete():
    request = _build_provider_request("anthropic_messages", (), ("read_file",))
    tool = request["tools"][0]
    assert tool["input_schema"]["properties"]["path"]["type"] == "string"
    assert tool["input_schema"]["required"] == ["path"]


def test_responses_tool_schema_is_complete():
    request = _build_provider_request("openai_responses", (), ("search_text",))
    tool = request["tools"][0]
    assert tool["parameters"]["properties"]["query"]["type"] == "string"
    assert tool["parameters"]["additionalProperties"] is False


def test_proposer_tool_schema_is_explicitly_non_executable():
    request = _build_provider_request("openai_chat_completions", (), ("read_file",), tools_are_suggestions=True)
    assert "Non-executable" in request["tools"][0]["function"]["description"]

from __future__ import annotations

from ibreeze.artifacts.diff import (
    MAX_DIFF_SIZE,
    generate_text_diff,
    is_text_content,
    should_generate_diff,
)


class TestGenerateTextDiff:
    def test_empty_content(self):
        result = generate_text_diff("", "")
        assert result["diff"] == ""
        assert result["line_count"] == 0
        assert result["needs_separate_artifact"] is False

    def test_same_content(self):
        result = generate_text_diff("hello\nworld\n", "hello\nworld\n")
        assert result["line_count"] >= 0

    def test_different_content(self):
        result = generate_text_diff("hello\n", "hello world\n")
        assert len(result["diff"]) > 0

    def test_with_filename(self):
        result = generate_text_diff("a\n", "b\n", filename="test.txt")
        assert "a/test.txt" in result["diff"]
        assert "b/test.txt" in result["diff"]

    def test_custom_context_lines(self):
        old = "\n".join(f"line {i}" for i in range(10))
        new = "\n".join(f"line {i}" for i in range(10) if i != 5)
        result = generate_text_diff(old, new, context_lines=1)
        assert result["line_count"] > 0

    def test_large_diff_triggers_separate_artifact(self):
        big_old = "x\n" * 1000000
        big_new = "y\n" * 1000000
        result = generate_text_diff(big_old, big_new)
        assert result["needs_separate_artifact"] is True


class TestIsTextContent:
    def test_text_content(self):
        assert is_text_content(b"hello world") is True

    def test_utf8_content(self):
        assert is_text_content("你好世界".encode()) is True

    def test_binary_content(self):
        assert is_text_content(b"\x00\x01\x02\xff") is False


class TestShouldGenerateDiff:
    def test_small_text(self):
        data = b"hello world"
        assert should_generate_diff(data) is True

    def test_small_binary(self):
        data = b"\x00\x01\x02\xff"
        assert should_generate_diff(data) is False

    def test_large_text_exceeds_max(self):
        data = b"x" * (MAX_DIFF_SIZE + 1)
        assert should_generate_diff(data) is False

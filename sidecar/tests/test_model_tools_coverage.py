"""Coverage tests for ibreeze/runtime/model_tools.py (uncovered branches)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ibreeze.runtime.model_tools import (
    MAX_FILE_BYTES,
    MAX_LIST_ENTRIES,
    ModelToolContext,
    _bounded_limit,
    _contains_symlink,
    build_model_tools,
    list_files,
    read_file,
    search_text,
)


@pytest.fixture
def ctx(tmp_path: Path) -> ModelToolContext:
    return ModelToolContext(tmp_path, "task_execution")


class TestRelativeArg:
    @pytest.mark.asyncio
    async def test_read_file_requires_path(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_REQUIRED"):
            await read_file(ctx, {})

    @pytest.mark.asyncio
    async def test_read_file_requires_string_path(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_REQUIRED"):
            await read_file(ctx, {"path": 123})

    @pytest.mark.asyncio
    async def test_read_file_requires_non_blank_path(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_REQUIRED"):
            await read_file(ctx, {"path": "   "})


class TestResolveReadPath:
    @pytest.mark.asyncio
    async def test_absolute_path_outside_workspace(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_OUTSIDE_WORKSPACE"):
            await read_file(ctx, {"path": "/etc/hosts"})

    @pytest.mark.asyncio
    async def test_absolute_path_inside_workspace(self, ctx, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
        result = await read_file(ctx, {"path": str(tmp_path / "a.txt")})
        assert result["content"] == "hi"

    @pytest.mark.asyncio
    async def test_absolute_path_with_dotdot_jumping_out(self, ctx, tmp_path) -> None:
        # An absolute path that lexically stays under the root but resolves
        # outside (via "..") must be rejected after resolution.
        (tmp_path / "inside").mkdir()
        outside = tmp_path.parent / "model-tools-outside.txt"
        outside.write_text("secret", encoding="utf-8")
        candidate = tmp_path / "inside" / ".." / ".." / outside.name
        with pytest.raises(ValueError, match="TOOL_PATH_OUTSIDE_WORKSPACE"):
            await read_file(ctx, {"path": str(candidate)})
        outside.unlink()


class TestContainsSymlink:
    def test_path_outside_root_is_symlink(self, ctx, tmp_path) -> None:
        assert _contains_symlink(tmp_path, tmp_path.parent / "elsewhere") is True

    def test_relative_child_is_not_symlink(self, ctx, tmp_path) -> None:
        (tmp_path / "plain.txt").write_text("x", encoding="utf-8")
        assert _contains_symlink(tmp_path, tmp_path / "plain.txt") is False


class TestBoundedLimit:
    def test_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            _bounded_limit({"limit": 0}, "limit", 200, MAX_LIST_ENTRIES)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            _bounded_limit({"limit": -3}, "limit", 200, MAX_LIST_ENTRIES)

    def test_non_int_rejected(self) -> None:
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            _bounded_limit({"limit": "x"}, "limit", 200, MAX_LIST_ENTRIES)

    def test_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            _bounded_limit({"limit": True}, "limit", 200, MAX_LIST_ENTRIES)


class TestReadFileBranches:
    @pytest.mark.asyncio
    async def test_directory_is_not_a_file(self, ctx, tmp_path) -> None:
        (tmp_path / "dir").mkdir()
        with pytest.raises(ValueError, match="TOOL_FILE_REQUIRED"):
            await read_file(ctx, {"path": "dir"})

    @pytest.mark.asyncio
    async def test_negative_offset(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_RANGE_INVALID"):
            await read_file(ctx, {"path": "f.txt", "offset": -1})

    @pytest.mark.asyncio
    async def test_zero_length(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_RANGE_INVALID"):
            await read_file(ctx, {"path": "f.txt", "length": 0})

    @pytest.mark.asyncio
    async def test_length_above_max(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_RANGE_INVALID"):
            await read_file(ctx, {"path": "f.txt", "length": MAX_FILE_BYTES + 1})

    @pytest.mark.asyncio
    async def test_bool_offset(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_RANGE_INVALID"):
            await read_file(ctx, {"path": "f.txt", "offset": True})

    @pytest.mark.asyncio
    async def test_offset_beyond_size(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_RANGE_INVALID"):
            await read_file(ctx, {"path": "f.txt", "offset": 100})

    @pytest.mark.asyncio
    async def test_offset_at_size(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("0123456789", encoding="utf-8")
        result = await read_file(ctx, {"path": "f.txt", "offset": 10})
        assert result["content"] == ""
        assert result["size"] == 0


class TestListFilesBranches:
    @pytest.mark.asyncio
    async def test_happy_path(self, ctx, tmp_path) -> None:
        (tmp_path / "b.txt").write_text("bbb", encoding="utf-8")
        (tmp_path / "a.txt").write_text("aaa", encoding="utf-8")
        result = await list_files(ctx, {"path": "."})
        assert [item["path"] for item in result["items"]] == ["a.txt", "b.txt"]
        assert result["truncated"] is False
        assert result["items"][0]["size"] == 3

    @pytest.mark.asyncio
    async def test_non_string_path(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_INVALID"):
            await list_files(ctx, {"path": 5})

    @pytest.mark.asyncio
    async def test_path_is_file_not_directory(self, ctx, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_DIRECTORY_REQUIRED"):
            await list_files(ctx, {"path": "a.txt"})

    @pytest.mark.asyncio
    async def test_empty_pattern(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATTERN_INVALID"):
            await list_files(ctx, {"path": ".", "pattern": ""})

    @pytest.mark.asyncio
    async def test_parent_pattern(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATTERN_INVALID"):
            await list_files(ctx, {"path": ".", "pattern": ".."})

    @pytest.mark.asyncio
    async def test_non_string_pattern(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATTERN_INVALID"):
            await list_files(ctx, {"path": ".", "pattern": 42})

    @pytest.mark.asyncio
    async def test_invalid_limit(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            await list_files(ctx, {"path": ".", "limit": 0})

    @pytest.mark.asyncio
    async def test_skips_symlinks_and_directories(self, ctx, tmp_path) -> None:
        (tmp_path / "keep.txt").write_text("keep", encoding="utf-8")
        (tmp_path / "dir").mkdir()
        outside = tmp_path.parent / "model-tools-list-outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (tmp_path / "alias.txt").symlink_to(outside)
        result = await list_files(ctx, {"path": "."})
        assert [item["path"] for item in result["items"]] == ["keep.txt"]
        outside.unlink()

    @pytest.mark.asyncio
    async def test_truncated_when_limit_reached(self, ctx, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        result = await list_files(ctx, {"path": ".", "limit": 1})
        assert result["truncated"] is True
        assert len(result["items"]) == 1


class TestSearchTextBranches:
    @pytest.mark.asyncio
    async def test_empty_query(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_QUERY_INVALID"):
            await search_text(ctx, {"query": ""})

    @pytest.mark.asyncio
    async def test_non_string_query(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_QUERY_INVALID"):
            await search_text(ctx, {"query": 42})

    @pytest.mark.asyncio
    async def test_oversized_query(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_QUERY_INVALID"):
            await search_text(ctx, {"query": "q" * 257})

    @pytest.mark.asyncio
    async def test_non_string_path(self, ctx) -> None:
        with pytest.raises(ValueError, match="TOOL_PATH_INVALID"):
            await search_text(ctx, {"query": "needle", "path": 5})

    @pytest.mark.asyncio
    async def test_path_is_file(self, ctx, tmp_path) -> None:
        (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_DIRECTORY_REQUIRED"):
            await search_text(ctx, {"query": "needle", "path": "a.txt"})

    @pytest.mark.asyncio
    async def test_query_matches_some_lines_only(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("first line\nneedle here\nlast line\n", encoding="utf-8")
        result = await search_text(ctx, {"query": "needle"})
        assert len(result["items"]) == 1
        assert result["items"][0]["line"] == 2
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_truncated_when_max_results_reached(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("needle\nneedle\nneedle\n", encoding="utf-8")
        result = await search_text(ctx, {"query": "needle", "max_results": 1})
        assert result["truncated"] is True
        assert len(result["items"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_max_results(self, ctx, tmp_path) -> None:
        (tmp_path / "f.txt").write_text("needle", encoding="utf-8")
        with pytest.raises(ValueError, match="TOOL_LIMIT_INVALID"):
            await search_text(ctx, {"query": "needle", "max_results": 0})


def test_build_model_tools_registers_fixed_tools(ctx) -> None:
    tools = build_model_tools(ctx)
    assert set(tools) == {"read_file", "list_files", "search_text"}
    assert callable(tools["read_file"])
    assert callable(tools["list_files"])
    assert callable(tools["search_text"])

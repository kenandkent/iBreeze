from pathlib import Path

import pytest

from ibreeze.runtime.model_tools import ModelToolContext, read_file, search_text


@pytest.mark.asyncio
async def test_read_file_supports_bounded_ranges(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text("0123456789", encoding="utf-8")
    result = await read_file(ModelToolContext(tmp_path, "task_execution"), {"path": "sample.txt", "offset": 2, "length": 4})
    assert result["content"] == "2345"
    assert result["offset"] == 2
    assert result["size"] == 4


@pytest.mark.asyncio
async def test_read_file_rejects_parent_and_symlink(tmp_path: Path):
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "link.txt").symlink_to(tmp_path / "outside.txt")
    context = ModelToolContext(tmp_path, "task_execution")
    with pytest.raises(ValueError, match="TOOL_PATH_OUTSIDE_WORKSPACE"):
        await read_file(context, {"path": "../outside.txt"})
    with pytest.raises(ValueError, match="TOOL_SYMLINK_NOT_ALLOWED"):
        await read_file(context, {"path": "link.txt"})


@pytest.mark.asyncio
async def test_search_text_skips_symlinked_files(tmp_path: Path):
    (tmp_path / "real.txt").write_text("needle", encoding="utf-8")
    outside = tmp_path.parent / "model-tools-outside.txt"
    outside.write_text("needle", encoding="utf-8")
    (tmp_path / "alias.txt").symlink_to(outside)
    result = await search_text(ModelToolContext(tmp_path, "task_execution"), {"query": "needle"})
    assert [item["path"] for item in result["items"]] == ["real.txt"]
    outside.unlink()

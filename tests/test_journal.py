"""需求 3 的测试：操作日志与撤销。"""

from __future__ import annotations

from pathlib import Path

from homework_archiver import journal


def _make(folder: Path, rel: str, content: bytes = b"x") -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_save_and_load_roundtrip(tmp_path: Path):
    moves = [journal.Move(src="a.pdf", dst="b.pdf")]

    path = journal.save_operation(tmp_path, "rename", moves)

    assert path is not None
    assert path.exists()
    op, loaded_path = journal.load_latest(tmp_path)
    assert op is not None and loaded_path == path
    assert op.kind == "rename"
    assert op.moves == moves


def test_save_nothing_when_no_moves(tmp_path: Path):
    assert journal.save_operation(tmp_path, "rename", []) is None
    op, _ = journal.load_latest(tmp_path)
    assert op is None


def test_load_latest_without_logs(tmp_path: Path):
    op, path = journal.load_latest(tmp_path)
    assert op is None and path is None


def test_undo_rename_restores_file(tmp_path: Path):
    _make(tmp_path, "新名字_1.pdf")
    journal.save_operation(
        tmp_path, "rename", [journal.Move(src="原名_1.pdf", dst="新名字_1.pdf")]
    )

    result = journal.undo_last(tmp_path)

    assert result.kind == "rename"
    assert (tmp_path / "原名_1.pdf").exists()
    assert not (tmp_path / "新名字_1.pdf").exists()
    assert result.restored_count == 1
    # 成功撤销后日志被删除，不能重复撤销
    assert journal.load_latest(tmp_path)[0] is None


def test_undo_archive_reverse_order_and_subdirs(tmp_path: Path):
    _make(tmp_path, "2026年春季学期/a.pdf")
    _make(tmp_path, "2025年秋季学期/b.pdf")
    journal.save_operation(
        tmp_path,
        "archive",
        [
            journal.Move(src="a.pdf", dst="2026年春季学期/a.pdf"),
            journal.Move(src="b.pdf", dst="2025年秋季学期/b.pdf"),
        ],
    )

    result = journal.undo_last(tmp_path)

    assert result.skipped == []
    assert (tmp_path / "a.pdf").exists()
    assert (tmp_path / "b.pdf").exists()
    assert not (tmp_path / "2026年春季学期/a.pdf").exists()


def test_undo_skips_when_destination_missing(tmp_path: Path):
    # 日志说移动过，但文件已不在目标位置
    journal.save_operation(
        tmp_path, "rename", [journal.Move(src="a.pdf", dst="b.pdf")]
    )

    result = journal.undo_last(tmp_path)

    assert result.restored == []
    assert result.skipped[0][0] == "b.pdf"
    assert "不在" in result.skipped[0][1]
    # 有失败项，日志保留
    assert journal.load_latest(tmp_path)[0] is not None


def test_undo_never_overwrites_existing_original(tmp_path: Path):
    _make(tmp_path, "b.pdf", b"moved")
    _make(tmp_path, "a.pdf", b"original")  # 原位置已被别的文件占用
    journal.save_operation(
        tmp_path, "rename", [journal.Move(src="a.pdf", dst="b.pdf")]
    )

    result = journal.undo_last(tmp_path)

    assert result.restored == []
    assert "已有文件" in result.skipped[0][1]
    assert (tmp_path / "a.pdf").read_bytes() == b"original"
    assert (tmp_path / "b.pdf").read_bytes() == b"moved"


def test_undo_uses_latest_log(tmp_path: Path):
    _make(tmp_path, "b.pdf")
    journal.save_operation(tmp_path, "rename", [journal.Move("a.pdf", "b.pdf")])
    # 第一次撤销成功（日志删除），再做第二次操作
    assert journal.undo_last(tmp_path).restored_count == 1
    _make(tmp_path, "c.pdf")
    journal.save_operation(tmp_path, "rename", [journal.Move("a.pdf", "c.pdf")])

    op, _ = journal.load_latest(tmp_path)
    assert op is not None
    assert op.moves == [journal.Move("a.pdf", "c.pdf")]

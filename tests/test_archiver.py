"""需求 3 的测试：按学期归档与整理报告。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from homework_archiver import archiver, journal, scanner


def _touch(folder: Path, name: str, when: datetime | None = None) -> Path:
    path = folder / name
    path.write_bytes(b"x")
    if when is not None:
        ts = when.timestamp()
        os.utime(path, (ts, ts))
    return path


def _find(items: list[archiver.ArchiveItem], name: str) -> archiver.ArchiveItem:
    for item in items:
        if item.source.name == name:
            return item
    raise AssertionError(f"计划中找不到 {name}")


# ---------- 学期推断 ----------

@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2025, 9, 1), "2025年秋季学期"),
        (datetime(2025, 12, 31), "2025年秋季学期"),
        (datetime(2026, 1, 15), "2025年秋季学期"),
        (datetime(2026, 2, 1), "2026年春季学期"),
        (datetime(2026, 6, 30), "2026年春季学期"),
        (datetime(2026, 7, 1), "2026年暑期"),
        (datetime(2026, 8, 31), "2026年暑期"),
    ],
)
def test_term_for_date(moment: datetime, expected: str):
    assert archiver.term_for_date(moment) == expected


def test_category_by_extension(tmp_path: Path):
    assert archiver.category_for_file(tmp_path / "a.PDF", archiver.EXT) == "PDF"
    assert archiver.category_for_file(tmp_path / "noext", archiver.EXT) == "无扩展名"


# ---------- 归档计划 ----------

def test_plan_archive_by_term_uses_mtime(tmp_path: Path):
    _touch(tmp_path, "作业.pdf", datetime(2025, 10, 5))

    item = _find(archiver.plan_archive(tmp_path), "作业.pdf")

    assert not item.skipped
    assert item.target_rel == "2025年秋季学期/作业.pdf"


def test_plan_archive_by_ext(tmp_path: Path):
    _touch(tmp_path, "论文.docx")

    item = _find(archiver.plan_archive(tmp_path, by=archiver.EXT), "论文.docx")

    assert item.target_rel == "DOCX/论文.docx"


def test_plan_archive_skips_existing_target(tmp_path: Path):
    _touch(tmp_path, "作业.pdf", datetime(2025, 10, 5))
    _touch(tmp_path, "2025年秋季学期/作业.pdf")

    item = _find(archiver.plan_archive(tmp_path), "作业.pdf")

    assert item.skipped
    assert "已存在" in (item.reason or "")


def test_plan_archive_empty_folder(tmp_path: Path):
    assert archiver.plan_archive(tmp_path) == []


def test_plan_archive_rejects_bad_mode(tmp_path: Path):
    with pytest.raises(ValueError):
        archiver.plan_archive(tmp_path, by="classroom")


# ---------- 执行、日志、报告 ----------

def test_apply_archive_moves_files_and_writes_journal(tmp_path: Path):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 10))
    _touch(tmp_path, "b.pdf", datetime(2025, 11, 2))

    result, journal_path = archiver.apply_archive(tmp_path, archiver.plan_archive(tmp_path))

    assert result.moved_count == 2
    assert (tmp_path / "2026年春季学期/a.pdf").exists()
    assert (tmp_path / "2025年秋季学期/b.pdf").exists()
    assert not (tmp_path / "a.pdf").exists()
    op, _ = journal.load_latest(tmp_path)
    assert op is not None and op.kind == "archive" and len(op.moves) == 2
    assert journal_path is not None


def test_apply_archive_no_moves_writes_no_journal(tmp_path: Path):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 10))
    _touch(tmp_path, "2026年春季学期/a.pdf")  # 目标已存在 → 全部跳过

    result, journal_path = archiver.apply_archive(tmp_path, archiver.plan_archive(tmp_path))

    assert result.moved_count == 0
    assert result.skipped_count == 1
    assert journal_path is None


def test_apply_archive_then_undo_restores(tmp_path: Path):
    _touch(tmp_path, "a.pdf", datetime(2026, 7, 20))
    result, _ = archiver.apply_archive(tmp_path, archiver.plan_archive(tmp_path))
    assert result.moved_count == 1
    assert (tmp_path / "2026年暑期/a.pdf").exists()

    undo = journal.undo_last(tmp_path)

    assert undo.restored_count == 1
    assert (tmp_path / "a.pdf").exists()
    assert not (tmp_path / "2026年暑期/a.pdf").exists()


def test_format_report_contains_counts_and_reasons(tmp_path: Path):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 1))
    _touch(tmp_path, "2026年春季学期/b.pdf") if False else None
    result, jp = archiver.apply_archive(tmp_path, archiver.plan_archive(tmp_path))

    text = archiver.format_report(result, jp)

    assert "处理（移动）：1 个" in text
    assert "跳过：0 个" in text
    assert "undo" in text


def test_save_report_creates_file(tmp_path: Path):
    path = archiver.save_report(tmp_path, "测试报告\n")
    assert path.exists()
    assert "测试报告" in path.read_text(encoding="utf-8")


def test_recursive_scan_ignores_internal_dir(tmp_path: Path):
    _touch(tmp_path, "a.pdf")
    log_dir = tmp_path / ".homework_archiver" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "op.json").write_text("{}", encoding="utf-8")

    infos = scanner.scan_folder(tmp_path, recursive=True)

    assert [info.name for info in infos] == ["a.pdf"]

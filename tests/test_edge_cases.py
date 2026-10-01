"""深度边界测试（先在调试分支云端验证，通过后回填功能分支）。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from homework_archiver import archiver, journal, renamer, scanner


def test_swap_rename_without_data_loss(tmp_path: Path):
    # 两个文件互相换成对方的名字：不能丢数据、不能误覆盖
    (tmp_path / "1_x_2.pdf").write_bytes(b"one")
    (tmp_path / "2_y_1.pdf").write_bytes(b"two")

    result = renamer.apply_renames(tmp_path, renamer.plan_renames(tmp_path))

    assert result.renamed_count == 2
    assert (tmp_path / "2_1.pdf").read_bytes() == b"one"
    assert (tmp_path / "1_2.pdf").read_bytes() == b"two"


def test_batch_collision_leaves_both_untouched(tmp_path: Path):
    (tmp_path / "2026001_赵六_作业.pdf").write_bytes(b"a")
    (tmp_path / "2026001_钱七_作业.pdf").write_bytes(b"b")

    result = renamer.apply_renames(tmp_path, renamer.plan_renames(tmp_path))

    assert result.renamed_count == 0
    assert (tmp_path / "2026001_赵六_作业.pdf").read_bytes() == b"a"
    assert (tmp_path / "2026001_钱七_作业.pdf").read_bytes() == b"b"


def test_undo_retry_after_blocker_cleared(tmp_path: Path):
    (tmp_path / "b.pdf").write_bytes(b"moved")
    (tmp_path / "a.pdf").write_bytes(b"blocker")  # 原位置被占
    journal.save_operation(tmp_path, "rename", [journal.Move("a.pdf", "b.pdf")])

    first = journal.undo_last(tmp_path)
    assert first.restored_count == 0
    assert first.skipped_count == 1
    assert journal.load_latest(tmp_path)[0] is not None  # 日志保留

    (tmp_path / "a.pdf").unlink()  # 阻塞解除
    second = journal.undo_last(tmp_path)
    assert second.restored_count == 1
    assert (tmp_path / "a.pdf").read_bytes() == b"moved"
    assert journal.load_latest(tmp_path)[0] is None      # 成功后日志删除


def test_journal_payload_shape(tmp_path: Path):
    path = journal.save_operation(tmp_path, "archive", [journal.Move("a.pdf", "d/a.pdf")])
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["kind"] == "archive"
    assert "timestamp" in data
    assert data["moves"] == [{"src": "a.pdf", "dst": "d/a.pdf"}]


def test_archive_leaves_first_level_empty(tmp_path: Path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x")
    ts = datetime(2025, 10, 15).timestamp()
    os.utime(f, (ts, ts))

    result, _ = archiver.apply_archive(tmp_path, archiver.plan_archive(tmp_path))

    assert result.moved_count == 1
    assert scanner.scan_folder(tmp_path) == []


def test_archive_by_ext_for_file_without_extension(tmp_path: Path):
    (tmp_path / "LICENSE").write_bytes(b"x")

    items = archiver.plan_archive(tmp_path, by=archiver.EXT)

    assert items[0].target_rel == "无扩展名/LICENSE"


def test_human_size_large_units():
    assert scanner.human_size(1024 ** 3).endswith("GB")
    assert scanner.human_size(1024 ** 4).endswith("TB")

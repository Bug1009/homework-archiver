"""需求 3 的端到端测试：archive / undo / 改名后可撤销。"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest

from homework_archiver import journal
from homework_archiver.cli import main


def _touch(folder: Path, name: str, when: datetime | None = None) -> Path:
    path = folder / name
    path.write_bytes(b"x")
    if when is not None:
        ts = when.timestamp()
        os.utime(path, (ts, ts))
    return path


def test_cli_archive_preview_does_not_touch_disk(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _touch(tmp_path, "a.pdf", datetime(2025, 10, 1))

    code = main(["archive", str(tmp_path)])

    assert code == 0
    out = capsys.readouterr().out
    assert "归档计划预览" in out
    assert "2025年秋季学期/a.pdf" in out
    assert (tmp_path / "a.pdf").exists()  # 未移动


def test_cli_archive_apply_moves_and_writes_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 1))

    code = main(["archive", str(tmp_path), "--apply", "--yes"])

    assert code == 0
    out = capsys.readouterr().out
    assert "整理报告" in out
    assert "处理（移动）：1 个" in out
    assert (tmp_path / "2026年春季学期/a.pdf").exists()
    # 报告文件落盘
    reports = list((tmp_path / ".homework_archiver/reports").glob("*.txt"))
    assert len(reports) == 1


def test_cli_archive_by_ext(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _touch(tmp_path, "a.pdf")

    code = main(["archive", str(tmp_path), "--by", "ext", "--apply", "--yes"])

    assert code == 0
    capsys.readouterr()
    assert (tmp_path / "PDF/a.pdf").exists()


def test_cli_archive_apply_can_be_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 1))
    monkeypatch.setattr("builtins.input", lambda *_: "n")

    code = main(["archive", str(tmp_path), "--apply"])

    assert code == 0
    assert "已取消" in capsys.readouterr().out
    assert (tmp_path / "a.pdf").exists()


def test_cli_undo_restores_archive(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 1))
    main(["archive", str(tmp_path), "--apply", "--yes"])
    capsys.readouterr()
    assert (tmp_path / "2026年春季学期/a.pdf").exists()

    code = main(["undo", str(tmp_path), "--yes"])

    assert code == 0
    out = capsys.readouterr().out
    assert "撤销完成：恢复 1 个" in out
    assert (tmp_path / "a.pdf").exists()
    assert not (tmp_path / "2026年春季学期/a.pdf").exists()


def test_cli_undo_rename_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _touch(tmp_path, "2026001_张三_作业.pdf")

    assert main(["rename", str(tmp_path), "--apply", "--yes"]) == 0
    assert (tmp_path / "作业_2026001.pdf").exists()
    capsys.readouterr()

    assert main(["undo", str(tmp_path), "--yes"]) == 0
    out = capsys.readouterr().out
    assert "恢复 1 个" in out
    assert (tmp_path / "2026001_张三_作业.pdf").exists()


def test_cli_undo_without_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    code = main(["undo", str(tmp_path), "--yes"])

    assert code == 0
    assert "没有可撤销的操作" in capsys.readouterr().out


def test_cli_undo_twice_only_restores_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _touch(tmp_path, "a.pdf", datetime(2026, 3, 1))
    main(["archive", str(tmp_path), "--apply", "--yes"])
    capsys.readouterr()

    main(["undo", str(tmp_path), "--yes"])
    capsys.readouterr()
    code = main(["undo", str(tmp_path), "--yes"])

    assert "没有可撤销的操作" in capsys.readouterr().out
    assert code == 0


def test_journal_dir_is_internal_constant():
    # 防止误改内部目录名导致旧日志无法撤销
    assert journal.JOURNAL_DIR == ".homework_archiver"

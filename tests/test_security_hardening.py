"""安全加固的回归测试：
1. 符号链接不被扫描/改名/归档跟随；
2. 输出净化（文件名中的换行/ANSI 控制字符不能伪造终端输出）；
3. 损坏日志显式报错而不是裸崩溃；
4. 撤销时路径越界（../ 或绝对路径）一律拦截，不允许移出文件夹。
"""
from __future__ import annotations

import json

import pytest

from homework_archiver import journal, renamer, scanner
from homework_archiver.cli import main


# ---------- 符号链接 ----------


def test_scan_skips_symlink_to_file(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.pdf"
    target.write_bytes(b"x")
    work = tmp_path / "work"
    work.mkdir()
    (work / "link.pdf").symlink_to(target)

    assert scanner.scan_folder(work) == []
    assert scanner.scan_folder(work, recursive=True) == []


def test_scan_recursive_skips_symlinked_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "real.pdf").write_bytes(b"x")
    work = tmp_path / "work"
    work.mkdir()
    (work / "linkdir").symlink_to(outside, target_is_directory=True)

    infos = scanner.scan_folder(work, recursive=True)
    assert infos == []


def test_rename_plan_ignores_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.pdf"
    target.write_bytes(b"secret")
    link_name = "2026001_张三_作业.pdf"
    (tmp_path / link_name).symlink_to(target)

    items = renamer.plan_renames(tmp_path)
    # 符号链接被跳过扫描，因此没有任何改名候选
    assert all(item.skipped for item in items)
    result = renamer.apply_renames(tmp_path, items)
    assert result.renamed == []
    assert target.read_bytes() == b"secret"  # 外部目标原封不动


# ---------- 输出净化 ----------


def test_sanitize_display_escapes_control_characters():
    assert scanner.sanitize_display("普通.pdf") == "普通.pdf"
    escaped = scanner.sanitize_display("a\nb.pdf")
    assert "\n" not in escaped
    assert "\\x0a" in escaped
    assert "\x1b" not in scanner.sanitize_display(chr(27) + "x")


def test_listing_escapes_newline_in_filename(tmp_path):
    (tmp_path / "a\nb.pdf").write_bytes(b"x")
    text = scanner.format_listing(scanner.scan_folder(tmp_path))
    assert "\\x0a" in text
    # 表头/分隔/数据/合计共 4 行，文件名中的换行不能再制造额外的行
    assert text.count("\n") == 3


def test_rename_preview_escapes_control_characters(tmp_path):
    (tmp_path / "note\n.txt").write_bytes(b"x")  # 不合规，会进入跳过行
    text = renamer.format_preview(renamer.plan_renames(tmp_path))
    assert "\\x0a" in text
    assert "\nnote" not in text


# ---------- 损坏日志 ----------


def _write_log(folder, content: str) -> None:
    logs = folder / journal.JOURNAL_DIR / journal.LOGS_DIR
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "20000101-000000-000000.json").write_text(content, encoding="utf-8")


def test_load_latest_rejects_broken_json(tmp_path):
    _write_log(tmp_path, "{这不是合法 JSON")
    with pytest.raises(journal.JournalError):
        journal.load_latest(tmp_path)


def test_load_latest_rejects_bad_structure(tmp_path):
    _write_log(tmp_path, json.dumps({"kind": "rename", "timestamp": "t"}))
    with pytest.raises(journal.JournalError):
        journal.load_latest(tmp_path)
    _write_log(tmp_path, json.dumps({"kind": "rename", "timestamp": "t", "moves": "nope"}))
    with pytest.raises(journal.JournalError):
        journal.load_latest(tmp_path)


def test_cli_undo_corrupt_journal_returns_error_code(tmp_path, capsys):
    _write_log(tmp_path, "{broken")
    code = main(["undo", str(tmp_path), "--yes"])
    assert code == 2
    assert "错误" in capsys.readouterr().err


# ---------- 撤销路径 containment ----------


def test_undo_rejects_relative_traversal(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.pdf").write_bytes(b"x")
    _write_log(
        work,
        json.dumps(
            {
                "version": 1,
                "kind": "archive",
                "timestamp": "t",
                "moves": [{"src": "../escaped.pdf", "dst": "a.pdf"}],
            }
        ),
    )

    result = journal.undo_last(work)
    assert result.restored_count == 0
    assert result.skipped_count == 1
    assert "越界" in result.skipped[0][1]
    assert not (tmp_path / "escaped.pdf").exists()  # 文件没有被移出文件夹
    assert (work / "a.pdf").exists()  # 原文件未动
    assert list((work / journal.JOURNAL_DIR / journal.LOGS_DIR).glob("*.json"))  # 日志保留


def test_undo_rejects_absolute_path(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a.pdf").write_bytes(b"x")
    outside_target = tmp_path / "absolute.pdf"
    _write_log(
        work,
        json.dumps(
            {
                "version": 1,
                "kind": "archive",
                "timestamp": "t",
                "moves": [{"src": str(outside_target), "dst": "a.pdf"}],
            }
        ),
    )

    result = journal.undo_last(work)
    assert result.restored_count == 0
    assert result.skipped_count == 1
    assert not outside_target.exists()
    assert (work / "a.pdf").exists()

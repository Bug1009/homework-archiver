"""需求 1 的测试：扫描与列出。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from homework_archiver import scanner
from homework_archiver.cli import main


def _make(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_scan_empty_folder(tmp_path: Path):
    assert scanner.scan_folder(tmp_path) == []


def test_scan_non_recursive_ignores_subdirectories(tmp_path: Path):
    _make(tmp_path / "a.docx")
    _make(tmp_path / "sub" / "b.docx")

    infos = scanner.scan_folder(tmp_path)

    assert [info.name for info in infos] == ["a.docx"]


def test_scan_recursive_lists_nested_files(tmp_path: Path):
    _make(tmp_path / "a.docx")
    _make(tmp_path / "sub" / "b.pdf")

    infos = scanner.scan_folder(tmp_path, recursive=True)

    assert sorted(info.name for info in infos) == ["a.docx", "b.pdf"]


def test_scan_skips_directories(tmp_path: Path):
    (tmp_path / "subdir").mkdir()
    _make(tmp_path / "a.docx")

    infos = scanner.scan_folder(tmp_path, recursive=True)

    assert [info.name for info in infos] == ["a.docx"]


def test_extension_filter_case_insensitive_and_dot_optional(tmp_path: Path):
    _make(tmp_path / "a.DOCX")
    _make(tmp_path / "b.pdf")
    _make(tmp_path / "c.txt")

    infos = scanner.scan_folder(tmp_path, extensions=["DOCX", ".pdf"])

    assert sorted(info.name for info in infos) == ["a.DOCX", "b.pdf"]


def test_extension_filter_with_empty_sequence_means_no_filter(tmp_path: Path):
    _make(tmp_path / "a.docx")
    _make(tmp_path / "b.txt")

    assert len(scanner.scan_folder(tmp_path, extensions=[])) == 2


def test_file_info_carries_size_and_mtime(tmp_path: Path):
    _make(tmp_path / "a.docx", b"hello")

    info = scanner.scan_folder(tmp_path)[0]

    assert info.size == 5
    assert isinstance(info.mtime, datetime)
    assert info.path == (tmp_path / "a.docx").resolve()


def test_result_is_sorted_by_path(tmp_path: Path):
    for name in ("c.docx", "a.docx", "B.docx"):
        _make(tmp_path / name)

    infos = scanner.scan_folder(tmp_path)

    assert [info.name for info in infos] == ["a.docx", "B.docx", "c.docx"]


def test_scan_missing_folder_raises(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        scanner.scan_folder(tmp_path / "nope")


def test_scan_file_instead_of_folder_raises(tmp_path: Path):
    f = _make(tmp_path / "a.docx")
    with pytest.raises(NotADirectoryError):
        scanner.scan_folder(f)


def test_normalize_extension():
    assert scanner.normalize_extension("DOCX") == ".docx"
    assert scanner.normalize_extension(".pdf") == ".pdf"
    with pytest.raises(ValueError):
        scanner.normalize_extension("  ")


def test_human_size():
    assert scanner.human_size(512) == "512 B"
    assert scanner.human_size(1024) == "1.0 KB"
    assert scanner.human_size(1536) == "1.5 KB"
    assert scanner.human_size(1024 * 1024) == "1.0 MB"


def test_format_listing_empty_and_nonempty(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert "没有符合条件的文件" in scanner.format_listing([])

    _make(tmp_path / "a.docx", b"hello")
    text = scanner.format_listing(scanner.scan_folder(tmp_path))
    assert "文件名" in text
    assert "a.docx" in text
    assert "修改时间" in text


def test_cli_scan_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _make(tmp_path / "report.docx")
    _make(tmp_path / "note.txt")

    code = main(["scan", str(tmp_path), "--ext", "docx"])

    assert code == 0
    out = capsys.readouterr().out
    assert "report.docx" in out
    assert "note.txt" not in out
    assert "共 1 个文件" in out


def test_cli_scan_missing_folder_returns_error_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    code = main(["scan", str(tmp_path / "nope")])

    assert code == 2
    assert "错误" in capsys.readouterr().err


# ---------- 安全加固：不跟随符号链接、输出净化 ----------


def test_scan_skips_symlink_to_file(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.pdf"
    target.write_bytes(b"x")
    work = tmp_path / "work"
    work.mkdir()
    (work / "link.pdf").symlink_to(target)

    assert scanner.scan_folder(work) == []
    assert scanner.scan_folder(work, recursive=True) == []


def test_scan_recursive_skips_symlinked_directory(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "real.pdf").write_bytes(b"x")
    work = tmp_path / "work"
    work.mkdir()
    (work / "linkdir").symlink_to(outside, target_is_directory=True)

    assert scanner.scan_folder(work, recursive=True) == []


def test_sanitize_display_escapes_control_characters():
    assert scanner.sanitize_display("普通.pdf") == "普通.pdf"
    escaped = scanner.sanitize_display("a\nb.pdf")
    assert "\n" not in escaped
    assert "\\x0a" in escaped
    assert "\x1b" not in scanner.sanitize_display(chr(27) + "x")


def test_listing_escapes_newline_in_filename(tmp_path: Path):
    (tmp_path / "a\nb.pdf").write_bytes(b"x")
    text = scanner.format_listing(scanner.scan_folder(tmp_path))
    assert "\\x0a" in text
    # 表头/分隔/数据/合计共 4 行，文件名中的换行不能再制造额外的行
    assert text.count("\n") == 3

"""需求 2 的测试：批量改名（预览确认、绝不覆盖）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from homework_archiver import renamer
from homework_archiver.cli import main


def _make(folder: Path, name: str, content: bytes = b"x") -> Path:
    path = folder / name
    path.write_bytes(content)
    return path


def _find(items: list[renamer.RenameItem], name: str) -> renamer.RenameItem:
    for item in items:
        if item.source.name == name:
            return item
    raise AssertionError(f"计划中找不到 {name}")


def test_compute_new_name_basic():
    assert renamer.compute_new_name("2026001_张三_高数作业.pdf") == "高数作业_2026001.pdf"


def test_compute_new_name_keeps_extension():
    assert renamer.compute_new_name("2026001_张三_论文.docx") == "论文_2026001.docx"


def test_compute_new_name_keeps_underscores_in_homework():
    assert renamer.compute_new_name("2026001_张三_期中_高数.docx") == "期中_高数_2026001.docx"


def test_compute_new_name_rejects_non_conforming():
    assert renamer.compute_new_name("随便一个文件.pdf") is None
    assert renamer.compute_new_name("a_b.pdf") is None


def test_plan_standard_rename(tmp_path: Path):
    _make(tmp_path, "2026001_张三_高数作业.pdf")
    item = _find(renamer.plan_renames(tmp_path), "2026001_张三_高数作业.pdf")
    assert not item.skipped
    assert item.target_name == "高数作业_2026001.pdf"


def test_plan_skips_non_conforming(tmp_path: Path):
    _make(tmp_path, "笔记.pdf")
    item = _find(renamer.plan_renames(tmp_path), "笔记.pdf")
    assert item.skipped
    assert "不符合规则" in (item.reason or "")


def test_plan_skips_when_target_already_exists(tmp_path: Path):
    _make(tmp_path, "2026001_张三_作业.pdf")
    _make(tmp_path, "作业_2026001.pdf")  # 目标名已被占用
    item = _find(renamer.plan_renames(tmp_path), "2026001_张三_作业.pdf")
    assert item.skipped
    assert "已存在" in (item.reason or "")


def test_plan_skips_all_files_in_batch_collision(tmp_path: Path):
    _make(tmp_path, "2026001_张三_作业.pdf")
    _make(tmp_path, "2026001_李四_作业.pdf")  # 同学号、作业名 → 同一目标
    items = renamer.plan_renames(tmp_path)
    moving = [item for item in items if not item.skipped]
    assert moving == []
    assert all("冲突" in (item.reason or "") for item in items)


def test_plan_detects_chain_overwrite(tmp_path: Path):
    # 1_a_2.pdf 想改成 2_1.pdf，而 2_1.pdf 已存在（它本身不合规、不会动）
    _make(tmp_path, "1_a_2.pdf")
    _make(tmp_path, "2_1.pdf")
    item = _find(renamer.plan_renames(tmp_path), "1_a_2.pdf")
    assert item.skipped
    assert "已存在" in (item.reason or "")


def test_plan_empty_folder(tmp_path: Path):
    assert renamer.plan_renames(tmp_path) == []


def test_apply_performs_rename(tmp_path: Path):
    _make(tmp_path, "2026001_张三_作业.pdf", b"data")
    items = renamer.plan_renames(tmp_path)
    result = renamer.apply_renames(tmp_path, items)
    assert result.renamed == [("2026001_张三_作业.pdf", "作业_2026001.pdf")]
    assert not (tmp_path / "2026001_张三_作业.pdf").exists()
    assert (tmp_path / "作业_2026001.pdf").read_bytes() == b"data"


def test_apply_skips_if_source_vanished(tmp_path: Path):
    src = _make(tmp_path, "2026001_张三_作业.pdf")
    items = renamer.plan_renames(tmp_path)
    src.unlink()  # 计划生成后原文件被删
    result = renamer.apply_renames(tmp_path, items)
    assert result.renamed == []
    assert result.skipped[0][0] == "2026001_张三_作业.pdf"
    assert "不存在" in result.skipped[0][1]


def test_apply_rechecks_target_existence(tmp_path: Path):
    _make(tmp_path, "2026001_张三_作业.pdf")
    items = renamer.plan_renames(tmp_path)
    _make(tmp_path, "作业_2026001.pdf")  # 计划后人为制造冲突
    result = renamer.apply_renames(tmp_path, items)
    assert result.renamed == []
    assert "已存在" in result.skipped[0][1]
    # 原有文件内容未被覆盖
    assert (tmp_path / "作业_2026001.pdf").read_bytes() == b"x"


def test_format_preview_shows_arrow_and_total(tmp_path: Path):
    _make(tmp_path, "2026001_张三_作业.pdf")
    _make(tmp_path, "杂项.txt")
    text = renamer.format_preview(renamer.plan_renames(tmp_path))
    assert "->" in text
    assert "将改名 1 个" in text
    assert "跳过 1 个" in text


def test_cli_preview_does_not_touch_disk(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _make(tmp_path, "2026001_张三_作业.pdf")
    code = main(["rename", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "改名计划预览" in out
    assert "作业_2026001.pdf" in out
    assert "预览" in out
    assert (tmp_path / "2026001_张三_作业.pdf").exists()  # 原文件还在


def test_cli_apply_with_yes_renames(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    _make(tmp_path, "2026001_张三_作业.pdf")
    code = main(["rename", str(tmp_path), "--apply", "--yes"])
    assert code == 0
    assert "执行完成：改名 1 个" in capsys.readouterr().out
    assert (tmp_path / "作业_2026001.pdf").exists()


def test_cli_apply_can_be_cancelled_at_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    _make(tmp_path, "2026001_张三_作业.pdf")
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    code = main(["rename", str(tmp_path), "--apply"])
    assert code == 0
    assert "已取消" in capsys.readouterr().out
    assert (tmp_path / "2026001_张三_作业.pdf").exists()


def test_cli_rename_missing_folder_returns_error_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    code = main(["rename", str(tmp_path / "nope")])
    assert code == 2
    assert "错误" in capsys.readouterr().err


# ---------- 安全加固：符号链接不跟随、预览输出净化 ----------


def test_rename_plan_ignores_symlink(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "secret.pdf"
    target.write_bytes(b"secret")
    (tmp_path / "2026001_张三_作业.pdf").symlink_to(target)

    items = renamer.plan_renames(tmp_path)
    # 符号链接被跳过扫描，因此没有任何改名候选
    assert all(item.skipped for item in items)
    result = renamer.apply_renames(tmp_path, items)
    assert result.renamed == []
    assert target.read_bytes() == b"secret"  # 外部目标原封不动


def test_rename_preview_escapes_control_characters(tmp_path: Path):
    (tmp_path / "note\n.txt").write_bytes(b"x")  # 不合规，会进入跳过行
    text = renamer.format_preview(renamer.plan_renames(tmp_path))
    assert "\\x0a" in text
    assert "\nnote" not in text

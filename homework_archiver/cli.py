"""命令行入口。

用法：
    python -m homework_archiver scan <文件夹> [--ext .docx] [--ext .pdf] [-r]
    python -m homework_archiver rename <文件夹>            # 只预览，不动盘
    python -m homework_archiver rename <文件夹> --apply     # 确认后真正改名
    python -m homework_archiver archive <文件夹>           # 按学期归档预览
    python -m homework_archiver archive <文件夹> --apply    # 确认后归档并出报告
    python -m homework_archiver undo <文件夹>              # 撤销上一次改名/归档
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from homework_archiver import __version__, archiver, journal, renamer, scanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homework-archiver",
        description="作业文件批量归档工具（扫描 / 改名 / 归档 / 撤销）",
    )
    parser.add_argument("--version", action="version", version=f"homework-archiver {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 需求 1：扫描与列出
    scan = subparsers.add_parser("scan", help="扫描文件夹并列出文件（大小、修改时间）")
    scan.add_argument("folder", help="要扫描的文件夹路径")
    scan.add_argument(
        "--ext",
        action="append",
        default=None,
        metavar=".docx",
        help="只保留指定扩展名，可多次使用，如 --ext .docx --ext .pdf",
    )
    scan.add_argument("-r", "--recursive", action="store_true", help="递归扫描子文件夹")

    # 需求 2：批量改名
    rename = subparsers.add_parser("rename", help="按 学号_姓名_作业名 → 作业名_学号 批量改名")
    rename.add_argument("folder", help="要整理的文件夹路径")
    rename.add_argument(
        "--apply",
        action="store_true",
        help="真正执行改名（默认只预览，不改动任何文件）",
    )
    rename.add_argument("-y", "--yes", action="store_true", help="执行时跳过交互确认")

    # 需求 3：归档与报告
    archive = subparsers.add_parser("archive", help="按学期（默认）或扩展名把文件移入子文件夹")
    archive.add_argument("folder", help="要整理的文件夹路径")
    archive.add_argument(
        "--by",
        choices=[archiver.TERM, archiver.EXT],
        default=archiver.TERM,
        help="归档方式：term=按修改时间推断学期（默认），ext=按扩展名分类",
    )
    archive.add_argument("--apply", action="store_true", help="真正执行归档（默认只预览）")
    archive.add_argument("-y", "--yes", action="store_true", help="执行时跳过交互确认")

    # 需求 3：撤销上次操作
    undo = subparsers.add_parser("undo", help="撤销上一次改名或归档操作")
    undo.add_argument("folder", help="要撤销操作的文件夹路径")
    undo.add_argument("-y", "--yes", action="store_true", help="跳过交互确认")

    return parser


def _confirm(prompt: str, skip: bool) -> bool:
    if skip:
        return True
    return input(prompt).strip().lower() == "y"


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        infos = scanner.scan_folder(
            args.folder,
            extensions=args.ext,
            recursive=args.recursive,
        )
    except NotADirectoryError as exc:
        print(f"错误：{scanner.sanitize_display(exc)}", file=sys.stderr)
        return 2
    print(scanner.format_listing(infos))
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    try:
        items = renamer.plan_renames(args.folder)
    except NotADirectoryError as exc:
        print(f"错误：{scanner.sanitize_display(exc)}", file=sys.stderr)
        return 2

    print("改名计划预览：")
    print(renamer.format_preview(items))

    if not args.apply:
        print("\n这是预览，未修改任何文件。确认无误后加 --apply 执行。")
        return 0

    will_change = sum(not item.skipped for item in items)
    if will_change == 0:
        print("\n没有需要改名的文件，未执行任何操作。")
        return 0

    if not _confirm(f"\n确认对以上 {will_change} 个文件执行改名？输入 y 继续，其他键取消：", args.yes):
        print("已取消，未修改任何文件。")
        return 0

    result = renamer.apply_renames(args.folder, items)
    moves = [journal.Move(src=old, dst=new) for old, new in result.renamed]
    journal.save_operation(args.folder, "rename", moves)
    print(f"\n执行完成：改名 {result.renamed_count} 个，跳过 {result.skipped_count} 个。")
    for old_name, reason in result.skipped:
        print(f"  已跳过：{scanner.sanitize_display(old_name)}（{scanner.sanitize_display(reason)}）")
    if result.renamed:
        print("可使用 undo 子命令撤销本次操作。")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    try:
        items = archiver.plan_archive(args.folder, by=args.by)
    except (NotADirectoryError, ValueError) as exc:
        print(f"错误：{scanner.sanitize_display(exc)}", file=sys.stderr)
        return 2

    print("归档计划预览：")
    print(archiver.format_plan(items))

    if not args.apply:
        print("\n这是预览，未修改任何文件。确认无误后加 --apply 执行。")
        return 0

    will_move = sum(not item.skipped for item in items)
    if will_move == 0:
        print("\n没有需要归档的文件，未执行任何操作。")
        return 0

    if not _confirm(f"\n确认移动以上 {will_move} 个文件？输入 y 继续，其他键取消：", args.yes):
        print("已取消，未修改任何文件。")
        return 0

    result, journal_path = archiver.apply_archive(args.folder, items)
    report = archiver.format_report(result, journal_path)
    report_path = archiver.save_report(args.folder, report)
    print("\n" + report)
    print(f"\n报告已保存：{report_path}")
    return 0


def cmd_undo(args: argparse.Namespace) -> int:
    root = Path(args.folder)
    if not root.is_dir():
        print(f"错误：文件夹不存在或不是文件夹：{scanner.sanitize_display(str(root))}", file=sys.stderr)
        return 2
    try:
        op, _ = journal.load_latest(root)
    except (OSError, journal.JournalError) as exc:
        print(f"错误：{scanner.sanitize_display(str(exc))}", file=sys.stderr)
        return 2
    if op is None:
        print("没有可撤销的操作（尚未执行过改名或归档，或已撤销过）。")
        return 0

    print(f"将撤销上一次操作（{op.kind}，{op.timestamp}），共 {len(op.moves)} 个文件。")
    if not _confirm("确认撤销？输入 y 继续，其他键取消：", args.yes):
        print("已取消。")
        return 0

    result = journal.undo_last(root)
    print(f"撤销完成：恢复 {result.restored_count} 个，跳过 {result.skipped_count} 个。")
    for name, reason in result.skipped:
        # name/reason 可能来自日志，打印前同样净化
        print(f"  已跳过：{scanner.sanitize_display(name)}（{scanner.sanitize_display(reason)}）")
    if result.skipped_count:
        print("\n有文件未能恢复，操作日志已保留，请检查上述冲突后重试 undo。")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "rename":
        return cmd_rename(args)
    if args.command == "archive":
        return cmd_archive(args)
    if args.command == "undo":
        return cmd_undo(args)
    parser.error(f"未知命令：{args.command}")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""命令行入口。

用法：
    python -m homework_archiver scan <文件夹> [--ext .docx] [--ext .pdf] [-r]
    python -m homework_archiver rename <文件夹>            # 只预览，不动盘
    python -m homework_archiver rename <文件夹> --apply     # 确认后真正改名

后续需求会在本文件增量加入 archive / undo 子命令。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from homework_archiver import __version__, renamer, scanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="homework-archiver",
        description="作业文件批量归档工具（扫描 / 改名 / 归档）",
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

    return parser


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        infos = scanner.scan_folder(
            args.folder,
            extensions=args.ext,
            recursive=args.recursive,
        )
    except NotADirectoryError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    print(scanner.format_listing(infos))
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    try:
        items = renamer.plan_renames(args.folder)
    except NotADirectoryError as exc:
        print(f"错误：{exc}", file=sys.stderr)
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

    if not args.yes:
        answer = input(f"\n确认对以上 {will_change} 个文件执行改名？输入 y 继续，其他键取消：")
        if answer.strip().lower() != "y":
            print("已取消，未修改任何文件。")
            return 0

    result = renamer.apply_renames(args.folder, items)
    print(
        f"\n执行完成：改名 {result.renamed_count} 个，跳过 {result.skipped_count} 个。"
    )
    for old_name, reason in result.skipped:
        print(f"  已跳过：{old_name}（{reason}）")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    if args.command == "rename":
        return cmd_rename(args)
    parser.error(f"未知命令：{args.command}")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

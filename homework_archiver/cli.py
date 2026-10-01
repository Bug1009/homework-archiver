"""命令行入口。

用法：
    python -m homework_archiver scan <文件夹> [--ext .docx] [--ext .pdf] [-r]

后续需求会在本文件增量加入 rename / archive / undo 子命令。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from homework_archiver import __version__, scanner


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        return cmd_scan(args)
    parser.error(f"未知命令：{args.command}")
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

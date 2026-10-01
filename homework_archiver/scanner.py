"""需求 1：扫描与列出。
扫描指定文件夹，列出其中的文件及其大小、修改时间；
支持按扩展名过滤（大小写不敏感，带不带点均可），可选递归子目录。
本模块只做“读”操作，不会创建、修改或删除任何文件。

安全说明：不跟随符号链接（避免扫描/改名意外触及文件夹之外的目标）；
sanitize_display 用于所有面向用户的输出，防止文件名中的控制字符
（换行、ANSI 转义等）伪造终端输出或报告内容。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Iterable, Sequence

# 本工具存放日志/报告的内部目录，扫描时跳过，避免把自己的产出当成作业文件
INTERNAL_DIR = ".homework_archiver"


@dataclass(frozen=True)
class FileInfo:
    """一个被扫描到的文件。

    Attributes:
        path: 文件绝对路径
        name: 文件名（含扩展名）
        size: 文件大小（字节）
        mtime: 最后修改时间
    """

    path: Path
    name: str
    size: int
    mtime: datetime


def sanitize_display(text: object) -> str:
    """把控制字符转义为可见形式（如 ``\\x0a``）。

    文件名可能来自不可信来源，其中的换行/ANSI 转义序列若原样打印，
    可能伪造终端输出或报告行。转义后只影响显示，不改写真实文件名。

    >>> sanitize_display("正常文件名.pdf")
    '正常文件名.pdf'
    >>> sanitize_display("a\\nb.pdf")
    'a\\\\x0ab.pdf'
    """
    return "".join(
        ch if (" " <= ch <= "~" or ord(ch) > 0x7F) and ch != "\x7f" else f"\\x{ord(ch):02x}"
        for ch in str(text)
    )


def normalize_extension(ext: str) -> str:
    """把用户输入的扩展名统一为小写、带前导点的形式。

    >>> normalize_extension("DOCX")
    '.docx'
    >>> normalize_extension(".pdf")
    '.pdf'
    """
    if not ext or not ext.strip():
        raise ValueError("扩展名不能为空")
    ext = ext.strip().lower()
    if not ext.startswith("."):
        ext = "." + ext
    return ext


def normalize_extensions(extensions: Iterable[str] | None) -> frozenset[str] | None:
    """批量规范化扩展名；None 或空集合表示不过滤。"""
    if not extensions:
        return None
    normalized = {normalize_extension(ext) for ext in extensions if ext and ext.strip()}
    return frozenset(normalized) if normalized else None


def scan_folder(
    folder: str | os.PathLike[str],
    *,
    extensions: Sequence[str] | None = None,
    recursive: bool = False,
) -> list[FileInfo]:
    """扫描文件夹，返回文件信息列表。

    Args:
        folder: 目标文件夹路径
        extensions: 只保留这些扩展名（如 ``['.docx', 'pdf']``）；
            None 或空表示不过滤
        recursive: 是否递归扫描子文件夹，默认只看第一层。
            递归时会跳过本工具的内部目录 ``.homework_archiver``。

    Returns:
        FileInfo 列表，按路径排序，保证输出稳定可测试。

    Raises:
        NotADirectoryError: folder 不存在或不是文件夹

    符号链接（无论指向文件还是目录）一律跳过：改名/归档只应处理
    文件夹内的真实文件，不能意外操作链接目标（可能在文件夹之外）。
    """
    root = Path(folder).expanduser()
    if not root.exists():
        raise NotADirectoryError(f"文件夹不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是文件夹：{root}")

    wanted = normalize_extensions(extensions)

    iterator = root.rglob("*") if recursive else root.iterdir()
    infos: list[FileInfo] = []
    for entry in iterator:
        if entry.is_symlink():
            # 不跟随符号链接，杜绝通过链接操作文件夹之外目标的可能
            continue
        if not entry.is_file():
            continue
        if recursive and INTERNAL_DIR in entry.relative_to(root).parts:
            continue
        if wanted is not None and entry.suffix.lower() not in wanted:
            continue
        stat = entry.stat()
        infos.append(
            FileInfo(
                path=entry.resolve(),
                name=entry.name,
                size=stat.st_size,
                mtime=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    infos.sort(key=lambda info: str(info.path).lower())
    return infos


def human_size(size: int) -> str:
    """把字节数转成易读形式，例如 ``1.5 KB``。"""
    if size < 1024:
        return f"{size} B"
    units = ("KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TB"


def format_listing(infos: Sequence[FileInfo]) -> str:
    """把扫描结果格式化为人类可读的表格文本。"""
    if not infos:
        return "没有符合条件的文件。"

    rows = [
        (
            sanitize_display(info.name),
            human_size(info.size),
            info.mtime.strftime("%Y-%m-%d %H:%M"),
        )
        for info in infos
    ]
    name_w = max(len("文件名"), *(len(row[0]) for row in rows))
    size_w = max(len("大小"), *(len(row[1]) for row in rows))

    header = f"{'文件名':<{name_w}}  {'大小':>{size_w}}  修改时间"
    lines = [header, "-" * len(header)]
    lines.extend(
        f"{name:<{name_w}}  {size:>{size_w}}  {mtime}"
        for name, size, mtime in rows
    )
    lines.append(f"共 {len(rows)} 个文件")
    return "\n".join(lines)

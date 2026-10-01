"""需求 3：按学期（或类别）归档与整理报告。

默认按文件“最后修改时间”推断学期，移动到对应子文件夹：
- 9–12 月 → ``YYYY年秋季学期``
- 1 月     → 上一年的秋季学期
- 2–6 月  → ``YYYY年春季学期``
- 7–8 月  → ``YYYY年暑期``

也支持 ``--by ext`` 按扩展名归类（如 ``PDF``、``DOCX``）。

与改名一致：先出计划、确认后执行、绝不覆盖；执行后写操作日志并生成报告。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from homework_archiver.journal import JOURNAL_DIR, Move, save_operation
from homework_archiver.scanner import scan_folder

TERM = "term"
EXT = "ext"


@dataclass(frozen=True)
class ArchiveItem:
    source: Path
    target_rel: str = ""  # 相对目标文件夹，如 “2025年秋季学期/作业.pdf”
    skipped: bool = False
    reason: str | None = None


@dataclass
class ArchiveResult:
    moved: list[tuple[str, str]] = field(default_factory=list)  # (原相对路径, 新相对路径)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def moved_count(self) -> int:
        return len(self.moved)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def term_for_date(moment: datetime) -> str:
    """按月份推断学期文件夹名。

    >>> term_for_date(datetime(2025, 9, 1))
    '2025年秋季学期'
    >>> term_for_date(datetime(2026, 1, 31))
    '2025年秋季学期'
    >>> term_for_date(datetime(2026, 3, 1))
    '2026年春季学期'
    >>> term_for_date(datetime(2026, 8, 1))
    '2026年暑期'
    """
    month = moment.month
    year = moment.year
    if 9 <= month <= 12:
        return f"{year}年秋季学期"
    if month == 1:
        return f"{year - 1}年秋季学期"
    if 2 <= month <= 6:
        return f"{year}年春季学期"
    return f"{year}年暑期"


def category_for_file(path: Path, by: str) -> str:
    if by == EXT:
        suffix = path.suffix.lstrip(".")
        return suffix.upper() if suffix else "无扩展名"
    raise ValueError(f"不支持的归档方式：{by}")


def plan_archive(folder: str | Path, by: str = TERM) -> list[ArchiveItem]:
    """生成归档计划（非递归，只整理文件夹第一层文件）。"""
    if by not in (TERM, EXT):
        raise ValueError(f"不支持的归档方式：{by}")

    root = Path(folder)
    infos = scan_folder(root)
    target_counter: dict[str, int] = {}
    planned: list[tuple[Path, str]] = []

    items: list[ArchiveItem] = []
    for info in infos:
        subdir = term_for_date(info.mtime) if by == TERM else category_for_file(info.path, EXT)
        target_rel = f"{subdir}/{info.name}"
        target_counter[target_rel] = target_counter.get(target_rel, 0) + 1
        planned.append((info.path, target_rel))

    for source, target_rel in planned:
        if target_counter[target_rel] > 1:
            items.append(ArchiveItem(source=source, skipped=True, reason="批次内多个文件指向同一目标，存在冲突"))
            continue
        if (root / target_rel).exists():
            items.append(
                ArchiveItem(source=source, skipped=True, reason=f"目标 {target_rel} 已存在，为避免覆盖已跳过")
            )
            continue
        items.append(ArchiveItem(source=source, target_rel=target_rel))

    items.sort(key=lambda item: str(item.source).lower())
    return items


def format_plan(items: list[ArchiveItem]) -> str:
    lines: list[str] = []
    move_n = sum(not item.skipped for item in items)
    skip_n = len(items) - move_n
    for item in items:
        rel = item.source.name
        if item.skipped:
            lines.append(f"  跳过：{rel}（{item.reason}）")
        else:
            lines.append(f"  移动：{rel}  ->  {item.target_rel}")
    lines.append(f"合计：将移动 {move_n} 个，跳过 {skip_n} 个")
    return "\n".join(lines)


def apply_archive(folder: str | Path, items: list[ArchiveItem]) -> tuple[ArchiveResult, Path | None]:
    """执行归档：创建子文件夹、移动文件、写日志。返回 (结果, 日志路径)。"""
    root = Path(folder)
    result = ArchiveResult()
    moves: list[Move] = []

    for item in items:
        old_rel = item.source.name
        if item.skipped:
            result.skipped.append((old_rel, item.reason or "未知原因"))
            continue
        src = root / old_rel
        dst = root / item.target_rel
        if not src.exists():
            result.skipped.append((old_rel, "计划生成后原文件已不存在"))
            continue
        if dst.exists():
            result.skipped.append((old_rel, f"目标 {item.target_rel} 已存在，为避免覆盖已跳过"))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        result.moved.append((old_rel, item.target_rel))
        moves.append(Move(src=old_rel, dst=item.target_rel))

    journal_path = save_operation(root, "archive", moves)
    return result, journal_path


def format_report(result: ArchiveResult, journal_path: Path | None) -> str:
    """渲染整理报告（处理多少、跳过多少、为什么跳过）。"""
    lines = [
        "整理报告",
        f"  处理（移动）：{result.moved_count} 个",
        f"  跳过：{result.skipped_count} 个",
    ]
    if result.moved:
        lines.append("  已移动：")
        lines.extend(f"    {old}  ->  {new}" for old, new in result.moved)
    if result.skipped:
        lines.append("  跳过明细：")
        lines.extend(f"    {name}：{reason}" for name, reason in result.skipped)
    if journal_path is not None:
        lines.append("  撤销本次操作：python -m homework_archiver undo <文件夹>")
    return "\n".join(lines)


def save_report(folder: str | Path, report: str) -> Path:
    """把报告写到 .homework_archiver/reports/ 下，返回报告路径。"""
    reports = Path(folder) / JOURNAL_DIR / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = reports / f"report-{stamp}.txt"
    path.write_text(report + "\n", encoding="utf-8")
    return path

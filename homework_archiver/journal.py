"""需求 3：操作日志与撤销。

每次真正执行的批量操作（改名 / 归档）都会在目标文件夹内的
``.homework_archiver/logs/`` 下写一份 JSON 日志，记录每个文件“从哪到哪”。
``undo_last`` 读取最新一份日志，按逆序把文件移回原处。

路径以文件夹为根存相对路径，即使整个文件夹被移动位置也能正确撤销。
撤销同样遵循“绝不覆盖”原则：原位置已有文件时跳过并报告。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = ".homework_archiver"
LOGS_DIR = "logs"


@dataclass(frozen=True)
class Move:
    """一次单文件移动（改名在本工具里也视为同目录移动）。"""

    src: str  # 相对目标文件夹的 POSIX 风格相对路径
    dst: str


@dataclass
class Operation:
    kind: str  # "rename" 或 "archive"
    timestamp: str
    moves: list[Move] = field(default_factory=list)


@dataclass
class UndoResult:
    restored: list[Move] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    kind: str | None = None
    journal_file: Path | None = None

    @property
    def restored_count(self) -> int:
        return len(self.restored)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def _logs_root(folder: str | Path) -> Path:
    return Path(folder) / JOURNAL_DIR / LOGS_DIR


def save_operation(folder: str | Path, kind: str, moves: list[Move]) -> Path | None:
    """把一次操作落盘为日志；没有实际移动则不写日志。"""
    if not moves:
        return None
    logs = _logs_root(folder)
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    path = logs / f"{stamp}.json"
    payload = {
        "version": 1,
        "kind": kind,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "moves": [{"src": m.src, "dst": m.dst} for m in moves],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest(folder: str | Path) -> tuple[Operation | None, Path | None]:
    """读取最新一份操作日志，没有则返回 (None, None)。"""
    logs = _logs_root(folder)
    if not logs.is_dir():
        return None, None
    files = sorted(logs.glob("*.json"))
    if not files:
        return None, None
    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    op = Operation(
        kind=data["kind"],
        timestamp=data["timestamp"],
        moves=[Move(src=item["src"], dst=item["dst"]) for item in data["moves"]],
    )
    return op, path


def undo_last(folder: str | Path) -> UndoResult:
    """撤销最近一次操作。

    - 逆序回移，防止目录嵌套时先后顺序出错；
    - 原位置已存在文件时跳过（绝不覆盖），并保留日志供人工处理；
    - 全部成功后删除该日志，避免重复撤销。
    """
    root = Path(folder)
    op, journal_path = load_latest(root)
    if op is None:
        return UndoResult()

    result = UndoResult(kind=op.kind, journal_file=journal_path)
    for move in reversed(op.moves):
        src = root / move.src
        dst = root / move.dst
        if not dst.exists():
            result.skipped.append((move.dst, "文件不在日志记录的位置，无法回移"))
            continue
        if src.exists():
            result.skipped.append((move.dst, f"原位置 {move.src} 已有文件，为避免覆盖已跳过"))
            continue
        src.parent.mkdir(parents=True, exist_ok=True)
        dst.rename(src)
        result.restored.append(Move(src=move.dst, dst=move.src))

    if result.skipped_count == 0 and journal_path is not None:
        journal_path.unlink()
    return result

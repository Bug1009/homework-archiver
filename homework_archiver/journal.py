"""需求 3：操作日志与撤销。
每次真正执行的批量操作（改名 / 归档）都会在目标文件夹内的
``.homework_archiver/logs/`` 下写一份 JSON 日志，记录每个文件“从哪到哪”。
``undo_last`` 读取最新一份日志，按逆序把文件移回原处。
路径以文件夹为根存相对路径，即使整个文件夹被移动位置也能正确撤销。
撤销同样遵循“绝不覆盖”原则：原位置已有文件时跳过并报告。

安全设计：
- 日志损坏/字段缺失时抛 :class:`JournalError`，由 CLI 转为错误码，不出现裸崩溃；
- 撤销前校验每条 src/dst 解析后仍在目标文件夹内，日志即使被篡改也无法
  借 ``../`` 或绝对路径把文件移到文件夹之外。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

JOURNAL_DIR = ".homework_archiver"
LOGS_DIR = "logs"


class JournalError(Exception):
    """操作日志损坏或内容不合法。"""


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


def _resolve_within(root: Path, rel: object) -> Path | None:
    """把日志中的相对路径解析为 root 内的绝对路径。

    任何绝对路径、``..`` 穿越、NUL 字节等越界/非法输入一律返回 None。
    """
    if not isinstance(rel, str) or not rel:
        return None
    try:
        target = (root / rel).resolve(strict=False)
    except (ValueError, OSError):
        return None
    if target != root and root not in target.parents:
        return None
    return target


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
    """读取最新一份操作日志，没有则返回 (None, None)。

    Raises:
        JournalError: 最新日志损坏（非法 JSON、缺字段、字段类型不对）。
    """
    logs = _logs_root(folder)
    if not logs.is_dir():
        return None, None
    files = sorted(logs.glob("*.json"))
    if not files:
        return None, None
    path = files[-1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JournalError(f"操作日志已损坏，无法解析：{path.name}（{exc}）") from exc
    if not isinstance(data, dict):
        raise JournalError(f"操作日志格式不合法：{path.name}")
    if not isinstance(data.get("kind"), str) or not isinstance(data.get("timestamp"), str):
        raise JournalError(f"操作日志缺少 kind/timestamp 字段：{path.name}")
    raw_moves = data.get("moves")
    if not isinstance(raw_moves, list):
        raise JournalError(f"操作日志的 moves 字段不合法：{path.name}")
    moves: list[Move] = []
    for item in raw_moves:
        if not isinstance(item, dict) or not isinstance(item.get("src"), str) or not isinstance(item.get("dst"), str):
            raise JournalError(f"操作日志中存在不合法的移动记录：{path.name}")
        moves.append(Move(src=item["src"], dst=item["dst"]))
    op = Operation(kind=data["kind"], timestamp=data["timestamp"], moves=moves)
    return op, path


def undo_last(folder: str | Path) -> UndoResult:
    """撤销最近一次操作。
    - 逆序回移，防止目录嵌套时先后顺序出错；
    - 原位置已存在文件时跳过（绝不覆盖），并保留日志供人工处理；
    - 日志中越界/非法路径直接跳过（不可能写到文件夹之外）；
    - 全部成功后删除该日志，避免重复撤销。
    """
    root = Path(folder).resolve(strict=False)
    op, journal_path = load_latest(root)
    if op is None:
        return UndoResult()

    result = UndoResult(kind=op.kind, journal_file=journal_path)
    for move in reversed(op.moves):
        src = _resolve_within(root, move.src)
        dst = _resolve_within(root, move.dst)
        if src is None or dst is None:
            result.skipped.append((str(move.dst), "日志记录的路径越界或非法，为安全起见已跳过"))
            continue
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

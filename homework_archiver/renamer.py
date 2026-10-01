"""需求 2：批量改名。

规则示例：``学号_姓名_作业名.pdf`` → ``作业名_学号.pdf``。

安全设计：
1. :func:`plan_renames` 只做分析，不动磁盘，输出完整的改名计划；
2. 调用方先把计划打印给用户确认，再调用 :func:`apply_renames`；
3. 以下情况一律跳过，绝不覆盖已有文件：
   - 文件名不符合“学号_姓名_作业名”规则（下划线不足 3 段）；
   - 目标文件在磁盘上已存在（包含链式改名会覆盖其他源文件的情况）；
   - 批次内有多个文件将改成同一个名字（全部跳过，不猜保留谁）；
4. 真正执行前对每个目标再次复查，防止计划生成后文件发生变化。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from homework_archiver.scanner import scan_folder


@dataclass(frozen=True)
class RenameItem:
    """单条改名计划。

    skipped 为 True 时 target_name 为空、reason 写明跳过原因。
    """

    source: Path
    target_name: str = ""
    skipped: bool = False
    reason: str | None = None


@dataclass
class RenameResult:
    """一次改名执行（或计划汇总）的结果。"""

    renamed: list[tuple[str, str]] = field(default_factory=list)  # (原名, 新名)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (原名, 原因)

    @property
    def renamed_count(self) -> int:
        return len(self.renamed)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


def compute_new_name(filename: str) -> str | None:
    """按规则计算新文件名；不符合规则返回 None。

    >>> compute_new_name("2026001_张三_高数作业.pdf")
    '高数作业_2026001.pdf'
    >>> compute_new_name("2026001_张三_期中_高数.docx")
    '期中_高数_2026001.docx'
    >>> compute_new_name("随便一个文件.pdf") is None
    True
    """
    path = Path(filename)
    parts = path.stem.split("_")
    if len(parts) < 3:
        return None
    student_id = parts[0]
    homework = "_".join(parts[2:])
    return f"{homework}_{student_id}{path.suffix}"


def plan_renames(folder: str | Path) -> list[RenameItem]:
    """分析文件夹（非递归）并生成改名计划，不触碰磁盘。"""
    root = Path(folder)
    infos = scan_folder(root)
    existing_names = {info.name for info in infos}

    # 第一轮：算出所有合规候选，并统计目标名出现次数
    candidates: dict[str, str] = {}
    items: list[RenameItem] = []
    for info in infos:
        new_name = compute_new_name(info.name)
        if new_name is None:
            items.append(
                RenameItem(
                    source=info.path,
                    skipped=True,
                    reason="不符合规则（需要 学号_姓名_作业名，至少两段下划线）",
                )
            )
            continue
        if new_name == info.name:
            items.append(RenameItem(source=info.path, skipped=True, reason="新名字与原名相同，无需修改"))
            continue
        candidates[info.name] = new_name

    target_counter = Counter(candidates.values())

    # 第二轮：对候选做冲突检测，保持与扫描结果一致的顺序
    candidate_lookup = set(candidates)
    for info in infos:
        if info.name not in candidate_lookup:
            continue
        new_name = candidates[info.name]
        if target_counter[new_name] > 1:
            reason = f"批次内有 {target_counter[new_name]} 个文件将改名为 {new_name}，存在冲突"
            items.append(RenameItem(source=info.path, skipped=True, reason=reason))
        elif new_name in existing_names:
            items.append(
                RenameItem(
                    source=info.path,
                    skipped=True,
                    reason=f"目标文件 {new_name} 已存在，为避免覆盖已跳过",
                )
            )
        else:
            items.append(RenameItem(source=info.path, target_name=new_name))

    items.sort(key=lambda item: str(item.source).lower())
    return items


def summarize_plan(items: list[RenameItem]) -> RenameResult:
    """把计划汇总成结果对象（不执行）。"""
    result = RenameResult()
    for item in items:
        if item.skipped:
            result.skipped.append((item.source.name, item.reason or "未知原因"))
        else:
            result.renamed.append((item.source.name, item.target_name))
    return result


def format_preview(items: list[RenameItem]) -> str:
    """把改名计划渲染成供用户确认的预览文本。"""
    lines: list[str] = []
    result = summarize_plan(items)
    for old_name, new_name in result.renamed:
        lines.append(f"  改名：{old_name}  ->  {new_name}")
    for old_name, reason in result.skipped:
        lines.append(f"  跳过：{old_name}（{reason}）")
    lines.append(
        f"合计：将改名 {result.renamed_count} 个，跳过 {result.skipped_count} 个"
    )
    return "\n".join(lines)


def apply_renames(folder: str | Path, items: list[RenameItem]) -> RenameResult:
    """执行改名计划。

    执行前对每个目标再次检查存在性，任何可能覆盖的情况都改为跳过。
    """
    root = Path(folder)
    result = RenameResult()
    for item in items:
        old_name = item.source.name
        if item.skipped:
            result.skipped.append((old_name, item.reason or "未知原因"))
            continue
        src = root / old_name
        dst = root / item.target_name
        if not src.exists():
            result.skipped.append((old_name, "计划生成后原文件已不存在"))
            continue
        if dst.exists():
            result.skipped.append((old_name, f"目标文件 {item.target_name} 已存在，为避免覆盖已跳过"))
            continue
        src.rename(dst)
        result.renamed.append((old_name, item.target_name))
    return result

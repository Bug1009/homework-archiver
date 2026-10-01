# 作业文件批量归档脚本（homework-archiver）

计算机协会项目开发部 · 部门卷素材 **pdd-03**。

用 Python 标准库实现的作业文件整理小工具，零第三方运行依赖。三个需求分别通过三个 PR 增量交付：

- [ ] **需求 1 · 扫描与列出**（PR #1）
- [ ] **需求 2 · 批量改名**（PR #2，先预览后确认、绝不覆盖）
- [ ] **需求 3 · 归档与报告 / 撤销上次操作**（PR #3）

## 安全原则

1. **默认只预览（dry-run）**：`rename` / `archive` 不带 `--apply` 时绝不改动磁盘。
2. **先打印、再确认、后执行**：执行前完整列出每个改动，需输入 `y` 确认。
3. **绝不覆盖**：目标文件已存在（含批次内多个文件指向同一新名）一律跳过并在报告中写明原因。
4. **可撤销**：每次实际执行都会写一份操作日志，`undo` 可完整回滚上一次批量操作。

## 目录结构

```
homework_archiver/
├── __init__.py
├── scanner.py    # 需求1：扫描与列出
├── renamer.py    # 需求2：批量改名
├── journal.py    # 需求3：操作日志与撤销
├── archiver.py   # 需求3：按学期归档 + 整理报告
└── cli.py        # 命令行入口
tests/            # pytest 测试，GitHub Actions 云端运行
```

## 环境要求

- Python 3.11+（仅用标准库；运行测试需要 pytest）

## 本地开发与测试

```bash
pip install pytest
pytest -q
```

每次推送到分支和 PR 都会在 GitHub Actions（Ubuntu + Python 3.11/3.12）上自动跑测试。

## 命令一览（随 PR 逐步开放）

```bash
# 需求1：扫描文件夹，可按扩展名过滤
python -m homework_archiver scan ./作业 --ext .docx --ext .pdf

# 需求2：预览改名（默认不动盘），确认后加 --apply
python -m homework_archiver rename ./作业
python -m homework_archiver rename ./作业 --apply

# 需求3：按学期归档、出报告，支持撤销上次操作
python -m homework_archiver archive ./作业
python -m homework_archiver archive ./作业 --apply
python -m homework_archiver undo ./作业
```

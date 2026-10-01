"""进程级入口测试：保证 README 里的 python -m homework_archiver 真的能跑。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_m_package_entrypoint_scan_empty(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, "-m", "homework_archiver", "scan", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "没有符合条件的文件" in proc.stdout


def test_python_m_package_entrypoint_scan_pdf(tmp_path: Path):
    (tmp_path / "作业.pdf").write_bytes(b"x")
    (tmp_path / "笔记.txt").write_bytes(b"x")

    proc = subprocess.run(
        [sys.executable, "-m", "homework_archiver", "scan", str(tmp_path), "--ext", ".pdf"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "作业.pdf" in proc.stdout
    assert "笔记.txt" not in proc.stdout
    assert "共 1 个文件" in proc.stdout


def test_python_m_package_version():
    proc = subprocess.run(
        [sys.executable, "-m", "homework_archiver", "--version"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "homework-archiver" in proc.stdout

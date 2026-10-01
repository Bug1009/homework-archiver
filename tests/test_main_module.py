"""进程级入口测试：保证 README 里的 python -m homework_archiver 真的能跑。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_python_m_package_entrypoint_scan(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, "-m", "homework_archiver", "scan", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "共 0 个文件" in proc.stdout


def test_python_m_package_version():
    proc = subprocess.run(
        [sys.executable, "-m", "homework_archiver", "--version"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "homework-archiver" in proc.stdout

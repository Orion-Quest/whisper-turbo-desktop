from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path


def test_app_import_does_not_load_whisper_or_torch() -> None:
    project_root = Path(__file__).resolve().parents[1]
    code = r'''
import importlib.abc
import sys

class BlockHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "torch" or fullname == "whisper":
            raise AssertionError(f"{fullname} must be imported only when transcription starts")
        return None

sys.meta_path.insert(0, BlockHeavyImports())
import whisper_turbo_desktop.app
print("ok")
'''
    env = dict(os.environ)
    src_path = str(project_root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_installed_entry_point_is_gui_script() -> None:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert "whisper-turbo-desktop" not in pyproject["project"].get("scripts", {})
    assert pyproject["project"]["gui-scripts"]["whisper-turbo-desktop"] == (
        "whisper_turbo_desktop.app:main"
    )

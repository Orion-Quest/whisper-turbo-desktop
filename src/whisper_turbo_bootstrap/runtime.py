from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLES = []


def configure_bootstrap_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return

    app_dir = Path(sys.executable).resolve().parent
    internal_dir = app_dir / "_internal"
    tcl_dir = internal_dir / "_tcl_data"
    tk_dir = internal_dir / "_tk_data"
    internal_dir_str = str(internal_dir)

    if internal_dir.exists():
        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(os.pathsep) if current_path else []
        if internal_dir_str not in path_parts:
            os.environ["PATH"] = internal_dir_str + os.pathsep + current_path if current_path else internal_dir_str

        if hasattr(os, "add_dll_directory"):
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(internal_dir_str))

    if tcl_dir.exists():
        os.environ["TCL_LIBRARY"] = str(tcl_dir)
    if tk_dir.exists():
        os.environ["TK_LIBRARY"] = str(tk_dir)

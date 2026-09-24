"""Working files for a migration live next to the tool, not on the Desktop."""

from __future__ import annotations

from pathlib import Path


def tool_root() -> Path:
    """Directory that contains this project (pyproject.toml), or the current directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "antigravity_mac_migrate").is_dir():
            return parent
    return Path.cwd()


def default_report_dir() -> Path:
    return tool_root() / "migrate-work"

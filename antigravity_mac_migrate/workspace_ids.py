"""VS Code workspaceStorage ID algorithms used by Antigravity IDE and Antigravity 2.0."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceIdResult:
    workspace_id: str
    fs_path_for_hash: str
    stat_salt: str | None
    kind: str  # "folder" | "code-workspace"


def compute_folder_workspace_id(path: Path) -> WorkspaceIdResult:
    """md5(fsPath + birthtimeMs) on macOS, matching VS Code."""
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_dir():
        raise NotADirectoryError(path)
    fs_path = _posix_fs_path(path)
    salt = _macos_birthtime_ms(path)
    hasher = hashlib.md5()
    hasher.update(fs_path.encode("utf-8"))
    hasher.update(salt.encode("utf-8"))
    return WorkspaceIdResult(
        workspace_id=hasher.hexdigest(),
        fs_path_for_hash=fs_path,
        stat_salt=salt,
        kind="folder",
    )


def compute_code_workspace_id(path: Path) -> WorkspaceIdResult:
    """md5(lowercase originalFSPath) on macOS for .code-workspace files."""
    fs_path = _posix_fs_path(path).lower()
    hasher = hashlib.md5()
    hasher.update(fs_path.encode("utf-8"))
    return WorkspaceIdResult(
        workspace_id=hasher.hexdigest(),
        fs_path_for_hash=fs_path,
        stat_salt=None,
        kind="code-workspace",
    )


def compute_workspace_id(path: Path) -> WorkspaceIdResult:
    if path.suffix.lower() == ".code-workspace" or path.is_file():
        return compute_code_workspace_id(path)
    return compute_folder_workspace_id(path)


def _posix_fs_path(path: Path) -> str:
    # Do not resolve() symlinks: Cursor hashes the path it opened.
    return path.absolute().as_posix()


def _macos_birthtime_ms(path: Path) -> str:
    stat = os.stat(path)
    birth_s = getattr(stat, "st_birthtime", None)
    if birth_s is None:
        birth_s = stat.st_ctime
    return str(int(birth_s * 1000))

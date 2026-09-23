"""Skills discovery and optional rename of path-encoded directories."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from antigravity_mac_migrate.paths import PathRewriter, project_dir_name
from antigravity_mac_migrate.profiles import ResolvedProfile

# Brain folders are conversation UUIDs. Only names that encode a Windows path qualify.
ENCODED_WINDOWS_DIR_RE = re.compile(r"^[A-Za-z]-Users(?:-|$)")


def list_skills(profiles: list[ResolvedProfile]) -> list[Path]:
    found: set[Path] = set()
    for profile in profiles:
        for root in profile.skill_dirs:
            if not root.is_dir():
                continue
            for skill in root.rglob("SKILL.md"):
                found.add(skill.parent)
    return sorted(found)


def rename_encoded_dirs(
    profiles: list[ResolvedProfile],
    rewriter: PathRewriter,
    windows_paths: list[str],
    *,
    dry_run: bool = False,
) -> list[tuple[str, str, str]]:
    """Rename a directory only when its name is an encoded Windows path.

    Conversation UUID folders under ``brain/`` are left alone. A name collision
    is reported and the existing directory is not overwritten.
    """
    changes: list[tuple[str, str, str]] = []
    seen: set[Path] = set()
    for profile in profiles:
        for root in profile.content_dirs:
            if not root.is_dir():
                continue
            for directory in _encoded_directories(root):
                if directory in seen:
                    continue
                seen.add(directory)
                changes.extend(
                    _rename_one(directory, rewriter, windows_paths, dry_run=dry_run)
                )
    return changes


def _encoded_directories(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_dir():
            continue
        if any("mac-migrate-backup" in part for part in path.parts):
            continue
        if ENCODED_WINDOWS_DIR_RE.match(path.name):
            found.append(path)
    return found


def _rename_one(
    directory: Path,
    rewriter: PathRewriter,
    windows_paths: list[str],
    *,
    dry_run: bool,
) -> list[tuple[str, str, str]]:
    old_name = directory.name
    for windows in windows_paths:
        if project_dir_name(windows) != old_name:
            continue
        mac = rewriter.rewrite_string(windows)
        if mac == windows:
            continue
        new_name = project_dir_name(mac)
        if not new_name or new_name == old_name:
            continue
        dest = directory.parent / new_name
        if dest.exists():
            return [(old_name, new_name, "collision")]
        if not dry_run:
            shutil.move(str(directory), str(dest))
        return [(old_name, new_name, "renamed")]
    return []

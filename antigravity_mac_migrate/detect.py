"""Scan copied Antigravity data for Windows paths that still need a map."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_mac_migrate.files_rewrite import iter_protobuf_files, iter_text_files
from antigravity_mac_migrate.mapping import default_python
from antigravity_mac_migrate.paths import extract_windows_paths, suggest_roots
from antigravity_mac_migrate.profiles import ResolvedProfile
from antigravity_mac_migrate.sqlite_rewrite import (
    _quote_ident,
    format_skipped_sqlite,
    is_sqlite_file,
    iter_sqlite_files,
)
from antigravity_mac_migrate.workspace_relink import (
    file_uri_to_native,
    read_workspace_json,
    workspace_target_from_json,
)


@dataclass
class ScanResult:
    windows_paths: Counter = field(default_factory=Counter)
    workspace_uris: list[tuple[str, str, str]] = field(default_factory=list)
    skills: list[Path] = field(default_factory=list)
    code_workspaces: list[str] = field(default_factory=list)
    python_hits: list[str] = field(default_factory=list)
    intellij_hits: list[str] = field(default_factory=list)
    files_with_windows: list[Path] = field(default_factory=list)
    protobuf_files: list[Path] = field(default_factory=list)
    skipped_binary: list[str] = field(default_factory=list)
    skipped_sqlite: list[str] = field(default_factory=list)


def scan_profiles(profiles: list[ResolvedProfile]) -> ScanResult:
    result = ScanResult()
    roots: list[Path] = []
    user_dirs: list[Path] = []
    for profile in profiles:
        roots.extend(profile.content_dirs)
        roots.extend(profile.extra_files)
        user_dirs.extend(profile.user_dirs)
        for skill_dir in profile.skill_dirs:
            if skill_dir.is_dir():
                result.skills.extend(sorted(skill_dir.rglob("SKILL.md")))
    result.skills = sorted({path.parent for path in result.skills})

    for root in roots:
        if not root.exists():
            continue
        for path in iter_text_files(root):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found = extract_windows_paths(text)
            if found:
                result.files_with_windows.append(path)
            for item in found:
                result.windows_paths[item] += 1
                _classify(item, text, result)

    for user_dir in user_dirs:
        storage = user_dir / "workspaceStorage"
        if not storage.is_dir():
            continue
        for entry in storage.iterdir():
            meta = entry / "workspace.json"
            if not meta.exists():
                continue
            try:
                data = read_workspace_json(meta)
            except (OSError, json.JSONDecodeError):
                continue
            target = workspace_target_from_json(data)
            if not target:
                continue
            kind, uri = target
            result.workspace_uris.append((entry.name, kind, uri))
            native = file_uri_to_native(uri)
            for item in extract_windows_paths(native) or [native]:
                result.windows_paths[item] += 1
            if kind == "workspace":
                result.code_workspaces.append(native)

    for db in iter_sqlite_files(roots):
        _scan_sqlite(db, result)

    result.protobuf_files = iter_protobuf_files(roots)
    return result


def _scan_sqlite(db_path: Path, result: ScanResult) -> None:
    if not is_sqlite_file(db_path):
        result.skipped_sqlite.append(
            format_skipped_sqlite(
                db_path,
                "skipped during preview: empty file or not a SQLite database",
            )
        )
        return
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        result.skipped_sqlite.append(
            format_skipped_sqlite(db_path, f"skipped during preview: {exc}")
        )
        return
    try:
        try:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            ]
        except sqlite3.DatabaseError as exc:
            result.skipped_sqlite.append(
                format_skipped_sqlite(
                    db_path, f"skipped during preview: database unreadable: {exc}"
                )
            )
            return
        for table in tables:
            if str(table).startswith("sqlite_"):
                continue
            quoted = _quote_ident(str(table))
            try:
                columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quoted})")]
                rows = conn.execute(f"SELECT * FROM {quoted}")
            except sqlite3.Error:
                continue
            for row in rows:
                for column, value in zip(columns, row):
                    if isinstance(value, bytes):
                        try:
                            value.decode("utf-8")
                        except UnicodeDecodeError:
                            key_note = ""
                            if "key" in columns:
                                key_note = f" key={row[columns.index('key')]!s}"
                            result.skipped_binary.append(
                                f"{db_path} table={table}{key_note} column={column}"
                            )
                            continue
                    text = _cell_text(value)
                    if not text:
                        continue
                    found = extract_windows_paths(text)
                    for item in found:
                        result.windows_paths[item] += 1
                        _classify(item, text, result)
    finally:
        conn.close()


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    return str(value)


def _classify(path: str, blob: str, result: ScanResult) -> None:
    lower = (path + " " + blob[:200]).lower()
    if "python.exe" in lower or "\\python\\" in lower or "/python/" in path.lower():
        if path not in result.python_hits:
            result.python_hits.append(path)
    if "idea64.exe" in lower or "intellij" in lower or "jetbrains" in lower:
        if path not in result.intellij_hits:
            result.intellij_hits.append(path)


def proposed_map(scan: ScanResult, mac_home: Path) -> dict:
    roots = suggest_roots(list(scan.windows_paths))
    homes = [root for root in roots if _looks_like_home(root)]
    workspaces = list(scan.code_workspaces)
    other = [root for root in roots if root not in homes and not root.lower().endswith(".code-workspace")]
    win_home = homes[0] if homes else r"C:\Users\WINDOWS_USER"
    return {
        "homes": {"windows": win_home, "mac": str(mac_home)},
        "roots": [
            {
                "windows": root,
                "mac": _guess_mac(root, win_home, mac_home),
                "kind": "folder",
            }
            for root in other
        ],
        "workspaces": [
            {
                "windows": workspace,
                "mac": _guess_mac(workspace, win_home, mac_home),
            }
            for workspace in sorted(set(workspaces))
        ],
        "tools": {
            "python": default_python() or "/usr/bin/python3",
            "intellij": "/Applications/IntelliJ IDEA.app",
        },
    }


def _looks_like_home(path: str) -> bool:
    parts = path.replace("/", "\\").split("\\")
    return len(parts) == 3 and parts[1].lower() == "users"


def _guess_mac(windows: str, win_home: str, mac_home: Path) -> str:
    from antigravity_mac_migrate.paths import normalize_windows_path, to_posix

    win = normalize_windows_path(windows)
    home = normalize_windows_path(win_home)
    if win.lower().startswith(home.lower()):
        suffix = win[len(home) :].replace("\\", "/")
        return to_posix(str(mac_home) + suffix)
    slug = win.replace("\\", "_")
    return f"FILL_IN_MAC_PATH_FOR_{slug}"

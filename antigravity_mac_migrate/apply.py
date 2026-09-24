"""Apply the Windows to macOS remap across the copied Antigravity trees."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from antigravity_mac_migrate.detect import scan_profiles
from antigravity_mac_migrate.extensions import iter_extensions
from antigravity_mac_migrate.files_rewrite import (
    SKIP_DIR_NAMES,
    iter_protobuf_files,
    iter_repo_context_files,
    iter_text_files,
    rewrite_file,
)
from antigravity_mac_migrate.mapping import PathMap, RootMap, missing_mac_targets
from antigravity_mac_migrate.profiles import ResolvedProfile
from antigravity_mac_migrate.skills import list_skills, rename_encoded_dirs
from antigravity_mac_migrate.sqlite_rewrite import checkpoint_and_copy, iter_sqlite_files, rewrite_db
from antigravity_mac_migrate.workspace_relink import RelinkResult, relink_workspaces


@dataclass
class ApplyReport:
    backup_dir: Path | None
    relink: RelinkResult
    sqlite: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    backup_dirs: list[str] = field(default_factory=list)
    protobuf_files: list[str] = field(default_factory=list)
    skipped_binary: list[str] = field(default_factory=list)


def apply_map(
    path_map: PathMap,
    *,
    dry_run: bool = False,
    skip_missing: bool = False,
    rewrite_roots: list[RootMap] | None = None,
) -> ApplyReport:
    missing = missing_mac_targets(path_map)
    warnings = list(missing)
    if missing and not skip_missing and not dry_run:
        raise SystemExit(
            "These Mac paths do not exist yet:\n  - "
            + "\n  - ".join(missing)
            + "\n\nCreate or clone them, edit path-map.json, or pass --allow-missing to continue."
        )

    profiles = list(path_map.profiles)
    scan_roots = _scan_roots(profiles)
    user_dirs = _existing_user_dirs(profiles)
    pre_scan = scan_profiles(profiles) if profiles else None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dirs: list[Path] = []
    if not dry_run:
        for db in iter_sqlite_files(scan_roots):
            base = _backup_sqlite(db, profiles, stamp)
            if base is not None:
                backup_dirs.append(base)

    merged = RelinkResult()
    for user_dir in user_dirs:
        relink = relink_workspaces(user_dir, path_map, dry_run=dry_run)
        merged.items.extend(relink.items)
        merged.id_map.update(relink.id_map)

    rewriter = _string_rewriter(path_map, rewrite_roots, merged.id_map)
    file_roots = _file_roots(path_map, rewrite_roots)
    report = ApplyReport(
        backup_dir=backup_dirs[0] if backup_dirs else None,
        relink=merged,
        warnings=warnings,
        backup_dirs=_unique_strs(backup_dirs),
        skills=[str(path) for path in list_skills(profiles)],
    )

    for db in iter_sqlite_files(scan_roots):
        stats = rewrite_db(db, rewriter, dry_run=dry_run)
        if stats.rows_changed:
            report.sqlite.append(
                f"{db}: {stats.rows_changed} rows rewritten ({stats.rows_seen} scanned)"
            )
        if stats.skipped_binary:
            report.skipped_binary.extend(stats.skipped_binary_notes)
            report.warnings.append(
                f"{db}: {stats.skipped_binary} binary SQLite cell(s) left unchanged. "
                "Paths inside those cells were not rewritten. If a sidebar index is in "
                "this list, those titles were not remapped."
            )
        report.warnings.extend(stats.warnings)

    rewritten: set[Path] = set()
    for path in _text_targets(profiles):
        _rewrite_once(path, rewriter, rewritten, report, dry_run=dry_run)

    for root in file_roots:
        base = Path(root.mac)
        if root.kind == "workspace" or base.suffix.lower() == ".code-workspace":
            if base.is_file():
                _rewrite_once(base, rewriter, rewritten, report, dry_run=dry_run)
            elif not base.exists() and not dry_run and root.kind == "workspace":
                report.warnings.append(f"workspace file not on disk yet: {root.mac}")
            continue
        if not _should_scan_repo(base):
            continue
        for path in iter_repo_context_files(base):
            _rewrite_once(path, rewriter, rewritten, report, dry_run=dry_run)
        for path in _nested_workspace_files(base):
            _rewrite_once(path, rewriter, rewritten, report, dry_run=dry_run)

    windows_paths = list(pre_scan.windows_paths) if pre_scan else _windows_from_map(path_map)
    if not windows_paths:
        windows_paths = _windows_from_map(path_map)
    for old, new, status in rename_encoded_dirs(
        profiles,
        rewriter,
        windows_paths,
        dry_run=dry_run,
    ):
        report.projects.append(f"{old} -> {new} ({status})")

    report.protobuf_files = [str(path) for path in iter_protobuf_files(scan_roots)]
    if report.protobuf_files:
        report.warnings.append(
            f"{len(report.protobuf_files)} protobuf .pb file(s) left byte-identical."
        )

    for profile in profiles:
        for dot in profile.dot_dirs:
            for ext in iter_extensions(dot, profile=profile.name):
                if not ext.needs_reinstall:
                    continue
                if profile.name == "ide":
                    report.warnings.append(
                        f"Reinstall IDE extension on Mac: {ext.ext_id} ({ext.reason})"
                    )
                else:
                    report.warnings.append(
                        "Windows-native extension left in place for "
                        f"{profile.name}: {ext.ext_id} ({ext.reason}). "
                        "The 2.0 install command is not confirmed, so it was not reinstalled."
                    )
    return report


def _file_roots(path_map: PathMap, rewrite_roots: list[RootMap] | None) -> list[RootMap]:
    """Prefix roots used for string replacement, plus the narrow attach map.

    ``rewrite_roots`` is the Windows home and ``--also`` prefixes. The narrow
    map stays responsible for which ``workspaceStorage`` entries are moved.
    """
    if not rewrite_roots:
        return list(path_map.roots)
    return [*rewrite_roots, *path_map.roots]


def _string_rewriter(
    path_map: PathMap,
    rewrite_roots: list[RootMap] | None,
    id_map: dict[str, str],
):
    broader = PathMap(
        roots=_file_roots(path_map, rewrite_roots),
        python=path_map.python,
        intellij=path_map.intellij,
        profiles=list(path_map.profiles),
    )
    return broader.rewriter(id_map)


def _rewrite_once(
    path: Path,
    rewriter,
    rewritten: set[Path],
    report: ApplyReport,
    *,
    dry_run: bool,
) -> None:
    if path.suffix.lower() == ".pb":
        return
    try:
        key = path.resolve()
    except OSError:
        key = path
    if key in rewritten:
        return
    rewritten.add(key)
    stats = rewrite_file(path, rewriter, dry_run=dry_run)
    if stats.changed:
        report.files.append(str(path))


def _nested_workspace_files(base: Path) -> list[Path]:
    """``.code-workspace`` files inside a mapped folder, not the whole home."""
    skip = set(SKIP_DIR_NAMES) | {".venv", "venv"}
    found: list[Path] = []
    for path in base.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".code-workspace":
            continue
        if any(part in skip or "mac-migrate-backup" in part for part in path.parts):
            continue
        try:
            depth = len(path.relative_to(base).parts)
        except ValueError:
            continue
        if depth > 6:
            continue
        found.append(path)
    return found


def _scan_roots(profiles: list[ResolvedProfile]) -> list[Path]:
    roots: list[Path] = []
    for profile in profiles:
        for path in (*profile.content_dirs, *profile.extra_files):
            if path.exists():
                roots.append(path)
    return roots


def _existing_user_dirs(profiles: list[ResolvedProfile]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for profile in profiles:
        for path in profile.user_dirs:
            if path.is_dir() and path not in seen:
                seen.add(path)
                found.append(path)
    return found


def _text_targets(profiles: list[ResolvedProfile]) -> list[Path]:
    files: list[Path] = []
    for profile in profiles:
        for root in profile.content_dirs:
            files.extend(iter_text_files(root))
        for extra in profile.extra_files:
            if extra.is_file() and extra.suffix.lower() != ".pb":
                files.append(extra)
    return files


def _should_scan_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    home = Path.home()
    try:
        if path.resolve() == home.resolve():
            return False
    except OSError:
        return True
    return True


def _backup_sqlite(db: Path, profiles: list[ResolvedProfile], stamp: str) -> Path | None:
    anchors: list[Path] = []
    for profile in profiles:
        anchors.extend(profile.user_dirs)
        anchors.extend(profile.content_dirs)
    anchors.sort(key=lambda path: len(path.as_posix()), reverse=True)
    for anchor in anchors:
        try:
            relative = db.relative_to(anchor)
        except ValueError:
            continue
        if anchor.name == "User":
            base = anchor.parent / f"User.mac-migrate-backup-{stamp}"
        else:
            base = anchor.parent / f"{anchor.name}.mac-migrate-backup-{stamp}"
        checkpoint_and_copy(db, base / "sqlite" / relative)
        return base
    fallback = db.parent / f"{db.name}.mac-migrate-backup-{stamp}"
    checkpoint_and_copy(db, fallback / db.name)
    return fallback


def _windows_from_map(path_map: PathMap) -> list[str]:
    return [root.windows for root in path_map.roots]


def _unique_strs(paths: list[Path]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for path in paths:
        text = str(path)
        if text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def write_report(report: ApplyReport, path: Path) -> None:
    payload = {
        "backup_dir": str(report.backup_dir) if report.backup_dir else None,
        "backup_dirs": report.backup_dirs,
        "relink": [
            {
                "old_id": item.old_id,
                "new_id": item.new_id,
                "windows_uri": item.windows_uri,
                "mac_path": item.mac_path,
                "kind": item.kind,
                "status": item.status,
                "detail": item.detail,
            }
            for item in report.relink.items
        ],
        "id_map": report.relink.id_map,
        "sqlite": report.sqlite,
        "files": report.files,
        "projects": report.projects,
        "skills": report.skills,
        "protobuf_files": report.protobuf_files,
        "skipped_binary": report.skipped_binary,
        "warnings": report.warnings,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

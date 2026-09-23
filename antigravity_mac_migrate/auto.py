"""One home-folder mapping that covers every project under that user."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_mac_migrate.detect import ScanResult
from antigravity_mac_migrate.mapping import PathMap, RootMap, default_intellij, default_python
from antigravity_mac_migrate.paths import normalize_windows_path, to_posix
from antigravity_mac_migrate.profiles import ResolvedProfile
from antigravity_mac_migrate.workspace_relink import file_uri_to_native


@dataclass
class AutoPlan:
    path_map: PathMap
    windows_home: str
    mac_home: str
    python: str | None
    intellij: str | None
    prefixes: list[tuple[str, str]] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    ready: list[str] = field(default_factory=list)
    ready_pairs: list[tuple[str, str]] = field(default_factory=list)
    rename_pairs: list[tuple[str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)
    outside_home: list[str] = field(default_factory=list)


def special_keep_reason(windows_path: str) -> str | None:
    """Paths that were not copied as projects and should stay untouched."""
    folded = windows_path.replace("/", "\\").lower()
    if "\\.git\\worktrees\\" in folded or "\\.cursor\\worktrees\\" in folded:
        return "worktree"
    if "\\appdata\\roaming\\antigravity" in folded:
        return "antigravity-internal"
    if "\\antigravity\\workspaces\\" in folded or "\\antigravity ide\\workspaces\\" in folded:
        return "antigravity-internal"
    return None


def compact_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def index_directory_names(roots: list[Path]) -> dict[str, list[str]]:
    """Map a loose folder name to real Mac directories under the copied trees."""
    skip = {".git", "node_modules", "target", ".venv", "venv", "dist", "build"}
    found: dict[str, list[str]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, _filenames in os.walk(root):
            current = Path(dirpath)
            try:
                depth = len(current.relative_to(root).parts)
            except ValueError:
                depth = 0
            if depth > 8:
                dirnames.clear()
                continue
            dirnames[:] = [name for name in dirnames if name not in skip and not name.startswith(".")]
            for name in dirnames:
                key = compact_name(name)
                if not key:
                    continue
                found.setdefault(key, [])
                path = str(current / name)
                if path not in found[key]:
                    found[key].append(path)
    return found


def suggest_renamed_folder(
    windows_path: str,
    translated_mac: str,
    index: dict[str, list[str]],
) -> str | None:
    key = compact_name(Path(windows_path.replace("\\", "/")).name)
    if not key:
        return None
    candidates = [path for path in index.get(key, []) if path != translated_mac]
    if len(candidates) == 1:
        return candidates[0]
    return None


def load_pair_file(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if not path.exists():
        return pairs
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        left, right = line.split("=", 1)
        left, right = left.strip(), right.strip()
        if left and right:
            pairs.append((left, right))
    return pairs


def load_path_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    values: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        values.append(line)
    return values


def _is_dropped(windows_path: str, drop_prefixes: list[str]) -> bool:
    folded = normalize_windows_path(windows_path).lower()
    for prefix in drop_prefixes:
        base = normalize_windows_path(prefix).lower()
        if folded == base or folded.startswith(base + "\\"):
            return True
    return False


def path_map_for_apply(
    plan: AutoPlan,
    renames: list[tuple[str, str]],
    drop_prefixes: list[str],
) -> PathMap:
    """Only exact matches and accepted renames. Missing projects stay as they are."""
    roots: list[RootMap] = []
    seen: set[str] = set()
    for source, target in list(plan.ready_pairs) + [
        (normalize_windows_path(source), target) for source, target in renames
    ]:
        source_n = normalize_windows_path(source)
        if _is_dropped(source_n, drop_prefixes):
            continue
        if source_n.lower() in seen:
            continue
        if not Path(target).exists():
            continue
        seen.add(source_n.lower())
        kind = "workspace" if source_n.lower().endswith(".code-workspace") else "folder"
        roots.append(RootMap(source_n, target, kind))
    return PathMap(
        roots=roots,
        python=plan.python,
        intellij=plan.intellij,
        profiles=list(plan.path_map.profiles),
    )


def translate_prefixes(windows_path: str, prefixes: list[tuple[str, str]]) -> str | None:
    """Rewrite a Windows path using the longest matching prefix."""
    ordered = sorted(
        prefixes,
        key=lambda item: len(normalize_windows_path(item[0])),
        reverse=True,
    )
    for source, target in ordered:
        rewritten = translate_home(windows_path, source, target)
        if rewritten is not None:
            return rewritten
    return None


def translate_home(windows_path: str, windows_home: str, mac_home: str) -> str | None:
    """C:\\Users\\WINDOWS_USER\\Projects\\api -> /Users/MAC_USER/Projects/api."""
    win = normalize_windows_path(windows_path)
    home = normalize_windows_path(windows_home)
    if len(win) < 2 or win[1] != ":":
        return None
    if not win.lower().startswith(home.lower()):
        return None
    if len(win) > len(home) and win[len(home)] not in "\\/":
        return None
    suffix = win[len(home) :].replace("\\", "/")
    return to_posix(str(Path(mac_home)) + suffix)


def build_auto_plan(
    scan: ScanResult,
    windows_home: str,
    mac_home: str,
    *,
    python: str | None = None,
    intellij: str | None = None,
    extra_prefixes: list[tuple[str, str]] | None = None,
    search_roots: list[Path] | None = None,
    profiles: list[ResolvedProfile] | None = None,
) -> AutoPlan:
    mac_home_path = str(Path(mac_home).expanduser())
    py = python or default_python()
    idea = intellij if intellij is not None else default_intellij()
    prefixes = [(normalize_windows_path(windows_home), mac_home_path)]
    for source, target in extra_prefixes or []:
        prefixes.append((normalize_windows_path(source), str(Path(target).expanduser())))
    prefixes.sort(key=lambda item: len(item[0]), reverse=True)
    path_map = PathMap(
        roots=[RootMap(source, target, "folder") for source, target in prefixes],
        python=py,
        intellij=idea,
        profiles=list(profiles or []),
    )
    plan = AutoPlan(
        path_map=path_map,
        windows_home=normalize_windows_path(windows_home),
        mac_home=mac_home_path,
        python=py,
        intellij=idea,
        prefixes=prefixes,
        skills=[path.name for path in scan.skills],
    )
    if search_roots is None:
        search_roots = [Path(target) for _source, target in (extra_prefixes or [])]
    name_index = index_directory_names(search_roots)

    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for _storage_id, kind, uri in scan.workspace_uris:
        native = file_uri_to_native(uri)
        entries.append((kind, native))
    for workspace in scan.code_workspaces:
        entries.append(("workspace", workspace))

    for kind, native in entries:
        key = normalize_windows_path(native) if len(native) >= 2 and native[1] == ":" else native
        if key in seen:
            continue
        seen.add(key)
        mac = translate_prefixes(native, prefixes)
        if mac is None:
            if len(native) >= 2 and native[1] == ":":
                plan.outside_home.append(normalize_windows_path(native))
            else:
                plan.outside_home.append(native)
            continue
        reason = special_keep_reason(native)
        if reason:
            plan.keep.append(f"[{reason}] {native}  ->  {mac}")
            continue
        if Path(mac).exists():
            plan.ready.append(f"{native}  ->  {mac}")
            plan.ready_pairs.append((normalize_windows_path(native), mac))
            if kind == "workspace" or native.lower().endswith(".code-workspace"):
                path_map.roots.append(RootMap(normalize_windows_path(native), mac, "workspace"))
            continue
        renamed = suggest_renamed_folder(native, mac, name_index)
        if renamed:
            plan.rename_pairs.append((normalize_windows_path(native), renamed))
            continue
        plan.missing.append(f"{native}  ->  {mac}")
        plan.keep.append(f"[not-copied] {native}  ->  {mac}")
    return plan

"""Load and validate the Windows to macOS path map."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_mac_migrate.paths import PathRewriter, Replacement, replacement_pairs, to_posix
from antigravity_mac_migrate.profiles import (
    ResolvedProfile,
    support_dir,
)


@dataclass
class RootMap:
    windows: str
    mac: str
    kind: str = "folder"  # folder | workspace | home | tool


@dataclass
class PathMap:
    roots: list[RootMap] = field(default_factory=list)
    python: str | None = None
    intellij: str | None = None
    profiles: list[ResolvedProfile] = field(default_factory=list)

    def rewriter(self, id_map: dict[str, str] | None = None) -> PathRewriter:
        pairs: list[Replacement] = []
        for root in sorted(self.roots, key=lambda item: len(item.windows), reverse=True):
            if _is_windows_path(root.windows) and root.mac:
                pairs.extend(replacement_pairs(root.windows, root.mac))
        extra: dict[str, str] = dict(id_map or {})
        return PathRewriter(
            pairs,
            extra_id_map=extra,
            python=self.python,
            intellij=self.intellij,
        )

    def mac_for_windows(self, windows_path: str) -> str | None:
        rewriter = self.rewriter()
        rewritten = rewriter.rewrite_string(windows_path)
        if rewritten == windows_path:
            alt = rewriter.rewrite_string(windows_path.replace("/", "\\"))
            if alt != windows_path.replace("/", "\\"):
                return alt
            return None
        return rewritten


def _is_windows_path(value: str) -> bool:
    return len(value) >= 2 and value[1] == ":"


def default_python() -> str | None:
    return shutil.which("python3") or shutil.which("python")


def default_intellij() -> str | None:
    apps = sorted(Path("/Applications").glob("IntelliJ IDEA*.app"))
    if apps:
        return str(apps[0])
    return None


def load_path_map(path: Path) -> PathMap:
    data = json.loads(path.read_text(encoding="utf-8"))
    roots: list[RootMap] = []
    homes = data.get("homes") or {}
    if homes.get("windows") and homes.get("mac"):
        roots.append(RootMap(homes["windows"], homes["mac"], "home"))
    for item in data.get("roots") or []:
        roots.append(
            RootMap(
                windows=item["windows"],
                mac=item["mac"],
                kind=item.get("kind", "folder"),
            )
        )
    for item in data.get("workspaces") or []:
        roots.append(
            RootMap(
                windows=item["windows"],
                mac=item["mac"],
                kind="workspace",
            )
        )
    tools = data.get("tools") or {}
    return PathMap(
        roots=roots,
        python=tools.get("python") or default_python(),
        intellij=tools.get("intellij") or default_intellij(),
    )


def dump_path_map(path_map: PathMap, home: Path | None = None) -> dict:
    homes = next((root for root in path_map.roots if root.kind == "home"), None)
    workspaces = [root for root in path_map.roots if root.kind == "workspace"]
    roots = [root for root in path_map.roots if root.kind not in {"home", "workspace"}]
    base = home or Path.home()
    return {
        "homes": {
            "windows": homes.windows if homes else r"C:\Users\WINDOWS_USER",
            "mac": homes.mac if homes else "/Users/MAC_USER",
        },
        "roots": [
            {"windows": root.windows, "mac": root.mac, "kind": root.kind} for root in roots
        ],
        "workspaces": [
            {"windows": root.windows, "mac": root.mac} for root in workspaces
        ],
        "tools": {
            "python": path_map.python or "/usr/bin/python3",
            "intellij": path_map.intellij or "/Applications/IntelliJ IDEA.app",
        },
        "profiles": _profile_block(path_map.profiles, base),
    }


def _profile_block(profiles: list[ResolvedProfile], home: Path) -> dict:
    by_name = {profile.name: profile for profile in profiles}

    def first(name: str, attr: str, fallback: Path) -> str:
        profile = by_name.get(name)
        if profile is None:
            return str(fallback)
        values = getattr(profile, attr)
        if not values:
            return str(fallback)
        return str(values[0])

    return {
        "ide_user_dir": first(
            "ide",
            "user_dirs",
            support_dir(home, "Antigravity IDE") / "User",
        ),
        "ide_dot_dir": first("ide", "dot_dirs", home / ".antigravity-ide"),
        "ide_gemini_dir": _gemini_member(by_name.get("ide"), home / ".gemini" / "antigravity-ide"),
        "app_user_dir": first(
            "app",
            "user_dirs",
            support_dir(home, "Antigravity") / "User",
        ),
        "app_dot_dir": first("app", "dot_dirs", home / ".antigravity"),
        "app_gemini_dir": _gemini_member(by_name.get("app"), home / ".gemini" / "antigravity"),
        "gemini_home": str(home / ".gemini"),
        "cli_dir": _gemini_member(by_name.get("cli"), home / ".gemini" / "antigravity-cli"),
    }


def _gemini_member(profile: ResolvedProfile | None, fallback: Path) -> str:
    if profile is None:
        return str(fallback)
    for path in profile.content_dirs:
        if path.name in {"antigravity-ide", "antigravity", "antigravity-cli"}:
            return str(path)
    return str(fallback)


def missing_mac_targets(path_map: PathMap) -> list[str]:
    missing: list[str] = []
    for root in path_map.roots:
        mac = to_posix(root.mac)
        if not mac or mac.startswith("FILL_") or "YOUR_" in mac:
            missing.append(f"{root.windows} -> (empty mac path)")
            continue
        target = Path(mac)
        if root.kind == "workspace":
            if not target.exists():
                missing.append(f"workspace file missing: {mac}")
        else:
            if not target.exists():
                missing.append(f"folder missing: {mac}")
    if path_map.python and not Path(path_map.python).exists():
        missing.append(f"python missing: {path_map.python}")
    return missing

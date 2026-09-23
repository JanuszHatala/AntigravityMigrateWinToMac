"""Detect Windows-native extensions that need a Mac reinstall."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LIKELY_NATIVE_IDS = {
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-vscode.cpptools",
    "ms-dotnettools.csharp",
    "rust-lang.rust-analyzer",
    "ms-vscode.cmake-tools",
    "vadimcn.vscode-lldb",
    "ms-vscode.powershell",
}

_IDE_CLI_NAMES = ("antigravity", "antigravity-ide")


@dataclass
class ExtensionInfo:
    ext_id: str
    path: Path
    needs_reinstall: bool
    reason: str
    profile: str = ""


def _ide_bin_dirs() -> list[Path]:
    return [
        Path("/Applications/Antigravity IDE.app/Contents/Resources/app/bin"),
        Path.home() / "Applications/Antigravity IDE.app/Contents/Resources/app/bin",
        Path("/usr/local/bin"),
        Path("/opt/homebrew/bin"),
    ]


def _native_binary_suffix(folder: Path) -> str:
    suffixes = (".dll", ".exe", ".node")
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [name for name in dirnames if name not in {"node_modules", ".git"}]
        if Path(dirpath) != folder and len(Path(dirpath).relative_to(folder).parts) > 4:
            dirnames.clear()
            continue
        for name in filenames:
            lower = name.lower()
            for suffix in suffixes:
                if lower.endswith(suffix):
                    return suffix
    return ""


def ide_cli() -> str | None:
    """Find the Antigravity IDE shell command. Do not use the separate ``agy`` CLI."""
    for directory in _ide_bin_dirs():
        for name in _IDE_CLI_NAMES:
            candidate = directory / name
            if candidate.is_file():
                return str(candidate)
    for name in _IDE_CLI_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for directory in _ide_bin_dirs()[:2]:
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if not child.is_file() or child.name.startswith("."):
                continue
            if child.suffix.lower() in {".cmd", ".bat", ".ps1"}:
                continue
            if os.access(child, os.X_OK):
                return str(child)
    return None


def iter_extensions(dot_dir: Path, *, profile: str = "") -> list[ExtensionInfo]:
    root = dot_dir / "extensions"
    if not root.is_dir():
        return []
    found: list[ExtensionInfo] = []
    for manifest in root.glob("*/package.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        publisher = str(data.get("publisher") or "")
        name = str(data.get("name") or manifest.parent.name)
        ext_id = f"{publisher}.{name}".lower() if publisher else manifest.parent.name.lower()
        folder = manifest.parent.name.lower()
        reason = ""
        needs = False
        if "win32" in folder or folder.endswith("-windows"):
            needs = True
            reason = "extension folder is a Windows build"
        elif any(ext_id.startswith(native) for native in LIKELY_NATIVE_IDS):
            needs = True
            reason = "ships native binaries; reinstall the darwin build"
        else:
            for hint in ("win32-x64", "win32-arm64"):
                if (manifest.parent / hint).exists():
                    needs = True
                    reason = f"contains {hint}"
                    break
            if not needs:
                native_suffix = _native_binary_suffix(manifest.parent)
                if native_suffix:
                    needs = True
                    reason = f"contains {native_suffix}"
        found.append(ExtensionInfo(ext_id, manifest.parent, needs, reason, profile))
    return found


def reinstall(ext_ids: list[str]) -> list[tuple[str, int, str]]:
    """Force-reinstall IDE extensions. The 2.0 CLI name is not confirmed, so this is IDE-only."""
    cli = ide_cli()
    if not cli:
        raise SystemExit(
            "Could not find the Antigravity IDE CLI. Looked on PATH and in "
            "'Antigravity IDE.app/Contents/Resources/app/bin' for 'antigravity' or "
            "'antigravity-ide'. The separate 'agy' command is not used for IDE extensions. "
            "Install the IDE shell command from the Command Palette, then retry."
        )
    results: list[tuple[str, int, str]] = []
    for ext_id in ext_ids:
        proc = subprocess.run(
            [cli, "--install-extension", ext_id, "--force"],
            capture_output=True,
            text=True,
            check=False,
        )
        results.append((ext_id, proc.returncode, (proc.stdout + proc.stderr).strip()))
    return results

"""Rewrite Windows paths in Antigravity JSON, markdown, and text files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from antigravity_mac_migrate.paths import PathRewriter, looks_like_windows_path

TEXT_SUFFIXES = {
    ".json",
    ".jsonc",
    ".jsonl",
    ".md",
    ".mdc",
    ".txt",
    ".yml",
    ".yaml",
    ".toml",
    ".pbtxt",
    ".code-workspace",
    ".cursorignore",
    ".css",
    ".js",
    ".ts",
    ".html",
}

SKIP_DIR_NAMES = {
    "Cache",
    "CachedData",
    "CachedExtensionVSIXs",
    "Code Cache",
    "GPUCache",
    "logs",
    "Crashpad",
    "Service Worker",
    "blob_storage",
    "node_modules",
    ".git",
    "extensions",
}

NAMED_TEXT_FILES = {
    "mcp.json",
    "mcp_config.json",
    "hooks.json",
    "cli-config.json",
    "argv.json",
    "settings.json",
    "keybindings.json",
    "workspace.json",
    "storage.json",
    "GEMINI.md",
    "AGENTS.md",
}


@dataclass
class FileRewriteStats:
    path: Path
    changed: bool
    reason: str = ""


def rewrite_file(path: Path, rewriter: PathRewriter, *, dry_run: bool = False) -> FileRewriteStats:
    if path.suffix.lower() == ".pb":
        return FileRewriteStats(path, False, "protobuf-unchanged")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return FileRewriteStats(path, False, f"unreadable: {exc}")
    if b"\x00" in raw[:4096]:
        return FileRewriteStats(path, False, "binary")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return FileRewriteStats(path, False, "not utf-8")
    new_text = _rewrite_text(path, text, rewriter)
    if new_text == text:
        return FileRewriteStats(path, False, "unchanged")
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return FileRewriteStats(path, True, "rewritten")


def _rewrite_text(path: Path, text: str, rewriter: PathRewriter) -> str:
    if path.suffix.lower() in {".json", ".code-workspace"} or path.name.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return rewriter.rewrite_string(text)
        rewritten = rewriter.rewrite_obj(data)
        if rewritten == data:
            return text
        return json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n"
    return rewriter.rewrite_string(text)


def _skipped_dir(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or "mac-migrate-backup" in part for part in path.parts)


def iter_text_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    if root.is_file():
        if root.suffix.lower() == ".pb" or _skipped_dir(root):
            return []
        if root.suffix.lower() in TEXT_SUFFIXES or root.name in NAMED_TEXT_FILES:
            return [root]
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _skipped_dir(path):
            continue
        if path.suffix.lower() == ".pb":
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in NAMED_TEXT_FILES:
            files.append(path)
    return files


def iter_protobuf_files(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        candidates = [root] if root.is_file() else list(root.rglob("*")) if root.is_dir() else []
        for path in candidates:
            if not path.is_file() or path.suffix.lower() != ".pb":
                continue
            if _skipped_dir(path):
                continue
            if path in seen:
                continue
            seen.add(path)
            found.append(path)
    return sorted(found)


def iter_repo_context_files(repo: Path) -> list[Path]:
    """Workspace rules and skills that travel with the repository."""
    if not repo.is_dir():
        return []
    files: list[Path] = []
    for name in ("GEMINI.md", "AGENTS.md"):
        candidate = repo / name
        if candidate.is_file():
            files.append(candidate)
    for dirname in (".agents", ".agent"):
        nested = repo / dirname
        if nested.is_dir():
            files.extend(iter_text_files(nested))
    return files


def scan_file_for_windows(path: Path) -> bool:
    if path.suffix.lower() == ".pb":
        return False
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in raw[:1024]:
        return False
    try:
        text = raw.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return False
    return looks_like_windows_path(text)

"""Windows path detection and prefix remapping."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

DRIVE_PATH_RE = re.compile(
    r"(?P<path>(?P<drive>[A-Za-z]):(?:[\\/][^\s\"'<>|*?\n\r]*)?)"
)
FILE_URI_RE = re.compile(
    r"file:///(?P<drive>[A-Za-z])(?:%3A|%3a|:)/(?P<rest>[^\s\"'<>]*)",
    re.IGNORECASE,
)
WIN_EXE_RE = re.compile(
    r"(?i)(?:^|[\\/])(?:python(?:w)?|py|conda|idea64|idea)\.exe\b"
)


def normalize_windows_path(path: str) -> str:
    path = path.strip().strip("\"'")
    path = unquote(path)
    if path.lower().startswith("file:"):
        path = file_uri_to_windows_path(path) or path
    path = path.replace("/", "\\")
    if len(path) >= 2 and path[1] == ":":
        path = path[0].upper() + path[1:]
    return path.rstrip("\\")


def file_uri_to_windows_path(uri: str) -> str | None:
    match = FILE_URI_RE.search(uri)
    if not match:
        if uri.startswith("file:///") and not re.match(r"file:///[A-Za-z](?:%3A|:)", uri):
            return None
        return None
    rest = unquote(match.group("rest")).replace("/", "\\")
    drive = match.group("drive").upper()
    if rest:
        return f"{drive}:\\{rest}".rstrip("\\")
    return f"{drive}:"


def windows_to_file_uri(path: str) -> str:
    path = normalize_windows_path(path)
    drive = path[0].lower()
    rest = path[2:].replace("\\", "/")
    if rest and not rest.startswith("/"):
        rest = "/" + rest
    return f"file:///{drive}%3A{quote(rest, safe='/')}"


def mac_to_file_uri(path: str) -> str:
    posix = to_posix(path)
    if not posix.startswith("/"):
        raise ValueError(f"Expected an absolute macOS path, got {path!r}")
    return "file://" + quote(posix, safe="/")


def to_posix(path: str) -> str:
    return path.replace("\\", "/").rstrip("/")


def project_dir_name(path: str) -> str:
    """Encode a workspace path as a directory name (drive colon and slashes become hyphens)."""
    posix = path.replace("\\", "/")
    posix = posix.replace(":", "")
    posix = posix.lstrip("/")
    return re.sub(r"/+", "-", posix)


@dataclass(frozen=True)
class Replacement:
    source: str
    target: str


def replacement_pairs(windows: str, mac: str) -> list[Replacement]:
    """All string forms Cursor might have stored for one mapped root."""
    win = normalize_windows_path(windows)
    mac_posix = to_posix(mac)
    if len(win) < 2 or win[1] != ":":
        raise ValueError(f"Not a Windows path: {windows!r}")
    if not mac_posix.startswith("/"):
        raise ValueError(f"Not an absolute macOS path: {mac!r}")

    drive_upper = win[0].upper()
    drive_lower = win[0].lower()
    rest_backslash = win[2:]  # starts with \
    rest_slash = rest_backslash.replace("\\", "/")
    rest_posix = rest_slash[1:] if rest_slash.startswith("/") else rest_slash

    pairs: list[Replacement] = []

    def add(src: str, dst: str) -> None:
        if src and src != dst:
            pairs.append(Replacement(src, dst))

    add(f"{drive_upper}:{rest_backslash}", mac_posix)
    add(f"{drive_lower}:{rest_backslash}", mac_posix)
    add(win.replace("\\", "\\\\"), mac_posix)
    add(win.replace("\\", "\\\\").replace(drive_upper, drive_lower, 1), mac_posix)
    add(f"{drive_upper}:{rest_slash}", mac_posix)
    add(f"{drive_lower}:{rest_slash}", mac_posix)
    add(f"{drive_upper}:/{rest_posix}", mac_posix)
    add(f"{drive_lower}:/{rest_posix}", mac_posix)

    add(windows_to_file_uri(win), mac_to_file_uri(mac_posix))
    add(
        f"file:///{drive_lower}:{rest_slash}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_upper}:{rest_slash}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_lower}:/{rest_posix}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_upper}:/{rest_posix}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_lower}%3A/{rest_posix}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_upper}%3A/{rest_posix}",
        mac_to_file_uri(mac_posix),
    )
    add(
        f"file:///{drive_lower}%3a/{rest_posix}",
        mac_to_file_uri(mac_posix),
    )

    add(project_dir_name(win), project_dir_name(mac_posix))
    add(project_dir_name(win.replace("\\", "/")), project_dir_name(mac_posix))

    # JSON object path field used by VS Code URIs
    add(f"/{drive_upper}:{rest_slash}", mac_posix)
    add(f"/{drive_lower}:{rest_slash}", mac_posix)
    add(f"/{drive_upper}:/{rest_posix}", mac_posix)
    add(f"/{drive_lower}:/{rest_posix}", mac_posix)

    # Deduplicate while keeping longest sources first.
    uniq: dict[str, str] = {}
    for pair in pairs:
        uniq.setdefault(pair.source, pair.target)
    ordered = [Replacement(src, dst) for src, dst in uniq.items()]
    ordered.sort(key=lambda item: len(item.source), reverse=True)
    return ordered


class PathRewriter:
    def __init__(
        self,
        pairs: list[Replacement],
        extra_id_map: dict[str, str] | None = None,
        python: str | None = None,
        intellij: str | None = None,
    ):
        self.pairs = sorted(pairs, key=lambda item: len(item.source), reverse=True)
        self.id_map = extra_id_map or {}
        self.python = python
        self.intellij = intellij

    def rewrite_string(self, value: str) -> str:
        if not value:
            return value
        out = value
        for pair in self.pairs:
            if pair.source in out:
                out = replace_path_prefix(out, pair.source, pair.target)
        if out in self.id_map:
            out = self.id_map[out]
        return rewrite_tool_path(out, self.python, self.intellij)

    def rewrite_json_text(self, text: str) -> str:
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return self.rewrite_string(text)
        rewritten = self.rewrite_obj(data)
        if rewritten == data and self.rewrite_string(text) == text:
            return text
        return json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))

    def rewrite_obj(self, obj):
        if isinstance(obj, str):
            maybe = obj
            stripped = maybe.strip()
            if stripped[:1] in "{[" and stripped[-1:] in "}]":
                try:
                    nested = json.loads(maybe)
                except json.JSONDecodeError:
                    return self.rewrite_string(maybe)
                return json.dumps(
                    self.rewrite_obj(nested),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            return self.rewrite_string(maybe)
        if isinstance(obj, list):
            return [self.rewrite_obj(item) for item in obj]
        if isinstance(obj, dict):
            new = {}
            for key, value in obj.items():
                new_key = self.rewrite_string(key) if isinstance(key, str) else key
                new[new_key] = self.rewrite_obj(value)
            ident = new.get("workspaceIdentifier")
            if isinstance(ident, dict):
                old_id = ident.get("id")
                if isinstance(old_id, str) and old_id in self.id_map:
                    ident["id"] = self.id_map[old_id]
            elif (
                isinstance(new.get("id"), str)
                and new["id"] in self.id_map
                and ("uri" in new or "configPath" in new or "folderUri" in new)
            ):
                new["id"] = self.id_map[new["id"]]
            return new
        return obj


def replace_path_prefix(text: str, source: str, target: str) -> str:
    """Replace a Windows path prefix and convert leftover \\ in the path suffix."""
    pieces: list[str] = []
    i = 0
    while True:
        found = text.find(source, i)
        if found < 0:
            pieces.append(text[i:])
            break
        pieces.append(text[i:found])
        pieces.append(target)
        start = found + len(source)
        end = start
        while end < len(text) and text[end] not in "\"'\n\r<>|*?,;()[]{} \t":
            end += 1
        suffix = text[start:end]
        if target.startswith("/"):
            suffix = suffix.replace("\\", "/")
        pieces.append(suffix)
        i = end
    return "".join(pieces)


def rewrite_tool_path(value: str, python: str | None, intellij: str | None) -> str:
    """Replace Windows interpreter / JetBrains executables when the whole value is a path."""
    if not value or "\n" in value or len(value) > 500:
        return value
    compact = value.strip().strip("\"'")
    lower = compact.lower()
    looks_path = (
        "\\" in compact
        or "/" in compact
        or lower.endswith(".exe")
        or lower.endswith(".app")
    )
    if not looks_path:
        return value
    if python and (
        lower.endswith("python.exe")
        or lower.endswith("pythonw.exe")
        or lower.endswith("py.exe")
        or lower.endswith("conda.exe")
        or (lower.endswith(".exe") and "python" in lower)
    ):
        return python
    if intellij and (
        lower.endswith("idea64.exe")
        or lower.endswith("idea.exe")
        or ("jetbrains" in lower and lower.endswith(".exe"))
        or ("intellij" in lower and lower.endswith(".exe"))
    ):
        return intellij
    return value


def looks_like_windows_path(text: str) -> bool:
    if not text:
        return False
    if DRIVE_PATH_RE.search(text):
        return True
    if FILE_URI_RE.search(text):
        return True
    return False


def extract_windows_paths(text: str) -> list[str]:
    found: list[str] = []
    if not text:
        return found
    for match in FILE_URI_RE.finditer(text):
        converted = file_uri_to_windows_path(match.group(0))
        if converted:
            found.append(normalize_windows_path(converted))
    for match in DRIVE_PATH_RE.finditer(text):
        raw = match.group("path").rstrip("\\/")
        if len(raw) >= 2:
            found.append(normalize_windows_path(raw))
    # Prefer longer unique paths.
    uniq = sorted(set(found), key=len, reverse=True)
    return uniq


def suggest_roots(paths: list[str]) -> list[str]:
    """Collapse individual file paths into likely mapping roots."""
    normalized = [normalize_windows_path(p) for p in paths]
    candidates: set[str] = set()
    for path in normalized:
        parts = [p for p in path.split("\\") if p]
        if not parts:
            continue
        # C:\Users\name
        if len(parts) >= 3 and parts[1].lower() == "users":
            candidates.add("\\".join(parts[:3]))
        # C:\Users\name\Projects (common workspace parent)
        if len(parts) >= 4 and parts[1].lower() == "users":
            candidates.add("\\".join(parts[:4]))
        # Drive root project folders D:\code
        if len(parts) >= 2:
            candidates.add("\\".join(parts[:2]))
        if path.lower().endswith(".code-workspace"):
            candidates.add(path)
    # Drop roots that are prefixes of a more specific commonly-used root only
    # when they never appear as a real endpoint. Keep all; the user edits.
    return sorted(candidates, key=lambda item: (len(item), item.lower()))

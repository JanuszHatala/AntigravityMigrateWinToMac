"""Refuse to write while Antigravity IDE or Antigravity 2.0 is running."""

from __future__ import annotations

import subprocess
from pathlib import Path

# Literal substrings. "Antigravity.app" is not contained in "Antigravity IDE.app".
_PROCESS_MARKERS = (
    "Antigravity IDE.app",
    "Antigravity IDE Helper",
    "Antigravity.app",
    "Antigravity Helper",
)


def is_antigravity_process(command: str) -> bool:
    """True for either desktop app or its helpers.

    Unrelated macOS services are ignored, including paths under
    ``/System/Library/`` and ``CursorUIViewService``. The check does not
    depend on which profile was selected: both apps write ``~/.gemini``.
    """
    if "antigravity_mac_migrate" in command or "pgrep" in command:
        return False
    if "/System/Library/" in command:
        return False
    if "CursorUIViewService" in command or "AntigravityUIViewService" in command:
        return False
    return any(marker in command for marker in _PROCESS_MARKERS)


def antigravity_pids() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for pattern in ("Antigravity IDE.app", "Antigravity.app"):
        for pid in _pgrep(pattern):
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
    running: list[str] = []
    for pid in ordered:
        command = _command_for_pid(pid)
        if command and is_antigravity_process(command):
            running.append(pid)
    return running


def _pgrep(pattern: str) -> list[str]:
    try:
        out = subprocess.check_output(
            ["pgrep", "-if", pattern],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _command_for_pid(pid: str) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
    except OSError:
        try:
            return subprocess.check_output(
                ["ps", "-p", pid, "-o", "command="],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""


def assert_apps_closed(*, allow_running: bool = False) -> None:
    """Abort unless both desktop apps are quit.

    There is no profile exception. A rewrite of only one tree still touches
    shared Gemini files, and either app can write ``~/.gemini`` while it runs.
    """
    if allow_running:
        return
    pids = antigravity_pids()
    if pids:
        raise SystemExit(
            "Antigravity IDE and Antigravity 2.0 must both be quit before any write "
            "(pids: "
            + ", ".join(pids)
            + "). They share ~/.gemini. Quit both with Cmd+Q, confirm in Activity Monitor, "
            "then retry."
        )


def db_looks_locked(db_path: Path) -> bool:
    try:
        out = subprocess.check_output(
            ["lsof", str(db_path)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return bool(out.strip())

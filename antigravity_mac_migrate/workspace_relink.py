"""Relink workspaceStorage folders to macOS paths and new workspace IDs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from antigravity_mac_migrate.mapping import PathMap
from antigravity_mac_migrate.paths import mac_to_file_uri
from antigravity_mac_migrate.workspace_ids import compute_workspace_id


@dataclass
class WorkspaceRelink:
    old_id: str
    new_id: str
    windows_uri: str
    mac_path: str
    kind: str
    status: str
    detail: str = ""


@dataclass
class RelinkResult:
    items: list[WorkspaceRelink] = field(default_factory=list)
    id_map: dict[str, str] = field(default_factory=dict)


def read_workspace_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def workspace_target_from_json(data: dict) -> tuple[str, str] | None:
    """Return ('folder'|'workspace', uri). Other shapes stay unmapped."""
    if data.get("folder"):
        return "folder", str(data["folder"])
    if data.get("workspace"):
        return "workspace", str(data["workspace"])
    return None


def file_uri_to_native(uri: str) -> str:
    """Decode a file URI to a Windows or POSIX path, depending on the URI."""
    parsed = urlparse(uri)
    raw = unquote(parsed.path or "")
    if raw.startswith("/") and len(raw) >= 3 and raw[2] == ":":
        drive = raw[1]
        rest = raw[3:].replace("/", "\\")
        return f"{drive}:{rest}"
    return raw


def relink_workspaces(
    user_dir: Path,
    path_map: PathMap,
    *,
    dry_run: bool = False,
) -> RelinkResult:
    result = RelinkResult()
    storage = user_dir / "workspaceStorage"
    if not storage.is_dir():
        return result

    rewriter = path_map.rewriter()
    for entry in sorted(path for path in storage.iterdir() if path.is_dir()):
        old_id = entry.name
        meta = entry / "workspace.json"
        if not meta.exists():
            continue
        try:
            data = read_workspace_json(meta)
        except json.JSONDecodeError:
            result.items.append(
                WorkspaceRelink(
                    old_id=old_id,
                    new_id=old_id,
                    windows_uri="",
                    mac_path="",
                    kind="unknown",
                    status="skip",
                    detail="workspace.json is not valid JSON",
                )
            )
            continue

        target = workspace_target_from_json(data)
        if target is None:
            result.items.append(
                WorkspaceRelink(
                    old_id=old_id,
                    new_id=old_id,
                    windows_uri="",
                    mac_path="",
                    kind="unknown",
                    status="unmapped",
                    detail="workspace.json has no folder or workspace URI. Left unchanged.",
                )
            )
            continue
        kind, uri = target
        native = file_uri_to_native(uri)
        mac_path = rewriter.rewrite_string(native)
        still_windows = len(mac_path) >= 2 and mac_path[1] == ":"
        if still_windows:
            result.items.append(
                WorkspaceRelink(
                    old_id=old_id,
                    new_id=old_id,
                    windows_uri=uri,
                    mac_path="",
                    kind=kind,
                    status="unmapped",
                    detail="No path-map entry covers this workspace. Add it under roots or workspaces.",
                )
            )
            continue

        mac_target = Path(mac_path)
        if not mac_target.exists():
            result.items.append(
                WorkspaceRelink(
                    old_id=old_id,
                    new_id=old_id,
                    windows_uri=uri,
                    mac_path=mac_path,
                    kind=kind,
                    status="missing",
                    detail=(
                        "Create this folder or copy the .code-workspace file to the Mac path, then rerun apply."
                    ),
                )
            )
            continue

        computed = compute_workspace_id(mac_target)
        new_id = computed.workspace_id
        dest = storage / new_id
        detail = f"hash path={computed.fs_path_for_hash!r} salt={computed.stat_salt!r}"

        if new_id != old_id and dest.exists():
            result.items.append(
                WorkspaceRelink(
                    old_id=old_id,
                    new_id=new_id,
                    windows_uri=uri,
                    mac_path=mac_path,
                    kind=kind,
                    status="collision",
                    detail=(
                        "This folder was already opened on the Mac, so a workspaceStorage entry "
                        "already exists and was not overwritten. Quit both Antigravity apps, move "
                        f"the Mac id aside (`mv {dest} {dest}.mac-empty`), then rerun apply."
                    ),
                )
            )
            continue

        status = "unchanged-id" if new_id == old_id else "renamed"
        if not dry_run:
            live = entry
            if new_id != old_id:
                shutil.move(str(entry), str(dest))
                live = dest
            payload = dict(data)
            new_uri = mac_to_file_uri(mac_path)
            if kind == "folder":
                payload["folder"] = new_uri
            else:
                payload["workspace"] = new_uri
            (live / "workspace.json").write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )

        if new_id != old_id:
            result.id_map[old_id] = new_id
        result.items.append(
            WorkspaceRelink(
                old_id=old_id,
                new_id=new_id,
                windows_uri=uri,
                mac_path=mac_path,
                kind=kind,
                status=status,
                detail=detail,
            )
        )
    return result

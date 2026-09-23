import json
import sqlite3
from pathlib import Path

import pytest

from antigravity_mac_migrate.apply import apply_map
from antigravity_mac_migrate.mapping import PathMap, RootMap
from antigravity_mac_migrate.paths import PathRewriter, project_dir_name, replacement_pairs, windows_to_file_uri
from antigravity_mac_migrate.profiles import ResolvedProfile
from antigravity_mac_migrate.skills import rename_encoded_dirs
from antigravity_mac_migrate.sqlite_rewrite import rewrite_db
from antigravity_mac_migrate.workspace_ids import compute_code_workspace_id, compute_folder_workspace_id
from antigravity_mac_migrate.workspace_relink import relink_workspaces


def _profile(name: str, user_dir: Path, dot: Path | None = None, gemini: Path | None = None) -> ResolvedProfile:
    content = [path for path in (user_dir, dot, gemini) if path is not None]
    skill_dirs = []
    if dot is not None:
        skill_dirs.append(dot / "skills")
    if gemini is not None:
        skill_dirs.append(gemini / "skills")
    return ResolvedProfile(
        name=name,
        user_dirs=[user_dir],
        dot_dirs=[dot] if dot is not None else [],
        content_dirs=content,
        skill_dirs=skill_dirs,
    )


def _make_db(path: Path, items: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO ItemTable(key, value) VALUES (?, ?)", list(items.items()))
    conn.commit()
    conn.close()


def test_sqlite_rewrites_composer_headers(tmp_path: Path):
    db = tmp_path / "state.vscdb"
    headers = {
        "allComposers": [
            {
                "composerId": "abc",
                "workspaceIdentifier": {
                    "id": "oldidoldidoldidoldidoldidoldidoldi",
                    "uri": {"fsPath": r"C:\Users\WINDOWS_USER\dev\api"},
                },
            }
        ]
    }
    _make_db(db, {"composer.composerHeaders": json.dumps(headers)})
    rewriter = PathRewriter(
        replacement_pairs(r"C:\Users\WINDOWS_USER\dev", "/Users/MAC_USER/dev"),
        extra_id_map={"oldidoldidoldidoldidoldidoldidoldi": "newidnewidnewidnewidnewidnewidnewi"},
    )
    stats = rewrite_db(db, rewriter)
    assert stats.rows_changed == 1
    conn = sqlite3.connect(db)
    value = conn.execute(
        "SELECT value FROM ItemTable WHERE key='composer.composerHeaders'"
    ).fetchone()[0]
    conn.close()
    data = json.loads(value)
    ident = data["allComposers"][0]["workspaceIdentifier"]
    assert ident["uri"]["fsPath"] == "/Users/MAC_USER/dev/api"
    assert ident["id"].startswith("newid")


def test_relink_multi_root_workspace(tmp_path: Path):
    mac_ws = tmp_path / "platform.code-workspace"
    mac_ws.write_text(
        json.dumps(
            {
                "folders": [
                    {"path": r"C:\\Users\\WINDOWS_USER\\dev\\api"},
                    {"path": r"C:\\Users\\WINDOWS_USER\\dev\\web"},
                ]
            }
        ),
        encoding="utf-8",
    )
    user_dir = tmp_path / "User"
    old_id = "windowsidwindowsidwindowsidwinid"
    storage = user_dir / "workspaceStorage" / old_id
    storage.mkdir(parents=True)
    (storage / "workspace.json").write_text(
        json.dumps(
            {"workspace": windows_to_file_uri(r"C:\Users\WINDOWS_USER\dev\platform.code-workspace")}
        ),
        encoding="utf-8",
    )
    path_map = PathMap(
        roots=[
            RootMap(r"C:\Users\WINDOWS_USER\dev", str(tmp_path), "folder"),
            RootMap(
                r"C:\Users\WINDOWS_USER\dev\platform.code-workspace",
                str(mac_ws),
                "workspace",
            ),
        ],
        profiles=[_profile("ide", user_dir)],
    )
    result = relink_workspaces(user_dir, path_map)
    expected = compute_code_workspace_id(mac_ws).workspace_id
    assert result.id_map[old_id] == expected
    new_meta = json.loads((user_dir / "workspaceStorage" / expected / "workspace.json").read_text())
    assert new_meta["workspace"].endswith("platform.code-workspace")
    assert "file://" in new_meta["workspace"]
    assert "C:" not in new_meta["workspace"]


@pytest.mark.parametrize("product", ["Antigravity IDE", "Antigravity"])
def test_relink_folder_workspace(tmp_path: Path, product: str):
    repo = tmp_path / "api"
    repo.mkdir()
    user_dir = tmp_path / "Library" / "Application Support" / product / "User"
    old_id = "folderidfolderidfolderidfolderidxx"
    storage = user_dir / "workspaceStorage" / old_id
    storage.mkdir(parents=True)
    (storage / "state.vscdb").write_bytes(b"")
    (storage / "workspace.json").write_text(
        json.dumps({"folder": windows_to_file_uri(r"C:\Users\WINDOWS_USER\dev\api")}),
        encoding="utf-8",
    )
    path_map = PathMap(
        roots=[RootMap(r"C:\Users\WINDOWS_USER\dev", str(tmp_path), "folder")],
        profiles=[_profile("ide" if "IDE" in product else "app", user_dir)],
    )
    result = relink_workspaces(user_dir, path_map)
    expected = compute_folder_workspace_id(repo).workspace_id
    assert result.id_map[old_id] == expected
    assert (user_dir / "workspaceStorage" / expected / "workspace.json").exists()
    assert not (user_dir / "workspaceStorage" / old_id).exists()


def test_relink_collision_does_not_overwrite(tmp_path: Path):
    repo = tmp_path / "api"
    repo.mkdir()
    user_dir = tmp_path / "User"
    old_id = "oldidoldidoldidoldidoldidoldidoldi"
    storage = user_dir / "workspaceStorage" / old_id
    storage.mkdir(parents=True)
    (storage / "workspace.json").write_text(
        json.dumps({"folder": windows_to_file_uri(r"C:\Users\WINDOWS_USER\Projects\api")}),
        encoding="utf-8",
    )
    (storage / "state.vscdb").write_bytes(b"windows-db")
    new_id = compute_folder_workspace_id(repo).workspace_id
    dest = user_dir / "workspaceStorage" / new_id
    dest.mkdir()
    (dest / "marker.txt").write_text("mac-empty", encoding="utf-8")
    path_map = PathMap(
        roots=[RootMap(r"C:\Users\WINDOWS_USER\Projects", str(tmp_path), "folder")],
        profiles=[_profile("ide", user_dir)],
    )
    result = relink_workspaces(user_dir, path_map)
    assert result.items[0].status == "collision"
    assert result.id_map == {}
    assert (dest / "marker.txt").read_text(encoding="utf-8") == "mac-empty"
    assert (storage / "state.vscdb").read_bytes() == b"windows-db"


def test_apply_rewrites_skill_and_workspace_file(tmp_path: Path):
    repo_a = tmp_path / "api"
    repo_b = tmp_path / "web"
    repo_a.mkdir()
    repo_b.mkdir()
    mac_ws = tmp_path / "platform.code-workspace"
    mac_ws.write_text(
        json.dumps(
            {
                "folders": [
                    {"path": r"C:\\Users\\WINDOWS_USER\\dev\\api"},
                    {"path": r"C:\\Users\\WINDOWS_USER\\dev\\web"},
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    user_dir = tmp_path / "User"
    dot = tmp_path / ".antigravity-ide"
    old_id = "multiidmultiidmultiidmultiidmulti"
    storage = user_dir / "workspaceStorage" / old_id
    storage.mkdir(parents=True)
    (storage / "workspace.json").write_text(
        json.dumps(
            {"workspace": windows_to_file_uri(r"C:\Users\WINDOWS_USER\dev\platform.code-workspace")}
        ),
        encoding="utf-8",
    )
    headers = {
        "allComposers": [
            {
                "composerId": "session-from-windows",
                "name": "Continue me on Mac",
                "workspaceIdentifier": {
                    "id": old_id,
                    "uri": {
                        "fsPath": r"C:\Users\WINDOWS_USER\dev\platform.code-workspace",
                        "scheme": "file",
                    },
                },
            }
        ]
    }
    (user_dir / "globalStorage").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(user_dir / "globalStorage" / "state.vscdb")
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("composer.composerHeaders", json.dumps(headers)),
    )
    conn.commit()
    conn.close()

    (user_dir / "settings.json").write_text(
        json.dumps(
            {
                "python.defaultInterpreterPath": r"C:\Users\WINDOWS_USER\AppData\Local\Programs\Python\Python312\python.exe",
                "terminal.integrated.cwd": r"C:\Users\WINDOWS_USER\dev",
            }
        ),
        encoding="utf-8",
    )
    skill = dot / "skills" / "ship-it" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("Use the repo at C:\\Users\\WINDOWS_USER\\dev\\api\n", encoding="utf-8")
    (repo_a / "GEMINI.md").write_text("Repo lives at C:\\Users\\WINDOWS_USER\\dev\\api\n", encoding="utf-8")

    (tmp_path / "home").mkdir()
    path_map = PathMap(
        roots=[
            RootMap(r"C:\Users\WINDOWS_USER\dev", str(tmp_path), "folder"),
            RootMap(r"C:\Users\WINDOWS_USER\dev\api", str(repo_a), "folder"),
            RootMap(
                r"C:\Users\WINDOWS_USER\dev\platform.code-workspace",
                str(mac_ws),
                "workspace",
            ),
            RootMap(r"C:\Users\WINDOWS_USER", str(tmp_path / "home"), "home"),
        ],
        python="/usr/bin/python3",
        profiles=[_profile("ide", user_dir, dot)],
    )
    report = apply_map(path_map, dry_run=False, skip_missing=True)
    assert any(item.status in {"renamed", "unchanged-id"} for item in report.relink.items)
    settings = json.loads((user_dir / "settings.json").read_text())
    assert settings["python.defaultInterpreterPath"] == "/usr/bin/python3"
    skill_text = skill.read_text(encoding="utf-8")
    assert "C:\\Users" not in skill_text
    assert "api" in skill_text
    ws = json.loads(mac_ws.read_text(encoding="utf-8"))
    assert all("C:" not in folder["path"] for folder in ws["folders"])
    repo_text = (repo_a / "GEMINI.md").read_text(encoding="utf-8")
    assert "C:\\Users" not in repo_text
    conn = sqlite3.connect(user_dir / "globalStorage" / "state.vscdb")
    headers_out = json.loads(
        conn.execute("SELECT value FROM ItemTable WHERE key='composer.composerHeaders'").fetchone()[0]
    )
    ident = headers_out["allComposers"][0]["workspaceIdentifier"]
    assert ident["id"] == compute_code_workspace_id(mac_ws).workspace_id
    assert "platform.code-workspace" in ident["uri"]["fsPath"]


def test_apply_rewrites_both_profiles_without_merging(tmp_path: Path):
    ide_user = tmp_path / "ide-user"
    app_user = tmp_path / "app-user"
    for user_dir, marker in ((ide_user, "ide-marker"), (app_user, "app-marker")):
        user_dir.mkdir()
        (user_dir / "settings.json").write_text(
            json.dumps({"terminal.integrated.cwd": r"C:\Users\WINDOWS_USER\Projects\api"}),
            encoding="utf-8",
        )
        (user_dir / marker).write_text(marker, encoding="utf-8")
    repo = tmp_path / "api"
    repo.mkdir()
    path_map = PathMap(
        roots=[RootMap(r"C:\Users\WINDOWS_USER\Projects", str(tmp_path), "folder")],
        profiles=[
            _profile("ide", ide_user),
            _profile("app", app_user),
        ],
    )
    apply_map(path_map, dry_run=False, skip_missing=True)
    ide_settings = json.loads((ide_user / "settings.json").read_text(encoding="utf-8"))
    app_settings = json.loads((app_user / "settings.json").read_text(encoding="utf-8"))
    assert ide_settings["terminal.integrated.cwd"].endswith("/api")
    assert app_settings["terminal.integrated.cwd"].endswith("/api")
    assert (ide_user / "ide-marker").read_text(encoding="utf-8") == "ide-marker"
    assert (app_user / "app-marker").read_text(encoding="utf-8") == "app-marker"
    assert not (ide_user / "app-marker").exists()
    assert not (app_user / "ide-marker").exists()


def test_non_itemtable_sqlite_is_rewritten_and_pb_stays_byte_identical(tmp_path: Path):
    repo = tmp_path / "api"
    repo.mkdir()
    user_dir = tmp_path / "User"
    gemini = tmp_path / "antigravity-ide"
    gemini.mkdir()
    (user_dir / "globalStorage").mkdir(parents=True)
    blob = b"\xff\xfeC:\\Users\\WINDOWS_USER\\Projects\\api"
    conn = sqlite3.connect(user_dir / "globalStorage" / "state.vscdb")
    conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value BLOB)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("trajectorySummaries", blob),
    )
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("a-note", r"C:\Users\WINDOWS_USER\Projects\api".encode()),
    )
    conn.commit()
    conn.close()

    conversation = gemini / "conversations" / "chat.db"
    conversation.parent.mkdir()
    original_pb = b"\x00\x01C:\\Users\\WINDOWS_USER\\Projects\\api\xffprotobuf"
    pb = gemini / "conversations" / "chat.pb"
    pb.write_bytes(original_pb)
    (gemini / "brain" / "123e4567-e89b-12d3-a456-426614174000").mkdir(parents=True)
    (gemini / "note.md").write_text("See C:\\Users\\WINDOWS_USER\\Projects\\api\n", encoding="utf-8")
    conn = sqlite3.connect(conversation)
    conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, body TEXT, payload BLOB)")
    conn.execute(
        "INSERT INTO messages VALUES (?, ?, ?)",
        (1, r"open C:\Users\WINDOWS_USER\Projects\api\main.py", blob),
    )
    conn.commit()
    conn.close()

    path_map = PathMap(
        roots=[RootMap(r"C:\Users\WINDOWS_USER\Projects", str(tmp_path), "folder")],
        profiles=[_profile("ide", user_dir, gemini=gemini)],
    )
    report = apply_map(path_map, dry_run=False, skip_missing=True)

    assert pb.read_bytes() == original_pb
    assert str(pb) in report.protobuf_files
    assert any("binary SQLite" in warning for warning in report.warnings)

    conn = sqlite3.connect(user_dir / "globalStorage" / "state.vscdb")
    stored_blob = conn.execute(
        "SELECT value FROM ItemTable WHERE key='trajectorySummaries'"
    ).fetchone()[0]
    note = conn.execute("SELECT value FROM ItemTable WHERE key='a-note'").fetchone()[0]
    conn.close()
    if isinstance(note, bytes):
        note = note.decode()
    assert stored_blob == blob
    assert str(repo) in note.replace("\\", "/")

    conn = sqlite3.connect(conversation)
    body, payload = conn.execute("SELECT body, payload FROM messages WHERE id=1").fetchone()
    conn.close()
    assert payload == blob
    assert "C:\\Users" not in body
    assert "main.py" in body
    assert (gemini / "brain" / "123e4567-e89b-12d3-a456-426614174000").is_dir()
    assert "C:\\Users" not in (gemini / "note.md").read_text(encoding="utf-8")


def test_uuid_brain_dir_is_kept_and_encoded_dir_is_renamed(tmp_path: Path):
    brain = tmp_path / "gemini" / "brain" / "123e4567-e89b-12d3-a456-426614174000"
    brain.mkdir(parents=True)
    (brain / "note.md").write_text("keep", encoding="utf-8")
    windows = r"C:\Users\WINDOWS_USER\Projects\api"
    encoded = project_dir_name(windows)
    projects = tmp_path / "dot" / "projects" / encoded
    projects.mkdir(parents=True)
    (projects / "a.txt").write_text("z", encoding="utf-8")
    mac_repo = tmp_path / "api"
    mac_repo.mkdir()
    profile = ResolvedProfile(
        name="ide",
        content_dirs=[tmp_path / "gemini", tmp_path / "dot"],
    )
    rewriter = PathRewriter(replacement_pairs(windows, str(mac_repo)))
    changes = rename_encoded_dirs([profile], rewriter, [windows])
    assert brain.is_dir()
    assert (brain / "note.md").read_text(encoding="utf-8") == "keep"
    assert changes == [(encoded, project_dir_name(str(mac_repo)), "renamed")]
    assert not projects.exists()
    assert (tmp_path / "dot" / "projects" / project_dir_name(str(mac_repo)) / "a.txt").is_file()

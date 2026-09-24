"""Export and import scripts: manifest layout, skip rules, absolute destinations."""

import json
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPORT = REPO / "scripts" / "Export-AntigravityWindows.ps1"
IMPORT = REPO / "scripts" / "import-antigravity-mac.sh"

PB_IDE = b"\x00ide-pb\r\n\xff"
PB_APP = b"\x00app-pb\r\n\xff"
PB_ALSO = b"\x00also-pb\r\n\xff"

SKIP_SEGMENTS = {
    "Cache",
    "CachedData",
    "Code Cache",
    "GPUCache",
    "Crashpad",
    "Service Worker",
    "blob_storage",
    "CachedExtensionVSIXs",
    "Session Storage",
    "Cookies",
    "Cookies-journal",
}

GEMINI_PREFIXES = (
    "profiles/ide/gemini-antigravity-ide/",
    "profiles/app/gemini-antigravity/",
    "profiles/gemini/",
    "profiles/cli/",
)


def _pwsh():
    found = shutil.which("pwsh")
    if not found:
        pytest.skip("pwsh is not installed")
    return found


def _run(args, cwd, env, check=False):
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return result


def _entries(stdout):
    rows = []
    for line in stdout.splitlines():
        if not line.startswith("entry\t"):
            continue
        parts = line.split("\t")
        assert len(parts) == 7, line
        rows.append(
            {
                "profile": parts[1],
                "id": parts[2],
                "kind": parts[3],
                "source": parts[4],
                "zipPath": parts[5],
                "macRelative": parts[6],
            }
        )
    return rows


def _write(path: Path, data: bytes | str = b"keep") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    path.write_bytes(data)


def _build_windows_profile(root: Path) -> dict[str, Path]:
    roaming = root / "AppData" / "Roaming"
    local = root / "AppData" / "Local"
    user = roaming / "Antigravity IDE" / "User"
    _write(user / "settings.json", '{"keep":true}')
    _write(user / "globalStorage" / "state.vscdb", b"sqlite-bytes")
    _write(user / "chat" / "one.pb", PB_IDE)
    _write(user / "Cache.txt", b"KEEPME-cache-txt")
    _write(user / "Cache" / "skip.txt", b"SKIPME-cache")
    _write(user / "CachedData" / "skip.txt", b"SKIPME-cacheddata")
    _write(user / "Code Cache" / "skip.txt", b"SKIPME-code-cache")
    _write(user / "GPUCache" / "skip.txt", b"SKIPME-gpucache")
    _write(user / "logs" / "app.log", b"SKIPME-logs")
    _write(user / "Crashpad" / "skip.txt", b"SKIPME-crashpad")
    _write(user / "Service Worker" / "skip.txt", b"SKIPME-sw")
    _write(user / "blob_storage" / "skip.txt", b"SKIPME-blob")
    _write(user / "CachedExtensionVSIXs" / "skip.txt", b"SKIPME-vsix")
    _write(user / "Session Storage" / "skip.txt", b"SKIPME-session")
    _write(user / "Network" / "Cookies", b"SKIPME-cookies")
    _write(user / "Network" / "Cookies-journal", b"SKIPME-cookies-journal")
    _write(roaming / "Antigravity IDE" / "argv.json", b'{"argv":1}')
    _write(roaming / "Antigravity IDE" / "CachedData" / "outside.txt", b"SKIPME-outside")
    _write(roaming / "Antigravity" / "User" / "only-app-user.txt", b"APPUSER")
    _write(roaming / "Antigravity" / "argv.json", b'{"argv":2}')
    _write(roaming / "antigravity" / "User" / "lower.txt", b"LOWER")
    _write(roaming / "antigravity" / "Cache" / "skip.txt", b"SKIPME-lower-cache")
    _write(local / "Programs" / "Antigravity" / "install.exe", b"SKIPME-install")
    _write(root / ".antigravity-ide" / "ext.txt", b"IDEEXT")
    _write(root / ".antigravity" / "ext.txt", b"APPEXT")
    _write(root / ".gemini" / "antigravity-ide" / "only-ide.txt", b"ONLYIDE")
    _write(root / ".gemini" / "antigravity-ide" / "conv.pb", PB_IDE)
    _write(root / ".gemini" / "antigravity" / "only-app.txt", b"ONLYAPP")
    _write(root / ".gemini" / "antigravity" / "conv.pb", PB_APP)
    _write(root / ".gemini" / "GEMINI.md", b"# rules\n")
    _write(root / ".gemini" / "config" / "skills" / "s.md", b"# skill\n")
    _write(root / ".gemini" / "config" / "logs" / "kept.txt", b"KEEPME-gemini-logs")
    _write(root / ".gemini" / "stray.txt", b"SKIPME-stray")
    transcript = (
        root
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / "abc"
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    _write(transcript, b'{"keep":"transcript"}\n')
    return {"roaming": roaming, "local": local, "user": user}


def _windows_env(root: Path, home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["USERPROFILE"] = str(root)
    env["APPDATA"] = str(root / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(root / "AppData" / "Local")
    env["HOME"] = str(home)
    return env


def _export(pwsh, args, cwd, env):
    return _run([pwsh, "-NoProfile", "-File", str(EXPORT), *args], cwd, env)


def _import(args, home, cwd):
    env = os.environ.copy()
    env["HOME"] = str(home)
    return _run(["bash", str(IMPORT), *args], cwd, env)


def _zip_segments(names):
    for name in names:
        parts = [part for part in name.split("/") if part]
        yield name, parts


def test_export_requires_an_absolute_zip(tmp_path):
    pwsh = _pwsh()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = _windows_env(tmp_path / "win", tmp_path / "mac")
    missing = _export(pwsh, [], cwd, env)
    assert missing.returncode != 0
    assert "OutputZip" in missing.stderr
    relative = _export(pwsh, ["-OutputZip", "antigravity.zip", "-DryRun"], cwd, env)
    assert relative.returncode != 0
    assert "absolute" in relative.stderr.lower()
    assert not (cwd / "antigravity.zip").exists()


def test_export_manifest_skip_rules_and_separated_trees(tmp_path):
    pwsh = _pwsh()
    root = tmp_path / "win home"
    decoy = tmp_path / "cwd"
    decoy.mkdir()
    _write(decoy / "Antigravity IDE" / "User" / "cwd-only.txt", b"SKIPME-cwd")
    _write(decoy / "cwd-decoy.txt", b"SKIPME-cwd-root")
    home_marker = tmp_path / "unused-home"
    _write(home_marker / "marker.txt", b"SKIPME-home")
    _build_windows_profile(root)
    repo = tmp_path / "repo"
    _write(repo / "notes.pb", PB_ALSO)
    _write(repo / "logs" / "keep.txt", b"KEEPME-repo-logs")
    out_dir = tmp_path / "out dir"
    out_dir.mkdir()
    zip_path = out_dir / "anti gravity.zip"
    env = _windows_env(root, home_marker)
    dry = _export(
        pwsh,
        ["-OutputZip", str(zip_path), "-Also", str(repo), "-DryRun"],
        decoy,
        env,
    )
    assert dry.returncode == 0, dry.stderr
    assert "mode\tdry-run" in dry.stdout
    assert not zip_path.exists()
    dry_rows = _entries(dry.stdout)
    assert any(line.startswith("skip\t") and line.endswith("Cache") or "/Cache" in line or "\\Cache" in line for line in dry.stdout.splitlines() if line.startswith("skip\t"))

    written = _export(
        pwsh,
        ["-OutputZip", str(zip_path), "-Also", str(repo)],
        decoy,
        env,
    )
    assert written.returncode == 0, written.stderr
    assert zip_path.is_file()
    rows = _entries(written.stdout)
    assert [(row["id"], row["zipPath"], row["macRelative"]) for row in rows] == [
        (
            "ide-user",
            "profiles/ide/application-support/User",
            "Library/Application Support/Antigravity IDE/User",
        ),
        (
            "ide-argv",
            "profiles/ide/application-support/argv.json",
            "Library/Application Support/Antigravity IDE/argv.json",
        ),
        (
            "ide-extensions",
            "profiles/ide/dot-antigravity-ide",
            ".antigravity-ide",
        ),
        (
            "ide-gemini",
            "profiles/ide/gemini-antigravity-ide",
            ".gemini/antigravity-ide",
        ),
        (
            "app-user",
            "profiles/app/application-support/User",
            "Library/Application Support/Antigravity/User",
        ),
        (
            "app-argv",
            "profiles/app/application-support/argv.json",
            "Library/Application Support/Antigravity/argv.json",
        ),
        (
            "app-extensions",
            "profiles/app/dot-antigravity",
            ".antigravity",
        ),
        (
            "app-gemini",
            "profiles/app/gemini-antigravity",
            ".gemini/antigravity",
        ),
        (
            "app-lower",
            "profiles/app/application-support-antigravity",
            "Library/Application Support/antigravity",
        ),
        ("gemini-rules", "profiles/gemini/GEMINI.md", ".gemini/GEMINI.md"),
        ("gemini-config", "profiles/gemini/config", ".gemini/config"),
        ("cli", "profiles/cli/antigravity-cli", ".gemini/antigravity-cli"),
        ("also-1", "also/1", "-"),
    ]
    assert rows == dry_rows
    for row in rows:
        assert os.path.isabs(row["source"])
        assert Path(row["source"]).resolve().is_relative_to(root.resolve()) or (
            row["id"] == "also-1" and Path(row["source"]).resolve() == repo.resolve()
        )
        assert not str(row["source"]).startswith(str(decoy))
        assert not str(row["source"]).startswith(str(REPO))
        if row["profile"] != "also":
            assert not row["macRelative"].startswith("/")
            assert ".." not in row["macRelative"].split("/")

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        ide_pb = archive.read("profiles/ide/gemini-antigravity-ide/conv.pb")
        app_pb = archive.read("profiles/app/gemini-antigravity/conv.pb")
        also_pb = archive.read("also/1/notes.pb")
        kept_logs = archive.read(
            "profiles/cli/antigravity-cli/brain/abc/.system_generated/logs/transcript.jsonl"
        )
        gemini_logs = archive.read("profiles/gemini/config/logs/kept.txt")
        repo_logs = archive.read("also/1/logs/keep.txt")
        cache_txt = archive.read("profiles/ide/application-support/User/Cache.txt")
        settings_text = archive.read("profiles/ide/application-support/User/settings.json")
        assert b"SKIPME" not in settings_text
        for info in archive.infolist():
            if info.is_dir():
                continue
            assert b"SKIPME" not in archive.read(info), info.filename
    assert manifest["version"] == 1
    assert Path(manifest["windowsHome"]).resolve() == root.resolve()
    assert [entry["id"] for entry in manifest["entries"]] == [row["id"] for row in rows]
    assert manifest["entries"][-1]["macRelative"] is None
    assert ide_pb == PB_IDE
    assert app_pb == PB_APP
    assert also_pb == PB_ALSO
    assert kept_logs == b'{"keep":"transcript"}\n'
    assert gemini_logs == b"KEEPME-gemini-logs"
    assert repo_logs == b"KEEPME-repo-logs"
    assert cache_txt == b"KEEPME-cache-txt"
    blob = "\n".join(names)
    assert "only-ide.txt" in blob
    assert "only-app.txt" in blob
    assert "stray.txt" not in blob
    assert "outside.txt" not in blob
    assert "install.exe" not in blob
    assert "cwd-only.txt" not in blob
    for name, parts in _zip_segments(names):
        for part in parts:
            assert part not in SKIP_SEGMENTS, name
        if "logs" in parts:
            assert name.startswith(GEMINI_PREFIXES) or name.startswith("also/"), name
    ide_names = [name for name in names if "/only-ide.txt" in name or name.endswith("only-ide.txt")]
    app_names = [name for name in names if name.endswith("only-app.txt")]
    assert ide_names == ["profiles/ide/gemini-antigravity-ide/only-ide.txt"]
    assert app_names == ["profiles/app/gemini-antigravity/only-app.txt"]
    assert any(name.startswith("profiles/app/application-support-antigravity/") for name in names)
    assert not any("application-support-antigravity" in name and "Antigravity IDE" in name for name in names)


def test_windows_home_override_ignores_appdata(tmp_path):
    pwsh = _pwsh()
    selected = tmp_path / "selected"
    other = tmp_path / "other"
    _write(selected / "AppData" / "Roaming" / "Antigravity IDE" / "User" / "from-home.txt", b"HOME")
    _write(other / "AppData" / "Roaming" / "Antigravity IDE" / "User" / "from-appdata.txt", b"APPDATA")
    out = tmp_path / "out"
    out.mkdir()
    zip_path = out / "one.zip"
    env = os.environ.copy()
    env["USERPROFILE"] = str(other)
    env["APPDATA"] = str(other / "AppData" / "Roaming")
    env["LOCALAPPDATA"] = str(other / "AppData" / "Local")
    env["HOME"] = str(tmp_path / "mac")
    result = _export(
        pwsh,
        ["-OutputZip", str(zip_path), "-WindowsHome", str(selected), "-Profile", "ide"],
        tmp_path,
        env,
    )
    assert result.returncode == 0, result.stderr
    rows = _entries(result.stdout)
    assert [row["id"] for row in rows] == ["ide-user"]
    assert Path(rows[0]["source"]).resolve() == (
        selected / "AppData" / "Roaming" / "Antigravity IDE" / "User"
    ).resolve()
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert any(name.endswith("from-home.txt") for name in names)
    assert not any(name.endswith("from-appdata.txt") for name in names)


def test_cli_is_omitted_until_the_folder_exists_and_localappdata_is_refused(tmp_path):
    pwsh = _pwsh()
    root = tmp_path / "win"
    _write(root / "AppData" / "Roaming" / "Antigravity IDE" / "User" / "settings.json", b"{}")
    out = tmp_path / "out"
    out.mkdir()
    zip_path = out / "partial.zip"
    env = _windows_env(root, tmp_path / "mac")
    dry = _export(pwsh, ["-OutputZip", str(zip_path), "-DryRun"], tmp_path, env)
    assert dry.returncode == 0, dry.stderr
    assert "cli" not in {row["profile"] for row in _entries(dry.stdout)}
    missing_cli = _export(
        pwsh,
        ["-OutputZip", str(zip_path), "-Profile", "cli", "-DryRun"],
        tmp_path,
        env,
    )
    assert missing_cli.returncode != 0
    assert "cli" in missing_cli.stderr
    local_repo = root / "AppData" / "Local" / "Programs" / "Antigravity"
    local_repo.mkdir(parents=True)
    refused = _export(
        pwsh,
        ["-OutputZip", str(zip_path), "-Profile", "ide", "-Also", str(local_repo)],
        tmp_path,
        env,
    )
    assert refused.returncode != 0
    assert "LocalAppData" in refused.stderr
    assert not zip_path.exists()


def _sample_zip(path: Path) -> None:
    manifest = {
        "version": 1,
        "windowsHome": "C:\\Users\\WINDOWS_USER",
        "entries": [
            {
                "profile": "ide",
                "id": "ide-user",
                "kind": "dir",
                "source": "C:\\Users\\WINDOWS_USER\\AppData\\Roaming\\Antigravity IDE\\User",
                "zipPath": "profiles/ide/application-support/User",
                "macRelative": "Library/Application Support/Antigravity IDE/User",
            },
            {
                "profile": "app",
                "id": "app-gemini",
                "kind": "dir",
                "source": "C:\\Users\\WINDOWS_USER\\.gemini\\antigravity",
                "zipPath": "profiles/app/gemini-antigravity",
                "macRelative": ".gemini/antigravity",
            },
            {
                "profile": "also",
                "id": "also-1",
                "kind": "dir",
                "source": "D:\\work",
                "zipPath": "also/1",
                "macRelative": None,
            },
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("profiles/ide/application-support/User/settings.json", b'{"ok":1}')
        archive.writestr("profiles/ide/application-support/User/chat/one.pb", PB_IDE)
        archive.writestr("profiles/app/gemini-antigravity/only-app.txt", b"ONLYAPP")
        archive.writestr("also/1/notes.pb", PB_ALSO)


def test_import_dry_run_uses_absolute_home_destinations(tmp_path):
    zip_path = tmp_path / "export.zip"
    _sample_zip(zip_path)
    home = tmp_path / "Mac Home"
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    _write(cwd / "Library" / "Application Support" / "Antigravity IDE" / "User" / "decoy.txt", b"no")
    result = _import(["--zip", str(zip_path), "-n"], home, cwd)
    assert result.returncode == 0, result.stderr + result.stdout
    copies = [line.split("\t") for line in result.stdout.splitlines() if line.startswith("copy\t")]
    assert [row[1] for row in copies] == ["ide-user", "app-gemini"]
    dests = [row[4] for row in copies]
    assert all(os.path.isabs(dest) for dest in dests)
    assert dests == [
        str(home / "Library" / "Application Support" / "Antigravity IDE" / "User"),
        str(home / ".gemini" / "antigravity"),
    ]
    assert all(not dest.startswith(str(REPO)) for dest in dests)
    assert all(not dest.startswith(str(cwd)) for dest in dests)
    leaves = [line.split("\t") for line in result.stdout.splitlines() if line.startswith("leave\t")]
    assert leaves == [["leave", "also-1", "D:\\work", "also/1"]]
    assert not home.exists()
    relative = _import(["--zip", "export.zip", "-n"], home, tmp_path)
    assert relative.returncode != 0
    assert "absolute" in relative.stderr.lower()
    relative_home = os.environ.copy()
    relative_home["HOME"] = "relative-home"
    bad_home = subprocess.run(
        ["bash", str(IMPORT), "--zip", str(zip_path), "-n"],
        cwd=cwd,
        env=relative_home,
        capture_output=True,
        text=True,
    )
    assert bad_home.returncode != 0
    assert "HOME" in bad_home.stderr


def test_import_places_trees_refuses_merge_and_can_move_aside(tmp_path):
    pwsh = _pwsh()
    root = tmp_path / "win home"
    _build_windows_profile(root)
    repo = tmp_path / "repo"
    _write(repo / "notes.pb", PB_ALSO)
    out = tmp_path / "out"
    out.mkdir()
    zip_path = out / "bundle.zip"
    env = _windows_env(root, tmp_path / "unused")
    exported = _export(pwsh, ["-OutputZip", str(zip_path), "-Also", str(repo)], tmp_path, env)
    assert exported.returncode == 0, exported.stderr
    home = tmp_path / "Mac Home"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    planned = _import(["--zip", str(zip_path), "-n"], home, cwd)
    assert planned.returncode == 0, planned.stderr + planned.stdout
    for line in planned.stdout.splitlines():
        if line.startswith("copy\t"):
            dest = line.split("\t")[4]
            assert os.path.isabs(dest)
            assert dest.startswith(str(home) + os.sep)
    placed = _import(["--zip", str(zip_path)], home, cwd)
    assert placed.returncode == 0, placed.stderr + placed.stdout
    ide_pb = home / ".gemini" / "antigravity-ide" / "conv.pb"
    app_pb = home / ".gemini" / "antigravity" / "conv.pb"
    user = home / "Library" / "Application Support" / "Antigravity IDE" / "User"
    assert ide_pb.read_bytes() == PB_IDE
    assert app_pb.read_bytes() == PB_APP
    assert (home / ".gemini" / "antigravity-ide" / "only-ide.txt").read_bytes() == b"ONLYIDE"
    assert not (home / ".gemini" / "antigravity" / "only-ide.txt").exists()
    assert (home / ".gemini" / "antigravity" / "only-app.txt").read_bytes() == b"ONLYAPP"
    assert not (home / ".gemini" / "antigravity-ide" / "only-app.txt").exists()
    assert (user / "chat" / "one.pb").read_bytes() == PB_IDE
    assert not (user / "Cache").exists()
    assert not (user / "Network" / "Cookies").exists()
    transcript = (
        home
        / ".gemini"
        / "antigravity-cli"
        / "brain"
        / "abc"
        / ".system_generated"
        / "logs"
        / "transcript.jsonl"
    )
    assert transcript.read_bytes() == b'{"keep":"transcript"}\n'
    assert (home / ".gemini" / "GEMINI.md").read_bytes() == b"# rules\n"
    assert (home / ".gemini" / "config" / "skills" / "s.md").read_bytes() == b"# skill\n"
    lower = home / "Library" / "Application Support" / "antigravity" / "User" / "lower.txt"
    canonical = home / "Library" / "Application Support" / "Antigravity" / "User" / "only-app-user.txt"
    assert lower.read_bytes() == b"LOWER"
    assert canonical.read_bytes() == b"APPUSER"
    assert not any(path.name == "notes.pb" for path in home.rglob("notes.pb"))
    assert "leave\talso-1\t" in placed.stdout
    again = _import(["--zip", str(zip_path)], home, cwd)
    assert again.returncode != 0
    assert "already exists" in again.stdout
    assert ide_pb.read_bytes() == PB_IDE
    marker = user / "mac-marker.txt"
    _write(marker, b"MAC")
    moved = _import(["--zip", str(zip_path), "--move-aside"], home, cwd)
    assert moved.returncode == 0, moved.stderr + moved.stdout
    aside = Path(str(user) + ".mac-before-migrate")
    assert aside.is_dir()
    assert (aside / "mac-marker.txt").read_bytes() == b"MAC"
    assert not marker.exists()
    assert (user / "chat" / "one.pb").read_bytes() == PB_IDE
    blocked = Path(str(home / ".antigravity") + ".mac-before-migrate")
    assert blocked.exists()
    clash = _import(["--zip", str(zip_path), "--move-aside"], home, cwd)
    assert clash.returncode != 0
    assert "mac-before-migrate" in clash.stdout
    explicit = tmp_path / "chosen" / "api"
    other_home = tmp_path / "Other Mac"
    with_also = _import(
        ["--zip", str(zip_path), "--also-to", "also-1=" + str(explicit)],
        other_home,
        cwd,
    )
    assert with_also.returncode == 0, with_also.stderr + with_also.stdout
    assert (explicit / "notes.pb").read_bytes() == PB_ALSO
    assert not any(path.name == "notes.pb" for path in other_home.rglob("*"))
    relative_dest = _import(
        ["--zip", str(zip_path), "--also-to", "also-1=Projects/api", "-n"],
        tmp_path / "unused-mac",
        cwd,
    )
    assert relative_dest.returncode != 0
    assert "absolute" in (relative_dest.stdout + relative_dest.stderr).lower()


def test_import_profile_filter_and_refuses_a_relative_mac_path(tmp_path):
    zip_path = tmp_path / "export.zip"
    _sample_zip(zip_path)
    home = tmp_path / "mac"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    only_ide = _import(["--zip", str(zip_path), "--profile", "ide"], home, cwd)
    assert only_ide.returncode == 0, only_ide.stderr + only_ide.stdout
    assert (home / "Library" / "Application Support" / "Antigravity IDE" / "User" / "settings.json").is_file()
    assert not (home / ".gemini").exists()
    assert "leave\talso-1\t" in only_ide.stdout
    bad = tmp_path / "bad.zip"
    manifest = {
        "version": 1,
        "windowsHome": "C:\\Users\\WINDOWS_USER",
        "entries": [
            {
                "profile": "ide",
                "id": "ide-user",
                "kind": "dir",
                "source": "C:\\Users\\WINDOWS_USER\\AppData\\Roaming\\Antigravity IDE\\User",
                "zipPath": "profiles/ide/application-support/User",
                "macRelative": "../outside",
            }
        ],
    }
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("profiles/ide/application-support/User/settings.json", b"{}")
    refused = _import(["--zip", str(bad)], tmp_path / "mac2", cwd)
    assert refused.returncode != 0
    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "mac2").exists()


def test_import_script_is_executable():
    mode = IMPORT.stat().st_mode
    assert mode & stat.S_IXUSR

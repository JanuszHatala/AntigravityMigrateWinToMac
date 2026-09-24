import inspect

import pytest

from antigravity_mac_migrate.cli import (
    DROP,
    KEEP,
    MISSING,
    OUTSIDE,
    PATH_MAP_NAME,
    PB,
    READY,
    RENAME,
    RENAME_SUGGESTED,
    SKIPPED,
    STILL,
    main,
)
from antigravity_mac_migrate.lock import assert_apps_closed, is_antigravity_process
from antigravity_mac_migrate.workdir import default_report_dir, tool_root


def test_unrelated_macos_service_is_not_an_antigravity_app():
    service = (
        "/System/Library/PrivateFrameworks/TextInputUIMacHelper.framework/"
        "Versions/A/XPCServices/CursorUIViewService.xpc/Contents/MacOS/CursorUIViewService"
    )
    assert is_antigravity_process(service) is False
    assert is_antigravity_process("/Applications/Antigravity IDE.app/Contents/MacOS/Antigravity IDE")
    assert is_antigravity_process("/Applications/Antigravity.app/Contents/MacOS/Antigravity")
    assert is_antigravity_process(
        "/Applications/Antigravity IDE.app/Contents/Frameworks/Antigravity IDE Helper.app/Contents/MacOS/Antigravity IDE Helper"
    )
    assert is_antigravity_process(
        "/Applications/Antigravity.app/Contents/Frameworks/Antigravity Helper.app/Contents/MacOS/Antigravity Helper"
    )
    assert is_antigravity_process("python3 -m antigravity_mac_migrate auto") is False


def test_lock_always_covers_both_apps():
    assert "profile" not in inspect.signature(assert_apps_closed).parameters


def test_reports_live_next_to_the_tool_not_on_the_desktop():
    root = tool_root()
    assert (root / "pyproject.toml").is_file()
    assert default_report_dir() == root / "migrate-work"
    assert default_report_dir().name != "Desktop"


def test_auto_and_verify_write_reports_beside_the_tool(tmp_path, monkeypatch, capsys):
    home = tmp_path / "copied"
    user = home / "Library" / "Application Support" / "Antigravity IDE" / "User"
    user.mkdir(parents=True)
    (user / "settings.json").write_text(
        "cwd=C:\\Users\\WINDOWS_USER\\Projects\\api\n",
        encoding="utf-8",
    )
    mac = tmp_path / "mac"
    mac.mkdir()
    reports = tmp_path / "migrate-work"
    monkeypatch.setattr("antigravity_mac_migrate.cli.default_report_dir", lambda: reports)
    code = main(
        [
            "auto",
            "--windows-home",
            r"C:\Users\WINDOWS_USER",
            "--mac-home",
            str(mac),
            "--home",
            str(home),
            "--profile",
            "ide",
        ]
    )
    assert code == 0
    written = {
        READY,
        RENAME_SUGGESTED,
        RENAME,
        KEEP,
        DROP,
        MISSING,
        OUTSIDE,
        PB,
        SKIPPED,
        PATH_MAP_NAME,
    }
    assert written <= {path.name for path in reports.iterdir()}
    assert not (mac / "Desktop").exists()
    output = capsys.readouterr().out
    assert f"Reports ({reports})" in output
    assert "On the Desktop" not in output

    verify_code = main(
        [
            "verify",
            "--home",
            str(home),
            "--profile",
            "ide",
        ]
    )
    assert verify_code == 1
    still = reports / STILL
    assert still.is_file()
    assert r"C:\Users\WINDOWS_USER" in still.read_text(encoding="utf-8")
    assert not (home / "Desktop").exists()


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_apply_aborts_when_either_app_is_running(monkeypatch, tmp_path):
    monkeypatch.setattr("antigravity_mac_migrate.lock.antigravity_pids", lambda: ["4242"])
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "apply",
                "--map",
                str(tmp_path / "missing.json"),
                "--profile",
                "ide",
                "--home",
                str(tmp_path),
            ]
        )
    assert "4242" in str(exc.value)
    assert "both" in str(exc.value).lower()


def test_allow_running_does_not_abort_before_the_map_is_read(monkeypatch, tmp_path):
    monkeypatch.setattr("antigravity_mac_migrate.lock.antigravity_pids", lambda: ["4242"])
    with pytest.raises(FileNotFoundError):
        main(
            [
                "apply",
                "--allow-running",
                "--map",
                str(tmp_path / "missing.json"),
                "--profile",
                "ide",
                "--home",
                str(tmp_path),
            ]
        )


def test_missing_profile_warns_and_does_not_fail(tmp_path, capsys):
    code = main(
        [
            "auto",
            "--windows-home",
            r"C:\Users\WINDOWS_USER",
            "--mac-home",
            str(tmp_path / "mac"),
            "--home",
            str(tmp_path / "copied"),
            "--profile",
            "app",
        ]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "Warning:" in output
    assert "Nothing was changed" in output

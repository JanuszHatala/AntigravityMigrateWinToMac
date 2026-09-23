import inspect

import pytest

from antigravity_mac_migrate.cli import main
from antigravity_mac_migrate.lock import assert_apps_closed, is_antigravity_process


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

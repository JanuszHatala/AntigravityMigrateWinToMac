from antigravity_mac_migrate.profiles import resolve_profiles


def test_windows_antigravity_folder_is_not_imported_into_the_ide(tmp_path):
    ide = tmp_path / "Library" / "Application Support" / "Antigravity IDE" / "User"
    app = tmp_path / "Library" / "Application Support" / "Antigravity" / "User"
    ide.mkdir(parents=True)
    app.mkdir(parents=True)
    selection = resolve_profiles(tmp_path, ["ide"])
    assert [profile.name for profile in selection.profiles] == ["ide"]
    assert selection.profiles[0].user_dirs == [ide]
    assert app not in selection.profiles[0].content_dirs
    assert app not in selection.profiles[0].user_dirs


def test_cli_folder_is_included_only_when_copied(tmp_path):
    (tmp_path / ".gemini" / "config").mkdir(parents=True)
    without = resolve_profiles(tmp_path, None)
    assert "cli" not in {profile.name for profile in without.profiles}
    assert any("antigravity-cli" in warning for warning in without.warnings)
    (tmp_path / ".gemini" / "antigravity-cli").mkdir()
    with_cli = resolve_profiles(tmp_path, None)
    names = {profile.name for profile in with_cli.profiles}
    assert "cli" in names
    assert "gemini" in names
    gemini = next(profile for profile in with_cli.profiles if profile.name == "gemini")
    assert all("antigravity-cli" not in str(path) for path in gemini.content_dirs)
    assert all(path.name != "antigravity" for path in gemini.content_dirs)
    assert all("antigravity-ide" not in str(path) for path in gemini.content_dirs)


def test_lowercase_probe_stays_on_the_app_profile(tmp_path):
    lower = tmp_path / "Library" / "Application Support" / "antigravity" / "User"
    lower.mkdir(parents=True)
    ide = resolve_profiles(tmp_path, ["ide"])
    assert ide.profiles == []
    app = resolve_profiles(tmp_path, ["app"])
    assert app.profiles[0].user_dirs == [lower]
    assert any("lowercase probe" in warning for warning in app.warnings)
    assert any("not the IDE" in warning for warning in app.warnings)

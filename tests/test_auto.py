from antigravity_mac_migrate.auto import build_auto_plan, path_map_for_apply, translate_home
from antigravity_mac_migrate.detect import ScanResult


def test_translate_windows_home_to_mac_home():
    assert (
        translate_home(
            r"C:\Users\WINDOWS_USER\Projects\api",
            r"C:\Users\WINDOWS_USER",
            "/Users/MAC_USER",
        )
        == "/Users/MAC_USER/Projects/api"
    )
    assert (
        translate_home(
            r"C:\Users\WINDOWS_USER\source\platform.code-workspace",
            r"C:\Users\WINDOWS_USER",
            "/Users/MAC_USER",
        )
        == "/Users/MAC_USER/source/platform.code-workspace"
    )
    assert translate_home(r"D:\work\api", r"C:\Users\WINDOWS_USER", "/Users/MAC_USER") is None


def test_extra_drive_is_rewritten_even_though_it_is_outside_the_user_folder(tmp_path):
    mac_repo = tmp_path / "work" / "demo"
    mac_repo.mkdir(parents=True)
    scan = ScanResult()
    scan.workspace_uris = [
        ("abc", "folder", "file:///d%3A/work/demo"),
        ("def", "folder", "file:///d%3A/work/demo-lab/automate/repos/sample"),
    ]
    plan = build_auto_plan(
        scan,
        r"C:\Users\WINDOWS_USER",
        "/Users/MAC_USER",
        python="/opt/homebrew/bin/python3",
        intellij=None,
        extra_prefixes=[(r"D:\work", str(tmp_path / "work"))],
    )
    assert any(str(mac_repo) in line or "/work/demo" in line for line in plan.ready)
    assert len(plan.missing) == 1
    assert "automate/repos/sample" in plan.missing[0]
    assert plan.outside_home == []


def test_rename_suggested_when_mac_folder_uses_hyphens(tmp_path):
    work = tmp_path / "work"
    (work / "old-name").mkdir(parents=True)
    scan = ScanResult()
    scan.workspace_uris = [
        ("abc", "folder", "file:///d%3A/work/oldname"),
        ("wt", "folder", "file:///d%3A/work/demo/.git/worktrees/abc"),
        (
            "roam",
            "folder",
            "file:///c%3A/Users/WINDOWS_USER/AppData/Roaming/Antigravity/Workspaces/abc",
        ),
    ]
    plan = build_auto_plan(
        scan,
        r"C:\Users\WINDOWS_USER",
        "/Users/MAC_USER",
        python="/opt/homebrew/bin/python3",
        intellij=None,
        extra_prefixes=[(r"D:\work", str(work))],
    )
    assert plan.ready_pairs == []
    assert plan.rename_pairs == [(r"D:\work\oldname", str(work / "old-name"))]
    assert any(line.startswith("[worktree]") for line in plan.keep)
    assert any(line.startswith("[antigravity-internal]") for line in plan.keep)
    accepted = path_map_for_apply(plan, plan.rename_pairs, [])
    assert any(root.mac.endswith("old-name") for root in accepted.roots)
    assert all(
        not root.windows.lower().startswith(r"d:\work") or root.windows.lower().endswith("oldname")
        for root in accepted.roots
    )
    blocked = path_map_for_apply(plan, plan.rename_pairs, [r"D:\work\oldname"])
    assert blocked.roots == []


def test_auto_plan_uses_one_home_prefix(tmp_path):
    mac_repo = tmp_path / "Projects" / "api"
    mac_repo.mkdir(parents=True)
    scan = ScanResult()
    scan.workspace_uris = [
        ("abc", "folder", "file:///c%3A/Users/WINDOWS_USER/Projects/api"),
        ("def", "folder", "file:///c%3A/Users/WINDOWS_USER/Projects/missing"),
        ("ghi", "folder", "file:///e%3A/other/repo"),
    ]
    plan = build_auto_plan(
        scan,
        r"C:\Users\WINDOWS_USER",
        str(tmp_path),
        python="/opt/homebrew/bin/python3",
        intellij=None,
    )
    assert plan.path_map.roots[0].windows == r"C:\Users\WINDOWS_USER"
    assert plan.path_map.roots[0].mac == str(tmp_path)
    assert len(plan.ready) == 1
    assert "Projects/api" in plan.ready[0]
    assert len(plan.missing) == 1
    assert plan.outside_home == [r"E:\other\repo"]

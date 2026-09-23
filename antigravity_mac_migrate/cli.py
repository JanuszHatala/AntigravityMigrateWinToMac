"""Command-line interface for antigravity-mac-migrate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from antigravity_mac_migrate import __version__
from antigravity_mac_migrate.apply import apply_map, write_report
from antigravity_mac_migrate.auto import (
    build_auto_plan,
    load_pair_file,
    load_path_list,
    path_map_for_apply,
)
from antigravity_mac_migrate.detect import proposed_map, scan_profiles
from antigravity_mac_migrate.extensions import ide_cli, iter_extensions, reinstall
from antigravity_mac_migrate.lock import assert_apps_closed
from antigravity_mac_migrate.mapping import dump_path_map, load_path_map, missing_mac_targets
from antigravity_mac_migrate.profiles import resolve_profiles
from antigravity_mac_migrate.skills import list_skills

READY = "antigravity-migrate-ready.txt"
RENAME_SUGGESTED = "antigravity-migrate-rename-suggested.txt"
RENAME = "antigravity-migrate-rename.txt"
DROP = "antigravity-migrate-drop.txt"
KEEP = "antigravity-migrate-keep.txt"
MISSING = "antigravity-migrate-missing.txt"
OUTSIDE = "antigravity-migrate-outside-home.txt"
PB = "antigravity-migrate-pb.txt"
SKIPPED = "antigravity-migrate-skipped-binary.txt"
NOT_ATTACHED = "antigravity-migrate-not-attached.txt"
REPORT = "antigravity-migrate-report.json"
STILL = "antigravity-migrate-still-windows.txt"
PATH_MAP_NAME = "path-map.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="antigravity-mac-migrate",
        description=(
            "Remap Antigravity IDE and Antigravity 2.0 profiles copied from Windows "
            "onto this Mac so chats, skills, and workspaces keep working."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    auto_p = sub.add_parser(
        "auto",
        help=r"Replace every C:\Users\<windows name> path with the same path under your Mac home",
    )
    _add_common(auto_p)
    auto_p.add_argument(
        "--also",
        action="append",
        default=[],
        help=r"Another folder pair, Windows=Mac. Example: D:\work=/Users/MAC_USER/work",
    )
    auto_p.add_argument("--windows-home", required=True, help=r"Example: C:\Users\WINDOWS_USER")
    auto_p.add_argument("--mac-home", default=str(Path.home()), help="Example: /Users/MAC_USER")
    auto_p.add_argument("--python", default=None, help="Mac python3, from: which python3")
    auto_p.add_argument("--intellij", default=None, help="Path ending in .app, or omit to auto-detect")
    auto_p.add_argument("--apply", action="store_true", help="Attach exact matches and accepted renames only")
    auto_p.add_argument("--renames", type=Path, default=None, help=f"Edited {RENAME}")
    auto_p.add_argument("--drop", type=Path, default=None, help="Windows paths to leave untouched")
    auto_p.add_argument("--allow-running", action="store_true")

    scan_p = sub.add_parser("scan", help="Find Windows paths still stored in the copied profiles")
    _add_common(scan_p)
    scan_p.add_argument("--write-map", type=Path, help="Write a starter path-map.json you can edit")

    check_p = sub.add_parser("check-map", help="Validate path-map.json against folders on this Mac")
    _add_common(check_p)
    check_p.add_argument("--map", type=Path, required=True)

    apply_p = sub.add_parser(
        "apply",
        help="Rewrite chats, settings, workspace IDs, skills, and .code-workspace files",
    )
    _add_common(apply_p)
    apply_p.add_argument("--map", type=Path, required=True)
    apply_p.add_argument("--dry-run", action="store_true")
    apply_p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Rewrite anyway even if some Mac repo paths do not exist yet",
    )
    apply_p.add_argument(
        "--allow-running",
        action="store_true",
        help="Do not abort if an Antigravity app appears to be running (unsafe)",
    )
    apply_p.add_argument("--report", type=Path, default=Path("migrate-report.json"))

    verify_p = sub.add_parser(
        "verify",
        help="Show leftover Windows paths, skills, and native extensions",
    )
    _add_common(verify_p)
    verify_p.add_argument("--map", type=Path, required=False)

    ext_p = sub.add_parser(
        "reinstall-native-extensions",
        help="Force-reinstall IDE extensions that shipped Windows native binaries",
    )
    _add_common(ext_p)
    ext_p.add_argument("--yes", action="store_true")

    keys_p = sub.add_parser(
        "mac-cmd-keybindings",
        help="For custom keybindings that only define ctrl, add a matching cmd binding",
    )
    _add_common(keys_p)
    keys_p.add_argument("--dry-run", action="store_true")
    keys_p.add_argument("--allow-running", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "auto":
        return cmd_auto(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "check-map":
        return cmd_check_map(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "reinstall-native-extensions":
        return cmd_reinstall(args)
    if args.cmd == "mac-cmd-keybindings":
        return cmd_keybindings(args)
    return 2


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="Home that holds the copied trees. Default: the Mac home.",
    )
    parser.add_argument(
        "--profile",
        action="append",
        choices=["ide", "app", "gemini", "cli"],
        default=None,
        help="Limit to ide, app, gemini, or cli. Repeat to select several. Default: every copied tree that exists.",
    )


def _home(args: argparse.Namespace) -> Path:
    if getattr(args, "home", None):
        return Path(args.home).expanduser()
    mac_home = getattr(args, "mac_home", None)
    if mac_home:
        return Path(mac_home).expanduser()
    return Path.home()


def _print_warnings(warnings: list[str]) -> None:
    for warning in warnings:
        print(f"Warning: {warning}")


def cmd_auto(args: argparse.Namespace) -> int:
    mac_home = str(Path(args.mac_home).expanduser())
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    _print_warnings(selection.warnings)
    if not selection.profiles:
        print("No copied Antigravity trees were found. Nothing was changed.")
        return 0

    desktop = Path(mac_home) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    print("Reading the copied Antigravity data. This can take a minute. Nothing is printed until it finishes.")
    scan = scan_profiles(selection.profiles)
    intellij = args.intellij if args.intellij else None
    extra: list[tuple[str, str]] = []
    for item in args.also:
        if "=" not in item:
            print(r"Each --also value must look like D:\work=/Users/MAC_USER/work")
            print(f"This one does not: {item}")
            return 1
        source, target = item.split("=", 1)
        extra.append((source, target))
    plan = build_auto_plan(
        scan,
        args.windows_home,
        mac_home,
        python=args.python,
        intellij=intellij,
        extra_prefixes=extra,
        profiles=selection.profiles,
    )
    (desktop / PATH_MAP_NAME).write_text(
        json.dumps(dump_path_map(plan.path_map, home), indent=2) + "\n",
        encoding="utf-8",
    )
    _write_lines(desktop / READY, plan.ready)
    (desktop / RENAME_SUGGESTED).write_text(
        "\n".join(
            [
                f"# Suggested renames. Copy a line into {RENAME} to accept it.",
                r"# Example: D:\work\oldname=/Users/MAC_USER/work/old-name",
                *[f"{source}={target}" for source, target in plan.rename_pairs],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rename_file = desktop / RENAME
    if not rename_file.exists():
        rename_file.write_text(
            "# Accepted renames. One Windows path=Mac path per line.\n",
            encoding="utf-8",
        )
    _write_lines(desktop / MISSING, plan.missing)
    (desktop / KEEP).write_text(
        "\n".join(
            [
                "# Left untouched. Copy a [not-copied] folder to the Mac path, then run the preview again.",
                "# [worktree] and [antigravity-internal] were not copied as projects. Leave them here.",
                *plan.keep,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _write_lines(desktop / OUTSIDE, plan.outside_home)
    if not (desktop / DROP).exists():
        (desktop / DROP).write_text(
            "# One Windows path per line. These paths are left unchanged.\n",
            encoding="utf-8",
        )
    (desktop / PB).write_text(
        "\n".join(
            [
                "# Protobuf conversation files. v1 leaves these byte-identical.",
                *[str(path) for path in scan.protobuf_files],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (desktop / SKIPPED).write_text(
        "\n".join(
            [
                "# SQLite cells that are not valid UTF-8. They were not rewritten.",
                "# If a sidebar index is listed here, those titles were not remapped.",
                *scan.skipped_binary,
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    internal = len([line for line in plan.keep if line.startswith("[antigravity-internal]") or line.startswith("[worktree]")])
    print()
    print("Nothing was changed yet." if not args.apply else "Applying exact matches and accepted renames.")
    print(f"Profiles: {', '.join(profile.name for profile in selection.profiles)}")
    print(f"Exact Mac folders found: {len(plan.ready)}")
    print(f"Different folder name, please check: {len(plan.rename_pairs)}")
    print(f"Not copied, left unchanged: {len(plan.missing)}")
    print(f"Worktrees and Antigravity-internal paths, left unchanged: {internal}")
    print(f"Outside {plan.windows_home} and the --also folders: {len(plan.outside_home)}")
    print(f"Protobuf .pb files left byte-identical: {len(scan.protobuf_files)}")
    print(f"Binary SQLite cells left unchanged: {len(scan.skipped_binary)}")
    print()
    print("On the Desktop:")
    for name in (READY, RENAME_SUGGESTED, RENAME, KEEP, DROP, MISSING, OUTSIDE, PB, SKIPPED, PATH_MAP_NAME):
        print(f"  {desktop / name}")

    if not args.apply:
        print()
        print(f"Edit {RENAME} and {DROP} on the Desktop.")
        print("Then run the same command again with --renames, --drop, and --apply.")
        print(f"Projects in {KEEP} are not touched.")
        return 0

    renames = load_pair_file(args.renames) if args.renames else []
    drops = load_path_list(args.drop) if args.drop else []
    apply_plan = path_map_for_apply(plan, renames, drops)
    dropped_renames = [source for source, target in renames if not Path(target).exists()]
    if dropped_renames:
        print("These rename targets do not exist, so they were skipped:")
        for source in dropped_renames:
            print(f"  {source}")

    assert_apps_closed(allow_running=args.allow_running)
    report = apply_map(apply_plan, dry_run=False, skip_missing=True)
    report_path = desktop / REPORT
    write_report(report, report_path)
    attached = [item for item in report.relink.items if item.status in {"renamed", "unchanged-id"}]
    not_attached = [
        item for item in report.relink.items if item.status not in {"renamed", "unchanged-id", "skip"}
    ]
    (desktop / NOT_ATTACHED).write_text(
        "\n".join(
            f"{item.status}\t{item.windows_uri}\t{item.mac_path}\t{item.detail}"
            for item in not_attached
        )
        + ("\n" if not_attached else ""),
        encoding="utf-8",
    )
    print()
    print(f"Rewrote the copied Antigravity data. Backup: {report.backup_dir}")
    print(f"Workspace storage entries attached to a Mac folder: {len(attached)}")
    print(f"Workspace storage entries left unattached: {len(not_attached)}")
    if not_attached:
        print(f"  See {desktop / NOT_ATTACHED}")
    print(f"Text files updated: {len(report.files)}")
    print(f"SQLite databases with rewritten text: {len(report.sqlite)}")
    print(f"Protobuf .pb files left byte-identical: {len(report.protobuf_files)}")
    print(f"Binary SQLite cells left unchanged: {len(report.skipped_binary)}")
    if report.skipped_binary:
        print("  Those cells still hold their original bytes. A sidebar index stored as protobuf was not remapped.")
        print(f"  See {desktop / SKIPPED}")
    print(f"Skills: {len(report.skills)}")
    print()
    print("Sign in on the Mac for auth only. Chat history is local and is not synced by login.")
    print("Open a repo only after this apply. File -> Open Folder, or File -> Open Workspace from File.")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    _print_warnings(selection.warnings)
    if not selection.profiles:
        print("No copied Antigravity trees were found.", file=sys.stderr)
        print("Copy the Windows profile trees into place first. See START-HERE.txt.", file=sys.stderr)
        return 0
    scan = scan_profiles(selection.profiles)
    print(f"Scanned profiles: {', '.join(profile.name for profile in selection.profiles)}")
    print()
    print(f"Skills found: {len(scan.skills)}")
    for skill in scan.skills:
        print(f"  - {skill.name}  ({skill})")
    print()
    print(f"Workspaces recorded in the copied profiles: {len(scan.workspace_uris)}")
    print("The full workspace list is not printed here, so it cannot flood the window.")
    print(f"Protobuf .pb files left unread: {len(scan.protobuf_files)}")
    print(f"Binary SQLite cells skipped: {len(scan.skipped_binary)}")
    print()
    if scan.python_hits:
        print("Python-looking Windows paths:")
        for item in scan.python_hits[:20]:
            print(f"  - {item}")
        print()
    if scan.intellij_hits:
        print("IntelliJ/JetBrains-looking Windows paths:")
        for item in scan.intellij_hits[:20]:
            print(f"  - {item}")
        print()
    top = scan.windows_paths.most_common(40)
    print(f"Unique Windows paths mentioned: {len(scan.windows_paths)}")
    print("A sample is below. The full list is not printed.")
    for path, count in top[:15]:
        print(f"  {count:5d}  {path}")
    print()
    if args.write_map:
        payload = proposed_map(scan, home)
        payload["profiles"] = dump_path_map(
            build_auto_plan(
                scan,
                payload["homes"]["windows"],
                str(home),
                profiles=selection.profiles,
            ).path_map,
            home,
        )["profiles"]
        args.write_map.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print()
        print(f"Wrote {args.write_map}")
        print("Edit every FILL_IN_MAC_PATH_FOR_* value, then run:")
        print(f"  python3 -m antigravity_mac_migrate check-map --map {args.write_map}")
    else:
        print()
        print("Next: write a map file with")
        print("  python3 -m antigravity_mac_migrate scan --write-map ./path-map.json")
    return 0


def cmd_check_map(args: argparse.Namespace) -> int:
    path_map = load_path_map(args.map)
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    path_map.profiles = selection.profiles
    _print_warnings(selection.warnings)
    print(json.dumps(dump_path_map(path_map, home), indent=2))
    missing = missing_mac_targets(path_map)
    if not missing:
        print()
        print("All mapped Mac paths exist. You can apply:")
        print(f"  python3 -m antigravity_mac_migrate apply --map {args.map} --dry-run")
        return 0
    print()
    print("Missing on this Mac:")
    for item in missing:
        print(f"  - {item}")
    print()
    print("Clone those repos, or fix the map.")
    return 1


def cmd_apply(args: argparse.Namespace) -> int:
    assert_apps_closed(allow_running=args.allow_running)
    path_map = load_path_map(args.map)
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    path_map.profiles = selection.profiles
    _print_warnings(selection.warnings)
    if not selection.profiles:
        print("No copied Antigravity trees were found. Nothing was changed.")
        return 0
    report = apply_map(
        path_map,
        dry_run=args.dry_run,
        skip_missing=args.allow_missing,
    )
    write_report(report, args.report)
    print(("DRY RUN " if args.dry_run else "") + "Apply summary")
    print(f"  backup: {report.backup_dir or '(dry-run, no backup)'}")
    print(f"  workspaces processed: {len(report.relink.items)}")
    for item in report.relink.items:
        print(f"    [{item.status}] {item.kind} {item.old_id} -> {item.new_id}")
        print(f"         {item.mac_path or item.windows_uri}")
        if item.detail:
            print(f"         {item.detail}")
    print(f"  sqlite DBs rewritten: {len(report.sqlite)}")
    for line in report.sqlite:
        print(f"    {line}")
    print(f"  text files rewritten: {len(report.files)}")
    print(f"  path-encoded folders renamed: {len(report.projects)}")
    print(f"  protobuf .pb files left byte-identical: {len(report.protobuf_files)}")
    print(f"  binary SQLite cells left unchanged: {len(report.skipped_binary)}")
    print(f"  skills visible: {len(report.skills)}")
    if report.warnings:
        print("  warnings:")
        for warn in report.warnings:
            print(f"    - {warn}")
    print()
    print(f"Full report: {args.report}")
    if args.dry_run:
        print("Looks good? Run without --dry-run. Both Antigravity apps must stay quit.")
    else:
        print("Next:")
        print("  1. python3 -m antigravity_mac_migrate verify --map", args.map)
        print("  2. python3 -m antigravity_mac_migrate reinstall-native-extensions")
        print("  3. Sign in on the Mac. Open a folder or .code-workspace only after apply.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    _print_warnings(selection.warnings)
    if not selection.profiles:
        print("No copied Antigravity trees were found.")
        return 0
    scan = scan_profiles(selection.profiles)
    print("Skills on this Mac:")
    skills = list_skills(selection.profiles)
    if not skills:
        print("  (none found under ~/.gemini/config/skills or the profile skill folders)")
    for skill in skills:
        print(f"  - {skill.name}")
    print()
    print(f"Protobuf .pb files left byte-identical: {len(scan.protobuf_files)}")
    print(f"Binary SQLite cells not rewritten: {len(scan.skipped_binary)}")
    if scan.skipped_binary:
        print("  Paths inside those cells were not remapped.")
    leftover = scan.windows_paths
    print(f"Windows paths still stored in text or SQLite: {len(leftover)}")
    status = 0
    if leftover:
        desktop = home / "Desktop" / STILL
        desktop.parent.mkdir(parents=True, exist_ok=True)
        desktop.write_text(
            "\n".join(f"{count}\t{path}" for path, count in leftover.most_common()) + "\n",
            encoding="utf-8",
        )
        print(f"  The list is in {desktop}")
        print("  It is not printed here.")
        status = 1
    else:
        print("  none in text or UTF-8 SQLite cells.")
    print()
    for profile in selection.profiles:
        for dot in profile.dot_dirs:
            native = [ext for ext in iter_extensions(dot, profile=profile.name) if ext.needs_reinstall]
            print(f"Windows-native extensions in {profile.name}: {len(native)}")
            for ext in native:
                print(f"  - {ext.ext_id}  ({ext.reason})")
            if native and profile.name == "ide":
                print("Run: python3 -m antigravity_mac_migrate reinstall-native-extensions")
            elif native:
                print("  Not reinstalled. The Antigravity 2.0 CLI name is not confirmed.")
    print()
    cli = ide_cli()
    print(f"Antigravity IDE CLI: {cli or 'not found (install the shell command from the IDE)'}")
    if args.map:
        path_map = load_path_map(args.map)
        missing = missing_mac_targets(path_map)
        if missing:
            print("Mapped Mac paths still missing:")
            for item in missing:
                print(f"  - {item}")
            status = 1
    return status


def cmd_reinstall(args: argparse.Namespace) -> int:
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    _print_warnings(selection.warnings)
    ide_ids: list[str] = []
    for profile in selection.profiles:
        for dot in profile.dot_dirs:
            native = [ext for ext in iter_extensions(dot, profile=profile.name) if ext.needs_reinstall]
            if profile.name != "ide":
                if native:
                    print(f"Windows-native extensions under {profile.name} (reported only, not reinstalled):")
                    for ext in native:
                        print(f"  - {ext.ext_id}  ({ext.reason})")
                continue
            ide_ids.extend(ext.ext_id for ext in native)
    ide_ids = sorted(set(ide_ids))
    if not ide_ids:
        print("No Windows-native IDE extensions detected.")
        return 0
    print("Will force-reinstall in Antigravity IDE:")
    for ext_id in ide_ids:
        print(f"  - {ext_id}")
    if not args.yes:
        print("Re-run with --yes to execute. Antigravity 2.0 extensions are never passed to a CLI.")
        return 0
    for ext_id, code, output in reinstall(ide_ids):
        mark = "ok" if code == 0 else f"fail ({code})"
        print(f"[{mark}] {ext_id}")
        if output:
            print(output)
    return 0


def cmd_keybindings(args: argparse.Namespace) -> int:
    assert_apps_closed(allow_running=args.allow_running)
    home = _home(args)
    selection = resolve_profiles(home, args.profile)
    _print_warnings(selection.warnings)
    if not selection.profiles:
        print("No copied Antigravity trees were found.")
        return 0
    changed_total = 0
    for profile in selection.profiles:
        for user_dir in profile.user_dirs:
            path = user_dir / "keybindings.json"
            if not path.exists():
                print(f"No {path}")
                continue
            changed = _rewrite_keybindings(path, dry_run=args.dry_run)
            changed_total += changed
            print(f"{profile.name}: bindings that need a Mac cmd equivalent: {changed}")
    if changed_total == 0:
        print("No ctrl-only bindings needed a cmd equivalent.")
    return 0


def _rewrite_keybindings(path: Path, *, dry_run: bool) -> int:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print(f"{path} has comments or trailing commas and was not changed.")
        print("Edit it in the app: open the keyboard shortcuts JSON.")
        return 0
    changed = 0
    if not isinstance(data, list):
        print(f"{path} is not a list of bindings and was not changed.")
        return 0
    for item in data:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        if "ctrl+" in key.lower() and not item.get("mac"):
            item["mac"] = _ctrl_to_cmd(key)
            changed += 1
    if dry_run or not changed:
        return changed
    path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
    print(f"Updated {path}")
    return changed


def _ctrl_to_cmd(key: str) -> str:
    return key.replace("ctrl+", "cmd+").replace("Ctrl+", "cmd+").replace("CTRL+", "cmd+")


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

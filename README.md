# AntigravityMigrateWinToMac

Point Antigravity IDE and Antigravity 2.0 profiles you copied from Windows at the folders you use on macOS: conversations, rules, skills, settings, and workspaces.

The tool does not copy files off Windows. You copy the trees, quit both apps, then run a Python 3.11 rewrite. Login does not bring chat history across. Sign in on the Mac for auth only.

This project follows the same command shape as [CursorMigrateWinToMac](https://github.com/JanuszHatala/CursorMigrateWinToMac). Antigravity is not Cursor: there are two desktop apps, one shared `~/.gemini` tree, and protobuf `.pb` conversation files that this version leaves byte-identical.

[![CI](https://github.com/JanuszHatala/AntigravityMigrateWinToMac/actions/workflows/ci.yml/badge.svg)](https://github.com/JanuszHatala/AntigravityMigrateWinToMac/actions/workflows/ci.yml)

## What you need before running the tool

The Windows folder named `Antigravity` used to be the editor. After the 2.0 split, that name belongs to the newer agent app, and the editor's data directory is `Antigravity IDE`. A Windows profile can hold old editor data, 2.0 data, or both, in `Antigravity`. This tool does not guess. It pairs `Antigravity` with the 2.0 Mac app and `Antigravity IDE` with the IDE. It never copies one tree into the other.

| Tree | Windows | macOS |
| --- | --- | --- |
| IDE user data | `%APPDATA%\Antigravity IDE\User` | `~/Library/Application Support/Antigravity IDE/User` |
| IDE extensions | `%USERPROFILE%\.antigravity-ide` | `~/.antigravity-ide` |
| IDE conversations | `%USERPROFILE%\.gemini\antigravity-ide` | `~/.gemini/antigravity-ide` |
| 2.0 user data | `%APPDATA%\Antigravity\User` | `~/Library/Application Support/Antigravity/User` |
| 2.0 extensions | `%USERPROFILE%\.antigravity` | `~/.antigravity` |
| 2.0 local data | `%USERPROFILE%\.gemini\antigravity` | `~/.gemini/antigravity` |
| Shared rules and skills | `%USERPROFILE%\.gemini\GEMINI.md` and `%USERPROFILE%\.gemini\config` | `~/.gemini/GEMINI.md` and `~/.gemini/config` |
| CLI, only if you copied it | `%USERPROFILE%\.gemini\antigravity-cli` | `~/.gemini/antigravity-cli` |
| Your repositories | Wherever you keep them | The layout you want on the Mac |

Example paths (replace the placeholders):

- Windows user folder: `C:\Users\WINDOWS_USER`
- Mac home: `/Users/MAC_USER`
- Another drive: `D:\work` on Windows, `/Users/MAC_USER/work` on the Mac

A lowercase `%APPDATA%\antigravity` folder is only a probe. If it shows up on the Mac as `~/Library/Application Support/antigravity`, it stays with the 2.0 app.

## Migration overview

```text
Windows                                      Mac (copy first)                                      After apply
-------------------------------------------  ----------------------------------------------------  ---------------------------
%APPDATA%\Antigravity IDE\User               ~/Library/.../Antigravity IDE/User                    paths + workspace IDs
%APPDATA%\Antigravity\User                   ~/Library/.../Antigravity/User                        paths + workspace IDs
%USERPROFILE%\.gemini                        ~/.gemini                                             text and SQLite paths
C:\Users\WINDOWS_USER\Projects\...           /Users/MAC_USER/Projects/...                          attached where the folder exists
```

1. On Windows: quit both apps, copy the trees below.
2. On the Mac: if a destination folder already exists, move that whole folder aside (for example `Antigravity IDE.mac-before-migrate`). Then place the Windows copy at the destination. Do not paste a Windows tree on top of a live Mac profile.
3. Preview (`auto` without `--apply`): writes reports into `migrate-work/` inside this tool folder; edit the rename and drop files there.
4. Apply (`auto` with `--apply`): rewrites ready paths and accepted renames. Everything in keep stays unchanged. Both apps must be quit, even if you only select one profile.

Do not open a migrated repo in either app until after apply. Opening a folder first creates an empty `workspaceStorage` id, and the relink will not overwrite it.

---

## Step 1: On Windows (manual)

1. Quit Antigravity IDE and Antigravity 2.0. Check Task Manager so neither process is still running.
2. Copy the trees in the table that exist on that PC. Skip a tree that is not there.
3. Copy your repositories separately.
4. You do not need to copy caches, or secrets that cannot survive the OS change:
   - `Cache`, `CachedData`, `Code Cache`, `GPUCache`, `logs`, `Crashpad`, `Service Worker`, `blob_storage`, `CachedExtensionVSIXs`
   - Cookies, Session Storage, and other safeStorage blobs. Windows DPAPI ciphertext will not decrypt on the Mac. Sign in again. This tool does not try to decrypt it.
   - LocalAppData install directories. Those are the apps, not the profile. Install both apps on the Mac from the official builds.

`%APPDATA%\Antigravity IDE\argv.json` and `%APPDATA%\Antigravity\argv.json` are optional siblings of `User`. Copy them if they exist.

Workspace rules and skills live inside repositories (`.agents/` and legacy `.agent/`, plus `GEMINI.md` and `AGENTS.md`). They move when you copy the repo.

## Step 2: On the Mac (manual placement)

1. Quit both apps. Apply aborts if either one is still running, because both write `~/.gemini`.
2. If `~/Library/Application Support/Antigravity IDE`, `~/Library/Application Support/Antigravity`, `~/.antigravity-ide`, `~/.antigravity`, or `~/.gemini` already exists, move that whole folder aside first.
3. Put each copied tree at the macOS path in the table. Do not merge `Antigravity` into `Antigravity IDE`.
4. Put repositories where you want them long term, for example `/Users/MAC_USER/Projects/api`.
5. Install both apps. You can sign in after apply.

---

## Step 3: Install this tool

**A. Clone from GitHub**

```bash
git clone https://github.com/JanuszHatala/AntigravityMigrateWinToMac.git
cd AntigravityMigrateWinToMac
```

**B. Copy the folder (no git)**

1. Copy the whole project folder (the one that contains `START-HERE.txt`, `migrate.sh`, `pyproject.toml`, and `antigravity_mac_migrate`) to the Mac.
2. Open Terminal, `cd` into that folder, and confirm:

   ```bash
   ls START-HERE.txt README.md pyproject.toml migrate.sh antigravity_mac_migrate
   ```

There is no folder named `antigravity-mac-migrate`. The Python package uses underscores:

```bash
python3 -m antigravity_mac_migrate
```

Install once:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

---

## Step 4: Preview (no changes yet)

Replace the placeholders with your account names.

```bash
python3 -m antigravity_mac_migrate auto \
  --windows-home 'C:\Users\WINDOWS_USER' \
  --mac-home /Users/MAC_USER \
  --also 'D:\work=/Users/MAC_USER/work'
```

Missing trees print a warning and do not fail the run. A machine with only one app still previews. Limit the scan with `--profile ide`, `--profile app`, `--profile gemini`, or `--profile cli` (repeat the flag to select more than one). The default is every copied tree that exists. `~/.gemini/antigravity-cli` is included only when that folder was copied.

This scans copied SQLite databases and config files, then writes reports into `migrate-work/` next to this tool (override with `--report-dir`):

| File | Meaning | You edit it? |
| --- | --- | --- |
| `antigravity-migrate-ready.txt` | Mac folder exists at the mirrored path | No |
| `antigravity-migrate-rename-suggested.txt` | Tool guessed a different Mac folder name | Copy chosen lines into the rename file |
| `antigravity-migrate-rename.txt` | Accepted Windows=Mac pairs | Yes |
| `antigravity-migrate-drop.txt` | Workspace entries to leave unattached | Yes, one Windows path per line |
| `antigravity-migrate-keep.txt` | Not applied: missing copy, worktree, or internal | No |
| `antigravity-migrate-missing.txt` | Same as `[not-copied]` lines in keep | No |
| `antigravity-migrate-outside-home.txt` | Paths outside `--windows-home` and `--also` | Fix the mapping or ignore |
| `antigravity-migrate-pb.txt` | Protobuf `.pb` files left byte-identical | No |
| `antigravity-migrate-skipped-binary.txt` | SQLite cells that are not UTF-8 | No |
| `path-map.json` | Prefixes used for this preview | Advanced use |

### Tags in `antigravity-migrate-keep.txt`

- `[not-copied]`: the mirrored Mac path does not exist yet. Copy the project, or add a line to the rename file, then preview again.
- `[worktree]`: a git worktree path. Leave it unless you recreate that worktree.
- `[antigravity-internal]`: an AppData or Workspaces path that is not a repository. Per-repo chats in ready can still attach.

### Rename file

One `Windows=Mac` line per row. Example, when the Mac folder name gained a hyphen:

```text
D:\work\oldname=/Users/MAC_USER/work/old-name
```

Longest matching prefix wins. The preview lists both prefixes when two rules could cover one path, so a bad `--also` is visible before apply.

---

## Step 5: Apply

Both apps must be quit. Selecting one profile does not relax that check.

```bash
python3 -m antigravity_mac_migrate auto \
  --windows-home 'C:\Users\WINDOWS_USER' \
  --mac-home /Users/MAC_USER \
  --also 'D:\work=/Users/MAC_USER/work' \
  --renames migrate-work/antigravity-migrate-rename.txt \
  --drop migrate-work/antigravity-migrate-drop.txt \
  --apply
```

Apply rewrites, in each copied profile:

- `settings.json`, `keybindings.json`, snippets, and profile JSON
- UTF-8 cells in every SQLite file under the copied trees, including `state.vscdb` and per-chat `.db` files whose tables are not `ItemTable`
- `workspaceStorage` ids when `workspace.json` has a `folder` or `workspace` URI
- Text and JSON under the extension directory and the matching `.gemini` tree (brain markdown, `.pbtxt` annotations, skills, workflows, rules, `mcp_config.json`). Installed packages inside an `extensions` folder are left unchanged
- `GEMINI.md`, `AGENTS.md`, `.agents/`, and `.agent/` inside a mapped repository
- `.code-workspace` files that already sit at the mapped Mac path, including ones nested inside a mapped folder

String replacement uses the Windows home and every `--also` prefix, including a folder that was not an exact workspace match. `workspaceStorage` is still attached only for exact Mac folders and accepted renames. A path listed in the drop file is not attached. Text under the Windows home or an `--also` prefix is still rewritten.

It does not patch `.pb` files. A path inside a protobuf step can stay wrong even when the sidebar text was rewritten. If `antigravity-migrate-skipped-binary.txt` lists a cell, that cell was left as stored. A sidebar index kept as protobuf was not remapped. Say that plainly: those chats were not rewritten.

SQLite databases are copied to a backup beside the tree before they are changed: `User.mac-migrate-backup-<timestamp>/` next to a User folder, or `<folder>.mac-migrate-backup-<timestamp>/` next to other roots.

A `workspaceStorage` id that already exists is a collision. That entry is not overwritten. Quit both apps, move the empty Mac id aside, and rerun apply. The same rule applies to two path-encoded directory names that would land on one Mac name.

`installation_id` and `storage.json` are copied with the profile and are not regenerated. Auth tokens inside them still will not decrypt.

Then, for the IDE only, reinstall extensions that shipped Windows native binaries:

```bash
python3 -m antigravity_mac_migrate reinstall-native-extensions --yes
```

The IDE command is looked up on `PATH`, under `/Applications/Antigravity IDE.app/.../bin`, and Homebrew. The separate `agy` CLI is not used. Packages under `~/.antigravity` are reported and not passed to a CLI. The 2.0 binary name is not confirmed.

Optional Ctrl-to-Cmd pass, once per app `keybindings.json` that was copied:

```bash
python3 -m antigravity_mac_migrate mac-cmd-keybindings
```

---

## Step 6: Open projects on the Mac

1. Start the app you migrated and sign in.
2. Confirm global skills under `~/.gemini/config/skills`. Legacy skills under `~/.gemini/antigravity/skills` are still read.
3. Single repo: File, Open Folder.
4. Multi-root: File, Open Workspace from File, and choose the `.code-workspace` on the Mac.

The same conversation UUID may exist in both `.gemini/antigravity` and `.gemini/antigravity-ide`. Both copies are kept.

---

## Command reference

```bash
python3 -m antigravity_mac_migrate auto \
  --windows-home 'C:\Users\WINDOWS_USER' \
  --mac-home /Users/MAC_USER \
  --also 'D:\work=/Users/MAC_USER/work'

python3 -m antigravity_mac_migrate auto ... \
  --renames migrate-work/antigravity-migrate-rename.txt \
  --drop migrate-work/antigravity-migrate-drop.txt \
  --apply

python3 -m antigravity_mac_migrate verify
python3 -m antigravity_mac_migrate reinstall-native-extensions --yes
```

`scan`, `check-map`, and `apply --map path-map.json` remain for an edited map. Most people only need `auto`.

`--profile` limits which trees are read. It does not let apply run while the other app is open.

## What this version does not do

No GUI. No Linux paths. No copy from Windows. No safeStorage decrypt. No `.pb` patch. No merge of two live profiles. No edit of an installed `workbench.desktop.main.js`. No automatic import of a Windows `Antigravity` folder into the IDE.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Warning about a missing tree | Expected when that app was not copied. The other trees still run. |
| Many lines in missing / keep | Copy the repo to the Mac path, or add a rename line, then preview and apply again. |
| Apply says an app is still running | Quit both with Cmd+Q. The check is not per profile. |
| Empty chat list after open | The folder you opened is not the path in ready or rename. |
| Collision in workspaceStorage | You opened the folder before apply. Move the empty Mac id aside and apply again. See `antigravity-migrate-not-attached.txt`. |
| Sidebar title still shows a Windows path | That cell was binary. See `antigravity-migrate-skipped-binary.txt`. |
| A step inside a conversation still has a Windows path | It lives in a `.pb` file. v1 did not patch it. |
| Chats from an old `Antigravity` folder show up in 2.0 | That folder is paired with the 2.0 app on purpose. |

## Development

```bash
pip install -e ".[dev]"
python -m pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).

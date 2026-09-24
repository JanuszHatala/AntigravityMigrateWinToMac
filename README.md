# AntigravityMigrateWinToMac

Point Antigravity IDE and Antigravity 2.0 data from Windows at the folders you use on macOS: conversations, rules, skills, settings, and workspaces.

`scripts/Export-AntigravityWindows.ps1` and `scripts/import-antigravity-mac.sh` copy those trees. This tool only rewrites paths in that copy. Sign in on the Mac for auth. Login does not bring chat history across.

The two apps stay separate. The editor's data directory is `Antigravity IDE`. The newer app's data directory is `Antigravity`. They share `~/.gemini`. Protobuf `.pb` conversation files stay byte-identical. A Windows `Antigravity` folder is never imported into the IDE.

[CursorMigrateWinToMac](https://github.com/JanuszHatala/CursorMigrateWinToMac) is a sibling project for a different editor. You do not need it. Every step is below.

[![CI](https://github.com/JanuszHatala/AntigravityMigrateWinToMac/actions/workflows/ci.yml/badge.svg)](https://github.com/JanuszHatala/AntigravityMigrateWinToMac/actions/workflows/ci.yml)

Placeholders in the commands: `C:\Users\WINDOWS_USER` and `/Users/MAC_USER`. Replace them with your account names.

## Copy from Windows to the Mac

Quit Antigravity IDE and Antigravity 2.0 on the PC. Check Task Manager so neither process is still running. Copy each tree that exists, then run preview and apply below. The table in this section is the same map if you copy by hand.

### Scripts

Run either script from any working directory. Profile paths come from `%APPDATA%`, `%USERPROFILE%`, and `$HOME`, not from the folder that contains the script. The scripts copy bytes. They do not rewrite paths, and `.pb` files stay byte-identical.

On Windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\AntigravityMigrateWinToMac\scripts\Export-AntigravityWindows.ps1 -OutputZip C:\Users\WINDOWS_USER\Desktop\antigravity-migrate.zip -Also D:\work
```

| Parameter | Meaning |
| --- | --- |
| `-OutputZip` | Required absolute path of the zip. A relative path is refused. Also required with `-DryRun`. |
| `-Profile` | `ide`, `app`, `gemini`, or `cli`. Repeat to select more than one. Default: every one of those trees that exists. |
| `-Also` | Extra absolute Windows folders, usually repositories. Repeat for another folder. The script does not search for repositories. |
| `-WindowsHome` | Profile root when it is not `%USERPROFILE%`. Dot folders are read from here. Roaming is then `WindowsHome\AppData\Roaming`. |
| `-DryRun` | Print each tree and the cache paths left out. The zip is not written. |

Drop `-Also` when every repository sits under the Windows profile. The CLI folder is included only when it exists. `Antigravity IDE`, `Antigravity`, shared `.gemini` (`GEMINI.md` and `config`), and the CLI stay separate zip trees. IDE data is not written into the 2.0 tree, or the reverse.

The zip starts with `manifest.json`: profile id, Windows source, path inside the zip, and the Mac path relative to the home directory. Extra `-Also` folders are stored under `also/` with no Mac path.

Copy the zip to the Mac. `python3` is required (the same interpreter as preview).

```bash
bash /path/to/AntigravityMigrateWinToMac/scripts/import-antigravity-mac.sh --zip /Users/MAC_USER/Desktop/antigravity-migrate.zip
```

| Parameter | Meaning |
| --- | --- |
| `--zip` | Required absolute path of the zip. |
| `--profile` | `ide`, `app`, `gemini`, or `cli`. Repeat to select more than one. Default: every profile in the manifest. |
| `-n`, `--dry-run` | Print the planned copies. Writes nothing under `$HOME`. |
| `--move-aside` | If a destination already exists, rename that whole folder or file to `name.mac-before-migrate`, then place the Windows copy. |
| `--also-to ID=ABSOLUTE_PATH` | Place one `also/` folder at that exact path. `ID` is `also-1`, `also-2`, and so on, in the `-Also` order. |

If a destination already exists and you omit `--move-aside`, the script exits and leaves the Mac files alone. It does not copy into a live folder.

`-Also` folders are left in the zip. The script prints the Windows path and the `also/<n>` path. Copy those repositories to the Mac folders you want, then pass the same pair to preview as `--also 'D:\work=/Users/MAC_USER/work'`. `--also-to` uses only a path you type. There is no default Projects folder.

Quit both apps on the Mac before import. They both write `~/.gemini`.

### Copy by hand

If a destination already exists, move that whole folder aside first (for example `Antigravity IDE.mac-before-migrate`). Then place the Windows copy at the destination. Do not paste a Windows tree on top of a live Mac profile. Do not merge `Antigravity` into `Antigravity IDE`.

After the 2.0 split, the name `Antigravity` belongs to the newer app. A Windows `Antigravity` folder can hold old editor data, 2.0 data, or both. This tool does not guess. It pairs `Antigravity` with the 2.0 app and `Antigravity IDE` with the IDE.

| What | Windows | Mac |
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

Copy repositories separately. An example Mac folder is `/Users/MAC_USER/Projects/api`. Any folder is fine.

Optional siblings of `User`, copy them if they exist: `%APPDATA%\Antigravity IDE\argv.json` and `%APPDATA%\Antigravity\argv.json`.

A lowercase `%APPDATA%\antigravity` folder is only a probe. If it shows up on the Mac as `~/Library/Application Support/antigravity`, it stays with the 2.0 app.

Rules and skills inside a repository (`.agents/`, legacy `.agent/`, `GEMINI.md`, `AGENTS.md`) move when you copy that repository.

Do not open a copied repository in either app until after apply. Opening a folder first creates an empty `workspaceStorage` id, and apply will not overwrite it.

## What to skip

- `Cache`, `CachedData`, `Code Cache`, `GPUCache`, `logs`, `Crashpad`, `Service Worker`, `blob_storage`, `CachedExtensionVSIXs`
- Cookies, Session Storage, and other safeStorage blobs. Windows DPAPI ciphertext will not decrypt on the Mac. Sign in again. This tool does not decrypt it.
- LocalAppData install directories. Those are the apps, not the profile. Install both apps on the Mac from the official builds.

The export script skips those directory names inside the Antigravity trees, plus files named `Cookies` and `Cookies-journal`. A directory named `logs` under `.gemini` is kept, because CLI transcripts live in `.system_generated/logs`. `-Also` folders are copied whole. A path under LocalAppData is refused. Install directories are not zipped.

## Check each placement

Quit both apps on the Mac. Apply later aborts if either is still running, because both write `~/.gemini`.

Each path below should be the Windows tree you just placed, not a mix of two profiles. A missing path is expected only when that tree was not on the PC. `ls` prints an error for a path you skipped. That is fine.

```bash
ls -d "$HOME/Library/Application Support/Antigravity IDE/User"
ls -d "$HOME/.antigravity-ide"
ls -d "$HOME/.gemini/antigravity-ide"
ls -d "$HOME/Library/Application Support/Antigravity/User"
ls -d "$HOME/.antigravity"
ls -d "$HOME/.gemini/antigravity"
ls -d "$HOME/.gemini/GEMINI.md" "$HOME/.gemini/config"
ls -d "$HOME/.gemini/antigravity-cli"
```

Confirm one repository as well. This path is an example. Any folder is fine.

```bash
ls -d /Users/MAC_USER/Projects/api
```

Install both apps. Sign in after apply.

## Preview

Put this tool folder anywhere on the Mac. It is the folder that contains `START-HERE.txt`, `README.md`, `pyproject.toml`, `migrate.sh`, and `antigravity_mac_migrate`. There is no folder named `antigravity-mac-migrate`. `./migrate.sh` runs the same module as the `python3 -m` commands below.

```bash
git clone https://github.com/JanuszHatala/AntigravityMigrateWinToMac.git
cd AntigravityMigrateWinToMac
ls START-HERE.txt README.md pyproject.toml migrate.sh scripts antigravity_mac_migrate
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Preview does not change either app. It writes reports into `migrate-work/` inside this tool folder (next to `antigravity_mac_migrate/`, the directory that contains `pyproject.toml`). Pass `--report-dir` to write that same set of files somewhere else.

```bash
python3 -m antigravity_mac_migrate auto \
  --windows-home 'C:\Users\WINDOWS_USER' \
  --mac-home /Users/MAC_USER \
  --also 'D:\work=/Users/MAC_USER/work'
```

`D:\work=/Users/MAC_USER/work` is an example of a folder outside the Windows user profile. Any pair is fine. Omit `--also` when every repository lives under `C:\Users\WINDOWS_USER`.

A missing tree prints a warning and does not fail the run. Limit the scan with `--profile ide`, `--profile app`, `--profile gemini`, or `--profile cli`. Repeat the flag to select more than one. The default is every copied tree that exists. `~/.gemini/antigravity-cli` is included only when that folder was copied. `--profile` does not let apply run while the other app is open.

## Read the reports

Open `migrate-work/` in the tool folder.

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

Tags in `antigravity-migrate-keep.txt`:

- `[not-copied]`: the mirrored Mac path does not exist yet. Copy the project, or add a line to the rename file, then preview again.
- `[worktree]`: a git worktree path. Leave it unless you recreate that worktree.
- `[antigravity-internal]`: an AppData or Workspaces path that is not a repository. Per-repo chats in ready can still attach.

One `Windows=Mac` line per row in the rename file. Longest matching prefix wins. Example, when the Mac folder name gained a hyphen:

```text
D:\work\oldname=/Users/MAC_USER/work/old-name
```

The preview lists both prefixes when two rules could cover one path.

## Apply

Both apps must be quit. Selecting one profile does not relax that check. Quit both with Cmd+Q and confirm in Activity Monitor.

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
- UTF-8 cells in every SQLite file under the copied trees, including `state.vscdb` and per-chat `.db` files
- `workspaceStorage` ids when `workspace.json` has a `folder` or `workspace` URI
- Text and JSON under the extension directory and the matching `.gemini` tree (brain markdown, `.pbtxt` annotations, skills, workflows, rules, `mcp_config.json`). Installed packages inside an `extensions` folder stay unchanged
- `GEMINI.md`, `AGENTS.md`, `.agents/`, and `.agent/` inside a mapped repository
- `.code-workspace` files that already sit at the mapped Mac path, including ones nested inside a mapped folder

String replacement uses the Windows home and every `--also` prefix. `workspaceStorage` is attached only for exact Mac folders and accepted renames. A path in the drop file is not attached. Text under the Windows home or an `--also` prefix is still rewritten.

`.pb` files are not patched. A path inside a protobuf step can stay wrong even when the sidebar text was rewritten. A cell listed in `antigravity-migrate-skipped-binary.txt` was left as stored.

Before a SQLite file is changed, it is copied to `User.mac-migrate-backup-<timestamp>/` next to a User folder, or to `<folder>.mac-migrate-backup-<timestamp>/` next to another root.

A `workspaceStorage` id that already exists is not overwritten. Quit both apps, move the empty Mac id aside, and rerun apply. The same rule applies when two path-encoded directory names would land on one Mac name.

`installation_id` and `storage.json` are copied with the profile and are not regenerated. Auth tokens inside them still will not decrypt.

The same conversation UUID may exist in both `~/.gemini/antigravity` and `~/.gemini/antigravity-ide`. Both copies are kept.

## Check that apply worked

Apply prints the backup path, how many workspace entries attached, and how many text files and SQLite databases changed. Entries left unattached are in `migrate-work/antigravity-migrate-not-attached.txt`. The JSON summary is `migrate-work/antigravity-migrate-report.json`.

```bash
python3 -m antigravity_mac_migrate verify
```

`verify` lists skills under the copied trees and any extensions that shipped Windows native binaries. If Windows paths remain in text or UTF-8 SQLite cells, it writes `migrate-work/antigravity-migrate-still-windows.txt` and exits with status 1. Paths that live only in `.pb` files, or in cells listed in `antigravity-migrate-skipped-binary.txt`, are expected to remain.

Then start the app you migrated and sign in. Global skills are under `~/.gemini/config/skills`. Legacy skills under `~/.gemini/antigravity/skills` are still read. Single repo: File, Open Folder. Multi-root: File, Open Workspace from File, and choose the `.code-workspace` on the Mac.

For the IDE only, reinstall extensions that shipped Windows native binaries:

```bash
python3 -m antigravity_mac_migrate reinstall-native-extensions --yes
```

The IDE command is looked up on `PATH`, under `/Applications/Antigravity IDE.app/.../bin`, and Homebrew. The separate `agy` CLI is not used. Packages under `~/.antigravity` are reported and not passed to a CLI.

Optional Ctrl-to-Cmd pass, once per copied `keybindings.json`:

```bash
python3 -m antigravity_mac_migrate mac-cmd-keybindings
```

`scan`, `check-map`, and `apply --map path-map.json` are for an edited map. Most people only need `auto`.

## What this version does not do

No GUI. No Linux paths. No safeStorage decrypt. No `.pb` patch. No merge of two live profiles. No edit of an installed `workbench.desktop.main.js`. No automatic import of a Windows `Antigravity` folder into the IDE. The Python commands only rewrite. Copying is the scripts above, or the hand-copy table.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Warning about a missing tree | Expected when that app was not copied. The other trees still run. |
| Many lines in missing / keep | Copy the repo to the Mac path, or add a rename line, then preview and apply again. |
| Apply says an app is still running | Quit both with Cmd+Q. The check is not per profile. |
| Empty chat list after open | The folder you opened is not the path in ready or rename. |
| Collision in workspaceStorage | You opened the folder before apply. Move the empty Mac id aside and apply again. See `migrate-work/antigravity-migrate-not-attached.txt`. |
| Sidebar title still shows a Windows path | That cell was binary. See `migrate-work/antigravity-migrate-skipped-binary.txt`. |
| A step inside a conversation still has a Windows path | It lives in a `.pb` file. This version does not patch it. |
| Chats from an old `Antigravity` folder show up in 2.0 | That folder is paired with the 2.0 app on purpose. |

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).

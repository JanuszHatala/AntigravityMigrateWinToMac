#!/usr/bin/env bash
# Place an Antigravity Windows export under $HOME.
# Destinations come from $HOME and the zip manifest, never from this script's directory.
# python3 reads the manifest. The moves below are plain mv of those trees.
# Re-exec under bash so `zsh scripts/import-antigravity-mac.sh` works on macOS bash 3.2.

if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -eu

usage() {
  cat <<'EOF'
usage: import-antigravity-mac.sh --zip ABSOLUTE_ZIP [options]

  --zip ABSOLUTE_ZIP     Zip written by Export-AntigravityWindows.ps1
  --profile NAME         ide, app, gemini, or cli. Repeat to select more than one.
                         Default: every profile entry in the manifest.
  -n, --dry-run          Print the planned copies. Do not change $HOME.
  --move-aside           If a destination already exists, rename that whole
                         folder or file to name.mac-before-migrate, then place
                         the Windows copy. Without this flag, an existing
                         destination is an error.
  --also-to ID=ABS_PATH  Place one extra folder from the zip at this absolute
                         path. Repeat for each extra folder you want placed.
                         Extra folders are otherwise left in the zip and printed.

The script does not choose a Projects folder for -Also entries.
EOF
}

if [ "${#@}" -eq 0 ]; then
  usage >&2
  exit 1
fi

zip_path=""
dry_run=0
move_aside=0
profiles=""
also_to=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --zip)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--zip requires an absolute path." >&2
        exit 1
      fi
      zip_path="$2"
      shift 2
      ;;
    --profile)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--profile requires ide, app, gemini, or cli." >&2
        exit 1
      fi
      if [ -n "$profiles" ]; then
        profiles="$profiles,$2"
      else
        profiles="$2"
      fi
      shift 2
      ;;
    -n|--dry-run)
      dry_run=1
      shift
      ;;
    --move-aside)
      move_aside=1
      shift
      ;;
    --also-to)
      if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
        echo "--also-to requires ID=ABSOLUTE_PATH." >&2
        exit 1
      fi
      if [ -n "$also_to" ]; then
        also_to="$also_to
$2"
      else
        also_to="$2"
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ -z "$zip_path" ]; then
  echo "--zip is required and must be an absolute path." >&2
  exit 1
fi

case "$zip_path" in
  /*) ;;
  *)
    echo "--zip must be an absolute path. Refusing: $zip_path" >&2
    exit 1
    ;;
esac

if [ ! -f "$zip_path" ]; then
  echo "Zip not found: $zip_path" >&2
  exit 1
fi

if [ -z "${HOME:-}" ]; then
  echo "HOME is not set." >&2
  exit 1
fi

case "$HOME" in
  /*) ;;
  *)
    echo "HOME must be an absolute path. Refusing: $HOME" >&2
    exit 1
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to read the zip manifest." >&2
  exit 1
fi

extract=""
if [ "$dry_run" -eq 0 ]; then
  extract=$(mktemp -d "${TMPDIR:-/tmp}/antigravity-import.XXXXXX")
  trap 'if [ -n "$extract" ]; then rm -rf "$extract"; fi' EXIT
fi

plan=$(mktemp "${TMPDIR:-/tmp}/antigravity-plan.XXXXXX")
trap 'rm -f "$plan"; if [ -n "$extract" ]; then rm -rf "$extract"; fi' EXIT

set +e
IMPORT_PROFILES="$profiles" IMPORT_ALSO_TO="$also_to" python3 - "$zip_path" "$HOME" "$extract" "$dry_run" "$move_aside" >"$plan" <<'PY'
import json
import os
import sys
import zipfile

zip_path, home, extract, dry_run, move_aside = sys.argv[1:6]
dry_run = dry_run == "1"
move_aside = move_aside == "1"
home = os.path.abspath(home)
errors = []
actions = []

def emit(line):
    sys.stdout.write(line + "\n")

def fail(message):
    errors.append(message)

requested = [part for part in os.environ.get("IMPORT_PROFILES", "").split(",") if part]
allowed = {"ide", "app", "gemini", "cli"}
for name in requested:
    if name not in allowed:
        fail("Unknown profile %s. Use ide, app, gemini, or cli." % name)

also_map = {}
for line in os.environ.get("IMPORT_ALSO_TO", "").splitlines():
    if not line:
        continue
    if "=" not in line:
        fail("--also-to must be ID=ABSOLUTE_PATH: %s" % line)
        continue
    ident, dest = line.split("=", 1)
    ident = ident.strip()
    dest = dest.strip()
    if not ident:
        fail("--also-to is missing an id.")
        continue
    if ident in also_map:
        fail("--also-to id is listed twice: %s" % ident)
        continue
    if not dest.startswith("/"):
        fail("--also-to destination must be an absolute path: %s" % dest)
        continue
    also_map[ident] = os.path.abspath(dest)

try:
    archive = zipfile.ZipFile(zip_path)
except zipfile.BadZipFile as exc:
    emit("error\tZip is not readable: %s" % exc)
    sys.exit(1)

def unsafe(name):
    rel = name.replace("\\", "/").lstrip("/")
    parts = [part for part in rel.split("/") if part not in ("", ".")]
    return any(part == ".." for part in parts), rel

names = []
for info in archive.infolist():
    bad, rel = unsafe(info.filename)
    if bad:
        fail("Unsafe path in zip: %s" % info.filename)
        continue
    names.append(rel.rstrip("/"))

if "manifest.json" not in names:
    fail("Zip has no manifest.json.")
    manifest = None
else:
    try:
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        fail("manifest.json is not UTF-8 JSON: %s" % exc)
        manifest = None

entries = []
if isinstance(manifest, dict):
    if manifest.get("version") != 1:
        fail("Unsupported manifest version.")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list):
        fail("Manifest entries must be a list.")
    else:
        entries = raw_entries
elif manifest is not None:
    fail("Manifest must be an object.")

present = set()
for entry in entries:
    if isinstance(entry, dict) and entry.get("profile") in allowed:
        present.add(entry.get("profile"))
for name in requested:
    if name not in present and name in allowed:
        fail("Profile %s is not in the manifest." % name)

used_ids = set()
destinations = {}

def under_home(dest):
    dest = os.path.abspath(dest)
    if dest == home:
        return False
    return dest.startswith(home + os.sep)

def zip_has_prefix(zip_path_rel):
    prefix = zip_path_rel.strip("/")
    if prefix in names:
        return True
    prefix_dir = prefix + "/"
    return any(name == prefix or name.startswith(prefix_dir) for name in names)

for entry in entries:
    if not isinstance(entry, dict):
        fail("Manifest entry is not an object.")
        continue
    profile = entry.get("profile")
    ident = entry.get("id")
    kind = entry.get("kind")
    source = entry.get("source") or ""
    zip_rel = entry.get("zipPath") or ""
    mac_rel = entry.get("macRelative")
    if not ident or ident in used_ids:
        fail("Manifest entry id is missing or repeated.")
        continue
    used_ids.add(ident)
    if kind not in ("dir", "file"):
        fail("Manifest entry %s has an unknown kind." % ident)
        continue
    if not zip_rel or zip_rel.startswith("/") or "\\" in zip_rel or ".." in zip_rel.split("/"):
        fail("Manifest zip path is not a relative path: %s" % zip_rel)
        continue
    if not zip_has_prefix(zip_rel):
        fail("Zip is missing %s for %s." % (zip_rel, ident))
        continue

    if profile == "also":
        dest = also_map.get(ident)
        if dest is None:
            emit("leave\t%s\t%s\t%s" % (ident, source, zip_rel))
            continue
        if os.path.abspath(dest) == home:
            fail("Refusing to use HOME as the destination for %s." % ident)
            continue
    elif profile in allowed:
        if requested and profile not in requested:
            continue
        if not isinstance(mac_rel, str) or not mac_rel:
            fail("Manifest entry %s has no Mac path. Refusing to guess." % ident)
            continue
        if mac_rel.startswith("/") or mac_rel.startswith("~") or "\\" in mac_rel:
            fail("Mac path for %s must be relative to HOME: %s" % (ident, mac_rel))
            continue
        parts = mac_rel.split("/")
        if any(part in ("", ".", "..") for part in parts):
            fail("Mac path for %s is not a safe relative path: %s" % (ident, mac_rel))
            continue
        dest = home
        for part in parts:
            dest = os.path.join(dest, part)
        dest = os.path.abspath(dest)
        if not dest.startswith("/") or not under_home(dest):
            fail("Destination for %s is not under HOME: %s" % (ident, dest))
            continue
    else:
        fail("Unknown profile in manifest: %s" % profile)
        continue

    if dest in destinations:
        fail("Two entries would write %s (%s and %s)." % (dest, destinations[dest], ident))
        continue
    destinations[dest] = ident
    exists = os.path.lexists(dest)
    aside = dest + ".mac-before-migrate"
    if exists and move_aside:
        if os.path.lexists(aside):
            fail("Aside name already exists: %s" % aside)
            continue
        emit("aside\t%s\t%s" % (dest, aside))
    elif exists:
        fail("Destination already exists: %s" % dest)
        continue
    emit("copy\t%s\t%s\t%s\t%s\t%s\t%s" % (ident, profile, kind, dest, source, zip_rel))

unknown_also = [ident for ident in also_map if ident not in used_ids]
for ident in unknown_also:
    fail("--also-to id is not in the manifest: %s" % ident)

if not dry_run and not errors:
    extract_root = os.path.realpath(extract)
    os.makedirs(extract_root, exist_ok=True)
    for info in archive.infolist():
        bad, rel = unsafe(info.filename)
        if bad or not rel:
            continue
        target = os.path.realpath(os.path.join(extract_root, rel))
        if target != extract_root and not target.startswith(extract_root + os.sep):
            fail("Unsafe path in zip: %s" % info.filename)
            break
    if not errors:
        archive.extractall(extract_root)

archive.close()

for message in errors:
    emit("error\t" + message)
sys.exit(1 if errors else 0)
PY
status=$?
set -e

cat "$plan"

if [ "$status" -ne 0 ]; then
  exit "$status"
fi

if [ "$dry_run" -eq 1 ]; then
  exit 0
fi

aside_from=""
aside_to=""
placed=""

restore() {
  # Best effort: drop trees this run placed, then put moved-aside folders back.
  if [ -n "$placed" ]; then
    printf '%s\n' "$placed" | while IFS= read -r dest; do
      if [ -n "$dest" ] && [ -e "$dest" -o -L "$dest" ]; then
        rm -rf "$dest"
      fi
    done
  fi
  if [ -n "$aside_from" ]; then
    printf '%s\n' "$aside_to" >"$plan.aside_to"
    printf '%s\n' "$aside_from" >"$plan.aside_from"
    paste -d "$(printf '\t')" "$plan.aside_to" "$plan.aside_from" | while IFS="$(printf '\t')" read -r src dest; do
      if [ -n "$src" ] && [ -e "$src" -o -L "$src" ] && [ ! -e "$dest" ] && [ ! -L "$dest" ]; then
        mv "$src" "$dest"
      fi
    done
    rm -f "$plan.aside_to" "$plan.aside_from"
  fi
}

# Move existing destinations aside before any Windows tree is placed.
while IFS="$(printf '\t')" read -r op dest aside; do
  if [ "$op" != "aside" ]; then
    continue
  fi
  if [ -e "$aside" ] || [ -L "$aside" ]; then
    echo "Aside name already exists: $aside" >&2
    restore
    exit 1
  fi
  if ! mv "$dest" "$aside"; then
    echo "Could not move aside: $dest" >&2
    restore
    exit 1
  fi
  if [ -n "$aside_from" ]; then
    aside_from="$aside_from
$dest"
    aside_to="$aside_to
$aside"
  else
    aside_from="$dest"
    aside_to="$aside"
  fi
done <"$plan"

while IFS="$(printf '\t')" read -r op ident profile kind dest source zip_rel; do
  if [ "$op" != "copy" ]; then
    continue
  fi
  src="$extract/$zip_rel"
  if [ ! -e "$src" ]; then
    echo "Missing extracted tree: $zip_rel" >&2
    restore
    exit 1
  fi
  parent=$(dirname "$dest")
  if ! mkdir -p "$parent"; then
    echo "Could not create $parent" >&2
    restore
    exit 1
  fi
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    echo "Destination already exists: $dest" >&2
    restore
    exit 1
  fi
  if ! mv "$src" "$dest"; then
    echo "Could not place $dest" >&2
    restore
    exit 1
  fi
  if [ -n "$placed" ]; then
    placed="$placed
$dest"
  else
    placed="$dest"
  fi
done <"$plan"

exit 0

"""Rewrite Windows paths inside SQLite databases copied with an Antigravity profile."""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from antigravity_mac_migrate.files_rewrite import SKIP_DIR_NAMES
from antigravity_mac_migrate.paths import PathRewriter

SQLITE_MAGIC = b"SQLite format 3\x00"


@dataclass
class SqliteRewriteStats:
    path: Path
    rows_seen: int = 0
    rows_changed: int = 0
    skipped_binary: int = 0
    skipped_binary_notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _skipped_dir(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES or "mac-migrate-backup" in part for part in path.parts)


def is_sqlite_file(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() == ".pb":
        return False
    try:
        with path.open("rb") as handle:
            return handle.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def iter_sqlite_files(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [path for path in root.rglob("*") if path.is_file()]
        else:
            continue
        for path in candidates:
            if _skipped_dir(path) or path.suffix.lower() == ".pb":
                continue
            key = path.resolve() if path.exists() else path
            if key in seen or not is_sqlite_file(path):
                continue
            seen.add(key)
            found.append(path)
    return sorted(found)


def checkpoint_and_copy(db_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        side = Path(str(db_path) + suffix)
        if side.exists():
            shutil.copy2(side, Path(str(backup_path) + suffix))
    if not db_path.exists():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()


def rewrite_db(
    db_path: Path,
    rewriter: PathRewriter,
    *,
    dry_run: bool = False,
) -> SqliteRewriteStats:
    """Rewrite UTF-8 text cells in every table. Undecodable blobs stay as they are.

    ``state.vscdb`` still stores workspace ids in ``ItemTable``. Those ids are
    rewritten when ``rewriter`` carries the relink map. Other conversation
    databases use their own table names and go through the same text walk.
    """
    stats = SqliteRewriteStats(path=db_path)
    if not db_path.exists() or db_path.suffix.lower() == ".pb":
        return stats
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        for table in tables:
            if str(table).startswith("sqlite_"):
                continue
            try:
                _rewrite_table(conn, str(table), rewriter, stats, dry_run=dry_run)
            except sqlite3.DatabaseError as exc:
                stats.warnings.append(f"{db_path} table {table}: {exc}")
        if not dry_run:
            conn.commit()
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise RuntimeError(f"{db_path}: integrity_check failed: {integrity}")
    finally:
        conn.close()
    return stats


def _rewrite_table(
    conn: sqlite3.Connection,
    table: str,
    rewriter: PathRewriter,
    stats: SqliteRewriteStats,
    *,
    dry_run: bool,
) -> None:
    quoted = _quote_ident(table)
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({quoted})")]
    if not columns:
        return
    try:
        cursor = conn.execute(f"SELECT rowid AS _migrate_rowid, * FROM {quoted}")
        has_rowid = True
    except sqlite3.OperationalError:
        cursor = conn.execute(f"SELECT * FROM {quoted}")
        has_rowid = False
    rows = cursor.fetchall()
    updates: list[tuple] = []
    for row in rows:
        stats.rows_seen += 1
        if has_rowid:
            rowid = row[0]
            values = list(row[1:])
        else:
            rowid = None
            values = list(row)
        if len(values) != len(columns):
            stats.warnings.append(f"{table}: column count mismatch; row left unchanged")
            continue
        new_values: list[object] = []
        changed = False
        binary_cols: list[str] = []
        for column, cell in zip(columns, values):
            new_cell, cell_changed, cell_binary = _rewrite_cell(cell, rewriter)
            new_values.append(new_cell)
            changed = changed or cell_changed
            if cell_binary:
                binary_cols.append(str(column))
        if binary_cols:
            stats.skipped_binary += 1
            key_note = ""
            if "key" in columns:
                key_note = f" key={values[columns.index('key')]!s}"
            stats.skipped_binary_notes.append(
                f"{stats.path} table={table}{key_note} columns={','.join(binary_cols)}"
            )
        if not changed:
            continue
        if not has_rowid:
            stats.warnings.append(
                f"{table}: text changed but the table has no rowid; left unchanged"
            )
            continue
        stats.rows_changed += 1
        updates.append((*new_values, rowid))
    if dry_run or not updates:
        return
    assignments = ", ".join(f"{_quote_ident(column)} = ?" for column in columns)
    conn.executemany(
        f"UPDATE {quoted} SET {assignments} WHERE rowid = ?",
        updates,
    )


def _rewrite_cell(cell, rewriter: PathRewriter) -> tuple[object, bool, bool]:
    if cell is None:
        return cell, False, False
    if isinstance(cell, bytes):
        try:
            text = cell.decode("utf-8")
        except UnicodeDecodeError:
            return cell, False, True
        new_text = _rewrite_text(text, rewriter)
        if new_text == text:
            return cell, False, False
        return new_text.encode("utf-8"), True, False
    if isinstance(cell, str):
        new_text = _rewrite_text(cell, rewriter)
        return new_text, new_text != cell, False
    return cell, False, False


def _rewrite_text(text: str, rewriter: PathRewriter) -> str:
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return rewriter.rewrite_string(text)
        rewritten = rewriter.rewrite_obj(data)
        if rewritten == data:
            return text
        return json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))
    return rewriter.rewrite_string(text)

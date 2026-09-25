import sqlite3
from pathlib import Path

from antigravity_mac_migrate.detect import scan_profiles
from antigravity_mac_migrate.profiles import ResolvedProfile
from antigravity_mac_migrate.sqlite_rewrite import SQLITE_MAGIC, rewrite_db
from antigravity_mac_migrate.paths import PathRewriter, replacement_pairs


def _profile(user_dir: Path) -> ResolvedProfile:
    return ResolvedProfile(
        name="ide",
        user_dirs=[user_dir],
        content_dirs=[user_dir],
    )


def test_scan_skips_empty_state_vscdb(tmp_path: Path):
    user_dir = tmp_path / "User"
    storage = user_dir / "globalStorage"
    storage.mkdir(parents=True)
    (storage / "state.vscdb").write_bytes(b"")

    result = scan_profiles([_profile(user_dir)])

    assert len(result.skipped_sqlite) == 1
    assert "state.vscdb" in result.skipped_sqlite[0]
    assert result.windows_paths == {}


def test_scan_skips_malformed_sqlite_header(tmp_path: Path):
    user_dir = tmp_path / "User"
    storage = user_dir / "globalStorage"
    storage.mkdir(parents=True)
    corrupt = storage / "state.vscdb"
    corrupt.write_bytes(SQLITE_MAGIC + b"\x00" * 64)

    result = scan_profiles([_profile(user_dir)])

    assert len(result.skipped_sqlite) == 1
    assert str(corrupt) in result.skipped_sqlite[0]


def test_scan_skips_non_sqlite_db_extension(tmp_path: Path):
    user_dir = tmp_path / "User"
    conv = user_dir / "conversations"
    conv.mkdir(parents=True)
    junk = conv / "chat.db"
    junk.write_bytes(b"not-a-database")

    result = scan_profiles([_profile(user_dir)])

    assert any(str(junk) in line for line in result.skipped_sqlite)


def test_rewrite_db_skips_malformed_without_raising(tmp_path: Path):
    db = tmp_path / "state.vscdb"
    db.write_bytes(SQLITE_MAGIC + b"\x00" * 32)
    rewriter = PathRewriter(replacement_pairs(r"C:\Users\X", "/Users/x"))

    stats = rewrite_db(db, rewriter)

    assert stats.rows_changed == 0
    assert len(stats.skipped_sqlite) == 1


def test_scan_reads_valid_sqlite(tmp_path: Path):
    user_dir = tmp_path / "User"
    storage = user_dir / "globalStorage"
    storage.mkdir(parents=True)
    db = storage / "state.vscdb"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    conn.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("demo", r"C:\Users\WINDOWS_USER\Projects\api"),
    )
    conn.commit()
    conn.close()

    result = scan_profiles([_profile(user_dir)])

    assert result.skipped_sqlite == []
    assert result.windows_paths[r"C:\Users\WINDOWS_USER\Projects\api"] == 1

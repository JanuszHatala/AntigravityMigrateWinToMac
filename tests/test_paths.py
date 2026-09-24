from pathlib import Path

from antigravity_mac_migrate.paths import (
    PathRewriter,
    extract_windows_paths,
    mac_to_file_uri,
    project_dir_name,
    replacement_pairs,
    windows_to_file_uri,
)
from antigravity_mac_migrate.workspace_ids import compute_code_workspace_id


def test_replacement_covers_uri_and_backslash():
    pairs = replacement_pairs(r"C:\Users\WINDOWS_USER\dev", "/Users/MAC_USER/dev")
    rewriter = PathRewriter(pairs)
    assert (
        rewriter.rewrite_string(r"C:\Users\WINDOWS_USER\dev\api\main.py")
        == "/Users/MAC_USER/dev/api/main.py"
    )
    assert rewriter.rewrite_string("C:/Users/WINDOWS_USER/dev/api") == "/Users/MAC_USER/dev/api"
    uri = windows_to_file_uri(r"C:\Users\WINDOWS_USER\dev")
    assert rewriter.rewrite_string(uri) == mac_to_file_uri("/Users/MAC_USER/dev")
    nested = r"C:\\Users\\WINDOWS_USER\\dev\\api"
    assert "Users/MAC_USER/dev" in rewriter.rewrite_string(nested).replace("\\", "/")


def test_drive_letter_forms_and_renamed_folder():
    pairs = replacement_pairs(r"D:\work", "/Users/MAC_USER/work")
    pairs += replacement_pairs(
        r"D:\work\acme\oldname",
        "/Users/MAC_USER/work/acme/old-name",
    )
    rewriter = PathRewriter(pairs)
    mac_repo = "/Users/MAC_USER/work/acme/portal"
    assert rewriter.rewrite_string("d:/work/acme/portal") == mac_repo
    assert rewriter.rewrite_string("D:/work/acme/portal") == mac_repo
    assert rewriter.rewrite_string("/d:/work/acme/portal") == mac_repo
    assert rewriter.rewrite_string("/D:/work/acme/portal") == mac_repo
    assert (
        rewriter.rewrite_string("d:/work/acme/oldname")
        == "/Users/MAC_USER/work/acme/old-name"
    )


def test_longest_prefix_wins():
    pairs = replacement_pairs(r"C:\Users\WINDOWS_USER", "/Users/MAC_USER")
    pairs += replacement_pairs(r"C:\Users\WINDOWS_USER\dev", "/Volumes/work/dev")
    rewriter = PathRewriter(pairs)
    assert rewriter.rewrite_string(r"C:\Users\WINDOWS_USER\dev\api") == "/Volumes/work/dev/api"
    assert rewriter.rewrite_string(r"C:\Users\WINDOWS_USER\Documents\x") == "/Users/MAC_USER/Documents/x"


def test_python_exe_becomes_mac_python():
    pairs = replacement_pairs(r"C:\Users\WINDOWS_USER", "/Users/MAC_USER")
    rewriter = PathRewriter(pairs, python="/opt/homebrew/bin/python3")
    assert (
        rewriter.rewrite_string(
            r"C:\Users\WINDOWS_USER\AppData\Local\Programs\Python\Python312\python.exe"
        )
        == "/opt/homebrew/bin/python3"
    )


def test_intellij_exe():
    rewriter = PathRewriter([], intellij="/Applications/IntelliJ IDEA.app")
    assert (
        rewriter.rewrite_string(
            r"C:\Program Files\JetBrains\IntelliJ IDEA 2024.3\bin\idea64.exe"
        )
        == "/Applications/IntelliJ IDEA.app"
    )


def test_extract_and_project_dir_name():
    blob = "folder: file:///c%3A/Users/WINDOWS_USER/dev/api"
    found = extract_windows_paths(blob)
    assert any("Users" in item and item.endswith("dev\\api") or item.endswith("dev/api") for item in found)
    assert project_dir_name(r"C:\Users\WINDOWS_USER\dev") == "C-Users-WINDOWS_USER-dev"
    assert project_dir_name("/Users/MAC_USER/dev") == "Users-MAC_USER-dev"


def test_code_workspace_id_is_lowercase_md5(tmp_path: Path):
    file = tmp_path / "Platform.CODE-workspace"
    file.write_text("{}", encoding="utf-8")
    result = compute_code_workspace_id(file)
    import hashlib

    expected = hashlib.md5(file.absolute().as_posix().lower().encode()).hexdigest()
    assert result.workspace_id == expected


def test_rewrite_workspace_identifier_id():
    pairs = replacement_pairs(r"C:\Users\WINDOWS_USER\dev", "/Users/MAC_USER/dev")
    rewriter = PathRewriter(
        pairs,
        extra_id_map={"aaaabbbbccccddddeeeeffffaaaabbbb": "0123456789abcdef0123456789abcdef"},
    )
    payload = {
        "allComposers": [
            {
                "composerId": "chat-1",
                "workspaceIdentifier": {
                    "id": "aaaabbbbccccddddeeeeffffaaaabbbb",
                    "uri": {
                        "fsPath": r"C:\Users\WINDOWS_USER\dev",
                        "scheme": "file",
                        "external": windows_to_file_uri(r"C:\Users\WINDOWS_USER\dev"),
                    },
                },
            }
        ]
    }
    out = rewriter.rewrite_obj(payload)
    ident = out["allComposers"][0]["workspaceIdentifier"]
    assert ident["id"] == "0123456789abcdef0123456789abcdef"
    assert ident["uri"]["fsPath"] == "/Users/MAC_USER/dev"

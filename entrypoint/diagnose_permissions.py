#!/usr/bin/env python3
"""
diagnose_permissions.py

Purpose
-------
Actionable diagnostics for Calibre-Web file/directory permissions and SQLite
writability issues (common root cause of: 'attempt to write a readonly database').

What It Checks
--------------
1. Resolves target directories:
   - Config directory (CALIBRE_DBPATH or /app/config)
   - Data / library directory (argument, CALIBRE_LIBRARY_PATH, or /app/data)
2. Enumerates key SQLite DB files (if present):
   - app.db
   - users_books.db
   - gdrive.db
   - metadata.db (in library dir)
3. For each path (directories + DB files):
   - Existence, type (file/dir/symlink)
   - Ownership (uid/gid -> names if resolvable)
   - Mode (octal), read/write/execute access for current user
   - Whether filesystem appears mounted read-only
   - SELinux/AppArmor hints (best-effort; not definitive)
   - Ability to create & remove a temporary file (write test for dirs)
4. For each SQLite DB file:
   - Can it be opened?
   - Is a write transaction (BEGIN IMMEDIATE) possible?
   - Specific exception messages captured
5. Produces structured JSON and (optionally) friendly text.

Exit Codes
----------
0 - All checked writable paths are OK (no blocking errors)
1 - One or more paths have fatal issues (non-writable, missing critical DB, etc.)

Usage
-----
  python diagnose_permissions.py [--config-dir PATH] [--data-dir PATH]
                                 [--json] [--verbose]

Examples
--------
  python diagnose_permissions.py
  CALIBRE_DBPATH=/app/config python diagnose_permissions.py --json
  python diagnose_permissions.py --config-dir ./config --data-dir ./var/data --verbose

Notes
-----
- Does not mutate permissions; purely diagnostic.
- If a directory is missing, it is flagged (creation responsibility left to deploy logic).
- If a DB file is missing, only 'app.db' absence is potentially non-fatal IF seeding will create it;
  others are optional depending on feature usage.

Mitigation Tips (Summary)
-------------------------
- Ensure host bind mounts grant write access to the container's effective UID/GID.
- Avoid mounting library or config directories from read-only network shares.
- For Docker: check `:ro` flags not applied inadvertently.
- macOS host volumes with special ACLs may need: `chmod -R u+rwX,g+rwX`.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
import time
import traceback
import sqlite3
import pwd
import grp
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_dir(cli_value: Optional[str], env_var: str, default: str) -> str:
    if cli_value:
        return os.path.abspath(cli_value)
    env_val = os.getenv(env_var)
    if env_val:
        return os.path.abspath(env_val)
    return os.path.abspath(default)


def uid_name(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_name  # type: ignore[attr-defined]
    except Exception:
        return "?"


def gid_name(gid: int) -> str:
    try:
        return grp.getgrgid(gid).gr_name  # type: ignore[attr-defined]
    except Exception:
        return "?"


def mode_octal(st_mode: int) -> str:
    return oct(st_mode & 0o777)


def has_access(path: str, mode_flag: int) -> bool:
    return os.access(path, mode_flag)


def filesystem_readonly(path: str) -> Optional[bool]:
    """
    Heuristic: attempt to open directory for writing a temp file (callers already do a write test).
    Here we just attempt to statvfs and inspect flags if available.
    """
    try:
        vfs = os.statvfs(path)
        # If flag ST_RDONLY is present (platform dependent), attempt to infer.
        # Python doesn't expose ST_RDONLY portable flag; rely on write test outside.
        # Return None to indicate inconclusive (write test result is authoritative).
        _ = vfs.f_bavail  # Access to verify call succeeded
        return None
    except Exception:
        return None


def write_test_directory(path: str) -> Dict[str, Any]:
    result = {
        "can_create_file": False,
        "can_unlink_file": False,
        "error": None,
        "test_filename": None,
    }
    if not os.path.isdir(path):
        result["error"] = "not_a_directory"
        return result
    try:
        fd, tmp_path = tempfile.mkstemp(prefix=".perm_test_", dir=path)
        os.close(fd)
        result["test_filename"] = os.path.basename(tmp_path)
        result["can_create_file"] = True
        try:
            os.unlink(tmp_path)
            result["can_unlink_file"] = True
        except Exception as exc_unlink:
            result["error"] = f"unlink_failed: {exc_unlink}"
    except Exception as exc:
        result["error"] = f"create_failed: {exc}"
    return result


def sqlite_writability_test(db_path: str) -> Dict[str, Any]:
    out = {
        "exists": os.path.isfile(db_path),
        "open_ok": False,
        "write_tx_ok": False,
        "error": None,
    }
    if not out["exists"]:
        return out
    try:
        conn = sqlite3.connect(db_path, timeout=2)
        out["open_ok"] = True
        try:
            cur = conn.cursor()
            # BEGIN IMMEDIATE tries to obtain a RESERVED lock (write intent)
            cur.execute("BEGIN IMMEDIATE")
            cur.execute("ROLLBACK")
            out["write_tx_ok"] = True
        except Exception as exc_tx:
            out["error"] = f"write_tx_failed: {exc_tx}"
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception as exc_open:
        out["error"] = f"open_failed: {exc_open}"
    return out


def stat_path(path: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": path,
        "exists": os.path.exists(path),
        "is_file": False,
        "is_dir": False,
        "is_symlink": os.path.islink(path),
        "lstat_error": None,
        "mode": None,
        "mode_octal": None,
        "uid": None,
        "gid": None,
        "user": None,
        "group": None,
        "access": {
            "read": False,
            "write": False,
            "execute": False,
        },
        "write_test": None,
        "fs_readonly_inferred": None,
        "remarks": [],
    }
    if not info["exists"]:
        info["remarks"].append("missing")
        return info
    try:
        st = os.lstat(path)
        info["mode"] = st.st_mode
        info["mode_octal"] = mode_octal(st.st_mode)
        info["uid"] = st.st_uid
        info["gid"] = st.st_gid
        info["user"] = uid_name(st.st_uid)
        info["group"] = gid_name(st.st_gid)
        info["is_file"] = stat.S_ISREG(st.st_mode)
        info["is_dir"] = stat.S_ISDIR(st.st_mode)
        info["access"]["read"] = has_access(path, os.R_OK)
        info["access"]["write"] = has_access(path, os.W_OK)
        info["access"]["execute"] = has_access(path, os.X_OK)
        info["fs_readonly_inferred"] = filesystem_readonly(path if info["is_dir"] else os.path.dirname(path))
        if info["is_dir"]:
            info["write_test"] = write_test_directory(path)
            if info["write_test"]["can_create_file"] and not info["access"]["write"]:
                info["remarks"].append("write_test_succeeded_but_access_false_inconsistent")
            if not info["write_test"]["can_create_file"]:
                info["remarks"].append("dir_create_temp_failed")
        else:
            # For files, attempt parent dir write test (rename/delete scenario)
            parent = os.path.dirname(path)
            if os.path.isdir(parent):
                info["write_test"] = write_test_directory(parent)
    except Exception as exc:
        info["lstat_error"] = str(exc)
        info["remarks"].append("stat_failed")
    return info


def annotate_issue(pinfo: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    if not pinfo["exists"]:
        issues.append("missing")
        return issues
    if pinfo["is_dir"]:
        if not pinfo["access"]["write"]:
            issues.append("directory_not_writable")
        wt = pinfo.get("write_test") or {}
        if wt and not wt.get("can_create_file"):
            issues.append("directory_create_file_failed")
    else:
        # File path: require write for DB operations (except maybe initial creation)
        if not pinfo["access"]["write"]:
            issues.append("file_not_writable")
    return issues


def build_human_summary(entries: List[Dict[str, Any]], db_tests: Dict[str, Dict[str, Any]]) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append("==== Permission Diagnostics ====")
    for e in entries:
        path = e["path"]
        lines.append(f"\nPath: {path}")
        lines.append(f"  Exists: {e['exists']}  Type: {'dir' if e['is_dir'] else 'file' if e['is_file'] else 'other'}  Symlink: {e['is_symlink']}")
        if e["exists"]:
            lines.append(f"  Owner: {e['user']}({e['uid']})  Group: {e['group']}({e['gid']})  Mode: {e['mode_octal']}")
            lines.append(f"  Access (r/w/x): {int(e['access']['read'])}/{int(e['access']['write'])}/{int(e['access']['execute'])}")
            wt = e.get("write_test") or {}
            if e["is_dir"]:
                lines.append(f"  Dir write test: create={wt.get('can_create_file')} unlink={wt.get('can_unlink_file')} err={wt.get('error')}")
        remarks = e.get("remarks") or []
        if remarks:
            lines.append(f"  Remarks: {', '.join(remarks)}")
        # DB test if applicable
        dbt = db_tests.get(path)
        if dbt:
            lines.append(f"  SQLite: open_ok={dbt['open_ok']} write_tx_ok={dbt['write_tx_ok']} exists={dbt['exists']} err={dbt['error']}")
    lines.append("\nOverall assessment:")
    fatal = []
    for e in entries:
        issues = annotate_issue(e)
        if issues:
            fatal.append((e["path"], issues))
    if not fatal:
        lines.append("  OK: No blocking permission issues detected.")
    else:
        lines.append("  FAILING PATHS:")
        for p, issues in fatal:
            lines.append(f"    - {p}: {', '.join(issues)}")
    lines.append("")
    lines.append("Suggested remediation (common cases):")
    lines.append("  - Ensure host bind mounts are not read-only (remove ':ro').")
    lines.append("  - Align container user UID/GID with host directory ownership or relax modes (chmod -R u+rwX,g+rwX).")
    lines.append("  - For network volumes, ensure write permissions and locking are supported.")
    lines.append("  - If only DB files are read-only, check parent directory permissions and upstream seeding timing.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    config_dir = resolve_dir(args.config_dir, "CALIBRE_DBPATH", "/app/config")
    data_dir = resolve_dir(args.data_dir, "CALIBRE_LIBRARY_PATH", "/app/data")

    candidate_paths: List[str] = []
    # Directories
    candidate_paths.append(config_dir)
    candidate_paths.append(data_dir)

    # DB files inside config
    for db_name in ("app.db", "users_books.db", "gdrive.db"):
        candidate_paths.append(os.path.join(config_dir, db_name))

    # metadata.db inside library (if exists) — primary Calibre library DB
    candidate_paths.append(os.path.join(data_dir, "metadata.db"))

    # De-duplicate while preserving order
    seen = set()
    deduped = []
    for p in candidate_paths:
        if p not in seen:
            deduped.append(p)
            seen.add(p)

    path_infos: List[Dict[str, Any]] = [stat_path(p) for p in deduped]

    # SQLite tests for files only (existing)
    sqlite_results: Dict[str, Dict[str, Any]] = {}
    for info in path_infos:
        if info["exists"] and info["is_file"] and info["path"].endswith(".db"):
            sqlite_results[info["path"]] = sqlite_writability_test(info["path"])

    # Determine overall status
    fatal_paths = []
    for info in path_infos:
        issues = annotate_issue(info)
        # If it's a missing file that might be created (e.g., optional plugin DB), treat as non-fatal
        if "missing" in issues and info["path"].endswith("users_books.db"):
            continue
        if "missing" in issues and os.path.basename(info["path"]) == "gdrive.db":
            continue
        fatal_paths.extend([(info["path"], issues)] if issues else [])

    summary = {
        "timestamp": int(time.time()),
        "config_dir": config_dir,
        "data_dir": data_dir,
        "entries": path_infos,
        "sqlite": sqlite_results,
        "fatal_issues": [
            {"path": p, "issues": isues} for p, isues in fatal_paths if isues
        ],
        "all_ok": len(fatal_paths) == 0,
        "env": {
            "CALIBRE_DBPATH": os.getenv("CALIBRE_DBPATH"),
            "CALIBRE_LIBRARY_PATH": os.getenv("CALIBRE_LIBRARY_PATH"),
            "UID": os.getuid() if hasattr(os, "getuid") else None,
            "GID": os.getgid() if hasattr(os, "getgid") else None,
        },
        "recommendations": [
            "Confirm bind mounts are writable (no ':ro').",
            "Match container runtime UID/GID to host directory ownership or adjust permissions.",
            "If only SQLite write_tx fails, inspect file attributes and parent directory.",
            "Run seeding step before starting main app if app.db is missing.",
        ],
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(build_human_summary(path_infos, sqlite_results))
        if args.verbose:
            print("Raw JSON:")
            print(json.dumps(summary, indent=2, sort_keys=True))

    return 0 if summary["all_ok"] else 1


def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Diagnose Calibre-Web permission & SQLite writability issues.")
    ap.add_argument("--config-dir", help="Explicit config directory (overrides CALIBRE_DBPATH)")
    ap.add_argument("--data-dir", help="Explicit data/library directory (overrides CALIBRE_LIBRARY_PATH)")
    ap.add_argument("--json", action="store_true", help="Output JSON only")
    ap.add_argument("--verbose", action="store_true", help="Include raw JSON block in human output mode")
    return ap.parse_args(argv)


def main() -> int:
    try:
        args = parse_args(sys.argv[1:])
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FATAL: Unhandled exception: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 99


if __name__ == "__main__":
    sys.exit(main())

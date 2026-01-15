#!/usr/bin/env bash
set -euo pipefail

# Compiles our translation overrides without modifying the calibre-web submodule.
#
# Source (override .po files):
#   translations/calibre-web/<lang>/LC_MESSAGES/messages.po
#
# Destination (compiled .mo files stored alongside overrides):
#   translations/calibre-web/<lang>/LC_MESSAGES/messages.mo

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT="$repo_root"

src_root="$repo_root/translations/calibre-web"
dst_root="$repo_root/translations/calibre-web"

python_bin="${PYTHON_BIN:-python3}"

if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "ERROR: PYTHON_BIN '$python_bin' not found" >&2
  exit 2
fi

"$python_bin" - <<'PY'
from __future__ import annotations

from pathlib import Path
import os
import sys

def compile_one(src_po: Path, dst_mo: Path) -> None:
    try:
        from babel.messages.mofile import write_mo
        from babel.messages.pofile import read_po
    except Exception as exc:
        raise SystemExit(f"Missing dependency: Babel is required (pip install babel). Details: {exc}")

    dst_mo.parent.mkdir(parents=True, exist_ok=True)
    with src_po.open("r", encoding="utf-8") as fp:
        catalog = read_po(fp, locale=src_po.parents[1].name, domain="messages")
    with dst_mo.open("wb") as fp:
        write_mo(fp, catalog, use_fuzzy=False)

repo_root = Path(os.environ["REPO_ROOT"]).resolve()
src_root = repo_root / "translations" / "calibre-web"
dst_root = repo_root / "translations" / "calibre-web"

if not src_root.exists():
    raise SystemExit(f"No override translations found at {src_root}")

compiled = 0
for src_po in src_root.glob("*/LC_MESSAGES/messages.po"):
    lang = src_po.parents[1].name  # <lang>/LC_MESSAGES/messages.po
    dst_mo = dst_root / lang / "LC_MESSAGES" / "messages.mo"
    compile_one(src_po, dst_mo)
    print(f"compiled: {dst_mo.relative_to(repo_root)}")
    compiled += 1

if compiled == 0:
    print("No translations compiled (no messages.po files found)")
PY

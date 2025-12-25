#!/usr/bin/env python3
"""Seeding orchestrator.

Runs all individual seed_xxx routines (settings + library) in a controlled,
idempotent order producing concise one‑line success logs per seed.

Exit Codes:
  0 = all ok / or already present
  3 = one or more seed steps failed (non-fatal for manual invocation)
"""
from __future__ import annotations

from pathlib import Path
import sys


def _ensure_lv_locale_assets() -> bool:
    """Ensure LV locale JS files exist in Calibre-Web's /static tree.

    Upstream templates load locale assets from `/static/...` (Calibre-Web static).
    Some Calibre-Web versions do not ship LV locale files; without them,
    bootstrap-select and bootstrap-datepicker show English UI strings.

    We keep our LV locale JS under `app/static/...` and copy into the expected
    Calibre-Web static locations if (and only if) the target files are missing.
    """

    try:
        repo_root = Path(__file__).resolve().parents[1]
        app_static_root = repo_root / "app" / "static" / "js" / "libs"
        cw_static_root = repo_root / "calibre-web" / "cps" / "static" / "js" / "libs"

        src_datepicker_lv = app_static_root / "bootstrap-datepicker" / "locales" / "bootstrap-datepicker.lv.min.js"
        src_select_lv = app_static_root / "bootstrap-select" / "defaults-lv.min.js"

        dst_datepicker_dir = cw_static_root / "bootstrap-datepicker" / "locales"
        dst_select_dir = cw_static_root / "bootstrap-select"

        pairs = [
            (src_datepicker_lv, dst_datepicker_dir / "bootstrap-datepicker.lv.min.js"),
            # Be defensive: some locale codes may include region.
            (src_datepicker_lv, dst_datepicker_dir / "bootstrap-datepicker.lv_LV.min.js"),
            (src_select_lv, dst_select_dir / "defaults-lv.min.js"),
            (src_select_lv, dst_select_dir / "defaults-lv_LV.min.js"),
        ]

        ok = True
        for src, dst in pairs:
            if dst.exists():
                continue
            if not src.exists():
                print(f"[SEED] assets WARNING missing source {src}", file=sys.stderr)
                ok = False
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            print(f"[SEED] assets ok installed {dst.relative_to(repo_root)}")
        return ok
    except Exception as exc:  # pragma: no cover
        print(f"[SEED] assets ERROR {exc}", file=sys.stderr)
        return False


def _run_library() -> bool:
    try:
        from entrypoint import seed_library  # type: ignore
        summary = seed_library.ensure_mz_price_column()
        if summary.get("error"):
            print(f"[SEED] library ERROR {summary['error']}", file=sys.stderr)
            return False
        print(
            f"[SEED] library ok mz_price_id={summary.get('id')} created={'yes' if summary.get('created') else 'no'} values={summary.get('values')}"
        )
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[SEED] library ERROR {exc}", file=sys.stderr)
        return False


def main() -> int:  # pragma: no cover (thin wrapper)
    # Only library seeding retained (price column); Calibre-Web core handles its own settings.
    ok_assets = _ensure_lv_locale_assets()
    ok_library = _run_library()
    return 0 if (ok_library and ok_assets) else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

#!/usr/bin/env python3
"""Generate a password-reset auth token URL for the admin user.

This is a QA helper meant to be run *inside* the docker container.

Env (optional):
  QA_BASE_URL (default: http://localhost:8083)
  QA_ADMIN_EMAIL (default: admin@example.org)

Output JSON: {status,email,url,token}
Exit codes: 0 ok, 2 import fail, 3 token fail

Note: Uses the real Flask app so token encoding has access to SECRET_KEY.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback


def main() -> int:
    try:
        if "/app" not in sys.path:
            sys.path.insert(0, "/app")
        if "/app/calibre-web" not in sys.path:
            sys.path.insert(0, "/app/calibre-web")

        # The entrypoint wrapper is intentionally chatty (seed/mainwrap prints).
        # Suppress that noise so this helper can emit clean JSON.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from entrypoint.entrypoint_mainwrap import application  # type: ignore
            from app.services import password_reset_service  # type: ignore
    except Exception:
        traceback.print_exc()
        print(json.dumps({"status": "error", "error": "import_failed"}))
        return 2

    base_url = (os.environ.get("QA_BASE_URL") or "http://localhost:8083").rstrip("/")
    email = (os.environ.get("QA_ADMIN_EMAIL") or "admin@example.org").strip()

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with application.app_context():
                token = password_reset_service.issue_reset_token(email=email)
        url = f"{base_url}/login?auth={token}"
        print(json.dumps({"status": "ok", "email": email, "url": url, "token": token}))
        return 0
    except Exception as exc:
        traceback.print_exc()
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 3


if __name__ == "__main__":
    code = main()
    os._exit(code)

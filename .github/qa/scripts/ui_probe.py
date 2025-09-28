#!/usr/bin/env python3
"""Probe UI for visible book IDs and optional admin nav link.

Env: BASE_URL, EMAIL, PASSWORD, ADMIN_USER, ADMIN_PASS
Output: {status,non_admin_books:[...],admin_nav:?bool}
Exit: 0 ok, 1 error
"""
from __future__ import annotations

import os, sys, re, json, urllib.request, urllib.parse, http.cookiejar

BASE = os.environ.get("BASE_URL", "http://localhost:8083").rstrip("/")
EMAIL = os.environ.get("EMAIL", "test.user@example.org")
PASSWORD = os.environ.get("PASSWORD", "")
ADMIN_USER = os.environ.get("ADMIN_USER")
ADMIN_PASS = os.environ.get("ADMIN_PASS")


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _login(op, username: str, password: str):
    if not username:
        return
    try:
        data = urllib.parse.urlencode({"username": username, "password": password}).encode()
        op.open(f"{BASE}/login", data, timeout=10)
    except Exception:
        pass


def _ids(html: str):
    ids = {int(m) for m in re.findall(r"/book/(\d+)", html)}
    ids.update({int(m) for m in re.findall(r"book_id=(\d+)", html)})
    return sorted(ids)


def main():
    out = {"status": "error"}
    try:
        op = _opener(); _login(op, EMAIL, PASSWORD)
        idx_html = op.open(f"{BASE}/", timeout=10).read().decode(errors="ignore")
        out["non_admin_books"] = _ids(idx_html)
        if ADMIN_USER and ADMIN_PASS:
            op2 = _opener(); _login(op2, ADMIN_USER, ADMIN_PASS)
            a_html = op2.open(f"{BASE}/", timeout=10).read().decode(errors="ignore")
            out["admin_nav"] = ("id=\"top_users_books\"" in a_html) or ("ebooks.lv" in a_html)
        out["status"] = "ok"
    except Exception as exc:
        out["error"] = str(exc)
    print(json.dumps(out))
    return 0 if out.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

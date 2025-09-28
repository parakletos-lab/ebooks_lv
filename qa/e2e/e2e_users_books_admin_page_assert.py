"""Executable assertion script for Users ↔ Books admin page.

Run inside container or host with requests installed.
Checks:
  - Redirect of legacy path
  - Users endpoint returns >=1 non-admin user
  - Books endpoint returns >=1 book
  - UI HTML contains management heading
"""
from __future__ import annotations
import os, sys, json, re
import urllib.request, urllib.error, http.cookiejar

BASE = os.environ.get("TEST_BASE", "http://localhost:8083")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

def _opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", "qa-e2e-script/1.0")] 
    return opener

def login(op):
    # Fetch login page for csrf token (Calibre-Web may not require explicit CSRF for login depending on config)
    login_url = f"{BASE}/login"
    op.open(login_url)
    data = urllib.parse.urlencode({"username": ADMIN_USER, "password": ADMIN_PASS, "remember_me": "on"}).encode()
    resp = op.open(login_url, data=data)
    assert resp.getcode() in (200, 302), f"login failed HTTP {resp.getcode()}"

def get_json(op, path):
    with op.open(f"{BASE}{path}") as r:
        assert r.getcode() == 200, f"GET {path} -> {r.getcode()}"
        return json.loads(r.read().decode())

def main():
    op = _opener()
    login(op)
    # Legacy redirect check
    legacy = op.open(f"{BASE}/users_books/admin")
    assert legacy.geturl().endswith("/admin/users_books"), "Legacy path did not redirect to canonical UI"

    html = op.open(f"{BASE}/admin/users_books").read().decode("utf-8", "replace")
    assert "Allow‑List Management" in html or "Allow-List Management" in html, "UI heading not found"

    users_json = get_json(op, "/admin/users_books/all_users")
    users = users_json.get("users", [])
    assert len(users) >= 1, "Expected at least one non-admin user"
    for u in users:
        assert not re.search(r"admin", u.get("email",""), re.I), "Admin leaked into non-admin list"

    books_json = get_json(op, "/admin/users_books/all_books")
    books = books_json.get("books", [])
    assert len(books) >= 1, "Expected at least one book"

    print("PASS: users_books admin page basic assertions succeeded.")

if __name__ == "__main__":
    main()
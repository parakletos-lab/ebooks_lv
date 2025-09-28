#!/usr/bin/env python3
"""Verify runtime core users_books patch is active.

Checks:
 1. Imports cps.db and inspects source text for marker comment.
 2. Creates/ensures non-admin test user (qa_filter) exists.
 3. Ensures a single mapping to one book id is present (lowest existing book id).
 4. Executes a Books listing query via calibre_db.session and prints returned book ids.
 5. Exits non-zero if invariant violated (e.g., multiple book ids returned when only one allowed).

Hard exits with os._exit to align with QA script policy.
"""
from __future__ import annotations
import sys, os, traceback, inspect

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
for p in (PROJECT_ROOT, '/app','/app/calibre-web','/app/plugins'):
    if p not in sys.path:
        sys.path.insert(0,p)

MARK = '# users_books patch begin'

rc = 0
try:
    from entrypoint.patch_calibre_init import get_patched_app
    # Ensure runtime core patcher also runs (in-memory replacement) before accessing calibre_db
    try:
        import entrypoint.apply_core_users_books_patch as _core_patch
        _core_patch.main()
    except Exception:
        pass
    get_patched_app()
    from cps import ub, db as cw_db  # type: ignore
    from cps.db import Books  # type: ignore
    from cps import calibre_db  # type: ignore
    import users_books
    from users_books import services
    import users_books.config as ub_cfg
    import sqlalchemy
    import types
except Exception:
    traceback.print_exc()
    os._exit(2)

try:
    # 1. Source inspection
    import cps.db as db_mod  # type: ignore
    try:
        src = inspect.getsource(db_mod)
        has_marker = MARK in src
    except OSError:
        has_marker = False
    # Shadow patched version may reside at /app/calibre-web-patched; check that file too if marker missing.
    if not has_marker:
        shadow_path = '/app/calibre-web-patched/cps/db.py'
        if os.path.isfile(shadow_path):
            try:
                shadow_src = open(shadow_path,'r',encoding='utf-8').read()
                if MARK in shadow_src:
                    has_marker = True
            except Exception:
                pass
    print(f"[VERIFY] marker_present={has_marker}")
    if not has_marker:
        print('[VERIFY] ERROR: core patch marker not found in cps.db (original or shadow).')
        rc = 1

    # 2. Ensure/non-admin user
    name = 'qa_filter'
    user = ub.session.query(ub.User).filter(ub.User.name==name).first()
    if not user:
        user = ub.User()
        user.name = name
        user.email = 'qa_filter@example.test'
        user.role = 0
        ub.session.add(user)
        ub.session.commit()
        print(f"[VERIFY] Created user id={user.id}")

    # 3. Determine a single existing book id
    # Need application + request context to access calibre_db.session
    from flask import Flask
    # Use existing app from patch init
    app_obj = get_patched_app()
    from flask import current_app
    # Push contexts
    ctx = app_obj.app_context(); ctx.push()
    req = app_obj.test_request_context('/verify'); req.push()
    # Simulate login session for qa_filter user so patched common_filters picks up user id
    try:
        from flask import session
        session['user_id'] = user.id
        session['is_admin'] = False
    except Exception:
        print('[VERIFY] WARNING: failed to set session user_id; filtering may not engage.')
    first_book = calibre_db.session.query(Books).order_by(Books.id.asc()).first()
    if not first_book:
        print('[VERIFY] ERROR: No books present to test filtering.')
        os._exit(3)
    allowed_id = first_book.id

    # Reset mappings
    # Direct plugin DB manipulation through services
    # Remove any existing and then add only allowed_id
    # Simpler approach: upsert
    services.upsert_user_books(user.id, [allowed_id])
    print(f"[VERIFY] Set allow-list to single id={allowed_id}")

    # 4. Execute listing query (simulate typical listing using common_filters indirectly)
    # Building a simple query should invoke common_filters somewhere in upstream call stacks.
    # As a direct minimal probe we apply our own base filter call if available.
    # Fallback: perform raw query and rely on patched common_filters condition not being auto-called
    # -> so we manually call it to emulate typical usage.
    single_ids = []
    try:
        base_filter = calibre_db.common_filters()
        q = calibre_db.session.query(Books.id).filter(base_filter)
        single_ids = [r[0] for r in q.all()]
    except Exception as exc:
        print(f"[VERIFY] WARNING: failed applying common_filters directly ({exc}); raw query fallback.")
        single_ids = [r.id for r in calibre_db.session.query(Books.id).all()]
    finally:
        req.pop(); ctx.pop()
    print(f"[VERIFY] returned_book_ids={single_ids}")

    if allowed_id not in single_ids:
        print('[VERIFY] ERROR: allowed id missing from results.')
        rc = 4
    # Should return only that id (strict mode). If more than one, failure.
    if len([bid for bid in single_ids if isinstance(bid, int)]) > 1:
        print('[VERIFY] ERROR: multiple book ids returned; filtering not effective.')
        rc = 5
except Exception:
    traceback.print_exc()
    rc = 6

try:
    sys.stdout.flush(); sys.stderr.flush()
except Exception:
    pass
os._exit(rc)

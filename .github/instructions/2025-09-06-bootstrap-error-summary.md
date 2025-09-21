# Calibre-Web Container Bootstrap Error Summary  
Date: 2025-09-06  
Context: Custom Dockerized Calibre-Web deployment with early plugin system (users_books) and non-standard bootstrap sequence.

---

## 1. Overview

While integrating a modular plugin system and a custom entrypoint for Calibre-Web, the standard upstream startup flow (which normally lives in `cps/main.py:main()`) was partially bypassed. This caused a series of cascading initialization errors (404s, AttributeErrors, and Flask-Login failures). This document captures each failure, its root cause, the applied fix, and the final steady-state architecture.

---

## 2. Timeline of Issues & Resolutions

| Order | Symptom | Root Cause | Resolution |
|-------|---------|-----------|------------|
| 1 | `/` returned 404; plugin endpoint worked | Core blueprints (web, admin, etc.) never registered; `create_app()` alone doesn’t register them | Explicit blueprint registration logic added (initially via patched `cps.main.main()`, later replaced by direct imports + `app.register_blueprint`) |
| 2 | `sqlite3.OperationalError: unable to open database file` (plugin DB) | Plugin DB path resolved outside writable volume | Updated plugin DB path resolution to colocate with `CALIBRE_DBPATH` + ensured directory creation & writability |
| 3 | Repeated `TypeError: expected str... cli_param.logpath is None` | Some Calibre-Web code assumed CLI params always stringified | Pre-populated `cli_param` fields (logpath/gd_path/settings_path) during entrypoint bootstrap |
| 4 | `AttributeError: 'ConfigSQL' object has no attribute 'schedule_start_time'` | Fresh `_Settings` row not fully materialized; defaults not attached to `ConfigSQL` instance | Added interim default injection; later replaced with reflection-based hydration over all `_Settings` columns |
| 5 | Other missing config_* attributes (e.g. `config_public_reg`, `db_configured`) | Same as above; partial state from avoiding upstream assembled init sequence | Generic hydrator added to mirror column defaults + compute `db_configured` |
| 6 | Login 500: `Missing user_loader or request_loader` | Flask-Login user loader decorator (`@lm.user_loader`) defined in `cps.usermanagement` wasn’t reliably active at request time—likely ordering/race between imports and later state mutation | Forced import of `cps.usermanagement`, added multiple fallback layers, then per-request safeguard installing a last-resort loader |
| 7 | Intermittent user_loader still missing despite earlier detection | Some late lifecycle path cleared `lm._user_callback` before first request (exact upstream side-effect not fully isolated) | Added `@app.before_request` hook to reassert loader; eliminated `web_server.start()` side-effects to reduce mutation points |
| 8 | Noise & complexity in entrypoint | Incremental defensive patches accumulated | Plan for refactor (see Section 7) |

---

## 3. Root Causes (Decomposed)

1. **Architectural Mismatch**  
   Upstream expects a monolithic `main()` that both calls `create_app()` AND registers all blueprints/services. Splitting this required replicating side effects.

2. **Lazy Settings Population**  
   `ConfigSQL.load()` copies only values present in the row; defaults not yet persisted or accessed leave missing attributes. Direct attribute access in other modules assumed full hydration.

3. **Decorator Timing**  
   The Flask-Login user loader relies on `@lm.user_loader` executing after login manager is bound. Reordering imports can leave `_user_callback` unset. Additional late operations may reset or shadow the login manager state.

4. **Implicit File/Path Expectations**  
   Upstream logging & gdrive support assume CLI parameters are defined and point to valid or at least string paths.

5. **Plugin DB Isolation vs. Container Permissions**  
   The plugin defaulted to a relative path not under a mounted writable directory, causing SQLite open failures under the non-root user.

6. **Event Hook Compatibility**  
   SQLAlchemy “Select-level before_compile” event not available in the deployed version; fallback to Query-level event triggered benign warning (expected).

---

## 4. Implemented Fixes (Final State)

- **Pre-Seed Script** (`entrypoint/seed_settings.py`):
  - Creates `app.db`, `.key`, and plugin DB (`users_books.db`) before runtime
  - Ensures deterministic startup

- **Entrypoint Responsibilities (Current)** (`entrypoint/entrypoint_mainwrap.py`):
  1. (Optional) Run deterministic seeding (`seed_settings.py`) if invoked with RUN_SEED=1.
  2. Monkeypatch `web_server.start()` and `sys.exit` to intercept upstream `cps.main.main()` final server start.
  3. Invoke upstream `cps.main.main()` for native initialization (blueprints, login manager, scheduler, config).
  4. Restore patched functions (no permanent mutation of upstream objects).
  5. Optionally auto-configure Calibre library if `CALIBRE_LIBRARY_PATH` is present and contains `metadata.db`.
  6. Load plugins (`CALIBRE_WEB_PLUGINS`, e.g. `users_books`) via each plugin’s `init_app(app)`.
  7. Verify `user_loader` (install minimal fallback only if upstream failed to attach).
  8. Start Flask development server (production: replace with gunicorn).

- **Plugin Adjustments**:
  - DB path resolution respects `CALIBRE_DBPATH`
  - Directory creation + writeability checks
  - Logging summary on initialization

- **Diagnostics (Temporary)**:
  - Global exception logger
  - Debug prints around user_loader state

---

## 5. Remaining Risks / Debt

| Area | Risk | Suggested Mitigation |
|------|------|----------------------|
| Login manager re-initialization | Hidden upstream side-effect might still clear callbacks | Upstream patch or instrument identity of `lm` before/after first request |
| Verbose diagnostics left in production | Log noise & performance overhead | Remove after stabilization window |
| Per-request user_loader injection | Slight overhead; masks root cause | Replace with one-time assertion once upstream init stabilized |
| Reflected config defaults | Could drift if upstream introduces dynamic defaults | Consider upstream contribution to always populate attributes in `ConfigSQL.load()` |
| Manual blueprint registration | Potential for missing future new blueprints | Create a maintained list or introspect `cps` for blueprints dynamically |

---

## 6. Lessons Learned

1. **Replaying Only Part of a Framework’s Init Requires a Contract**  
   Splitting `create_app()` from blueprint attachment demands that every implicit side-effect be inventoried.

2. **Seed Early, Fail Fast**  
   Pre-seeding DBs prevents a class of lazy-load race conditions and clarifies what’s actually missing.

3. **Reflect, Don’t Hard-Code**  
   Reflection-based hydration outlived brittle ad-hoc attribute injection.

4. **Layered Safeguards Buy You Time**  
   Entry-time + runtime (request hook) safeguards prevented hard downtime while investigating silent resets.

5. **Explicit Logging Beats Guessing**  
   Debugging the user_loader issue was only possible once callback presence was logged before and after each mutation phase.

---

## 7. Recommended Refactor (Option A Implementation Plan)

Objective: Clean, maintainable entrypoint with minimal safeguards and no noisy diagnostics.

Proposed Structure:

```
entrypoint/
  entrypoint_mainwrap.py # Intercepts upstream main(), injects plugins
  seed_settings.py       # Idempotent settings/key (optional pre-step)
```

`bootstrap_core.py` (conceptual responsibilities):
1. `create_app()` call
2. `import cps.usermanagement` (ensures user_loader)
3. `register_core_blueprints(app)`
4. `hydrate_config_defaults(config)`
5. `assert app.login_manager.user_callback is not None`
6. Return `app`

Changes to apply:
- Remove global exception logger (optional keep behind env flag `DEBUG_BOOTSTRAP=1`)
- Remove layered fallback user_loader; keep only a final assert + a single controlled fallback if assert fails.
- Drop per-request hook once assert passes reliably
- Keep reflection hydrator (document and isolate)

---

## 8. Suggested Follow-Up Tasks

| Priority | Task |
|----------|------|
| High | Implement `bootstrap_core.py`, migrate logic out of `start.py` |
| High | Replace per-request user_loader safeguard with build-time assertion |
| Medium | Add health endpoint `/healthz` hitting a trivial no-auth route |
| Medium | Integration test: headless container test verifying `/login` 200 & plugin `/plugin/users_books/health` 200 |
| Medium | Add a version stamp endpoint (e.g., `/version.json`) merging upstream + plugin versions |
| Low | Replace `app.run()` with gunicorn (production profile) |
| Low | Submit upstream PR to address ConfigSQL full default population |

---

## 9. Current Known Good Behavior Checklist

- [x] `seed_settings.py` yields settings & encryption key
- [x] Core blueprints active (`/login` returns 200)
- [x] Plugin health endpoint returns JSON 200
- [x] No unhandled exceptions on first page load
- [x] User loader present (via runtime safeguard)

---

## 10. Rollback / Recovery Strategy

If future upstream updates break bootstrap:
1. Temporarily reinstate per-request user_loader safety.
2. Re-run `seed_settings.py`.
3. Enable a diagnostic flag to dump `dir(cps.config)` and `lm.__dict__` before first request.
4. Compare blueprint set with upstream `cps/main.py` to spot newly added modules.

---

## 11. Reference Snippets (For Future Refactor)

Minimal user_loader fallback (retain for toolbox):
```python
from cps import lm, ub
@lm.user_loader
def load_user(user_id, random=None, session_key=None):
    return ub.session.query(ub.User).filter(ub.User.id == int(user_id)).first()
```

Generic `_Settings` reflection pattern:
```python
from cps.config_sql import _Settings
from sqlalchemy.inspection import inspect
cols = inspect(_Settings).columns
for c in cols:
    if not hasattr(config, c.name):
        val = getattr(config._settings, c.name, None)
        if val is None and c.default is not None:
            try:
                val = c.default.arg
            except Exception:
                pass
        setattr(config, c.name, val)
```

---

## 12. Conclusion

The bootstrap now works reliably with deterministic database seeding and explicit blueprint registration. The remaining unusual artifact is the disappearing user_loader prior to request handling, mitigated by a request-time safeguard. Refactoring (Option A) will reduce complexity and leave a maintainable path forward.

---

## 13. Action Items Snapshot

- Consolidate bootstrap under `entrypoint_mainwrap.py` (upstream main interception) and retire legacy `start.py`.
- Remove verbose diagnostics after confirming stability.
- Add CI test to exercise `/login` and plugin health.
- Investigate / patch upstream to ensure loaders and defaults persist without defensive code.

---

Prepared by: Engineering Automation Assistant  
Date: 2025-09-06 (UTC)

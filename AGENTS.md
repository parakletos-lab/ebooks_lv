
## users_books Plugin Rules (Simplified)

### 1. Purpose & Integration
- Function: per-user allow-list (positive visibility) for Calibre-Web Books.
- Integrate by calling `users_books.init_app(app)` once early; this: initializes logging, ensures DB schema, registers blueprint at `/plugin/users_books`, installs filter hook.
- Extensibility hooks: add new service functions or route modules; keep YAML updated.

### 2. Configuration (Env Variables)

| Env Var | Accessor | Default | Description |
|---------|----------|---------|-------------|
| `USERS_BOOKS_DB_PATH` | `get_db_path()` | `users_books.db` | SQLite file path (relative resolved under `CALIBRE_DBPATH` if set) |
| `CALIBRE_DBPATH` | (external) | - | Base config dir; used to colocate plugin DB |
| `USERS_BOOKS_MAX_IDS_IN_CLAUSE` | `max_ids_in_clause()` | `500` | Max IDs allowed in an `IN (...)` before failing open |
| `USERS_BOOKS_ENFORCE_EMPTY` | `enforce_empty_behaviour()` | `true` | If true: empty allow-list => zero rows; else skip filter |
| `USERS_BOOKS_ENABLE_METRICS` | `metrics_enabled()` | `false` | Enable metrics endpoint |
| `USERS_BOOKS_WEBHOOK_API_KEY` | `webhook_api_key()` | (unset) | API key required for purchase webhook; absence disables route |
| `USERS_BOOKS_SESSION_EMAIL_KEY` | `session_email_key()` | `email` | Session key name storing current user email |
| `USERS_BOOKS_LOG_LEVEL` | `log_level_name()` | `INFO` | Logging verbosity |

Boolean parsing: case-insensitive membership in {`1`,`true`,`yes`,`on`}.

---

### 3. Data Model

Table: `users_books`
- Columns: `id (PK autoincrement)`, `user_id (int, indexed)`, `book_id (int, indexed)`
- Constraints:
	- `UNIQUE(user_id, book_id)` name: `uq_users_books_user_book`
	- Composite index `ix_users_books_user_book (user_id, book_id)`
- No foreign keys (loose coupling with Calibre-Web core).

Entity semantics: each row grants a user visibility to a single book (positive allow-list only).

---

### 4. Service Layer Contracts

General rules:
- Use `plugin_session()` context from `db.py` for persistence.
- Return primitive Python types (list[int], dict, bool) for JSON friendliness.
- After any mutation, call cache invalidation (`invalidate_user_cache(user_id)` or `invalidate_all_caches`).
- Defensive existence checks prevent IntegrityError on duplicates.

Expected operations (illustrative; exact function names to be kept stable for agents):
- `add_user_book(user_id: int, book_id: int) -> bool` (True if created, False if existed)
- `remove_user_book(user_id: int, book_id: int) -> bool` (True if removed)
- `list_user_book_ids(user_id: int) -> list[int]` (ordered or arbitrary; treat as set semantics)
- `bulk_add(user_id: int, book_ids: list[int]) -> dict` (e.g., counts: added, existing)
- `bulk_remove(user_id: int, book_ids: list[int]) -> dict`
- `replace_user_books(user_id: int, book_ids: list[int]) -> dict` (synchronize exact membership)
- `count_mappings(user_id: Optional[int]=None) -> int | dict` (aggregate stats for metrics)

Mutation invariants:
- Unique (user_id, book_id) maintained always.
- Only commit inside `plugin_session()` context (atomic per call).

---

### 5. Caching

Scope: request-scoped (Flask `g`).
- Key namespace: `_users_books_allowed_ids` -> dict[user_id -> list[int]]
- Bypass (no-op) outside request context.
- Functions:
	- `get_cached_allowed_ids(user_id)` -> list[int] | None
	- `set_cached_allowed_ids(user_id, ids)` -> None
	- `get_or_load_allowed_ids(user_id, loader)` -> list[int]
	- `invalidate_user_cache(user_id)` -> None
	- `invalidate_all_caches()` -> None

Usage pattern: filter hook uses `get_or_load_allowed_ids` with a loader that queries `UserFilter` once per request.

---

### 6. Filter Hook Summary
- Event: SQLAlchemy `before_compile(Select)`.
- Predicate injected: `Books.id IN (<allowed_ids>)`.
- Skip conditions: no request context, unauthenticated, admin, statement lacks Books, empty+lenient mode, too many IDs (> `max_ids_in_clause()`).
- Empty handling: strict -> false predicate; lenient -> pass through.
- Large lists: current strategy uses IN clause + request cache (future: temp table).

### 7. Permissions & Identity
- User id from session key `user_id` (int cast).
- Admin determination chain: `current_user.role_admin()` -> role bitmask -> session `is_admin`.
- `ensure_admin()` raises `PermissionError` if not admin.
- Email normalization: trim+lower; configurable key via `USERS_BOOKS_SESSION_EMAIL_KEY`.
- User resolution tolerant of multiple model names.

### 8. Webhook & Metrics
- Webhook enabled when `USERS_BOOKS_WEBHOOK_API_KEY` set; action: email -> user_id -> allow-list (idempotent).
- Metrics enabled when `USERS_BOOKS_ENABLE_METRICS` true; returns metadata, runtime config, mapping counts.

### 9. Logging & Error Handling
- Logger singleton `users_books`; level dynamic via env + `refresh_level()`.
- Use `@log_exceptions` for service/API boundaries; never expose raw SQLAlchemy errors.
- Duplicate insert attempts treat as noop success (idempotent semantics).
- Filter hook failures: log ERROR and fail open (never block results unexpectedly).
- Runtime DB path permission failure: raise RuntimeError during init.

### 10. Operations
- Always mutate via service functions inside `plugin_session()` (atomic commit).
- Invalidate per-request cache after ANY mutation before reading again.
- For tests: `db.reset_for_tests(drop=True)` then `init_engine_once()`.
- Adjust log level: set env then call `logging_setup.refresh_level()`.
- Do not add extra logging handlers; reuse existing.

### 11. Machine YAML

Singleton logger name: `users_books`.
- Format: `[users_books] %(asctime)s %(levelname)s %(name)s %(message)s`
- Dynamic adjustments via `refresh_level()` reading `USERS_BOOKS_LOG_LEVEL`.
- Temporary verbosity: `temp_level(logging.DEBUG)` context manager.
- Decorator: `@log_exceptions(message=..., reraise=True)` for wrapping service/API functions.

Agent rule: never add additional handlers unless necessary; reuse existing logger.

---

### 11. Permissions & Identity (`utils.py`)

- Current user id: session key `user_id` (cast to int) via `get_current_user_id()`.
- Admin detection precedence:
	1. `cps.ub.current_user.role_admin()` if available & authenticated.
	2. Bitmask check against `constants.ROLE_ADMIN` if direct.
	3. Session flag `is_admin` fallback.
- Enforce admin: call `ensure_admin()` (raises `PermissionError`).
- Email normalization: lowercase + trim; configurable session key.
- Dynamic user resolution by normalized email; tolerant to model name variations (`User`, `Users`, `CWUser`).

---

### 12. Agent Enforcement

```yaml
plugin: users_books
version: 0.2.0
description: Per-user allow-list filtering for Calibre-Web with webhook-based purchase integration.
runtime:
	init_call: users_books.init_app(app)
	blueprint_mount: /plugin/users_books
	logger: users_books
config:
	db_path: ${USERS_BOOKS_DB_PATH:-users_books.db}
	max_ids_in_clause: ${USERS_BOOKS_MAX_IDS_IN_CLAUSE:-500}
	enforce_empty: ${USERS_BOOKS_ENFORCE_EMPTY:-true}
	metrics_enabled: ${USERS_BOOKS_ENABLE_METRICS:-false}
	webhook_enabled: ${USERS_BOOKS_WEBHOOK_API_KEY ? true : false}
	session_email_key: ${USERS_BOOKS_SESSION_EMAIL_KEY:-email}
	log_level: ${USERS_BOOKS_LOG_LEVEL:-INFO}
data_model:
	table: users_books
	columns: [id, user_id, book_id]
	unique: [user_id, book_id]
	indexes: [[user_id, book_id]]
services:
	add: add_user_book(user_id, book_id) -> created: bool
	remove: remove_user_book(user_id, book_id) -> removed: bool
	list: list_user_book_ids(user_id) -> [int]
	bulk_add: bulk_add(user_id, [int]) -> {added: int, existing: int}
	bulk_remove: bulk_remove(user_id, [int]) -> {removed: int, missing: int}
	replace: replace_user_books(user_id, [int]) -> {added: int, removed: int, final_count: int}
	count: count_mappings(user_id?) -> int | {total: int, by_user: int}
cache:
	scope: request
	key: _users_books_allowed_ids
	strategy: lazy-load + invalidate on mutation
filter_hook:
	event: sqlalchemy.before_compile(Select)
	predicate: Books.id IN (allowed_ids)
	skip_conditions: [no_request_ctx, unauthenticated, admin, no_books_table, empty_and_lenient, too_many_ids]
	empty_modes:
		strict: false_predicate
		lenient: pass_through
permissions:
	admin_determination: [current_user.role_admin(), bitmask_role, session.is_admin]
	ensure_admin: raises PermissionError
webhook:
	enabled_when: USERS_BOOKS_WEBHOOK_API_KEY set
	action: map email -> user_id -> allow-list additions
metrics:
	enabled_when: USERS_BOOKS_ENABLE_METRICS true
logging:
	dynamic_level: true
	decorator: log_exceptions
errors:
	duplicate_insert: noop
	filter_hook_failure: log_and_fail_open
```

---

Agents MUST:
1. Always prefer service-layer functions over raw SQL.
2. Invalidate caches after ANY mutation before performing follow-up reads.
3. Avoid altering logging handlers; adjust level only via accessor.
4. Treat allow-list semantics as authoritative; do not fabricate book IDs.
5. Use config accessors (not os.environ) inside Python logic.
6. Fail open (no filter) only under documented skip conditions; never silently narrow results.
7. Keep YAML summary in sync if adding new environment variables or service operations.


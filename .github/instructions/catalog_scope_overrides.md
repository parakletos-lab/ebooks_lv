# Scoped Catalog View Pattern

This note documents how we added the “My Books” scope without touching `/calibre-web` sources, so the same pattern can be reused for any future user-specific catalog variant. Everything lives in our overlay (`app/*`) and clamps Calibre-Web through request hooks and runtime monkey patches.

## When to reach for this pattern

Use it whenever you need to expose an alternate catalog surface that:

- filters the standard Calibre listings without duplicating templates,
- switches scopes through regular navigation links (no custom pages), and
- must continue to honor every Calibre feature (sorting, pagination, shelves, etc.).

## High level building blocks

1. **Per-request state** – extend `app/services/*` to compute the set of book IDs (or any other selector) tied to the logged-in user. Store it on `g` inside a before-request hook (`register_catalog_access`).
2. **Session scope selector** – add a tiny Blueprint with endpoints like `/catalog/my-books` or `/catalog/all-books` that simply set a session key and redirect back to `web.index`. Use `_safe_redirect_target` to avoid open redirects.
3. **Monkey patch Calibre filters** – wrap `CalibreDB.common_filters` in `app/routes/overrides/calibre_overrides.py`. Inside the wrapper, inspect `g.catalog_scope` and, if the view is scoped, `and_` a `Books.id.in_(...)` clause (or any other SQLAlchemy expression).
4. **Front-end toggle** – expose the scope metadata inside the JSON payload we already ship to `non_admin_catalog.js`. That script inserts navigation links under the existing `#nav_new` item and keeps them highlighted according to `payload.views.current`.
5. **Optional access guard** – if the scoped view implies read restrictions (e.g., non-purchased titles should not open in the reader), check the ID during the same before-request hook and redirect away when necessary.

## Backend steps in detail

1. **Extend state payload**
   - `app/services/catalog_access.py` already knows how to gather per-user metadata. Add any new fields you need there.
2. **Before-request registration** (`app/routes/overrides/catalog_access.py`)
   - Build the `UserCatalogState` early in the request.
   - Persist it on `g.catalog_state` for downstream consumers (filters, templates, JS payload).
   - Resolve the active scope from `session[CATALOG_SCOPE_SESSION_KEY]`, defaulting to `CatalogScope.ALL` for admins or first-time visitors.
   - Serialize a payload that includes both the purchased IDs (or whatever identifiers you filter on) and the URLs for the toggle endpoints. Inject it into the response as JSON for the JS layer.
3. **Scope blueprint** (`scope_bp` in the same file)
   - Each endpoint should set the session key, then redirect to `url_for("web.index")` or the `next` query parameter.
4. **Query patch** (`app/routes/overrides/calibre_overrides.py`)
   - Import `cps.db` lazily so the patch only runs once.
   - Store the original `common_filters` implementation, then replace it with a wrapper that applies your additional clause when `g.catalog_scope` matches the custom mode.
   - Guard against calls that happen outside a Flask request (e.g., background jobs) by catching `RuntimeError` and returning the original clause.
5. **Route registration** (`app/routes/inject.py`)
   - Ensure `register_calibre_overrides(app)` runs during startup before the first request so every Calibre view is filtered automatically.

## Front-end considerations

- `non_admin_catalog.js` is our single hook for catalog UX. Keep it data-driven:
  - Read scope metadata from the injected JSON (`payload.views`).
  - Repoint the default “Books” link to the “all” scope endpoint so users can always return.
  - Insert a sibling link (`#nav_mybooks`) using DOM APIs; avoid editing upstream templates.
  - Update `classList` to reflect the active scope so Calibre’s layout keeps the correct highlighting.
- Reuse the same payload to drive any extra UI state (badges, buttons, labels) so the server never needs to duplicate templates.

## Testing checklist

1. Run `bash ./scripts/dev_rebuild.sh` to bake the overlay into the container (Calibre templates are cached).
2. Login with a test account that has both allowed and disallowed titles.
3. Click the custom nav link and confirm the listing only shows the scoped set.
4. Switch back to the default view and make sure full catalog behavior (filters, pagination, shelves) still works.
5. Attempt to open a disallowed book detail/reader URL directly and verify the guard redirects to the safe page.
6. Watch browser console logs for JS errors (`catalog payload parse error`, missing DOM nodes, etc.).

## Adding another scope

1. Define a new `Enum` member in `CatalogScope` (e.g., `WISHLIST`).
2. Extend the session blueprint with `/catalog/wishlist` (can be another route or parameterized handler).
3. Update the state payload to include whatever IDs or metadata the new scope needs.
4. Teach the patched `common_filters` wrapper how to translate the new metadata into SQL (e.g., join custom tables or apply different WHERE clauses).
5. Adjust the front-end script to insert the extra nav item(s) and to respect the additional scope when toggling classes.

## Operational notes

- Keep everything in our overlay — never edit `calibre-web/cps/*` files. If you need new hooks, add them to `app/routes/overrides/*` and patch at runtime.
- Because we rely on session keys, remember that scope is per-browser. If a future feature needs per-request toggles (query parameters), adapt `_resolve_scope` to read both sources.
- Any new environment variables or services introduced for scope resolution must be documented in `AGENTS.md` and exposed through `app.config` accessors.
- Re-run Playwright smoke flows (chrome-devtools MCP) after adding scopes to make sure DOM mutations still align with test selectors.

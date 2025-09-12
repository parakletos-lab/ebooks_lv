# Plugin Admin Landing Navigation Link – Implementation Guide (Signal-Based, No JS)
Date: 2025-09-09 (revised)  
Status: Implementation Guide  
Audience: Calibre-Web plugin developers  
Goal: Provide a reusable, purely server-side pattern to expose a “Plugin Admin” navigation link (and landing index) without editing upstream `layout.html` or injecting client‑side DOM manipulation JavaScript.

---

## 1. Objective

Expose one or many plugin administrative UI entry points to Calibre‑Web administrators by:

- Dynamically adding a “Plugin Admin” (single or dropdown) item into the existing top navigation *purely server-side*
- Aggregating plugin admin pages into a landing index page
- Avoiding permanent divergence (no forking `layout.html`)
- Keeping the pattern idempotent, safe, testable, and low maintenance

This revision supersedes earlier guidance that recommended client‑side JS DOM insertion. We now prefer Flask’s server-side rendering signals.

---

## 2. Core Idea (Why Signals)

Flask emits `before_render_template` (and `template_rendered`) signals when rendering templates (Blinker required).  
- `before_render_template` fires before the Jinja environment renders – mutating the `context` here affects output.  
- `template_rendered` fires after rendering – useful for logging, NOT for injecting new context keys (too late).

Therefore we attach a listener to `before_render_template` to inject `plugin_admin_links` (already resolved for the current user) into the context of any template that might include the navigation bar.

No template patch. No JS. No copying upstream layout.

---

## 3. High-Level Approaches (Updated)

| Approach | Pros | Cons | Recommendation |
|----------|------|------|----------------|
| A. Hard patch / fork `layout.html` | Simple to reason about | Ongoing merge burden | NO |
| B. Context processor + JS DOM injection | Worked without upstream change | Client fragility; FOUC; extra script | Legacy / Fallback ONLY |
| C. Flask `before_render_template` signal injection (server-side) | Pure server-side, no layout edit, no JS | Requires Blinker (already common) | YES (Primary) |
| D. Introduce upstream nav block (e.g. `{% block nav_extra %}`) | Clean, explicit | Needs upstream edit acceptance | Maybe (Future optional) |

Current Recommendation: **Approach C** (signals).

---

## 4. Target UX

Top navigation (admins only):

Single page:
```
[ Admin ] [ Plugin Admin ]
```

Multiple plugin admin pages (dropdown):
```
[ Admin ] [ Plugin Admin ▼ ]
  • Users ⇄ Books
  • Collections Manager
  • Feature Flags
```

---

## 5. Registry Data Model

An in‑memory shared registry collects plugin admin page metadata:

```/dev/null/registry_spec.json#L1-18
[
  {
    "plugin": "users_books",
    "title": "Users ⇄ Books Allow‑List",
    "url_endpoint": "users_books.admin_ui",
    "icon": "glyphicon-random",
    "description": "Manage per-user visibility allow-list."
  }
]
```

Rules:
- Either `url_endpoint` OR raw `url` required.
- `plugin` should match plugin package/import name.
- `title` required for display.
- Optional: `icon`, `description`, `order`, `visible_predicate`.

---

## 6. Server-Side Signal Injection – Design

Flow:
1. Plugins register themselves (append dict to central registry) during `init_app(app)`.
2. A one-time initialization function wires a `before_render_template` signal handler.
3. On each template render:
   - Determine if current user is authenticated admin.
   - If not: do nothing (fast path).
   - Resolve registry entries to concrete URLs (cache per request).
   - Add `plugin_admin_links` to the `context`.
4. Base template (already contains nav list) references `plugin_admin_links` in a conditional snippet we inject through a Jinja overlay (NOT DOM JS).  
   - We still need *some* minimal template inclusion point. Two options:  
     a. Use an existing block (e.g. `block header` or `block body` if nav is there) to insert a tiny macro call; or  
     b. (If there is no convenient block) create a very small overlay template that extends `layout.html` and is used by plugin admin pages.  
   - For visibility across *all* pages, if upstream layout lacks an injection block you can fallback to JS (legacy) OR propose a minimal upstream patch adding, e.g., `{% block nav_inject %}{% endblock %}` just before the nav `<ul>` closing tag.  
   - If neither patch nor JS is acceptable, you can still conditionally add links by altering `context` and enumerating them where any template you control loops navigation items (partial adoption).

If you have sufficient control to add a single harmless block to upstream layout, that is the cleanest synergy (Approach D). If not, use a macro loaded via an included template already referenced by layout (if one exists). Many Calibre-Web forks include a generic `messages.html` or similar include; piggyback if present (audit first).

---

## 7. Registry & Initialization Code

```/dev/null/plugin_admin/navigation.py#L1-160
"""
Signal-based Plugin Admin navigation injection (server-side only).
"""
from __future__ import annotations
from typing import Callable, Dict, List, Optional
from threading import RLock
from flask import current_app, url_for, before_render_template

# Thread-safety: registry mutated during plugin init (single threaded usually),
# but we add a lock for defensive correctness (e.g., dynamic plugin load).
_REGISTRY_LOCK = RLock()
_PLUGIN_ADMIN_REGISTRY: List[Dict] = []
_INITIALIZED = False


def register_plugin_admin_page(entry: Dict):
    """
    Register (idempotent) a plugin admin page.
    Keys:
        plugin (str) - logical plugin name
        title (str) - display label
        url_endpoint (str) OR url (str)
        icon (str, optional)
        description (str, optional)
        order (int, optional) - for sorting
        visible_predicate (callable, optional) -> bool
    """
    required = {"plugin", "title"}
    if not required.issubset(entry):
        raise ValueError(f"Missing required keys: {required - set(entry)}")
    if "url_endpoint" not in entry and "url" not in entry:
        raise ValueError("Must supply either 'url_endpoint' or 'url'.")

    with _REGISTRY_LOCK:
        # Deduplicate by (url_endpoint or url)
        key = entry.get("url_endpoint") or entry.get("url")
        for existing in _PLUGIN_ADMIN_REGISTRY:
            ek = existing.get("url_endpoint") or existing.get("url")
            if ek == key:
                return
        _PLUGIN_ADMIN_REGISTRY.append(entry)


def _resolve_links():
    """Return resolved links (list of dict) for the current request user context."""
    try:
        from cps import ub  # Lazy import to avoid circular issues
        cu = getattr(ub, "current_user", None)
    except Exception:
        return []

    if not (cu and cu.is_authenticated and getattr(cu, "role_admin", lambda: False)()):
        return []

    resolved = []
    with _REGISTRY_LOCK:
        items = list(_PLUGIN_ADMIN_REGISTRY)

    for e in items:
        # Optional visibility predicate
        pred: Optional[Callable[[], bool]] = e.get("visible_predicate")
        if pred:
            try:
                if not pred():
                    continue
            except Exception:
                continue

        # Resolve URL
        url_val = None
        if "url_endpoint" in e:
            try:
                url_val = url_for(e["url_endpoint"])
            except Exception:
                continue
        else:
            url_val = e.get("url")

        if not url_val:
            continue

        resolved.append({
            "plugin": e.get("plugin"),
            "title": e.get("title"),
            "url": url_val,
            "icon": e.get("icon", "glyphicon-wrench"),
            "description": e.get("description", ""),
            "order": e.get("order", 100)
        })

    resolved.sort(key=lambda d: d.get("order", 100))
    return resolved


def init_plugin_admin_nav(app):
    """
    Wire signal listener once. Safe to call multiple times.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    def _before_render(sender, template, context, **extra):
        # If we *know* certain templates never show nav, could early-return using template.name
        # e.g., if template.name in ("login.html",): return
        if "plugin_admin_links" in context:
            # Idempotency (maybe another layer added already)
            return
        links = _resolve_links()
        if links:
            # Build structure for single vs multi
            context["plugin_admin_links"] = links
            context["has_multiple_plugin_admin_links"] = len(links) > 1

    before_render_template.connect(_before_render, app)
    app.logger.info("Plugin Admin nav injection initialized (signal-based)")

```

Key Points:
- Uses `before_render_template` (modifies context before final render).
- Idempotent (checks key presence).
- Registry resolution does per-request admin check.
- Sorted by optional `order`.

---

## 8. Minimal Plugin Registration Snippet

```/dev/null/plugins/users_books/__init__.py#L1-40
from .navigation import register_plugin_admin_page, init_plugin_admin_nav

def init_app(app):
    # Register blueprint(s) first so endpoints exist for url_for.
    # app.register_blueprint(bp_users_books)

    # Initialize nav injection (safe multi-call)
    init_plugin_admin_nav(app)

    # Add registry entry
    register_plugin_admin_page({
        "plugin": "users_books",
        "title": "Users ⇄ Books Mapping",
        "url_endpoint": "users_books.admin_ui",
        "icon": "glyphicon-random",
        "description": "Manage per-user allow-list"
    })
```

---

## 9. Template Consumption Pattern

Because we are not editing upstream `layout.html`, we need a way to render the injected links. Options:

1. Upstream already loops something like `nav_entries`: Extend that pattern by merging `plugin_admin_links` into the list in a downstream template you control.
2. If there is a `block` in the nav region, override it and conditionally render links.
3. If neither exists, lobby for a small upstream addition:
   - Example patch (proposed upstream, not required here):

```/dev/null/patch_example_layout.diff#L1-20
@@
 <ul id="main-nav" class="nav navbar-nav">
   ... existing items ...
+  {% block plugin_admin_nav %}
+    {% if plugin_admin_links %}
+      {% if has_multiple_plugin_admin_links %}
+        <li class="dropdown" id="nav-plugin-admin-anchor">
+          <a href="#" class="dropdown-toggle" data-toggle="dropdown">
+            <span class="glyphicon glyphicon-wrench"></span> <span class="hidden-sm">Plugin Admin</span> <span class="caret"></span>
+          </a>
+          <ul class="dropdown-menu">
+            {% for l in plugin_admin_links %}
+              <li><a href="{{ l.url }}"><span class="glyphicon {{ l.icon }}"></span> {{ l.title }}</a></li>
+            {% endfor %}
+          </ul>
+        </li>
+      {% else %}
+        <li id="nav-plugin-admin-anchor">
+          <a href="{{ plugin_admin_links[0].url }}"><span class="glyphicon {{ plugin_admin_links[0].icon }}"></span> <span class="hidden-sm">Plugin Admin</span></a>
+        </li>
+      {% endif %}
+    {% endif %}
+  {% endblock %}
 </ul>
```

If adding a block is not possible: you can (temporarily) revert to the legacy JS injection (Section 16) OR create a derived base template for plugin-owned pages only (limited visibility) — but that will not show the link on unrelated pages.

---

## 10. Landing Page Blueprint

```/dev/null/plugin_admin/landing.py#L1-120
from flask import Blueprint, render_template, abort, url_for
from .navigation import _PLUGIN_ADMIN_REGISTRY, _resolve_links
from cps import ub

bp_plugin_admin = Blueprint(
    "plugin_admin_landing",
    __name__,
    template_folder="templates"
)

@bp_plugin_admin.route("/plugin/admin")
def plugin_admin_index():
    cu = getattr(ub, "current_user", None)
    if not (cu and cu.is_authenticated and getattr(cu, "role_admin", lambda: False)()):
        abort(403)
    # Use internal registry directly to show descriptions even if endpoint broken later
    raw = list(_PLUGIN_ADMIN_REGISTRY)
    rows = []
    for e in raw:
        try:
            if "url_endpoint" in e:
                link = url_for(e["url_endpoint"])
            else:
                link = e.get("url")
        except Exception:
            link = None
        rows.append({
            "plugin": e.get("plugin"),
            "title": e.get("title"),
            "description": e.get("description", ""),
            "icon": e.get("icon", "glyphicon-wrench"),
            "url": link,
            "endpoint": e.get("url_endpoint")
        })
    return render_template("plugin_admin_index.html", entries=rows)
```

Template:

```/dev/null/plugin_admin/templates/plugin_admin_index.html#L1-60
{% extends "layout.html" %}
{% set title = "Plugin Admin" %}
{% block body %}
<h3 style="margin-top:0;">Plugin Administration</h3>
<p class="text-muted">Central index of registered plugin admin pages.</p>
<table class="table table-condensed table-striped">
  <thead><tr>
    <th>Plugin</th><th>Title</th><th>Description</th><th>Link</th>
  </tr></thead>
  <tbody>
  {% for e in entries %}
    <tr>
      <td>{{ e.plugin }}</td>
      <td>{{ e.title }}</td>
      <td>{{ e.description }}</td>
      <td>
        {% if e.url %}
          <a href="{{ e.url }}" class="btn btn-xs btn-primary">Open</a>
        {% else %}
          <span class="text-danger">Endpoint missing</span>
        {% endif %}
      </td>
    </tr>
  {% else %}
    <tr><td colspan="4" class="text-muted">No plugin admin pages registered.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

---

## 11. Blueprint Registration

```/dev/null/plugins/users_books/__init__.py#L42-80
from .landing import bp_plugin_admin
from .navigation import init_plugin_admin_nav, register_plugin_admin_page

def init_app(app):
    # Ensure landing blueprint registered (once)
    if "plugin_admin_landing" not in app.blueprints:
        app.register_blueprint(bp_plugin_admin)
    init_plugin_admin_nav(app)

    register_plugin_admin_page({
        "plugin": "users_books",
        "title": "Users ⇄ Books Mapping",
        "url_endpoint": "users_books.admin_ui",
        "icon": "glyphicon-random",
        "description": "Per-user allow-list administration"
    })
```

---

## 12. Idempotence & Safety

| Concern | Strategy |
|---------|----------|
| Duplicate registry entries | Deduplicate by endpoint/url key |
| Multiple init calls | `_INITIALIZED` guard in `init_plugin_admin_nav` |
| Missing endpoints | Skip silently when resolving (do not break page) |
| Non-admin view leakage | Admin check inside `_resolve_links()` |
| Race condition on registry mutation | `RLock` around mutation |

---

## 13. Testing Matrix

| Scenario | Expectation |
|----------|-------------|
| Admin loads normal page | Nav shows “Plugin Admin” / dropdown |
| Non-admin loads page | No plugin admin nav item |
| Multiple pages registered | Dropdown variant appears |
| Remove plugin / endpoint fails | That link disappears (no error) |
| Landing page with 0 entries | “No plugin admin pages registered.” row |
| Intentional duplicate registration | Single nav entry |
| Large number (e.g. 15) | Dropdown scrolls (consider grouping future) |

Manual sanity:
```
curl -b session.txt http://localhost:8083/plugin/admin
```

---

## 14. Performance Notes

- Registry typically tiny (single-digit entries).
- Per-request resolution: O(n) with straightforward `url_for` calls.
- Negligible overhead vs full page render.
- Could implement simple request-scope memoization if future growth (not needed now).

---

## 15. Future Enhancements

| Enhancement | Description |
|-------------|-------------|
| Upstream nav block | Adds explicit insertion point, removes need for heuristics |
| Ordering | Already supported via `order` field |
| Permission predicates | Provide per-entry `visible_predicate()` |
| Category grouping | Add `category` and group inside dropdown subheaders |
| Caching | Cache resolved endpoints once per process load; flush on plugin (re)registration |
| JSON API | Provide `/plugin/admin/_links.json` for runtime introspection |
| Telemetry | Count admin tool usage events |

---

## 16. Legacy JS DOM Injection (Fallback Reference ONLY)

If signals are unavailable (very old Flask) or upstream absolutely cannot add a block, a minimal legacy snippet (previous approach) can be used. Not recommended for long-term:

```/dev/null/legacy_js_injection.html#L1-40
{% if plugin_admin_links %}
<script type="application/json" id="plugin-admin-links-data">
{{ plugin_admin_links|tojson }}
</script>
<script>
(function(){
  var nav=document.getElementById("main-nav");
  if(!nav||document.getElementById("nav-plugin-admin-anchor")) return;
  var data=document.getElementById("plugin-admin-links-data");
  if(!data) return;
  try {
    var links=JSON.parse(data.textContent||"[]");
    if(!links.length) return;
    if(links.length===1){
      var li=document.createElement("li");
      li.id="nav-plugin-admin-anchor";
      li.innerHTML='<a href="'+links[0].url+'"><span class="glyphicon '+(links[0].icon||'glyphicon-wrench')+'"></span> <span class="hidden-sm">Plugin Admin</span></a>';
      nav.appendChild(li);
    } else {
      var w=document.createElement("li");
      w.id="nav-plugin-admin-anchor"; w.className="dropdown";
      var html=['<a href="#" class="dropdown-toggle" data-toggle="dropdown"><span class="glyphicon glyphicon-wrench"></span> <span class="hidden-sm">Plugin Admin</span> <span class="caret"></span></a><ul class="dropdown-menu">'];
      links.forEach(function(l){
        html.push('<li><a href="'+l.url+'"><span class="glyphicon '+(l.icon||'glyphicon-wrench')+'"></span> '+(l.title||'Admin')+'</a></li>');
      });
      html.push('</ul>');
      w.innerHTML=html.join("");
      nav.appendChild(w);
    }
  }catch(e){ console.warn("Plugin admin injection failed", e); }
})();
</script>
{% endif %}
```

---

## 17. Migration From Previous JS-Based Implementation

| Step | Action |
|------|--------|
| 1 | Add new `navigation.py` with signal logic |
| 2 | Register entries via `register_plugin_admin_page()` |
| 3 | Remove old inline JS injection (or keep temporarily while verifying) |
| 4 | Add nav block upstream (optional) OR finalize server-side dropdown rendering |
| 5 | Test admin/non-admin views |
| 6 | Remove legacy fallback code after validation |

---

## 18. Security Considerations

| Vector | Mitigation |
|--------|-----------|
| Unauthorized exposure | Admin check in `_resolve_links()` |
| XSS via titles/descriptions | Jinja autoescaping (do not mark safe) |
| Malicious plugin injecting callable raising errors | Wrap predicate & URL resolution in try/except |
| Enumeration of hidden endpoints | Omit entries failing resolution, no leakage text |

---

## 19. Checklist (Execution Order)

```
[ ] Create navigation.py (registry + signal hookup)
[ ] Create landing blueprint + template
[ ] Register blueprint & init nav in plugin init
[ ] Register first plugin admin entry
[ ] (Optionally) Add nav block upstream OR integrate into existing block
[ ] Verify single plugin link
[ ] Add second entry → dropdown
[ ] Document usage in plugin README
[ ] Remove any legacy JS injection
```

---

## 20. Quick Reference Snippet

```/dev/null/quick_add.py#L1-30
# Call inside plugin init after blueprint(s) registered
from plugin_admin.navigation import init_plugin_admin_nav, register_plugin_admin_page

def init_app(app):
    init_plugin_admin_nav(app)
    register_plugin_admin_page({
        "plugin": "users_books",
        "title": "Users ⇄ Books Mapping",
        "url_endpoint": "users_books.admin_ui",
        "icon": "glyphicon-random",
        "description": "Per-user allow-list administration",
        "order": 10
    })
```

---

## 21. Summary

We now recommend a **purely server-side, signal-driven** approach for injecting plugin admin navigation into Calibre-Web:

- No DOM mutation JavaScript required
- No persistent fork of `layout.html`
- Centralized registry resolves links per request with admin gating
- Extensible (ordering, predicates, categories)
- Clean migration path away from legacy JS

Adopt this pattern for all future plugin admin surfaces to maintain a consistent, secure, and maintainable operator experience.

---

(End of document)
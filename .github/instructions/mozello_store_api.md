# Mozello Store API – Internal Integration Notes

Source (authoritative, keep link handy): https://www.mozello.com/developers/store-api/
These notes are a concise, engineering‑focused summary to aid implementation of sync jobs, webhooks, and admin tooling. Always consult the official docs for authoritative field lists, edge cases and any legal / licensing constraints. Avoid copying large verbatim sections from the public docs into this repo.

---
## 1. Overview
Mozello Store API enables programmatic management of store catalog (products, categories), inventory/price updates, and reception of order & product/webhook notifications. Communication is JSON over HTTPS with API key header auth. Supports CRUD plus batch update patterns and webhook callbacks for changes originating inside Mozello.

Typical internal use cases for this project:
- Periodic catalog import/export or reconciliation.
- On‑demand price / stock synchronization (book or variant mapped to our internal entities).
- Receiving ORDER_* and PRODUCT/STOCK_* notifications to trigger downstream updates (e.g., update Calibre metadata, adjust allow‑list, analytics logging).

---
## 2. Authentication & Base URL
- Base URL: `https://api.mozello.com/v1/`
- Header: `Authorization: ApiKey <API_KEY>` (format: `ApiKey MZL-...`).
- All successful responses: HTTP 200 with `{ "error": false, ... }` (even for partial success). Failures return non‑2xx + `{ "error": true, error_code, error_message }`.

Implementation tips:
- Centralize API key via config accessor (see `AGENTS.md` rules – do NOT read env inline in business logic). Add new accessor if needed.
- Wrap requests with retry/backoff only for transient network problems (NOT for 4xx application errors).

---
## 3. HTTP Methods & Resource Patterns
| Resource Domain | Core Paths (handle/id placeholder) | Methods (common) |
|-----------------|------------------------------------|------------------|
| Products        | `/store/products/`, `/store/product/<handle>/` | GET (list/get), POST (create), PUT (update), DELETE (delete) |
| Batch Products  | `/store/products/batch_update/`, `/store/products/batch_update_by_sku/`, `/store/products/batch_delete/` | POST |
| Product Pictures| `/store/product/<handle>/picture/`, `/store/product/<handle>/picture/<picture-handle>/` | POST(add), DELETE(remove) |
| Variant Pictures| `/store/product/<handle>/variant_picture/`, `/store/product/<handle>/variant_picture/<picture-handle>/` | POST, DELETE |
| Categories      | `/store/categories/`, `/store/category/<handle>/`, `/store/category/<handle>/move/` | GET list/get, POST add, PUT update, DELETE, POST move |
| Orders          | `/store/orders/`, `/store/order/<order-id>/` | GET list/get, PUT update |
| Notifications   | `/store/notifications/` | GET (current config), PUT (update URL & events) |

Notes:
- Product create requires a unique `handle` (prefix `uid-` convention from examples) OR will be created when batch‑updating with new handle.
- Updating variants: you MUST supply existing `variant_handle` (and option value handles) or Mozello will treat them as replacements (overwriting existing variant set).

---
## 4. Request Modifiers (List Endpoints)
Supported on most list endpoints (see official docs for each):
- Pagination: `page_size` plus `next_page_uri` returned; follow until absent.
- Reverse sorting: `desc=1`.
- Filtering: `filter=<field><op><value>` URL‑encoded. Operators: `> < = <= >= <>`. Date/time fields use `YYYY-MM-DD HH:MM:SS`.

Internal helper suggestion:
```
def build_filter(field: str, op: str, value: str) -> str:
    return urllib.parse.quote(f"{field}{op}{value}")
```

---
## 5. Core Data Structures (Simplified)
(Fields here are the ones we’re likely to use; the official spec lists more. Omitted fields may appear as null or be absent.)

### Product
- Identification: `handle`, optional `sku` (top‑level) plus variant SKUs.
- Categorization: either full `category.path` (array of up to 2 multilanguage text objects) OR `category_handle`.
- Text fields: `title`, `description`, `url` (multilanguage text object or string if single language).
- Options: array or null; each includes `option_name`, `display_style` (list|colors|buttons) and `values` (each has `value_handle`, `value_name`, optional `color_code`). New values use fresh handles (non‑existing).
- Variants: array or null; each variant has `variant_no`, `variant_handle`, `option_value_handle1..3`, `price`, `sale_price`, `sku`, `stock`, `picture_handle`.
- Media: `pictures[]` (uid + url), `variant_pictures[]` (uid + url).
- Pricing & Inventory: `price`, `sale_price`, `stock` (null means not managed), `visible`, `featured`, `vendor`, `model`, `weight`.

### Category
`handle`, `title` (multilanguage), `level` (1..3), ordering (`previous_handle`), hierarchy (`parent_handle`), SEO slug (`seo_url`), `picture` (URL or upload object when creating/updating).

### Order
Core: `order_id`, `created_at`, `payment_status` (paid|pending|failed), `dispatched`, `archived`, customer contact fields, shipping address, pricing summary (`subtotal`, `shipping_price`, `taxes`, `total`, `currency`), discount codes, `cart[]` lines (product/variant identifiers, pricing, tax rates, quantities), possible `shipping_tracking_code` & URLs.

### Multilanguage Text
Object keyed by language codes (e.g. `{ "en": "Memory", "lv": "Atmiņa" }`) or a plain string for single‑language updates. Updating behavior adjustable via API options (see below).

### API Options
`text_update_mode`: `overwrite` (default) or `merge` – controls whether unspecified languages are cleared or retained when updating.

---
## 6. Product Operations – Practical Patterns
1. Create product:
   - POST `/store/product/` body `{ "product": { handle, category OR category_handle, title, ... options?, variants?, price/... } }`
   - Then (optional) add pictures: POST picture endpoints with base64 image data.
2. Update product price/visibility:
   - PUT `/store/product/<handle>/` body `{ "product": { "price": 12.34 } }` (only changed fields + required variant handles if touching variants).
   - Note: Per Mozello docs, update payload excludes `pictures` and `variant_pictures`, so picture ordering cannot be set via `PUT /store/product/<handle>/`.
3. Batch upsert (mixed create/update):
   - POST `/store/products/batch_update/` body `{ "products": [ { handle|sku, ... } ] }`.
     * If `handle` exists → update; missing handle but `sku` unique → update by SKU; new handle → create.
4. Quick stock/price bumps by SKU (faster minimal payload):
   - POST `/store/products/batch_update_by_sku/` with items each containing `sku` plus one or more of `price`, `special_price` (note: doc uses both terms; check final field name), `stock`.
5. Delete products:
   - Single: DELETE `/store/product/<handle>/`.
   - Bulk: POST `/store/products/batch_delete/` with `products: [{ "handle": H } | { "sku": S }]`.

Edge considerations:
- Variant overwrite risk: Always include `variant_handle` when updating variants; otherwise unreferenced variants may be lost.
- Image workflow: add product first, then pictures, then update variant `picture_handle` associations.

### 6.1 Product Pictures (Detailed)
New (expanded) summary from official docs:

List product pictures:
GET `/store/product/<product-handle>/pictures/`
Response example:
```
{
   "pictures": [
      { "uid": "uid-1234567890", "url": "https://site-123.../image1234567890.jpg" }
   ]
}
```

Add product picture:
POST `/store/product/<product-handle>/picture/`
Request body:
```
{
   "picture": {
      "filename": "greenshirt.jpg",
      "data": "/9j/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUG..."
   }
}
```
Notes:
- `data` is base64-encoded binary image content (JPEG/PNG as supported by Mozello).
- Multiple POSTs can be issued to attach multiple pictures; Mozello assigns each a `uid`.
- Ordering: Mozello API does not document a way to reorder existing product pictures. The only supported operations are add (POST) and delete (DELETE), so ordering can only be influenced indirectly via add/delete sequence.

Delete product picture:
DELETE `/store/product/<product-handle>/picture/<picture-handle>/`

Implementation status (ebooks_lv):
- Helper `add_product_picture(handle, b64_image, filename)` added in `mozello_service` (best-effort upload after export).
- Currently only uploads the primary Calibre `cover.jpg` once during initial export (bulk or single).
- Listing & deletion endpoints not yet integrated; future enhancement could reconcile remote vs local covers.

---
## 7. Categories
- Add: POST `/store/category/` with `{ "category": { title, previous_handle?, parent_handle?, seo_url?, picture? } }`.
- Update: PUT `/store/category/<handle>/` (cannot change `parent_handle` or `previous_handle` here – use move endpoint).
- Move / reorder: POST `/store/category/<handle>/move/` with `{ parent_handle, previous_handle }` (null allowed to move to root / first position).
- Delete: DELETE requires no sub‑categories; products become uncategorized.

---
## 8. Orders
- List: GET `/store/orders/` (supports `archived=true|false`, pagination, filtering by `created_at`).
- Get: GET `/store/order/<order-id>/`.
- Update: PUT `/store/order/<order-id>/` with partial `{ "order": { payment_status?, archived?, dispatched?, shipping_tracking_code?, shipping_tracking_url?, shipping_label_url? } }`. Setting `dispatched=true` auto‑archives.

---
## 9. Notifications (Webhooks)
Configuration:
- GET/PUT `/store/notifications/` with `notifications_url` and array `notifications_wanted`.
- Possible events (current documented list):
  - `ORDER_CREATED`, `ORDER_DELETED`, `PAYMENT_CHANGED`, `DISPATCH_CHANGED`, `PRODUCT_CHANGED`, `PRODUCT_DELETED`, `STOCK_CHANGED`.

Delivery:
- HTTPS POST JSON payload `{ event: EVENT_NAME, <resource>: {...} }` where `<resource>` is `order` or `product` structure subset (full object often supplied for convenience).
- Headers: `X-Mozello-API-Version`, `X-Mozello-Hash`, `X-Mozello-Alias`.
- Authenticity: Compute `base64( HMAC_SHA256( raw_body, api_key ) )` and compare to `X-Mozello-Hash`.

Internal handling checklist:
- Verify HMAC before enqueue.
- Idempotency: Deduplicate by `(event, order_id|product.handle, timestamp)` if necessary.
- Offload heavy processing (e.g., image fetch) to async worker.

---
## 10. Rate Limits & Performance
- Item limits: Do not send > 1000 product items in a single batch.
- Request rate: ≤ 5 requests/second; bursts > 300/minute may trigger HTTP 403 (temporary block). If sustained higher throughput is needed, coordinate with Mozello support.
- Webhook retries: Mozello retries failed notifications for up to 48 hours (exact retry cadence not documented – design for at‑least‑once delivery).

Recommendations:
- Client: Implement token bucket or simple sleep to enforce 5 rps.
- Backoff: On 429/403 with rate message, exponential backoff + jitter.
- Pagination: Stream process pages rather than building large in‑memory lists.

---
## 11. Error Handling Strategy (Internal)
| Scenario | Action |
|----------|--------|
| 4xx validation (e.g., missing handle) | Log warning, mark item failed, continue batch. |
| 401 Unauthorized | Surface config/secrets alert, halt further calls until resolved. |
| 403 Access Denied (rate) | Backoff & retry within limit window. |
| 5xx server errors | Limited retries with exponential backoff. |
| Deserialization anomalies | Capture raw response for diagnostics; fail gracefully. |

Include correlation IDs in logs: combine our job run ID + Mozello handle/SKU/order_id.

---
## 12. Mapping to Internal Domain (Suggested)
| Mozello Concept | Internal (ebooks_lv) Candidate Mapping |
|-----------------|----------------------------------------|
| Product handle  | `mz_handle` (Calibre identifier type 'mz') as documented in `AGENTS.md` field design notes. |
| Product price   | `mz_price` custom float column. |
| SKU             | Potentially variant SKU -> internal edition mapping (if multi‑variant). |
| Stock           | Could drive availability flags / allow‑list automation. |
| Order events    | Trigger updating user ↔ book allow‑list or usage analytics. |

---
## 13. Minimal Code Snippets (Pseudo-Python)

### Auth Header Builder
```
headers = { 'Authorization': f'ApiKey {api_key}', 'Content-Type': 'application/json' }
```

### HMAC Verification (webhook)
```
digest = base64.b64encode(hmac.new(api_key.encode(), raw_body, hashlib.sha256).digest()).decode()
if digest != received_hash: raise ValueError('Invalid Mozello signature')
```

### Pagination Loop (generic)
```
url = base + '/store/products/?page_size=100'
while url:
    r = http_get(url)
    data = r.json()
    process(data.get('products', []))
    url = data.get('next_page_uri') and base + data['next_page_uri']
```

### Batch Update by SKU (payload skeleton)
```
{
  "products": [
    { "sku": "ABC-1", "stock": 5 },
    { "sku": "ABC-2", "price": 9.99 }
  ]
}
```

---
## 14. Security & Compliance Notes
- Treat API key as secret; inject via runtime config/provider (never commit).
- Validate & sanitize any data before mapping into internal DB to avoid injection or size blowups.
- Consider request/response logging with PII scrubbing (emails, addresses) where stored.

---
## 15. Open Questions / TODOs
- Confirm whether field `special_price` vs `sale_price` naming differences appear in batch_update_by_sku responses (doc hints at both). Empirically detect during integration and update this file.
- Decide if we need delta detection (hash previous product JSON) before sending updates to minimize calls.
- Determine frequency & scheduler for full catalog reconciliation (daily?).

---
## 16. Change Log (Local Notes)
| Date | Change |
|------|--------|
| 2025-10-11 | Initial concise summary drafted from public Mozello documentation. |

---
© Mozello SIA (original API design & field names). This derivative summary is for internal engineering reference only and should not be redistributed externally. Always review the latest official documentation before making significant changes.

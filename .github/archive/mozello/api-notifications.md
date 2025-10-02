## Store Notifications (Webhooks)

### Get Store Notifications
**Request**

`GET /store/notifications/`

Returns currently configured notification endpoint and subscribed event list.

**Response Example**

```json
{
    "notifications_url": "https://www.example.com/notifications.php",
    "notifications_wanted": [
        "ORDER_CREATED",
        "ORDER_DELETED",
        "PAYMENT_CHANGED",
        "DISPATCH_CHANGED",
        "PRODUCT_CHANGED",
        "PRODUCT_DELETED",
        "STOCK_CHANGED"
    ]
}
```

### Update Store Notifications
**Request**

`PUT /store/notifications/`

Updates or removes the URL to which Mozello sends notifications and the subscribed events.

**Parameters**

- `notifications_url` (string | null): New webhook URL or `null` to disable.
- `notifications_wanted` (array[string]): List of desired events. Allowed values:
    - `ORDER_CREATED`
    - `ORDER_DELETED`
    - `PAYMENT_CHANGED`
    - `DISPATCH_CHANGED`
    - `PRODUCT_CHANGED`
    - `PRODUCT_DELETED`
    - `STOCK_CHANGED`

**Request Body Example**

```json
{
    "notifications_url": "https://www.example.com/notifications.php",
    "notifications_wanted": [
        "ORDER_CREATED",
        "ORDER_DELETED",
        "PAYMENT_CHANGED",
        "DISPATCH_CHANGED",
        "PRODUCT_CHANGED",
        "PRODUCT_DELETED",
        "STOCK_CHANGED"
    ]
}
```

---

## Delivery & Verification

Notifications are sent via HTTPS POST with a JSON payload.

### HTTP Headers

- `X-Mozello-API-Version`: API version number
- `X-Mozello-Hash`: Base64-encoded HMAC-SHA256 of the raw POST body using your API key
- `X-Mozello-Alias`: Website alias

### Authenticity Verification

Compute the signature: `base64( HMAC_SHA256( raw_body, api_key ) )` and compare with `X-Mozello-Hash`.

**PHP Example**

```php
$post_body = file_get_contents('php://input');
$api_key   = 'YOUR_API_KEY_HERE';
$signature = base64_encode(hash_hmac('sha256', $post_body, $api_key, true));

$headers = getallheaders();
if (isset($headers['X-Mozello-Hash']) && hash_equals($signature, $headers['X-Mozello-Hash'])) {
        // Valid request - process payload
} else {
        http_response_code(401);
        exit('Invalid signature');
}
```

---

## Event Payloads
Each event includes `event` plus an `order` object (fields may be omitted if not applicable).

### ORDER_CREATED
Triggered when an order is created (payment status will be `pending`).

**Example**

```json
{
    "event": "ORDER_CREATED",
    "order": {
        "order_id": "MZ-1234567-123456",
        "created_at": "2020-12-30 15:25:33",
        "payment_status": "pending",
        "dispatched": false,
        "archived": false,
        "name": "John Smith",
        "company": "Universal Exports LTD",
        "vat_id": "LV40001234567",
        "company_id": "40001234567",
        "email": "johnsmith@example.com",
        "phone": "+371 22222222",
        "country_name": "Latvia",
        "country_code": "lv",
        "address": "Summer street 10",
        "city": "Riga",
        "province_code": "",
        "zip": "LV-1000",
        "shipping": {
            "country_name": "Latvia",
            "country_code": "lv",
            "address": "Summer street 10",
            "city": "Riga",
            "province_code": "",
            "zip": "LV-1000",
            "pickup_point_id": ""
        },
        "notes": "",
        "payment_method": "paypal",
        "shipping_method": "omniva-latvija",
        "shipping_tracking_code": "AA111111111111EE",
        "shipping_tracking_url": "",
        "currency": "EUR",
        "subtotal": 100,
        "shipping_price": 10,
        "shipping_tax_inclusive_percent": 21,
        "shipping_tax_exclusive_percent": null,
        "taxes": 23.1,
        "total": 133.1,
        "discount_code": "",
        "discount_amount": 0,
        "cart": [
            {
                "product_handle": "uid-1234567890",
                "product_name": "Trousers, Red, XXL, TR-12345",
                "product_variant": ["Red", "XXL"],
                "product_variant_handle": "uid-1024",
                "product_price": 50,
                "product_price_discounted": null,
                "product_sku": "TR-12345",
                "product_quantity": 1,
                "product_value": 50,
                "weight": 700,
                "tax_inclusive_percent": 21,
                "tax_exclusive_percent": null
            },
            {
                "product_handle": "uid-1234567891",
                "product_name": "Sweater, SW-12345",
                "product_price": 50,
                "product_price_discounted": null,
                "product_sku": "SW-12345",
                "product_quantity": 1,
                "product_value": 50,
                "weight": 400,
                "tax_inclusive_percent": 21,
                "tax_exclusive_percent": null
            }
        ],
        "print_url": "https://www.mozello.com/m/invoice/333444555/"
    }
}
```

### ORDER_DELETED
Triggered when an order is deleted manually.

Payload structure equals `ORDER_CREATED` (order data at deletion time). See above example.

### PAYMENT_CHANGED
Triggered whenever payment status changes (manual or automatic).

**Example (abbreviated)**

```json
{
    "event": "PAYMENT_CHANGED",
    "order": {
        "payment_status": "paid"
    }
}
```

---

## Notes
- Fields may be omitted when values are not set.
- Use the signature check before any state mutation.
- Treat unknown event types defensively (log & ignore) to allow forward compatibility.

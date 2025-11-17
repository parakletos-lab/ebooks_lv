# HTTPS Frontend (Caddy) Integration Guide

This document captures how to enable HTTPS for the ebooks_lv stack using a lightweight Caddy reverse proxy. It terminates TLS, serves on ports 80/443, and proxies internally to the existing Gunicorn service listening on 8083. The droplet deployment overlay (`compose.droplet.yml`) now ships with this configuration out of the box; customize the root `Caddyfile` and set `EBOOKSLV_DOMAIN` in `.env` to activate it.

## Goals

- Provide an `https://` webhook endpoint for Mozello: `https://<YOUR_DOMAIN>/mozello/webhook`
- Automatic certificate issuance & renewal (Let's Encrypt)
- Preserve client protocol/host info via `X-Forwarded-*` headers
- Minimal changes to the existing `calibre-web` service

## Prerequisites

1. A domain you control (example: `ebooks.example.com`).
2. DNS A record pointing to the server public IP (e.g. `159.223.xxx.xxx`).
3. Ports 80 and 443 open in firewall/cloud security groups.
4. The application already running via Docker Compose.

## Directory / File Additions

Add two artifacts to the repository root:

```
Caddyfile
compose.tls.yml
```

## Caddy Overlay Compose File (`compose.tls.yml`)

Use this as an overlay on top of the existing `compose.yml`. It removes the public port map from `calibre-web` (we expose it only to the internal network) and adds the Caddy proxy.

```yaml
services:
  calibre-web:
    # Remove direct host port mapping; keep internal exposure only
    ports: []
    expose:
      - "8083"

  caddy:
    image: caddy:2
    container_name: caddy
    restart: unless-stopped
    depends_on:
      - calibre-web
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

## `Caddyfile`

Replace `ebooks.example.com` with your domain. Caddy will obtain/renew certificates automatically.

```caddy
ebooks.example.com {
    # Compression & simple request optimizations
    encode zstd gzip

    # Reverse proxy all relevant paths to the internal app
    reverse_proxy /mozello/* calibre-web:8083
    reverse_proxy /admin/* calibre-web:8083
    reverse_proxy /healthz calibre-web:8083
    reverse_proxy / calibre-web:8083

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        Referrer-Policy "no-referrer"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
    }

    # Structured access logs (stdout)
    log {
        output stdout
        format json
    }
}
```

Notes:
- Caddy sets `X-Forwarded-Proto` and `X-Forwarded-For` automatically.
- If you add more internal endpoints later, append more `reverse_proxy` lines (or collapse to a single `reverse_proxy calibre-web:8083`).

## Start With TLS

From repository root:

```bash
docker compose -f compose.yml -f compose.tls.yml up -d --build
```

Verify status:

```bash
curl -I https://ebooks.example.com/healthz
```
You should receive `HTTP/2 200` (or your route's success code) with a valid certificate.

## Webhook URL Computation

The application already derives the webhook URL using `X-Forwarded-Proto` and `Host`. Once behind Caddy, URLs exposed in the Mozello admin page will show `https://<domain>/mozello/webhook`.

If a forced port was configured earlier (e.g. `forced_port` in MozelloConfig), remove it unless you explicitly need a non-standard port. Default HTTPS (443) does not need to appear in the URL.

## Rollback

If you need to revert temporarily to plain HTTP:

```bash
docker compose -f compose.yml -f compose.tls.yml down
# fall back
docker compose up -d
```

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| Caddy fails to obtain cert | DNS not propagated or port 80 blocked | Confirm A record & firewall, wait a few minutes |
| Browser shows HTTP only | Accessing old IP, or direct port mapping still active | Ensure `calibre-web` has no `ports:` mapping in TLS overlay |
| Webhook still `http://` | Missing `X-Forwarded-Proto` (unlikely with Caddy) | Confirm request flows through Caddy; remove direct container exposure |
| 502 errors from Caddy | App not ready / container name mismatch | Check `docker compose logs caddy calibre-web` |

## Security Hardening (Optional)

- Add rate limiting (Caddy plugin or external) for `/mozello/webhook`.
- Deny large bodies if not needed: `request_body { max_size 2MB }` (requires Caddy 2.7+ module or plugin approach).
- Enable access log sampling for noise reduction if high traffic.
- Implement fail2ban on Caddy logs if brute-force suspected.

## Mozello Registration Reminder

Remember: local configuration does not automatically update Mozello’s remote notification settings unless you build the outbound client. After HTTPS is active, register the URL with Mozello via its dashboard or API (`PUT /store/notifications/`). Use events you enabled in the admin UI.

Example desired remote config:
```json
{
  "notifications_url": "https://ebooks.example.com/mozello/webhook",
  "notifications_wanted": [
    "ORDER_CREATED",
    "PAYMENT_CHANGED",
    "DISPATCH_CHANGED"
  ]
}
```

## Future Enhancements

- Add an outbound sync button to push local event selections to Mozello automatically.
- Store remote sync timestamp & status.
- Add a retention policy for stored webhook debug JSON files.
- Enforce 401 (instead of 400) on signature failures.

## Quick Verification Checklist

- [ ] DNS A record resolves to server IP.
- [ ] Ports 80/443 open & reachable.
- [ ] Caddy container running (`docker ps`).
- [ ] `curl -I https://<domain>/healthz` returns 200 and valid cert.
- [ ] Admin page shows HTTPS webhook URL.
- [ ] Mozello dashboard updated to new HTTPS URL.
- [ ] Manual test: `curl -X POST https://<domain>/mozello/webhook -H 'Content-Type: application/json' -H 'X-Mozello-Test: unsigned' --data '{"event":"PAYMENT_CHANGED"}'` returns `{ "status": "ok" }`.

---
Document version: 2025-10-09

# Migration: App Platform → Droplet (Primary: DOCR-Pulled Images)

Comprehensive guide for moving from DigitalOcean App Platform (or local dev) to a self‑hosted Droplet pulling immutable images from DigitalOcean Container Registry (DOCR). Alternatives (local build / offline transfer) are retained.

AGENTS.md note: All environment-derived settings must be accessed via `app.config.*` (Rule 10). Do not read raw `os.environ` in business logic.

---

## 0. Quick Path (TL;DR – Recommended Option A: DOCR Pull)
```bash
# On fresh Ubuntu 22.04+ Droplet (run as sudo-capable user):
doctl auth init
doctl registry login
sudo apt-get update && sudo apt-get install -y ca-certificates curl gnupg
sudo install -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
 https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
 sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER

git clone https://github.com/<your-org>/ebooks_lv.git /opt/ebooks_lv
cd /opt/ebooks_lv
cp .env.example .env   # set MOZELLO_API_KEY + TZ
docker compose -f compose.yaml -f compose.droplet.yml pull
docker compose -f compose.yaml -f compose.droplet.yml up -d
curl -fsS http://localhost:8083/healthz
```
Enable systemd (optional) for autostart (see §12).

---

## 1. What Changes When Leaving App Platform
You now own:
- Build artifact selection (image tag)
- Runtime uptime & restarts
- TLS / reverse proxy (Caddy / Nginx)
- Secrets delivery (`.env`)
- Backups (config + library)
- Monitoring & logging
- Security hardening

---

## 2. Key Paths
| Purpose | In Container | Recommended Host Path |
|---------|--------------|-----------------------|
| App config & DB (Calibre-Web + custom tables) | /app/config | /opt/calibre/config |
| Library (ebooks + metadata.db) | /app/library | /opt/calibre/library |
| Source checkout (only if local build / reference) | (image FS) | /opt/ebooks_lv |

---

## 3. Provision & Basic Hardening
```bash
adduser deploy
usermod -aG sudo deploy
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```
SSH hardening: disable password + root login in `/etc/ssh/sshd_config`, then:
```bash
sudo systemctl reload sshd
```
(Optional) `sudo apt-get install -y unattended-upgrades`.

---

## 4. Docker & Compose Install (If Not Using Quick Path)
(See TL;DR section – identical commands.)

Relogin to gain `docker` group.

---

## 5. Image Strategy Options
### Option A (Primary) – Pull From DOCR
Pros: reproducible, fast, no compiler toolchain.  
```bash
doctl auth init
doctl registry login
docker pull registry.digitalocean.com/ebookslv-registry/calibre-web-server:latest
```
Compose override already references registry image.

### Option B – Local Build (No Registry Dependency)
Edit service:
```yaml
build:
  context: .
  dockerfile: Dockerfile
image: calibre-web-server:local
```

### Option C – Offline Transfer
```bash
docker save -o calibre.tar registry.digitalocean.com/ebookslv-registry/calibre-web-server:v0.1.0
scp calibre.tar deploy@droplet:~
ssh droplet "docker load -i calibre.tar"
```

---

## 6. Persistent Storage Setup
```bash
sudo mkdir -p /opt/calibre/{config,library}
sudo chown -R $USER:$USER /opt/calibre
```
Migrate existing:
```bash
scp -r ./config deploy@droplet:/opt/calibre/config
scp -r ./library deploy@droplet:/opt/calibre/library
```

---

## 7. Environment / Secrets
`.env.example` provided—copy and edit:
```
MOZELLO_API_KEY=replace_me
TZ=Europe/Riga
```
MOZELLO_API_KEY is seeded once if DB empty (no overwrite). Request a force flag later if rotation needed.

---

## 8. Compose Files Layout
- `compose.yaml`: baseline (prod-safe)
- `compose.dev.yml`: dev overrides (mounts, etc.)
- `compose.droplet.yml`: Droplet runtime (ports, healthcheck, volumes, env)
Run:
```bash
docker compose -f compose.yaml -f compose.droplet.yml up -d
```

Host path variant (edit `compose.droplet.yml`):
```yaml
volumes:
  - /opt/calibre/config:/app/config
  - /opt/calibre/library:/app/library
```

---

## 9. Health Endpoint
`GET /healthz` – lightweight JSON; used by healthcheck. Avoids loading full UI.

Test:
```bash
curl -fsS http://localhost:8083/healthz
```

---

## 10. Verification
```bash
docker compose -f compose.yaml -f compose.droplet.yml ps
docker logs -f calibre-web | grep -i mozello
```
Check seeded key message if first run.

---

## 11. Reverse Proxy & TLS (Recommended)
### Caddy (Auto HTTPS)
`/opt/caddy/Caddyfile`:
```
your.domain.com {
    reverse_proxy calibre-web:8083
}
```
Add Caddy service with ports 80/443 and same Docker network.

### Nginx
Proxy pass to `http://calibre-web:8083` and set:
```
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

If skipping proxy temporarily: map `"80:8083"` (HTTP only).

---

## 12. systemd Autostart (Optional)
File already in repo: `scripts/systemd-calibre-compose.service`.

Install:
```bash
sudo cp scripts/systemd-calibre-compose.service /etc/systemd/system/calibre-compose.service
sudo systemctl daemon-reload
sudo systemctl enable --now calibre-compose
```
Ensure `WorkingDirectory` matches `/opt/ebooks_lv`.

---

## 13. Backups
Nightly cron (config + library):
```bash
0 2 * * * tar czf /opt/backups/cw-config-$(date +\%F).tgz -C /opt/calibre config && \
           tar czf /opt/backups/cw-library-$(date +\%F).tgz -C /opt/calibre library && \
           find /opt/backups -type f -mtime +14 -delete
```
Consider restic/borg for encryption + remote target.

---

## 14. Docker Log Rotation
`/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
```
Then:
```bash
sudo systemctl restart docker
```

---

## 15. Updates & Rollbacks
Update (latest tag):
```bash
docker compose -f compose.yaml -f compose.droplet.yml pull
docker compose -f compose.yaml -f compose.droplet.yml up -d
```
Version pin (recommended):
- Change image tag to `vX.Y.Z`
- Pull + up

Rollback:
1. Pick prior tag (e.g., `v0.1.0`)
2. Edit override file
3. `docker compose -f compose.yaml -f compose.droplet.yml up -d`
4. If corruption suspected: restore `/opt/calibre/config` backup before step 3.

---

## 16. Security Hardening Ideas
| Measure | Benefit | Notes |
|---------|---------|-------|
| Reverse proxy TLS | Encrypt traffic | Caddy simplest |
| Read-only root FS | Reduce mutation surface | Needs tmpfs /tmp |
| Non-root user | Contained impact | Already applied |
| no-new-privileges | Prevent escalation | In compose security_opt |
| Signed images (cosign) | Supply chain integrity | Future enhancement |
| Fail2ban / SSH limits | Brute force mitigation | Optional |

---

## 17. Operational Checklist
| Step | Done |
|------|------|
| Droplet hardened | ☐ |
| Docker + compose installed | ☐ |
| Data migrated | ☐ |
| `.env` created | ☐ |
| Compose up | ☐ |
| Healthz OK | ☐ |
| TLS proxy active | ☐ |
| Backups scheduled | ☐ |
| Update strategy documented | ☐ |
| Rollback tested | ☐ |

---

## 18. Troubleshooting Table
| Symptom | Action |
|---------|--------|
| Healthcheck failing | `docker logs calibre-web`; curl `/healthz` |
| API key missing | Confirm `.env` loaded; first-run seeding logged |
| 502 behind proxy | Network / container name mismatch |
| Port conflict | `ss -tlnp | grep 8083` or mapping to 80 |
| Slow first load | Library scan / dependency cold start |
| Unexpected overwrite fears | Validate volume paths (no ephemeral) |

---

## 19. Why Keep DOCR (Recap)
- Immutable & reproducible artifacts
- Fast deploy / rollback
- Central vulnerability scanning potential
- Multi-arch capability
- Reduced host complexity (no build toolchain)

---

## 20. Future Enhancements
| Feature | Value |
|---------|-------|
| GitHub Actions tag build | Automated pipeline |
| Image digest pinning | Strong provenance |
| `/version` endpoint | Runtime traceability |
| Forced API key rotation flag | Secret hygiene |
| SBOM + signing | Supply chain security |

---

_Last updated: 2025-10-01_
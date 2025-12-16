# Log retention / disk growth guardrails

Goal: prevent any log source (Calibre-Web, this app, Caddy, Docker) from growing without bounds over months/years.

## What was changed

### Docker container logs (stdout/stderr)

All long-running services now have bounded Docker `json-file` logs:

- `max-size: 10m`
- `max-file: 10`

Worst-case disk use from Docker logs is therefore ~100 MiB per container.

Where configured:

- [compose.yml](../compose.yml)
- [compose.dev.yml](../compose.dev.yml)
- [compose.droplet.yml](../compose.droplet.yml)
- [compose.droplet.caddy-http.yml](../compose.droplet.caddy-http.yml)
- [compose.droplet.caddy-https.yml](../compose.droplet.caddy-https.yml)

This covers:

- Caddy access logs (currently `output stdout` + JSON format)
- Gunicorn logs
- Any Python `StreamHandler` logs from the `app` package

### Calibre-Web file logs in `/app/config`

Calibre-Web itself uses `RotatingFileHandler` for `calibre-web.log` and `access.log` under its config dir (`/app/config`):

- main log: `maxBytes=100000`, `backupCount=2`
- access log: `maxBytes=50000`, `backupCount=2`

So file logs inside the config volume are already bounded and will not grow indefinitely.

## Droplet host (recommended)

Even with Docker log limits, the host can still accumulate:

- `systemd-journald` logs
- apt logs

On Ubuntu droplets, you can add a small periodic cleanup.

### Option A: one-off cleanup

- Limit journal by time: `sudo journalctl --vacuum-time=30d`
- Or limit by size: `sudo journalctl --vacuum-size=500M`

### Option B: cron/timer cleanup

Use the helper script:

- [scripts/droplet_logs_vacuum.sh](../scripts/droplet_logs_vacuum.sh)

Example (weekly):

```bash
sudo crontab -e
# add:
0 3 * * 0 /opt/calibre/ebooks_lv/scripts/droplet_logs_vacuum.sh
```

Adjust the path to wherever you deploy the repo.

## How to verify disk is stable

### Docker

- Disk usage summary: `docker system df`
- Container log size (per container):

```bash
docker inspect --format='{{.Name}} -> {{.LogPath}}' calibre-web
sudo du -h "$(docker inspect --format='{{.LogPath}}' calibre-web)"
```

### Droplet host

- Journal usage: `sudo journalctl --disk-usage`
- Biggest directories: `sudo du -xh /var | sort -h | tail -n 20`


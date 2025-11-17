# scripts directory

This folder contains operational helper scripts for deploying and maintaining the ebooks_lv droplet installation. All scripts require Bash; invoke them with `bash script_name` (or `sudo bash ...` when running as root) because `/bin/sh` on Ubuntu/Debian lacks the features they rely on.

Scripts:
- ebooks_lv_init.sh: One-time (idempotent) initializer. Creates /opt/calibre/{config,library}, migrates existing repo library (metadata.db) to /opt/calibre/library (Option A), fixes ownership (UID 1000), ensures .env exists. Safe to re-run if it failed partway.
- ebooks_lv_setup.sh: Re-runnable update/start script. Pulls latest code, prompts/updates env vars, pulls images, (re)starts stack. Use this for regular updates after init. The droplet compose overlay now includes an HTTPS-enabled Caddy proxy, so make sure DNS for `EBOOKSLV_DOMAIN` points at the droplet before running.

Future scripts (ideas):
- upgrade.sh to pull latest git changes & re-run setup.

## Manual bootstrap on a fresh droplet (private repo, logged in as root)

Follow these steps after creating a Droplet with the Docker image from DigitalOcean Marketplace.

1) Create a non-root user for operations and allow Docker access

```bash
id deploy || adduser deploy
usermod -aG docker deploy
chown -R deploy:deploy /home/deploy
su - deploy -c 'mkdir -p ~/.docker && chmod 700 ~/.docker'
```

2) Log in to DigitalOcean (required — registry is private)

Prefer environment-based auth to avoid doctl writing to root’s home. This step is mandatory because the image registry is private.

```bash
# As root or as deploy
export DIGITALOCEAN_ACCESS_TOKEN='paste_do_token_here'

# Install doctl via Snap (as root), then allow Docker access
sudo snap install doctl
sudo snap connect doctl:dot-docker

# Alternatively install doctl binary (avoids snap confinement):
# DOCTL_VERSION=1.111.0
# curl -fsSL https://github.com/digitalocean/doctl/releases/download/v${DOCTL_VERSION}/doctl-${DOCTL_VERSION}-linux-amd64.tar.gz \
#   | tar -xz -C /usr/local/bin doctl

sudo -iu deploy env DIGITALOCEAN_ACCESS_TOKEN="$DIGITALOCEAN_ACCESS_TOKEN" doctl account get
sudo -iu deploy env DIGITALOCEAN_ACCESS_TOKEN="$DIGITALOCEAN_ACCESS_TOKEN" doctl registry login
```

3) Prepare GitHub access (private repo) using a fine-grained PAT

Create a fine-grained Personal Access Token with Repository contents: Read for this repo only. Use Git credential-store (persistent, scoped to github.com).

```bash
# Run as deploy user (robust flow using git credential approve)
sudo -iu deploy bash -lc '
	set -e
	mkdir -p ~/.config/git; chmod 700 ~/.config/git;
	git config --global credential.helper "store --file ~/.config/git/credentials";
	read -s -p "GitHub PAT (contents:read): " GH_TOKEN; echo;
	printf "protocol=https\nhost=github.com\nusername=x-access-token\npassword=%s\n" "$GH_TOKEN" | git credential approve;
	unset GH_TOKEN;
	chmod 600 ~/.config/git/credentials;
	# Optional: verify stored creds (should print username/password lines)
	printf "protocol=https\nhost=github.com\n" | git credential fill | grep -E "^(username|password)=" || true
'
```



4) Clone the repo (with submodules) to /opt/ebooks_lv

```bash
sudo install -d -o deploy -g deploy -m 755 /opt/ebooks_lv
sudo -iu deploy git clone --recurse-submodules https://github.com/parakletos-lab/ebooks_lv.git /opt/ebooks_lv
```

5) Run the init script (does not start containers yet)

```bash
sudo bash /opt/ebooks_lv/scripts/ebooks_lv_init.sh
```

If you had an existing library under /opt/ebooks_lv/library with metadata.db, it is migrated to /opt/calibre/library during init (only if target is empty).

6) Run the setup script to pull images and start

```bash
sudo bash /opt/ebooks_lv/scripts/ebooks_lv_setup.sh
```

Before running setup, confirm the DNS A record for your `EBOOKSLV_DOMAIN` resolves to the droplet public IP and that inbound TCP ports 80/443 are open. The droplet compose overlay starts a Caddy proxy that terminates HTTPS, provisions/renews certificates via Let's Encrypt automatically, and forwards traffic to the internal `calibre-web` container on port 8083.

If you see "command not found" or interpreter errors for either script:
- Ensure it’s executable and not CRLF:
	```bash
	sudo chmod +x /opt/ebooks_lv/scripts/ebooks_lv_setup.sh
	sudo sed -i 's/\r$//' /opt/ebooks_lv/scripts/ebooks_lv_setup.sh
	sudo bash /opt/ebooks_lv/scripts/ebooks_lv_setup.sh
	```

If the setup reports "Missing required binary: docker compose" or similar:
- Install the Compose plugin (preferred on Ubuntu 22.04+):
	```bash
	sudo apt-get update
	sudo apt-get install -y docker-compose-plugin
	```
- Or install the legacy docker-compose binary:
	```bash
	VER="v2.27.0"; sudo curl -L "https://github.com/docker/compose/releases/download/${VER}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
	sudo chmod +x /usr/local/bin/docker-compose
	```

Init (ebooks_lv_init.sh) does:
- Ensures docker + compose + git available
- Creates /opt/calibre/config and /opt/calibre/library
- Migrates legacy /opt/ebooks_lv/library (if metadata.db present and destination empty)
- Fixes ownership to UID:GID 1000:1000
- Creates .env if missing
- Prompts for timezone (TZ) and `EBOOKSLV_DOMAIN` so HTTPS can be configured automatically

Setup (ebooks_lv_setup.sh) does each run:
- Ensures docker + compose + git available
- Updates code (git fetch/pull, submodules)
- Prompts / updates TZ (and future env vars)
- Pulls images and starts stack (compose.yml + compose.droplet.yml)

Mozello store configuration (store URL and API key) is now managed inside the Calibre-Web admin UI under “Mozello Settings”.
Optional: define `MOZELLO_STORE_URL` in the environment or `.env` file to seed the initial value into `config/users_books.db` (skipped if already present).

Re-run setup anytime after changing env vars or after publishing a new image tag.

7) Security notes

- Do not commit .env to git. If it’s tracked, remove and ignore:
	```bash
	cd /opt/ebooks_lv
	git rm --cached .env || true
	echo ".env" >> .gitignore
	git commit -m "Stop tracking .env"
	```
- Consider deleting /home/deploy/.netrc after cloning if you prefer immutable deployments (you’ll need to recreate or use a PAT again to pull updates):
	```bash
	sudo -iu deploy shred -u ~/.netrc
	```

8) Troubleshooting

- doctl “permission denied” writing ~/.docker: ensure the directory exists and is owned by deploy:
	```bash
	sudo -iu deploy mkdir -p ~/.docker && chmod 700 ~/.docker
	```
- Snap doctl can’t access Docker: connect plug
	```bash
	sudo snap connect doctl:dot-docker
	```
- Use `doctl` binary instead of Snap to avoid confinement (see step 2).

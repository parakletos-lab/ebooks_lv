# scripts directory

This folder contains operational helper scripts for deploying and maintaining the ebooks_lv droplet installation.

Scripts:
- ebooks_lv_setup.sh: Interactive, idempotent setup script executed after the droplet bootstrap. Prompts for required environment variables, ensures compose dependencies, pulls images, and starts the stack. Safe to re-run when new env vars are introduced.

Future scripts (ideas):
- upgrade.sh to pull latest git changes & re-run setup.
- rotate_key.sh to rotate MOZELLO_API_KEY if needed.

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

5) Run the setup script to configure env and start (you can run as root)

```bash
sudo bash /opt/ebooks_lv/scripts/ebooks_lv_setup.sh
```

If you see "command not found" or interpreter errors:
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

What this script does each run:
- Ensures docker/docker compose/git are available
- Updates code: git fetch/pull; syncs and updates submodules
- Creates/updates /opt/ebooks_lv/.env and prompts for required variables
- Pulls images and starts the stack via compose.yml + compose.droplet.yml

Re-run the same script anytime to update code and restart the stack.

6) Security notes

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

7) Troubleshooting

- doctl “permission denied” writing ~/.docker: ensure the directory exists and is owned by deploy:
	```bash
	sudo -iu deploy mkdir -p ~/.docker && chmod 700 ~/.docker
	```
- Snap doctl can’t access Docker: connect plug
	```bash
	sudo snap connect doctl:dot-docker
	```
- Use `doctl` binary instead of Snap to avoid confinement (see step 2).

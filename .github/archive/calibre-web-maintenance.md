# 1. (If this repo is not yet a git repository)
git init

# 2. Add the Calibre-Web upstream project as a submodule in directory "calibre-web"
# (Default: tracks the default branch of upstream, usually master or main)
git submodule add https://github.com/janeczku/calibre-web.git calibre-web

# 3. Initialize and fetch the submodule contents (if not already done automatically)
git submodule update --init --recursive

# 4. (Optional) Checkout a specific tagged release or commit to pin version
cd calibre-web
# List tags (optional)
git tag --list | sort -V | tail -n 10
# Example: checkout a specific release tag (replace with real tag)
git checkout v0.6.22
cd ..

# 5. Stage submodule reference + .gitmodules file
git add .gitmodules calibre-web

# 6. Commit the pinned submodule state
git commit -m "Add calibre-web upstream submodule (pinned to v0.6.22)"

# 7. (Optional) Push to your remote
git remote add origin <YOUR_REMOTE_URL>
git push -u origin main

# ------------------------------------------------------------------
# Updating the submodule later (to latest upstream default branch)
# ------------------------------------------------------------------
# Fetch latest upstream changes
cd calibre-web
git fetch origin
# Switch to upstream default branch (main or master depending on project)
git checkout master  # or: git checkout main
git pull
cd ..

# Stage the new submodule pointer and commit
git add calibre-web
git commit -m "Update calibre-web submodule to latest master"

# ------------------------------------------------------------------
# Alternative: one-liner to update to latest remote commit on tracked branch
# ------------------------------------------------------------------
git submodule update --remote calibre-web
git add calibre-web
git commit -m "Update calibre-web submodule (remote tracking)"

# ------------------------------------------------------------------
# Inspect submodule status (shows SHA & cleanliness)
# ------------------------------------------------------------------
git submodule status

# ------------------------------------------------------------------
# Cloning your repo elsewhere with submodule
# ------------------------------------------------------------------
git clone <YOUR_REPO_URL> calibre-web-server
cd calibre-web-server
git submodule update --init --recursive

# ------------------------------------------------------------------
# Pinning to a specific commit (instead of tag)
# ------------------------------------------------------------------
cd calibre-web
git checkout <commit_sha>
cd ..
git add calibre-web
git commit -m "Pin calibre-web to commit <commit_sha>"

# ------------------------------------------------------------------
# Shallow clone the submodule (optional optimization)
# (Requires newer Git versions; depth disables deep history)
# ------------------------------------------------------------------
git submodule add --depth 1 https://github.com/janeczku/calibre-web.git calibre-web
# If you later need full history inside the submodule:
cd calibre-web
git fetch --unshallow
cd ..

# ------------------------------------------------------------------
# Removing the submodule (if needed)
# ------------------------------------------------------------------
git submodule deinit -f calibre-web
rm -rf .git/modules/calibre-web
git rm -f calibre-web
git commit -m "Remove calibre-web submodule"

# ------------------------------------------------------------------
# Scriptable update (example helper you could store in scripts/update_upstream.sh)
# ------------------------------------------------------------------
# #!/usr/bin/env bash
# set -euo pipefail
# echo "[INFO] Updating calibre-web submodule..."
# git submodule update --remote calibre-web
# echo "[INFO] New pointer:"
# git -C calibre-web log -1 --oneline
# git add calibre-web
# git commit -m "Update calibre-web submodule"
# echo "[INFO] Done."

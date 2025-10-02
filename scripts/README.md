# scripts directory

This folder contains operational helper scripts for deploying and maintaining the ebooks_lv droplet installation.

Scripts:
- ebooks_lv_setup.sh: Interactive, idempotent setup script executed after the droplet bootstrap. Prompts for required environment variables, ensures compose dependencies, pulls images, and starts the stack. Safe to re-run when new env vars are introduced.

Future scripts (ideas):
- upgrade.sh to pull latest git changes & re-run setup.
- rotate_key.sh to rotate MOZELLO_API_KEY if needed.

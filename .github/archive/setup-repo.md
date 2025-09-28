# Calibre-Web Wrapper + Plugin Docker Setup

## Goal
- Keep plugin in a separate repository.
- Calibre-Web repo as a submodule.
- Initialize plugin before starting Calibre-Web.
- Dockerized for easy deployment and development.
- Safe for upgrades and minimal core changes.

---

## 1️⃣ Initial Repository Setup

```bash
# Create main repo
mkdir e-books && cd e-books
git init

# Add Calibre-Web as submodule
git submodule add https://github.com/janeczku/calibre-web.git calibre-web

# Add plugin folder
mkdir e-books_plugin
mkdir server_wrapper

# Commit initial structure
git add .
git commit -m "Initial repo structure with Calibre-Web submodule, plugin, and wrapper"
```

**Directory Structure:**
```
e-books/
  server_wrapper/
  e-books_plugin/
  calibre-web/  (submodule)
```

---

## 2️⃣ Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --upgrade pip
RUN pip install -r calibre-web/requirements.txt
EXPOSE 8083
CMD ["python", "entrypoint/entrypoint_mainwrap.py"]
```

---

## 3️⃣ Interception Entrypoint `entrypoint_mainwrap.py`

```python
import sys
import os

# Add plugin path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../e-books_plugin"))
import my_plugin

# Add Calibre-Web path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../calibre-web"))
from cps.__init__ import app

# Initialize plugin
my_plugin.init_app(app)

# Start server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8083)
```

---

## 4️⃣ Docker Compose

```yaml
version: "3.9"
services:
  calibre-web:
    build: .
    container_name: calibre_web
    ports:
      - "8083:8083"
    volumes:
      - ./calibre-web/config:/app/config
      - ./e-books_plugin:/app/e-books_plugin
      - ./server_wrapper:/app/server_wrapper
      - ./data:/app/data
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/Riga
    restart: unless-stopped
```

---

## 5️⃣ Calibre-Web Upgrade Scripts

### Pull updates for Calibre-Web submodule
```bash
cd calibre-web
git fetch origin
git checkout main
git pull
cd ..
```

### Rebuild Docker image and restart
```bash
docker-compose build
docker-compose up -d
```

- This ensures plugin integration remains intact.
- Wrapper script automatically initializes the plugin on startup.

---

## 6️⃣ Benefits
- Plugin is fully separate from Calibre-Web core.
- Wrapper manages plugin initialization before server start.
- Safe upgrades for Calibre-Web via submodule.
- Dockerized deployment and easy development.
- Supports multiple plugins in the future.

---

## 7️⃣ Notes
- Plugin templates, routes, and hooks live entirely in `e-books_plugin/`.
- Admin pages and hooks are initialized via `e-books_plugin.init_app(app)`.
- Volumes in Docker Compose allow live development and persistent config/library data.

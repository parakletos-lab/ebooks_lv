# E2E: Login secondary button is outlined

## Goal
Ensure that on the login page (and login reset variant) the secondary action renders as an outlined button (bordered), not a plain text link, and that there is spacing between primary and secondary actions.

## Preconditions
- Local dev stack is running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Use any locale.

## Steps
### 1) Standard login form
1. Open `http://localhost:8083/login`.
2. Locate the actions row under the form.

**Expected**
- The primary action is a filled button (e.g. “Pieteikties”).
- The secondary action (e.g. “Aizmirsi paroli?”) is a bordered button.
- There is visible horizontal space between the two buttons.

### 2) Secure-link / password update variant
1. Generate a valid initial token in the container (uses Calibre-Web secret key):

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python - <<'PY'
import os
import sys

for p in ('/app', '/app/calibre-web'):
    if p not in sys.path:
        sys.path.insert(0, p)

from cps import ub, config_sql  # type: ignore
ub.app_DB_path = os.path.join(os.environ.get('CALIBRE_DBPATH') or '/app/config', 'app.db')
session = ub.init_db_thread()
secret = os.environ.get('SECRET_KEY') or config_sql.get_flask_session_key(session)

from flask import Flask
from app.services import password_reset_service

app = Flask('token_gen')
app.config['SECRET_KEY'] = secret

with app.app_context():
    print(password_reset_service.issue_initial_token(
        email='qa_user@example.test',
        temp_password='TempPass123!',
    ))
PY
```

2. Open `http://localhost:8083/login?email=qa_user%40example.test&auth=<TOKEN>`.

**Expected**
- The secondary action “Atcelt” is a bordered button.
- There is visible horizontal space between “Saglabāt paroli” and “Atcelt”.

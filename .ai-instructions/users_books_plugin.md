# Calibre-Web Hybrid Plugin as Separate Repository

## Goal
- Keep plugin in a separate repository to maintain independence.
- Filter books per user using a separate DB (`user_filters.db`).
- Preserve Calibre-Web bookmarks.
- Admin users bypass filtering.
- Minimal changes to Calibre-Web core code.

---

## 1️⃣ Repository Structure

```
calibre-web/                  # Main Calibre-Web repo
  cps/
  my_plugin/                  # Git submodule (plugin repo)
    __init__.py
    filter_hook.py
    models.py
```

---

## 2️⃣ Add Plugin as Git Submodule

```bash
cd calibre-web
git submodule add https://github.com/yourname/my_plugin.git my_plugin
git submodule update --init --recursive
```

---

## 3️⃣ Plugin Repository (`my_plugin`)

**`__init__.py`**
```python
from .filter_hook import attach_hook

def init_app(app):
    """
    Initialize the plugin:
    - attach the SQLAlchemy filtering hook
    """
    attach_hook()
```

**`filter_hook.py`**
```python
from flask import session
from sqlalchemy.orm import Query
from cps.models import Books
from .models import PluginSession, UserFilter

def filter_books(query):
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)

    if user_id is None or is_admin:
        return query

    with PluginSession() as s:
        allowed_book_ids = [f.book_id for f in s.query(UserFilter).filter_by(user_id=user_id)]

    if not allowed_book_ids:
        return query.filter(False)

    return query.filter(Books.id.in_(allowed_book_ids))

def attach_hook():
    from sqlalchemy import event
    from sqlalchemy.orm import Query
    event.listen(Query, "before_compile", lambda q: filter_books(q))
```

**`models.py`**
```python
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class UserFilter(Base):
    __tablename__ = "user_filters"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    book_id = Column(Integer, nullable=False)

plugin_engine = create_engine("sqlite:///user_filters.db")
PluginSession = sessionmaker(bind=plugin_engine)
Base.metadata.create_all(plugin_engine)
```

---

## 4️⃣ Minimal Integration in Calibre-Web

Add to `cps/__init__.py`:
```python
try:
    import my_plugin
    my_plugin.init_app(app)  # attach filtering hook
except ImportError:
    pass
```

- Only one line of integration.
- Admin bypass handled in plugin.
- Core code untouched.

---

## 5️⃣ Updating Workflow

1. **Update Calibre-Web**:
```bash
cd calibre-web
git fetch upstream
git merge upstream/develop
```

2. **Update Plugin Submodule**:
```bash
cd my_plugin
git fetch origin
git checkout main
git pull
cd ..
git add my_plugin
git commit -m "Update plugin submodule"
```

- Plugin and Calibre-Web can be updated independently.

---

## 6️⃣ Benefits
- Clean separation between Calibre-Web and plugin.
- Safe upgrades of Calibre-Web.
- Minimal maintenance.
- All filtering logic contained in plugin repo.

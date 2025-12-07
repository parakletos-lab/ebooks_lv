# Translation Packs

This folder stores all first-party translation catalogs outside of the vendored
`calibre-web/` tree. Each subdirectory represents a translation root that is
appended to Flask-Babel's `BABEL_TRANSLATION_DIRECTORIES` during startup.

- `calibre-web/` – strings intended for upstream Calibre-Web contribution. Only
  stock UI strings should live here.
- `ebookslv/` – ebooks.lv specific UI strings (admin pages, login override,
  Mozello tooling, etc.).

To add or update translations:

1. Edit the relevant `messages.po` file under the desired root/locale.
2. Compile it with `msgfmt` so that `messages.mo` stays in sync, e.g.:
   `msgfmt translations/ebookslv/lv/LC_MESSAGES/messages.po -o translations/ebookslv/lv/LC_MESSAGES/messages.mo`
3. Restart the application (or reload the WSGI server) so Babel picks up the
   updated catalog.

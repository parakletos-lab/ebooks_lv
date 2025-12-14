Automated DOM assertion (manual run steps until MCP scripted):
1. Navigate to http://localhost:8083
2. Login with admin credentials (admin / admin123)
3. Ensure element with id 'top_admin' exists.
4. Assert element with id 'top_users_books' exists (ebooks.lv hub link).
5. Assert element with id 'top_orders' exists.
6. Navigate to `/admin/ebookslv/` and ensure a Mozello card/link to `/admin/mozello/` exists.
7. If missing, open console and check for injection debug logs (search for 'nav injected').

Notes:
- `#top_users_books` is a legacy id kept for compatibility; it now links to `/admin/ebookslv/`.

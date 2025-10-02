Automated DOM assertion (manual run steps until MCP scripted):
1. Navigate to http://localhost:8083
2. Login with admin credentials (admin / admin123)
3. Ensure element with id 'top_admin' exists.
4. Assert element with id 'top_users_books' exists (in DOM after load ~1s).
5. If missing, open console and check for JS injection errors containing 'users_books'.

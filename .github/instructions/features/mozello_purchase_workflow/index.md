# Mozello Purchase Workflow – Implementation Index

- Update the status column as each sub-task is finished. When all rows reach **Completed**, close the feature.
- Work only on one sub-task at a time in order.
- Make sure all implemented previous sub-task aligned at current working task.
- After tests do review and cleanup, mark sub-task as completed. (will commit manually after)

For tests:
- Use scripts/dev_rebuild.sh
- Check docker logs if needed
- Use Playwright MCP for in browser functionality tests
- Use admin user credentials: admin/admin123

| Task ID | Description | Status | Details |
| --- | --- | --- | --- |
| T1 | Data & credential storage foundations | Completed | See `sub_tasks.md#t1-data-credential-storage-foundations` (commit `aa8f5db`) |
| T2 | Auth link & password-reset services | Not Started | See `sub_tasks.md#t2-auth-link-and-password-reset-services` |
| T3 | Email template & subject editor upgrades | Not Started | See `sub_tasks.md#t3-email-template-and-subject-editor-upgrades` |
| T4 | Mozello webhook + email dispatch workflow | Not Started | See `sub_tasks.md#t4-mozello-webhook-and-email-dispatch-workflow` |
| T5 | Login override UX & session handling | Not Started | See `sub_tasks.md#t5-login-override-ux-and-session-handling` |
| T6 | Documentation & automated tests | Not Started | See `sub_tasks.md#t6-documentation-and-automated-tests` |

**Reminder:** Mark a task as Completed only after its code, tests, and docs have landed on the feature branch.

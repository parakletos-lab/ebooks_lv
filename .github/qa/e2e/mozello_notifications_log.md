# e2e: Mozello Notifications Log

## Goal
Verify Mozello webhook notifications logging can be toggled and cleared on `/admin/mozello/`.

## Preconditions
- App running locally (recommended: `bash .github/qa/scripts/run_all.sh`).
- Admin credentials available (default from QA bootstrap): `admin / AdminTest123!`.

## Steps
1. Login as admin.
2. Open `/admin/mozello/`.
3. In **Mozello Notification Settings** find **Notifications Log**.
4. Ensure the **power** button next to **Notifications Log** is OFF (grey).
5. Click **Post Test (unsigned)**.
   - Expect: log table stays empty (no new row).
6. Turn logging ON using the **power** button (it becomes red).
7. Click **Post Test (unsigned)** again.
   - Expect: a new row appears in the log table with event `PAYMENT_CHANGED` and an outcome (likely rejected due to missing required order fields).
   - Optional: click the **JSON open** icon in the row to open formatted JSON in a new tab.
8. Click **Clear**.
   - Expect: log table becomes empty.
9. Turn logging OFF (power button grey) and repeat step 7.
   - Expect: no new rows are added.

## Notes
- The test POST is intentionally unsigned and uses a minimal payload; it may be rejected by order validation, but it should still appear in the log when logging is enabled.

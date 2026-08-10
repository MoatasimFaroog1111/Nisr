# Nisr v0.5.0 — Durable Production Sessions

## What is durable

Agent state remains persisted through `SessionStorePort`. Browser state now has a separate `BrowserSessionStorePort` and a `BrowserSessionSnapshot` domain model. The default adapter stores browser snapshots in SQLite.

A browser snapshot contains only recoverable operational state:

- session/user/task identity
- browser owner and control state
- takeover status/reason
- current URL
- tab URLs/titles/active tab
- Playwright storage state (cookies + localStorage)
- expiry and recovery metadata

It never serializes Playwright/browser-process objects, frames, page text, form field values, passwords, OTP values, or card values into audit logs.

## Restart recovery

When a new process receives the same authenticated session:

1. `DurableBrowserManager` loads the logical snapshot.
2. User ownership is verified before recovery.
3. `ReliablePlaywrightBrowserProvider` creates a new Chromium context.
4. Playwright storage state restores cookies and localStorage.
5. Known tabs/URLs are reopened and the active tab is selected.
6. Control ownership and task binding are restored.
7. Browser state is marked with `recovered_after_restart=true` and `browser_state_changed=true`.

The agent is never told that recovery was bit-for-bit exact.

## Explicit limitations

Playwright `storage_state` does not provide a general exact restoration of browser `sessionStorage` or the full navigation-history stack. Nisr therefore reports:

- `session_storage_restored=false`
- `exact_history_restored=false`

A recovered browser may have the same authenticated cookies/localStorage and URLs while still representing a newly created Chromium context.

## Railway requirement

For recovery across a Railway container replacement or redeploy, the SQLite path must be on a Railway persistent Volume. Configure `AGENT_SESSION_DB` and `AGENT_BROWSER_SESSION_DB` to paths on that Volume. The default browser-session DB is the same path as `AGENT_SESSION_DB`.

A stable `AGENT_BROWSER_SESSION_SECRET` (or stable non-placeholder `AGENT_APPROVAL_SECRET`, which is used as fallback) is also required for existing browser tokens to survive a process restart.

## Security

Browser storage state can contain authentication cookies or localStorage tokens. It is operational persistence, not an audit log. The SQLite file is created with owner-only filesystem permissions where supported and must live on a private application Volume. Never publish or attach this database as an artifact.

Expired sessions are purged according to `AGENT_BROWSER_SESSION_TIMEOUT_SECONDS`. Explicit browser close deletes the durable browser snapshot; normal process shutdown closes Chromium runtime objects but intentionally keeps non-expired snapshots for recovery.

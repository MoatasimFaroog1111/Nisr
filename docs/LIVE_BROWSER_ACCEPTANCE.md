# Live Browser / User Takeover Acceptance

This checklist maps the v0.4 live-computer feature to executable architecture and tests.

1. User sends a browsing objective: UI creates a lightweight browser session and passes the same session id to `/run`.
2. Agent creates Chromium lazily: `browser.*` Tool Registry entry -> `BrowserService` -> `BrowserProvider` -> `PlaywrightBrowserProvider`.
3. Computer Panel is visible beside Chat.
4. Browser frames stream over authenticated WebSocket while the agent works.
5. Agent browser actions publish user-facing action/status events.
6. Sensitive credential/OTP/payment/CAPTCHA signals produce `user_takeover_requested`.
7. Agent state becomes `WAITING_USER` rather than bypassing protection.
8. User presses Take Control; session ownership becomes `USER_CONTROL`.
9. Agent browser calls while user owns the session return `BROWSER_CONTROLLED_BY_USER`.
10. User interacts with the same Chromium context using frame clicks, scroll, keyboard, private text, URL navigation and tabs.
11. Cookies, localStorage, sessionStorage, URL and tabs stay in the same browser context during takeover.
12. User presses Return Control to Agent.
13. Backend captures current URL/tabs/browser state and appends a `browser.userObservation` to the same AgentState.
14. Orchestrator resumes the same task/session; it does not restart the objective.
15. Computer Panel remains connected through the transition.
16. Per-session lock and owner state prevent concurrent agent/user actions.
17. Browser contexts are isolated by session/user id and protected by short-lived bound tokens.
18. Browser input values, credentials, OTPs and payment text are redacted or bypass audit/state persistence; browser frame payloads are not audit logged.
19. WebSocket disconnect does not close Chromium; inactivity timeout performs cleanup.
20. Browser process loss emits `browser.error`; potentially state-changing actions are not blindly retried.

Primary automated coverage:

- `tests/test_browser_takeover.py`
- `tests/test_browser_realtime_api.py`
- `tests/test_waiting_user.py`
- `tests/test_runtime_hardening.py`
- `tests/test_ui.py`
- `tests/test_architecture.py`

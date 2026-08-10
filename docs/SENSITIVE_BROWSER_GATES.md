# Sensitive Browser Gates

Nisr v0.4.3 treats CAPTCHA, login credentials, OTP/2FA, payment/card entry, banking authentication, identity/security verification and similar browser states as mandatory user-interaction gates.

## Invariant

An agent browser action may not lead directly to task completion when the authoritative browser observation contains sensitive signals.

The browser tool boundary refreshes browser state after every agent action. If a sensitive signal is present it returns `waiting_user=true`, emits a user-takeover request through Browser Service, and redacts page text/interactables from the agent observation.

## Resume rule

`Return Control to Agent` does not resume the agent merely because ownership changed. The current browser observation must first have an empty `sensitive_signals` list. If the gate is still present, the same task remains `WAITING_USER` and the same browser session is preserved.

Expected lifecycle:

```text
RUNNING
  -> browser action
  -> sensitive gate detected
  -> WAITING_USER
  -> USER_CONTROL
  -> user completes verification
  -> Return Control
  -> browser state re-read
  -> gate clear
  -> RECOVERY/RUNNING
```

No credential, OTP, card value or sensitive page text is added to the agent observation or audit stream by this gate.

# Nisr v0.4.3

Sensitive Browser Gate Hardening.

- Authoritative browser-state refresh after every agent browser action.
- CAPTCHA/login/OTP/2FA/payment/security signals force `WAITING_USER`.
- Sensitive page text and interactables remain redacted from agent observations.
- Returning browser control does not resume the task while a sensitive gate remains visible.
- Same browser session and task state are preserved until the user completes the sensitive step.

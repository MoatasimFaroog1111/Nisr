# Security model

- Catastrophic shell patterns are blocked.
- Mutating file, Git, GitHub, database, browser-interaction, and deployment operations are approval-gated.
- Approval tokens are scoped to the exact action payload and expire.
- Runtime-level approval tokens are checked by the approval manager; they do not need to be included in model context.
- Audit events redact common secret/token/password fields.
- Database `query` accepts only SQL classified as read-only.
- File tools constrain paths to the configured workspace.
- Web fetch accepts HTTP(S) URLs only.

This is defense-in-depth, not a full OS sandbox. Production deployments should additionally run the agent with least-privilege OS/container credentials, network egress policy, secret storage, and isolated workspaces.

# Security model

- `RiskPolicy` is pure domain logic and classifies shell, file-write, and SQL operations.
- Mutating adapters call `ApprovalPort`; the application layer does not know HMAC or SQLite approval details.
- `ApprovalService` composes `SqliteApprovalRepository` and `HmacApprovalTokenService`, separating persistence from token cryptography and authorization policy.
- Approval tokens are scoped to the exact canonicalized action payload and expire.
- Audit adapters redact token/password/secret/API-key fields before persistence.
- Workspace file tools reject paths outside the configured workspace.
- Read-only SQL is separated from mutation execution, and database technology is selected by the composition root.

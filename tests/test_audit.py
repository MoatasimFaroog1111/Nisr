from adapters.storage.audit_jsonl import JsonlAuditAdapter

def test_audit_redacts_secrets(tmp_path):
    audit = JsonlAuditAdapter(tmp_path / "audit.jsonl")
    audit.record("x", data={"approval_token": "abc", "nested": {"password": "pw"}})
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "abc" not in text and "pw" not in text and "REDACTED" in text

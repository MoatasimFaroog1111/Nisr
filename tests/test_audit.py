from super_agent.core.audit import AuditLog

def test_audit_redacts_tokens(tmp_path):
    log=AuditLog(tmp_path/'audit.jsonl'); log.record('x',data={'approval_token':'abc','nested':{'password':'pw'}})
    text=(tmp_path/'audit.jsonl').read_text(); assert 'abc' not in text and 'pw' not in text and 'REDACTED' in text

from super_agent.core.approvals import ApprovalManager
from super_agent.models import RiskLevel

def test_approval_token_is_action_scoped(tmp_path):
    m=ApprovalManager(tmp_path/'a.sqlite3','secret')
    payload={'path':'x.txt'}; req=m.request('file_write',payload,RiskLevel.MEDIUM); token=m.approve(req['request_id'])
    assert m.verify(token,'file_write',payload)
    assert not m.verify(token,'file_write',{'path':'y.txt'})


def test_approved_token_can_be_supplied_at_runtime_level(tmp_path):
    m=ApprovalManager(tmp_path/'b.sqlite3','secret')
    payload={'operation':'x'}
    req=m.request('deployment',payload,RiskLevel.MEDIUM)
    token=m.approve(req['request_id'])
    ok, pending=m.authorize_or_request('deployment',payload,RiskLevel.MEDIUM,legacy_approvals=[token])
    assert ok and pending is None

from adapters.storage.approval_sqlite import ApprovalService, HmacApprovalTokenService, SqliteApprovalRepository
from domain.models import RiskLevel

def build_service(tmp_path):
    return ApprovalService(SqliteApprovalRepository(tmp_path / "approvals.sqlite3"), HmacApprovalTokenService("test-secret"))

def test_approval_token_is_action_scoped(tmp_path):
    service = build_service(tmp_path)
    payload = {"path": "x.txt"}
    request = service.request("file_write", payload, RiskLevel.MEDIUM)
    token = service.approve(request["request_id"])
    assert service.verify(token, "file_write", payload)
    assert not service.verify(token, "file_write", {"path": "y.txt"})

def test_repository_and_token_signer_are_separate_components(tmp_path):
    repository = SqliteApprovalRepository(tmp_path / "a.sqlite3")
    signer = HmacApprovalTokenService("secret")
    service = ApprovalService(repository, signer)
    request = service.request("deploy", {"image": "nisr"}, RiskLevel.MEDIUM)
    assert request["status"] == "pending"

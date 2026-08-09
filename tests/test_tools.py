import pytest

from adapters.storage.approval_sqlite import ApprovalService, HmacApprovalTokenService, SqliteApprovalRepository
from adapters.tools.files import FileReadTool, FileWriteTool
from domain.contracts import RiskPolicy


def approvals(tmp_path):
    return ApprovalService(SqliteApprovalRepository(tmp_path / "approvals.sqlite3"), HmacApprovalTokenService("secret"))


@pytest.mark.asyncio
async def test_file_write_requires_scoped_approval(tmp_path):
    service = approvals(tmp_path)
    tool = FileWriteTool(tmp_path, RiskPolicy(), service)
    denied = await tool.run({"path": "x.txt", "content": "hello"})
    assert not denied.ok
    token = service.approve(denied.metadata["approval_required"]["request_id"])
    wrote = await tool.run({"path": "x.txt", "content": "hello", "approval_token": token})
    assert wrote.ok
    read = await FileReadTool(tmp_path).run({"path": "x.txt"})
    assert read.output == "hello"

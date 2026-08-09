import pytest
from adapters.database.sqlite import SqliteDatabaseAdapter
from adapters.database.tool import DatabaseTool
from adapters.storage.approval_sqlite import ApprovalService, HmacApprovalTokenService, SqliteApprovalRepository
from domain.contracts import RiskPolicy

def approval_service(tmp_path):
    return ApprovalService(SqliteApprovalRepository(tmp_path / "approvals.sqlite3"), HmacApprovalTokenService("secret"))

@pytest.mark.asyncio
async def test_database_tool_uses_database_port(tmp_path):
    db = SqliteDatabaseAdapter(tmp_path / "db.sqlite3")
    approvals = approval_service(tmp_path)
    tool = DatabaseTool(db, RiskPolicy(), approvals)
    denied = await tool.run({"operation": "execute", "sql": "create table t(id integer)"})
    assert not denied.ok
    token = approvals.approve(denied.metadata["approval_required"]["request_id"])
    created = await tool.run({"operation": "execute", "sql": "create table t(id integer)", "approval_token": token})
    assert created.ok
    query = await tool.run({"operation": "query", "sql": 'select name from sqlite_master where type="table"'})
    assert query.ok and any(row["name"] == "t" for row in query.output)

@pytest.mark.asyncio
async def test_database_tool_accepts_another_port_implementation(tmp_path):
    class FakeDatabase:
        async def query(self, sql, params): return [{"fake": True}]
        async def execute(self, sql, params): return {"rowcount": 1}
    tool = DatabaseTool(FakeDatabase(), RiskPolicy(), approval_service(tmp_path))
    result = await tool.run({"operation": "query", "sql": "select 1"})
    assert result.ok and result.output == [{"fake": True}]

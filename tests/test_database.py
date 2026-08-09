import pytest
from super_agent.core.approvals import ApprovalManager
from super_agent.core.risk import RiskGate
from super_agent.tools.database import DatabaseTool

@pytest.mark.asyncio
async def test_sqlite_database_read_and_approved_write(tmp_path):
    db=tmp_path/'db.sqlite3'; approvals=ApprovalManager(tmp_path/'a.sqlite3','secret'); tool=DatabaseTool(f'sqlite:///{db}',RiskGate(),approvals)
    denied=await tool.run({'operation':'execute','sql':'create table t(id integer)'})
    assert not denied.ok; req=denied.metadata['approval_required']; token=approvals.approve(req['request_id'])
    ok=await tool.run({'operation':'execute','sql':'create table t(id integer)','approval_token':token}); assert ok.ok
    q=await tool.run({'operation':'query','sql':'select name from sqlite_master where type="table"'}); assert q.ok and any(r['name']=='t' for r in q.output)

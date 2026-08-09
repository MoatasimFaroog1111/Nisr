import json
import pytest
from adapters.llm.mock import MockModelAdapter
from infrastructure.composition_root import build_runtime
from infrastructure.settings import Settings

@pytest.mark.asyncio
async def test_orchestrator_completes_single_task(tmp_path):
    provider = MockModelAdapter([json.dumps({"tasks":[{"id":"t1","title":"Inspect","description":"List files","depends_on":[],"verification":[]}]}), json.dumps({"action":"tool","thought_summary":"Inspect","tool":{"name":"list_files","arguments":{"path":"."}}}), json.dumps({"action":"finish","result":"Workspace inspected"})])
    settings = Settings(provider="mock", model="mock", api_base="http://example.invalid", api_key="x", workspace=tmp_path / "workspace", memory_db=tmp_path / "memory.sqlite3", approval_db=tmp_path / "approvals.sqlite3", approval_secret="s", audit_log=tmp_path / "audit.jsonl", artifacts_dir=tmp_path / "artifacts", database_url="", max_steps=5)
    container = build_runtime(settings, provider=provider)
    state = await container.orchestrator.run("Inspect workspace")
    assert "t1" in state.completed_tasks and state.final_result == "Workspace inspected"

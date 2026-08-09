from adapters.llm.mock import MockModelAdapter
from infrastructure.composition_root import build_management, build_runtime
from infrastructure.settings import Settings

def settings_for(tmp_path):
    return Settings(provider="mock", model="mock", api_base="http://example.invalid", api_key="x", workspace=tmp_path / "workspace", memory_db=tmp_path / "memory.sqlite3", approval_db=tmp_path / "approvals.sqlite3", approval_secret="s", audit_log=tmp_path / "audit.jsonl", artifacts_dir=tmp_path / "artifacts", database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}")

def test_composition_root_registers_advanced_tools(tmp_path):
    container = build_runtime(settings_for(tmp_path), provider=MockModelAdapter([]))
    for expected in {"read_file","write_file","shell","web_search","browser","git","github","database","deployment","artifact","approval_status"}: assert expected in container.tools.names

def test_management_container_does_not_require_llm_credentials(tmp_path):
    settings = settings_for(tmp_path); settings.api_key = ""; settings.model = ""
    management = build_management(settings)
    assert management.approvals.list() == []

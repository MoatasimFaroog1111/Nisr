from super_agent.config import Settings
from super_agent.providers.mock import MockProvider
from super_agent.runtime import build_runtime


def make_settings(tmp_path):
    return Settings(
        provider='mock', model='mock', api_base='http://example.invalid', api_key='x',
        workspace=tmp_path/'workspace', memory_db=tmp_path/'memory.sqlite3',
        approval_db=tmp_path/'approvals.sqlite3', approval_secret='secret',
        audit_log=tmp_path/'audit.jsonl', artifacts_dir=tmp_path/'artifacts',
        database_url=f'sqlite:///{tmp_path / "db.sqlite3"}', github_token='',
        github_api_base='https://api.github.com', web_user_agent='test', max_steps=5,
        context_budget_chars=20000, auto_approve_low_risk=True,
    )


def test_advanced_tools_are_registered(tmp_path):
    settings=make_settings(tmp_path); settings.workspace.mkdir(parents=True, exist_ok=True)
    runtime=build_runtime(settings=settings, provider=MockProvider([]), approvals=[])
    expected={'web_search','web_fetch','browser','git','github','database','deployment','artifact','approval_status'}
    assert expected.issubset(set(runtime.router.names))

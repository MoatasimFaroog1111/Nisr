import json, pytest
from super_agent.config import Settings
from super_agent.providers.mock import MockProvider
from super_agent.runtime import build_runtime

@pytest.mark.asyncio
async def test_orchestrator_completes_single_task(tmp_path):
    provider=MockProvider([
        json.dumps({'tasks':[{'id':'t1','title':'Inspect','description':'List files','depends_on':[],'verification':[]}]}),
        json.dumps({'action':'tool','thought_summary':'Inspect','tool':{'name':'list_files','arguments':{'path':'.'}}}),
        json.dumps({'action':'finish','result':'Workspace inspected'})])
    settings=Settings(provider='mock',model='mock',api_base='http://example.invalid',api_key='x',workspace=tmp_path/'workspace',memory_db=tmp_path/'memory.sqlite3',approval_db=tmp_path/'approvals.sqlite3',approval_secret='s',audit_log=tmp_path/'audit.jsonl',artifacts_dir=tmp_path/'artifacts',database_url='',github_token='',github_api_base='https://api.github.com',web_user_agent='test',max_steps=5,context_budget_chars=20000,auto_approve_low_risk=True)
    settings.workspace.mkdir(parents=True,exist_ok=True); runtime=build_runtime(settings=settings,provider=provider,approvals=[]); state=await runtime.run('Inspect')
    assert 't1' in state.completed_tasks and state.mode.value=='DELIVERY' and state.final_result=='Workspace inspected'

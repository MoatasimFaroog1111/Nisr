import asyncio, pytest
from super_agent.providers.base import ModelProvider
from super_agent.core.subagents import SubagentManager
from super_agent.models import SubagentRequest

class EchoProvider(ModelProvider):
    async def complete(self,prompt:str,system:str='')->str:
        await asyncio.sleep(0.01); return system.split('.')[0]

@pytest.mark.asyncio
async def test_parallel_subagents():
    m=SubagentManager(EchoProvider()); out=await m.run_many([SubagentRequest(role='researcher',task='a'),SubagentRequest(role='tester',task='b')],'ctx')
    assert len(out)==2 and {x['role'] for x in out}=={'researcher','tester'}

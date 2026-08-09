import pytest
from super_agent.core.risk import RiskGate
from super_agent.tools.files import FileReadTool, FileWriteTool

@pytest.mark.asyncio
async def test_file_write_requires_approval(tmp_path):
    tool=FileWriteTool(tmp_path,RiskGate(),[]); result=await tool.run({'path':'x.txt','content':'hello'}); assert not result.ok

@pytest.mark.asyncio
async def test_file_write_and_read_with_approval(tmp_path):
    writer=FileWriteTool(tmp_path,RiskGate(),['risk:medium']); reader=FileReadTool(tmp_path)
    wrote=await writer.run({'path':'x.txt','content':'hello'}); assert wrote.ok
    read=await reader.run({'path':'x.txt'}); assert read.ok and read.output=='hello'

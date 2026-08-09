from __future__ import annotations
from super_agent.models import VerificationResult
from super_agent.tools.router import ToolRouter

class VerificationEngine:
    def __init__(self,router:ToolRouter):self.router=router
    async def verify_commands(self,commands:list[str],session_id:str="")->VerificationResult:
        if not commands:return VerificationResult(ok=True,checks=[],summary="No explicit verification commands.")
        checks=[]; overall=True
        for command in commands:
            result=await self.router.call("shell",{"command":command,"verification_only":True},session_id=session_id)
            checks.append({"command":command,"ok":result.ok,"output":result.output,"error":result.error}); overall=overall and result.ok
        return VerificationResult(ok=overall,checks=checks,summary="Verification passed." if overall else "Verification failed.")

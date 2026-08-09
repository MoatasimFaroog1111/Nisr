from __future__ import annotations

import json
from pydantic import ValidationError
from super_agent.core.context import ContextManager
from super_agent.core.memory import MemoryStore
from super_agent.core.planner import Planner
from super_agent.core.subagents import SubagentManager
from super_agent.core.system_prompt import SYSTEM_PROMPT
from super_agent.core.verification import VerificationEngine
from super_agent.core.compression import ContextCompressor
from super_agent.core.audit import AuditLog
from super_agent.models import AgentAction, AgentMode, AgentState, TaskStatus
from super_agent.providers.base import ModelProvider
from super_agent.tools.router import ToolRouter

ACTION_PROTOCOL = """
Return exactly one JSON object matching one form:
Tool: {"action":"tool","thought_summary":"short reason","tool":{"name":"tool_name","arguments":{}}}
Delegate: {"action":"delegate","subagent_role":"researcher","subagent_task":"..."}
Parallel delegates: {"action":"delegate_parallel","subagents":[{"role":"researcher","task":"..."},{"role":"tester","task":"..."}]}
Memory: {"action":"memory_write","memory_key":"...","memory_value":"..."}
Plan update: {"action":"plan_update","plan":{"tasks":[...]}}
Finish: {"action":"finish","result":"final user-facing result"}
Do not wrap JSON in markdown.
"""

class Orchestrator:
    def __init__(self,provider:ModelProvider,router:ToolRouter,memory:MemoryStore,max_steps:int=30,context_budget_chars:int=50000,audit:AuditLog|None=None):
        self.provider=provider; self.router=router; self.memory=memory; self.max_steps=max_steps; self.audit=audit
        self.context=ContextManager(ContextCompressor(context_budget_chars)); self.planner=Planner(provider); self.subagents=SubagentManager(provider); self.verifier=VerificationEngine(router)

    async def run(self,objective:str,constraints:list[str]|None=None,approvals:list[str]|None=None)->AgentState:
        state=AgentState(objective=objective,constraints=constraints or [],user_approvals=approvals or [])
        if self.audit:self.audit.record("agent.start",session_id=state.session_id,data={"objective":objective,"constraints":state.constraints})
        state.mode=AgentMode.PLANNING; state.plan=await self.planner.create_plan(objective,state.constraints)
        if self.audit:self.audit.record("plan.created",session_id=state.session_id,data=state.plan.model_dump(mode="json"))
        for task in state.plan.tasks:
            if state.step_count>=self.max_steps:break
            if any(dep not in state.completed_tasks for dep in task.depends_on):
                task.status=TaskStatus.BLOCKED; state.blocked_tasks.append(task.id); continue
            task.status=TaskStatus.IN_PROGRESS; state.current_task=task.id; state.mode=AgentMode.EXECUTION; task_done=False
            while not task_done and state.step_count<self.max_steps:
                state.step_count+=1; memories=self.memory.search(objective,limit=6); state.memories_read=memories
                context=self.context.build(state,memories,self.router.describe())
                prompt=f"{ACTION_PROTOCOL}\n\nCURRENT TASK:\n{task.model_dump_json(indent=2)}\n\nRUNTIME CONTEXT:\n{context}\n"
                raw=await self.provider.complete(prompt,system=SYSTEM_PROMPT)
                try:action=AgentAction.model_validate(json.loads(raw))
                except (json.JSONDecodeError,ValidationError) as e:
                    state.evidence.append(f"Invalid model action: {e}"); continue
                if self.audit:self.audit.record("agent.action",session_id=state.session_id,data={"action":action.action,"summary":action.thought_summary})
                if action.action=="tool":
                    if not action.tool:state.evidence.append("Tool action missing tool payload.");continue
                    result=await self.router.call(action.tool.name,action.tool.arguments,session_id=state.session_id)
                    row={"tool":action.tool.name,"arguments":action.tool.arguments,"ok":result.ok,"output":result.output,"error":result.error,"metadata":result.metadata}; state.tool_results.append(row)
                    changed=result.metadata.get("changed_artifact") if result.metadata else None
                    if changed:state.changed_artifacts.append(str(changed))
                    req=result.metadata.get("approval_required") if result.metadata else None
                    if req and req not in state.pending_approvals:state.pending_approvals.append(req)
                    continue
                if action.action=="delegate":
                    if not action.subagent_task:state.evidence.append("Delegate action missing task.");continue
                    report=await self.subagents.run(action.subagent_role or "researcher",action.subagent_task,context); state.evidence.append(f"Subagent report: {report}");continue
                if action.action=="delegate_parallel":
                    if not action.subagents:state.evidence.append("Parallel delegate action missing subagents.");continue
                    reports=await self.subagents.run_many(action.subagents,context)
                    for report in reports:state.evidence.append(f"Parallel subagent [{report['role']}]: {report['result']}")
                    continue
                if action.action=="memory_write":
                    if action.memory_key and action.memory_value:self.memory.upsert(action.memory_key,action.memory_value);state.memories_written.append(action.memory_key)
                    continue
                if action.action=="plan_update":
                    if action.plan:state.plan=action.plan;state.evidence.append("Plan updated by agent.")
                    continue
                if action.action=="finish":
                    task_done=True; state.final_result=action.result or state.final_result; state.evidence.append(action.result or "Task finished.")
            if task_done:
                state.mode=AgentMode.VERIFICATION; verification=await self.verifier.verify_commands(task.verification,state.session_id); state.verification_results.append(verification.model_dump())
                if verification.ok:task.status=TaskStatus.COMPLETED;state.completed_tasks.append(task.id)
                else:task.status=TaskStatus.BLOCKED;state.blocked_tasks.append(task.id);state.mode=AgentMode.DEBUGGING;break
        state.mode=AgentMode.DELIVERY
        if state.step_count>=self.max_steps and not state.final_result:state.final_result="Execution stopped at the configured maximum step limit."
        if self.audit:self.audit.record("agent.finish",session_id=state.session_id,data={"completed":state.completed_tasks,"blocked":state.blocked_tasks,"steps":state.step_count,"final_result":state.final_result})
        return state

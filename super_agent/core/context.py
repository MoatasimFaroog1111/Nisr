from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from super_agent.models import AgentState
from super_agent.core.compression import ContextCompressor


@dataclass
class ContextManager:
    compressor: ContextCompressor

    def build(self, state: AgentState, memories: Iterable[str], tools_description: str) -> str:
        tool_results = self.compressor.compress_tool_results(state.tool_results)
        evidence = self.compressor.compress_evidence(state.evidence)
        return self.compressor.fit([
            ("OBJECTIVE", state.objective),
            ("CONSTRAINTS", state.constraints),
            ("MODE", state.mode.value),
            ("PLAN", state.plan.model_dump(mode="json")),
            ("CURRENT TASK", state.current_task or ""),
            ("EVIDENCE", evidence),
            ("TOOL RESULTS", tool_results),
            ("RELEVANT MEMORY", list(memories)),
            ("PENDING APPROVALS", state.pending_approvals),
            ("AVAILABLE TOOLS", tools_description),
        ])

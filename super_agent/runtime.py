from __future__ import annotations

from super_agent.config import Settings, settings as default_settings
from super_agent.core.memory import MemoryStore
from super_agent.core.orchestrator import Orchestrator
from super_agent.core.risk import RiskGate
from super_agent.core.audit import AuditLog
from super_agent.core.approvals import ApprovalManager
from super_agent.core.artifacts import ArtifactManager
from super_agent.providers.base import ModelProvider
from super_agent.providers.factory import build_provider
from super_agent.tools.files import FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from super_agent.tools.router import ToolRouter
from super_agent.tools.shell import ShellTool
from super_agent.tools.web import WebSearchTool, WebFetchTool
from super_agent.tools.browser import BrowserSessionManager, BrowserTool
from super_agent.tools.git import GitTool
from super_agent.tools.github import GitHubTool
from super_agent.tools.database import DatabaseTool
from super_agent.tools.deployment import DeploymentTool
from super_agent.tools.artifacts import ArtifactTool
from super_agent.tools.approvals import ApprovalStatusTool


def build_runtime(settings:Settings=default_settings,provider:ModelProvider|None=None,approvals:list[str]|None=None)->Orchestrator:
    provider=provider or build_provider(settings); approvals_ref=approvals if approvals is not None else []
    risk=RiskGate(); audit=AuditLog(settings.audit_log)
    approval_manager=ApprovalManager(settings.approval_db,settings.approval_secret,settings.auto_approve_low_risk)
    artifact_manager=ArtifactManager(settings.artifacts_dir)
    browser_sessions=BrowserSessionManager(settings.artifacts_dir)
    router=ToolRouter(audit=audit)
    for tool in [
        FileListTool(settings.workspace), FileReadTool(settings.workspace), FileSearchTool(settings.workspace),
        FileWriteTool(settings.workspace,risk,approvals_ref,approval_manager), ShellTool(settings.workspace,risk,approvals_ref,approval_manager),
        WebSearchTool(settings.web_user_agent), WebFetchTool(settings.web_user_agent), BrowserTool(browser_sessions,approval_manager),
        GitTool(settings.workspace,risk,approval_manager), GitHubTool(settings.github_token,settings.github_api_base,approval_manager),
        DatabaseTool(settings.database_url,risk,approval_manager), DeploymentTool(settings.workspace,approval_manager),
        ArtifactTool(artifact_manager), ApprovalStatusTool(approval_manager),
    ]: router.register(tool)
    memory=MemoryStore(settings.memory_db)
    runtime=Orchestrator(provider=provider,router=router,memory=memory,max_steps=settings.max_steps,context_budget_chars=settings.context_budget_chars,audit=audit)
    runtime.approval_manager=approval_manager; runtime.artifact_manager=artifact_manager; runtime.audit_log=audit; runtime.browser_sessions=browser_sessions
    return runtime

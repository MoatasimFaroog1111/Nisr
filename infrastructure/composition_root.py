from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adapters.browser.playwright import BrowserSession, PlaywrightBrowserTool
from adapters.database.postgres import PostgresDatabaseAdapter
from adapters.database.sqlite import SqliteDatabaseAdapter
from adapters.database.tool import DatabaseTool
from adapters.deployment.docker import DockerDeploymentTool
from adapters.github.rest import GitHubRestTool
from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from adapters.storage.approval_sqlite import ApprovalService, HmacApprovalTokenService, SqliteApprovalRepository
from adapters.storage.artifact_filesystem import FileSystemArtifactAdapter
from adapters.storage.audit_jsonl import JsonlAuditAdapter
from adapters.storage.memory_sqlite import SqliteMemoryAdapter
from adapters.tools.approval_status import ApprovalStatusTool
from adapters.tools.artifact import ArtifactTool
from adapters.tools.files import FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from adapters.tools.git import GitTool
from adapters.tools.registry import ToolRegistry
from adapters.tools.shell import ShellTool
from adapters.tools.web import WebFetchTool, WebSearchTool
from application.execution import ActionExecutor, ContextBuilder, ContextCompressor, ExecutionEngine, SubagentCoordinator
from application.orchestrator import Orchestrator
from application.planning import PlanningService
from application.verification import VerificationService
from domain.contracts import RiskPolicy
from infrastructure.settings import Settings, settings as default_settings
from ports.database import DatabasePort
from ports.model_provider import ModelProviderPort


@dataclass(slots=True)
class ManagementContainer:
    approvals: ApprovalService
    audit: JsonlAuditAdapter
    artifacts: FileSystemArtifactAdapter


@dataclass(slots=True)
class RuntimeContainer(ManagementContainer):
    orchestrator: Orchestrator
    memory: SqliteMemoryAdapter
    tools: ToolRegistry
    browser_session: BrowserSession


def _build_provider(settings: Settings) -> ModelProviderPort:
    if settings.provider == "openai_compatible":
        return OpenAICompatibleAdapter(settings.api_base, settings.api_key, settings.model)
    raise ValueError(f"Unsupported provider: {settings.provider}")


def _sqlite_path_from_url(url: str) -> Path:
    if url.startswith("sqlite:///"):
        return Path(url[10:]).resolve()
    if url.startswith("sqlite://"):
        return Path(url[9:]).resolve()
    raise ValueError("Not a SQLite URL")


def _build_database(url: str) -> DatabasePort | None:
    if not url:
        return None
    if url.startswith("sqlite:"):
        return SqliteDatabaseAdapter(_sqlite_path_from_url(url))
    if url.startswith(("postgresql://", "postgres://")):
        return PostgresDatabaseAdapter(url)
    raise ValueError("Unsupported database URL scheme")


def build_management(settings: Settings = default_settings) -> ManagementContainer:
    settings.prepare_directories()
    audit = JsonlAuditAdapter(settings.audit_log)
    artifact_store = FileSystemArtifactAdapter(settings.artifacts_dir)
    approval_repository = SqliteApprovalRepository(settings.approval_db)
    approval_tokens = HmacApprovalTokenService(settings.approval_secret)
    approval_service = ApprovalService(approval_repository, approval_tokens, settings.auto_approve_low_risk)
    return ManagementContainer(approvals=approval_service, audit=audit, artifacts=artifact_store)


def build_runtime(settings: Settings = default_settings, *, provider: ModelProviderPort | None = None, approvals: list[str] | None = None) -> RuntimeContainer:
    """Composition root: the only place that chooses concrete adapters."""
    settings.prepare_directories()
    provider = provider or _build_provider(settings)
    legacy_approvals = approvals or []
    risk = RiskPolicy()
    management = build_management(settings)
    audit = management.audit
    artifact_store = management.artifacts
    approval_service = management.approvals
    memory = SqliteMemoryAdapter(settings.memory_db)
    browser_session = BrowserSession(settings.artifacts_dir)
    tools = ToolRegistry(audit=audit)
    for tool in (
        FileListTool(settings.workspace),
        FileReadTool(settings.workspace),
        FileSearchTool(settings.workspace),
        FileWriteTool(settings.workspace, risk, approval_service, legacy_approvals),
        ShellTool(settings.workspace, risk, approval_service, legacy_approvals),
        WebSearchTool(settings.web_user_agent),
        WebFetchTool(settings.web_user_agent),
        PlaywrightBrowserTool(browser_session, approval_service),
        GitTool(settings.workspace, risk, approval_service),
        GitHubRestTool(settings.github_token, settings.github_api_base, approval_service),
        DockerDeploymentTool(settings.workspace, approval_service),
        ArtifactTool(artifact_store),
        ApprovalStatusTool(approval_service),
    ):
        tools.register(tool)
    database = _build_database(settings.database_url)
    if database is not None:
        tools.register(DatabaseTool(database, risk, approval_service))
    planner = PlanningService(provider)
    verifier = VerificationService(tools)
    subagents = SubagentCoordinator(provider)
    context = ContextBuilder(ContextCompressor(settings.context_budget_chars))
    action_executor = ActionExecutor(tools, memory, subagents, audit)
    execution = ExecutionEngine(provider, tools, memory, action_executor, context)
    orchestrator = Orchestrator(planner, execution, verifier, max_steps=settings.max_steps, audit=audit)
    return RuntimeContainer(orchestrator=orchestrator, approvals=approval_service, audit=audit, artifacts=artifact_store, memory=memory, tools=tools, browser_session=browser_session)

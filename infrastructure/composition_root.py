from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adapters.browser.playwright_provider import PlaywrightBrowserProvider
from adapters.database.postgres import PostgresDatabaseAdapter
from adapters.database.sqlite import SqliteDatabaseAdapter
from adapters.database.tool import DatabaseTool
from adapters.deployment.docker import DockerDeploymentTool
from adapters.github.rest import GitHubRestTool
from adapters.llm.openai_compatible import OpenAICompatibleAdapter
from adapters.realtime.browser_events import InMemoryBrowserEventHub
from adapters.security.browser_tokens import BrowserSessionTokenService
from adapters.storage.approval_sqlite import ApprovalService, HmacApprovalTokenService, SqliteApprovalRepository
from adapters.storage.artifact_filesystem import FileSystemArtifactAdapter
from adapters.storage.audit_jsonl import JsonlAuditAdapter
from adapters.storage.memory_sqlite import SqliteMemoryAdapter
from adapters.storage.session_sqlite import SqliteSessionStore
from adapters.telemetry.provider_audit import AuditProviderTelemetry
from adapters.tools.approval_status import ApprovalStatusTool
from adapters.tools.artifact import ArtifactTool
from adapters.tools.browser import browser_tools
from adapters.tools.files import FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from adapters.tools.git import GitTool
from adapters.tools.registry import ToolRegistry
from adapters.tools.shell import ShellTool
from adapters.tools.web import WebFetchTool, WebSearchTool
from application.browser_runtime import BrowserControlManager, BrowserManager, BrowserService
from application.browser_streaming import BrowserFrameStreamer
from application.execution import ActionExecutor, ContextBuilder, ContextCompressor, ExecutionEngine
from application.orchestrator import Orchestrator
from application.planning import PlanningService
from application.subagent_budget import AdaptiveSubagentCoordinator
from application.token_budget import RunTokenBudgetManager
from application.verification import VerificationService
from domain.contracts import RiskPolicy
from infrastructure.settings import Settings, settings as default_settings
from ports.database import DatabasePort
from ports.model_provider import ModelProviderPort
from ports.provider_telemetry import ProviderTelemetryPort
from ports.token_budget import TokenBudgetPort


@dataclass(slots=True)
class ManagementContainer:
    approvals: ApprovalService
    audit: JsonlAuditAdapter
    artifacts: FileSystemArtifactAdapter


@dataclass(slots=True)
class BrowserRuntimeContainer:
    provider: PlaywrightBrowserProvider
    events: InMemoryBrowserEventHub
    manager: BrowserManager
    control: BrowserControlManager
    service: BrowserService
    streamer: BrowserFrameStreamer
    tokens: BrowserSessionTokenService

    async def close(self) -> None:
        await self.streamer.close()
        await self.manager.close_all()


@dataclass(slots=True)
class RuntimeContainer(ManagementContainer):
    orchestrator: Orchestrator
    memory: SqliteMemoryAdapter
    sessions: SqliteSessionStore
    tools: ToolRegistry
    browser_runtime: BrowserRuntimeContainer
    token_budget: RunTokenBudgetManager


def _build_provider(
    settings: Settings,
    telemetry: ProviderTelemetryPort,
    token_budget: TokenBudgetPort,
) -> ModelProviderPort:
    if settings.provider == "openai_compatible":
        return OpenAICompatibleAdapter(
            settings.api_base,
            settings.api_key,
            settings.model,
            max_retries=settings.provider_max_retries,
            retry_base_seconds=settings.provider_retry_base_seconds,
            telemetry=telemetry,
            token_budget=token_budget,
        )
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


def build_management(
    settings: Settings = default_settings,
    presented_approvals: list[str] | None = None,
) -> ManagementContainer:
    settings.prepare_directories()
    audit = JsonlAuditAdapter(settings.audit_log)
    artifact_store = FileSystemArtifactAdapter(settings.artifacts_dir)
    approval_repository = SqliteApprovalRepository(settings.approval_db)
    approval_tokens = HmacApprovalTokenService(settings.approval_secret)
    approval_service = ApprovalService(
        approval_repository,
        approval_tokens,
        settings.auto_approve_low_risk,
        presented_approvals=presented_approvals,
    )
    return ManagementContainer(approvals=approval_service, audit=audit, artifacts=artifact_store)


def build_browser_runtime(settings: Settings = default_settings) -> BrowserRuntimeContainer:
    provider = PlaywrightBrowserProvider()
    events = InMemoryBrowserEventHub()
    manager = BrowserManager(
        provider,
        viewport={"width": settings.browser_viewport_width, "height": settings.browser_viewport_height},
        timeout_seconds=settings.browser_session_timeout_seconds,
        max_sessions=settings.browser_max_sessions,
    )
    control = BrowserControlManager()
    service = BrowserService(manager, control, provider, events)
    streamer = BrowserFrameStreamer(service, settings.browser_frame_interval_ms)
    tokens = BrowserSessionTokenService(
        settings.browser_session_secret,
        ttl_seconds=settings.browser_token_ttl_seconds,
    )
    return BrowserRuntimeContainer(
        provider=provider,
        events=events,
        manager=manager,
        control=control,
        service=service,
        streamer=streamer,
        tokens=tokens,
    )


def build_runtime(
    settings: Settings = default_settings,
    *,
    provider: ModelProviderPort | None = None,
    approvals: list[str] | None = None,
    browser_runtime: BrowserRuntimeContainer | None = None,
) -> RuntimeContainer:
    """Composition root: the only place that chooses concrete adapters."""
    settings.prepare_directories()
    legacy_approvals = approvals or []
    risk = RiskPolicy()
    management = build_management(settings, presented_approvals=legacy_approvals)
    audit = management.audit
    artifact_store = management.artifacts
    approval_service = management.approvals

    token_budget = RunTokenBudgetManager(
        run_token_budget=settings.run_token_budget,
        provider_token_reserve=settings.provider_token_reserve,
        chars_per_token=settings.token_chars_per_token,
        min_context_chars=settings.min_context_budget_chars,
        context_safety_ratio=settings.context_budget_safety_ratio,
    )
    telemetry = AuditProviderTelemetry(audit)
    provider = provider or _build_provider(settings, telemetry, token_budget)

    memory = SqliteMemoryAdapter(settings.memory_db)
    sessions = SqliteSessionStore(settings.session_db)
    browser_runtime = browser_runtime or build_browser_runtime(settings)
    tools = ToolRegistry(audit=audit)
    for tool in (
        FileListTool(settings.workspace),
        FileReadTool(settings.workspace),
        FileSearchTool(settings.workspace),
        FileWriteTool(settings.workspace, risk, approval_service, legacy_approvals),
        ShellTool(settings.workspace, risk, approval_service, legacy_approvals),
        WebSearchTool(settings.web_user_agent),
        WebFetchTool(settings.web_user_agent),
        GitTool(settings.workspace, risk, approval_service),
        GitHubRestTool(settings.github_token, settings.github_api_base, approval_service),
        DockerDeploymentTool(settings.workspace, approval_service),
        ArtifactTool(artifact_store),
        ApprovalStatusTool(approval_service),
        *browser_tools(browser_runtime.service),
    ):
        tools.register(tool)
    database = _build_database(settings.database_url)
    if database is not None:
        tools.register(DatabaseTool(database, risk, approval_service))

    planner = PlanningService(provider)
    verifier = VerificationService(tools)
    subagents = AdaptiveSubagentCoordinator(provider, token_budget)
    context = ContextBuilder(ContextCompressor(settings.context_budget_chars), token_budget)
    action_executor = ActionExecutor(tools, memory, subagents, audit)
    execution = ExecutionEngine(provider, tools, memory, action_executor, context)
    orchestrator = Orchestrator(
        planner,
        execution,
        verifier,
        max_steps=settings.max_steps,
        audit=audit,
        sessions=sessions,
    )
    return RuntimeContainer(
        orchestrator=orchestrator,
        approvals=approval_service,
        audit=audit,
        artifacts=artifact_store,
        memory=memory,
        sessions=sessions,
        tools=tools,
        browser_runtime=browser_runtime,
        token_budget=token_budget,
    )

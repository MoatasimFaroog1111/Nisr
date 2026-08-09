from __future__ import annotations

from typing import Any

from adapters.tools.base import BaseTool
from application.browser_runtime import BrowserService
from domain.browser import BrowserControlError, SensitiveBrowserOperation
from domain.models import ToolResult
from ports.tool import ToolExecutionContext


_DESCRIPTIONS = {
    "navigate": "Navigate the active browser tab to an HTTP(S) URL. args: url.",
    "view": "Read current browser state, tabs, visible interactable elements, safe page text, and sensitive-step signals.",
    "click": "Click an element in the active tab. args: selector.",
    "input": "Fill a non-sensitive field. args: selector, value. Password/OTP/payment fields require user takeover.",
    "pressKey": "Press a keyboard key or shortcut in the active tab. args: key.",
    "scroll": "Scroll the active page. args: optional delta_x, delta_y.",
    "selectOption": "Select an option in a select element. args: selector, value.",
    "back": "Navigate backward in the active tab history.",
    "forward": "Navigate forward in the active tab history.",
    "refresh": "Refresh the active tab.",
    "getTabs": "List browser tabs and identify the active tab.",
    "switchTab": "Switch to a browser tab. args: tab_id.",
    "closeTab": "Close a browser tab. args: tab_id.",
    "requestTakeover": "Pause browser work and ask the user to take control. args: reason. Use for login credentials, CAPTCHA, 2FA/OTP, payment, banking authentication, sensitive personal information, or security verification.",
}


class BrowserActionTool(BaseTool):
    sensitive_fields = frozenset({"value", "text"})
    audit_output = False

    def __init__(self, action: str, service: BrowserService):
        if action not in _DESCRIPTIONS:
            raise ValueError(f"Unsupported browser action: {action}")
        self._action = action
        self._service = service
        self.name = f"browser.{action}"
        self.description = _DESCRIPTIONS[action]

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=False, error="Browser tools require agent execution context")

    async def run_contextual(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        if not context.session_id:
            return ToolResult(ok=False, error="Browser action requires a session_id")
        user_id = context.user_id or "api"
        await self._service.register_session(context.session_id, user_id)
        task_id = context.task_id or None
        try:
            if self._action == "navigate":
                state = await self._service.navigate(context.session_id, user_id, task_id, str(arguments.get("url", "")))
            elif self._action == "view":
                state = await self._service.view(context.session_id, user_id, task_id)
                metadata = {}
                if state.sensitive_signals:
                    metadata = {
                        "waiting_user": True,
                        "code": "USER_TAKEOVER_REQUIRED",
                        "reason": ", ".join(state.sensitive_signals),
                    }
                    return ToolResult(ok=True, output=state.model_dump(mode="json"), metadata=metadata)
                return ToolResult(ok=True, output=state.model_dump(mode="json"))
            elif self._action == "click":
                state = await self._service.click(context.session_id, user_id, task_id, str(arguments.get("selector", "")))
            elif self._action == "input":
                state = await self._service.input(
                    context.session_id,
                    user_id,
                    task_id,
                    str(arguments.get("selector", "")),
                    str(arguments.get("value", "")),
                )
            elif self._action == "pressKey":
                state = await self._service.press_key(context.session_id, user_id, task_id, str(arguments.get("key", "")))
            elif self._action == "scroll":
                state = await self._service.scroll(
                    context.session_id,
                    user_id,
                    task_id,
                    float(arguments.get("delta_x", 0)),
                    float(arguments.get("delta_y", 700)),
                )
            elif self._action == "selectOption":
                state = await self._service.select_option(
                    context.session_id,
                    user_id,
                    task_id,
                    str(arguments.get("selector", "")),
                    str(arguments.get("value", "")),
                )
            elif self._action == "back":
                state = await self._service.back(context.session_id, user_id, task_id)
            elif self._action == "forward":
                state = await self._service.forward(context.session_id, user_id, task_id)
            elif self._action == "refresh":
                state = await self._service.refresh(context.session_id, user_id, task_id)
            elif self._action == "getTabs":
                state = await self._service.get_tabs(context.session_id, user_id, task_id)
            elif self._action == "switchTab":
                state = await self._service.switch_tab(context.session_id, user_id, task_id, str(arguments.get("tab_id", "")))
            elif self._action == "closeTab":
                state = await self._service.close_tab(context.session_id, user_id, task_id, str(arguments.get("tab_id", "")))
            elif self._action == "requestTakeover":
                reason = str(arguments.get("reason", "User input is required"))[:500]
                await self._service.request_user_takeover(context.session_id, user_id, reason, task_id=task_id)
                return ToolResult(
                    ok=True,
                    output="User takeover requested",
                    metadata={"waiting_user": True, "code": "USER_TAKEOVER_REQUIRED", "reason": reason},
                )
            else:
                return ToolResult(ok=False, error="Unsupported browser action")
            return ToolResult(ok=True, output=state.model_dump(mode="json"))
        except SensitiveBrowserOperation as exc:
            return ToolResult(
                ok=False,
                error="USER_TAKEOVER_REQUIRED",
                metadata={"waiting_user": True, "code": "USER_TAKEOVER_REQUIRED", "reason": exc.reason},
            )
        except BrowserControlError as exc:
            return ToolResult(
                ok=False,
                error=exc.code,
                metadata={
                    "waiting_user": exc.code == "BROWSER_CONTROLLED_BY_USER",
                    "code": exc.code,
                },
            )
        except (KeyError, ValueError, PermissionError) as exc:
            return ToolResult(ok=False, error=str(exc), metadata={"error_type": type(exc).__name__})
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=f"Browser action failed: {exc}",
                metadata={"error_type": type(exc).__name__, "action": self._action},
            )


class LegacyBrowserTool(BaseTool):
    """Compatibility facade that routes the old `browser` tool through BrowserService."""

    name = "browser"
    description = "Compatibility browser tool. Prefer browser.navigate/view/click/input/pressKey/scroll/selectOption/back/forward/refresh/getTabs/switchTab/closeTab."
    sensitive_fields = frozenset({"value", "text"})
    audit_output = False

    _ALIASES = {
        "open": "navigate",
        "snapshot": "view",
        "fill": "input",
        "press_key": "pressKey",
        "select_option": "selectOption",
        "get_tabs": "getTabs",
        "switch_tab": "switchTab",
        "close_tab": "closeTab",
    }

    def __init__(self, service: BrowserService):
        self._service = service

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=False, error="Browser tools require agent execution context")

    async def run_contextual(self, arguments: dict[str, Any], context: ToolExecutionContext) -> ToolResult:
        operation = str(arguments.get("operation", "view"))
        action = self._ALIASES.get(operation, operation)
        if action == "close":
            user_id = context.user_id or "api"
            await self._service.close_session(context.session_id, user_id)
            return ToolResult(ok=True, output="Browser closed")
        try:
            delegate = BrowserActionTool(action, self._service)
        except ValueError:
            return ToolResult(ok=False, error=f"Unknown browser operation: {operation}")
        copied = {key: value for key, value in arguments.items() if key != "operation"}
        return await delegate.run_contextual(copied, context)


def browser_tools(service: BrowserService) -> list[BaseTool]:
    return [BrowserActionTool(action, service) for action in _DESCRIPTIONS] + [LegacyBrowserTool(service)]

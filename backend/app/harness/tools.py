from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.harness.contracts import HarnessExecutionRequest

ToolHandler = Callable[[dict[str, Any]], Any]


class ToolRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    handler: ToolHandler
    allowed_node_types: set[str] = field(default_factory=set)
    allowed_agent_types: set[str] = field(default_factory=set)
    timeout_seconds: int = 45
    max_retries: int = 0


@dataclass(frozen=True)
class ToolExecutionResult:
    tool_name: str
    status: str
    output: Any = None
    error_message: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if not definition.name:
            raise ToolRegistryError("tool name is required")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def execute(
        self,
        request: HarnessExecutionRequest,
        payload: dict[str, Any],
    ) -> ToolExecutionResult:
        tool_name = request.tool_name or (request.allowed_tools[0] if request.allowed_tools else "")
        if not tool_name:
            raise ToolRegistryError("no tool selected")
        if tool_name not in request.allowed_tools:
            raise ToolRegistryError(f"tool is not allowed for this request: {tool_name}")
        definition = self._tools.get(tool_name)
        if definition is None:
            raise ToolRegistryError(f"tool is not registered: {tool_name}")
        if (
            definition.allowed_node_types
            and request.node_type not in definition.allowed_node_types
        ):
            raise ToolRegistryError(f"tool {tool_name} is not allowed for node {request.node_type}")
        if (
            definition.allowed_agent_types
            and request.agent_type not in definition.allowed_agent_types
        ):
            raise ToolRegistryError(
                f"tool {tool_name} is not allowed for agent {request.agent_type}"
            )
        try:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="succeeded",
                output=definition.handler(payload),
            )
        except Exception as exc:
            return ToolExecutionResult(tool_name=tool_name, status="failed", error_message=str(exc))

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "CheckpointManager",
    "ContextBuilder",
    "HarnessExecutionRequest",
    "HarnessExecutionResult",
    "HarnessExecutionService",
    "OutputValidator",
    "ReplayService",
    "RuleEvaluator",
    "ToolDefinition",
    "ToolRegistry",
    "TraceRecorder",
]

_EXPORT_MODULES = {
    "CheckpointManager": "app.harness.state",
    "ContextBuilder": "app.harness.context_builder",
    "HarnessExecutionRequest": "app.harness.contracts",
    "HarnessExecutionResult": "app.harness.contracts",
    "HarnessExecutionService": "app.harness.execution",
    "OutputValidator": "app.harness.output_validation",
    "ReplayService": "app.harness.replay",
    "RuleEvaluator": "app.harness.rules",
    "ToolDefinition": "app.harness.tools",
    "ToolRegistry": "app.harness.tools",
    "TraceRecorder": "app.harness.trace",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value

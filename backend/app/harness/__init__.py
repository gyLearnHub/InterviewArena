from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "HarnessExecutionRequest",
    "OutputValidator",
    "RuleEvaluator",
]

_EXPORT_MODULES = {
    "HarnessExecutionRequest": "app.harness.contracts",
    "OutputValidator": "app.harness.output_validation",
    "RuleEvaluator": "app.harness.rules",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value

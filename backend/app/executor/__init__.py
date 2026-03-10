"""Workflow execution abstraction: CLI now, Flyte remote later."""

from __future__ import annotations

from app.executor.base import (
    ExecutionStatus,
    WorkflowExecutor,
    ExecutionResult,
)
from app.executor.cli import CLIWorkflowExecutor

__all__ = [
    "ExecutionResult",
    "ExecutionStatus",
    "WorkflowExecutor",
    "CLIWorkflowExecutor",
]

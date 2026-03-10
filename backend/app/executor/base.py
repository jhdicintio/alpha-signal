"""Abstract workflow executor interface.

The backend uses this interface to start runs and query status. Implementations
can use the CLI (subprocess) or later Flyte remote API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ExecutionStatus(str, Enum):
    """Status of a single workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ExecutionResult:
    """Result of get_status for an execution.

    Same shape regardless of executor (CLI or Flyte remote) so job store
    and API responses stay consistent.
    """

    status: ExecutionStatus
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"status": self.status.value}
        if self.result is not None:
            out["result"] = self.result
        if self.error is not None:
            out["error"] = self.error
        if self.execution_id is not None:
            out["execution_id"] = self.execution_id
        return out


# Type aliases for request params (same keys as API request bodies)
IngestParams = dict[str, Any]
ExtractParams = dict[str, Any]
PipelineParams = dict[str, Any]


class WorkflowExecutor(ABC):
    """Abstract interface for starting workflow runs and querying status.

    Implementations: CLI (subprocess) now, Flyte remote later.
    """

    @abstractmethod
    def start_ingest(self, params: IngestParams, cache_path: str) -> str:
        """Start an ingest run. Returns execution_id (opaque)."""
        ...

    @abstractmethod
    def start_extract(self, params: ExtractParams, cache_path: str) -> str:
        """Start an extract run. Returns execution_id."""
        ...

    @abstractmethod
    def start_pipeline(self, params: PipelineParams, cache_path: str) -> str:
        """Start a full pipeline (ingest then extract) run. Returns execution_id."""
        ...

    @abstractmethod
    def get_status(self, execution_id: str) -> ExecutionResult:
        """Return current status and optional result/error for an execution."""
        ...

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution if supported. Returns True if cancelled."""
        return False

"""CLI-based workflow executor: runs Task/pyflyte in a subprocess."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from app.executor.base import (
    ExecutionResult,
    ExecutionStatus,
    WorkflowExecutor,
)


def _repo_root() -> Path:
    """Return the repository root (parent of backend/ and alpha_signal/)."""
    return Path(__file__).resolve().parent.parent.parent.parent


def _alpha_signal_dir() -> Path:
    return _repo_root() / "alpha_signal"


def _build_ingest_args(params: dict[str, Any], cache_path: str) -> list[str]:
    query = params.get("query")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if not query and not date_from and not date_to:
        raise ValueError("At least one of query, date_from, or date_to is required for ingest")
    args = [
        "poetry",
        "run",
        "pyflyte",
        "run",
        "alpha_signal/workflows/ingest.py",
        "ingest_wf",
        "--cache_path",
        cache_path,
    ]
    if query:
        args.extend(["--query", str(query)])
    if date_from:
        args.extend(["--date_from", str(date_from)])
    if date_to:
        args.extend(["--date_to", str(date_to)])
    sources = params.get("sources")
    if sources:
        if isinstance(sources, list):
            sources = ",".join(sources)
        args.extend(["--sources", f"[{sources}]"])
    max_results = params.get("max_results_per_source")
    if max_results is not None:
        args.extend(["--max_results_per_source", str(max_results)])
    return args


def _build_extract_args(
    params: dict[str, Any], cache_path: str
) -> tuple[list[str], str | None]:
    """Build extract_wf CLI args. Returns (args, temp_prompt_path or None)."""
    args = [
        "poetry",
        "run",
        "pyflyte",
        "run",
        "alpha_signal/workflows/extract.py",
        "extract_wf",
        "--cache_path",
        cache_path,
        "--model",
        str(params.get("model", "gpt-4o-mini")),
        "--budget_usd",
        str(params.get("budget_usd", 1.0)),
    ]
    skip_existing = params.get("skip_existing", True)
    args.extend(["--skip_existing", "true" if skip_existing else "false"])
    provider = params.get("provider")
    if provider:
        args.extend(["--provider", str(provider)])
    temp_path: str | None = None
    system_prompt = params.get("system_prompt")
    if system_prompt and isinstance(system_prompt, str) and system_prompt.strip():
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            f.write(system_prompt)
            f.close()
            temp_path = f.name
            args.extend(["--system_prompt_path", temp_path])
        except Exception:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise
    return args, temp_path


def _build_pipeline_args(
    params: dict[str, Any], cache_path: str
) -> tuple[list[str], str | None]:
    """Build pipeline_wf CLI args. Returns (args, temp_prompt_path or None)."""
    query = params.get("query")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if not query and not date_from and not date_to:
        raise ValueError("At least one of query, date_from, or date_to is required for pipeline")
    args = [
        "poetry",
        "run",
        "pyflyte",
        "run",
        "alpha_signal/workflows/pipeline.py",
        "pipeline_wf",
        "--cache_path",
        cache_path,
        "--model",
        str(params.get("model", "gpt-4o-mini")),
        "--budget_usd",
        str(params.get("budget_usd", 1.0)),
    ]
    if query:
        args.extend(["--query", str(query)])
    if date_from:
        args.extend(["--date_from", str(date_from)])
    if date_to:
        args.extend(["--date_to", str(date_to)])
    sources = params.get("sources")
    if sources:
        if isinstance(sources, list):
            sources = ",".join(sources)
        args.extend(["--sources", f"[{sources}]"])
    max_results = params.get("max_results_per_source")
    if max_results is not None:
        args.extend(["--max_results_per_source", str(max_results)])
    temp_path: str | None = None
    system_prompt = params.get("system_prompt")
    if system_prompt and isinstance(system_prompt, str) and system_prompt.strip():
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        )
        try:
            f.write(system_prompt)
            f.close()
            temp_path = f.name
            args.extend(["--system_prompt_path", temp_path])
        except Exception:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
            raise
    return args, temp_path


def _parse_ingest_stdout(stdout: str) -> dict[str, Any]:
    """Extract articles_added / total from ingest workflow stdout."""
    result: dict[str, Any] = {"raw_tail": stdout.strip().splitlines()[-5:] if stdout.strip() else []}
    # e.g. "cache: 12 new articles added (0 -> 12 total)"
    m = re.search(r"(\d+)\s+new articles added.*?(\d+)\s+total", stdout)
    if m:
        result["articles_added"] = int(m.group(1))
        result["cache_total"] = int(m.group(2))
    return result


def _parse_extract_stdout(stdout: str) -> dict[str, Any]:
    """Extract cost summary from extract workflow stdout."""
    result: dict[str, Any] = {"raw_tail": stdout.strip().splitlines()[-10:] if stdout.strip() else []}
    if "Estimated cost:" in stdout or "cost:" in stdout.lower():
        result["cost_summary"] = stdout.strip()[-2000:]  # last 2k chars
    return result


class CLIWorkflowExecutor(WorkflowExecutor):
    """Execute workflows by running pyflyte in a subprocess."""

    def __init__(self) -> None:
        self._running: dict[str, subprocess.Popen] = {}
        self._completed: dict[str, ExecutionResult] = {}
        self._temp_prompt_files: dict[str, str] = {}

    def _start(self, cmd: list[str], execution_id: str) -> None:
        cwd = _alpha_signal_dir()
        env = None  # inherit so API keys etc. are available
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._running[execution_id] = process

    def _reap(self, execution_id: str) -> ExecutionResult | None:
        process = self._running.get(execution_id)
        if process is None:
            return self._completed.get(execution_id)
        ret = process.poll()
        if ret is None:
            return None
        stdout, stderr = process.communicate()
        self._running.pop(execution_id, None)
        temp_path = self._temp_prompt_files.pop(execution_id, None)
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        if ret == 0:
            result_payload: dict[str, Any] = {"raw_stdout": stdout[-3000:] if stdout else ""}
            result = ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                result=result_payload,
                execution_id=execution_id,
            )
        else:
            result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=stderr.strip() or stdout.strip() or f"Exit code {ret}",
                execution_id=execution_id,
            )
        self._completed[execution_id] = result
        return result

    def start_ingest(self, params: dict[str, Any], cache_path: str) -> str:
        execution_id = str(uuid.uuid4())
        cmd = _build_ingest_args(params, cache_path)
        self._start(cmd, execution_id)
        return execution_id

    def start_extract(self, params: dict[str, Any], cache_path: str) -> str:
        execution_id = str(uuid.uuid4())
        cmd, temp_path = _build_extract_args(params, cache_path)
        if temp_path:
            self._temp_prompt_files[execution_id] = temp_path
        self._start(cmd, execution_id)
        return execution_id

    def start_pipeline(self, params: dict[str, Any], cache_path: str) -> str:
        execution_id = str(uuid.uuid4())
        cmd, temp_path = _build_pipeline_args(params, cache_path)
        if temp_path:
            self._temp_prompt_files[execution_id] = temp_path
        self._start(cmd, execution_id)
        return execution_id

    def get_status(self, execution_id: str) -> ExecutionResult:
        completed = self._reap(execution_id)
        if completed is not None:
            return completed
        if execution_id in self._running:
            return ExecutionResult(
                status=ExecutionStatus.RUNNING,
                execution_id=execution_id,
            )
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            error="Unknown execution_id",
            execution_id=execution_id,
        )

    def cancel(self, execution_id: str) -> bool:
        process = self._running.get(execution_id)
        if process is None:
            return False
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        self._running.pop(execution_id, None)
        temp_path = self._temp_prompt_files.pop(execution_id, None)
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        self._completed[execution_id] = ExecutionResult(
            status=ExecutionStatus.CANCELLED,
            execution_id=execution_id,
        )
        return True

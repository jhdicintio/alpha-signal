"""Shared fixtures and helpers for the test suite."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx


def make_response(json_data: dict | None = None, text: str = "") -> httpx.Response:
    """Build a fake :class:`httpx.Response` suitable for patching ``_get``."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.status_code = 200
    return resp

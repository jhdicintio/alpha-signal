"""Abstract base class that every article source must implement."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date

import httpx

from alpha_signal.models.articles import Article

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class BaseSource(ABC):
    """Interface for a scientific-article data source.

    Subclasses must implement :meth:`search` and :meth:`fetch_by_id`.  The base
    class provides a shared :class:`httpx.Client` with sensible defaults and a
    convenience :meth:`_get` wrapper that handles retries and error logging.
    """

    name: str
    base_url: str

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    # -- public interface ----------------------------------------------------

    @abstractmethod
    def search(
        self,
        *,
        query: str | None = None,
        max_results: int | None = 10,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        """Return articles matching *query* and/or in the given date range.

        When *max_results* is None, fetch all matching results by paginating
        until the source returns no more. When *max_results* is an int, return
        at most that many (subject to each source's API limits per request).

        When *query* is None, *date_from* and/or *date_to* must be set; return
        articles in that date range. When *query* is set, search for that term
        and optionally restrict by dates.
        """

    @abstractmethod
    def fetch_by_id(self, identifier: str) -> Article | None:
        """Fetch a single article by its source-specific *identifier*."""

    # -- helpers -------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Issue a GET request against *path* with basic error handling."""
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BaseSource:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"

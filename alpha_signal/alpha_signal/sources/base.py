"""Abstract base class that every article source must implement."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from alpha_signal.models.articles import Article

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_MAX_RETRIES = 5


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP 429 / 5xx and transient connection errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout))


class BaseSource(ABC):
    """Interface for a scientific-article data source.

    Subclasses must implement :meth:`search` and :meth:`fetch_by_id`.  The base
    class provides a shared :class:`httpx.Client` with sensible defaults and a
    convenience :meth:`_get` wrapper that handles retries and error logging.

    Set :attr:`rate_delay` on subclasses to sleep between pagination requests
    (seconds). Defaults to 0 (no delay).
    """

    name: str
    base_url: str
    rate_delay: float = 0.0

    def __init__(self, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._request_count = 0

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

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=60),
        reraise=True,
        before_sleep=lambda rs: logger.warning(
            "Retrying %s (attempt %d) after %s",
            rs.fn.__qualname__ if rs.fn else "request",
            rs.attempt_number,
            rs.outcome.exception() if rs.outcome else "unknown",
        ),
    )
    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        """Issue a GET with retry on 429/5xx and Retry-After support."""
        if self._request_count > 0 and self.rate_delay > 0:
            time.sleep(self.rate_delay)
        self._request_count += 1

        logger.debug("%s GET %s %s", self.name, path, params)
        resp = self._client.get(path, params=params)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                try:
                    wait_secs = int(retry_after)
                except ValueError:
                    wait_secs = 5
                logger.info("Rate limited, sleeping %ds (Retry-After)", wait_secs)
                time.sleep(wait_secs)
            resp.raise_for_status()
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

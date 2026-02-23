"""Abstract base class for article caches."""

from __future__ import annotations

from abc import ABC, abstractmethod

from alpha_signal.models.articles import Article


class BaseArticleCache(ABC):
    """Interface for persisting and retrieving :class:`Article` objects.

    Implementations may use SQLite, Redis, Postgres, etc.  Articles are keyed
    on ``(source, source_id)`` — storing the same key twice overwrites the
    previous record.
    """

    @abstractmethod
    def put(self, article: Article) -> None:
        """Insert or update a single article."""

    @abstractmethod
    def put_many(self, articles: list[Article]) -> None:
        """Insert or update many articles in one transaction."""

    @abstractmethod
    def get(self, source: str, source_id: str) -> Article | None:
        """Retrieve an article by its source key, or ``None`` if absent."""

    @abstractmethod
    def contains(self, source: str, source_id: str) -> bool:
        """Return ``True`` if the cache holds an article with this key."""

    @abstractmethod
    def count(self) -> int:
        """Return the total number of cached articles."""

    @abstractmethod
    def all(self) -> list[Article]:
        """Return every cached article."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all articles from the cache."""

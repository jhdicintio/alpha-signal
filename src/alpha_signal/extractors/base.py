"""Abstract base class that every LLM extractor must implement."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Interface for extracting structured data from article abstracts.

    Subclasses wrap a specific LLM provider (OpenAI, Anthropic, etc.) and
    must implement :meth:`extract`, which takes an :class:`Article` and
    returns an :class:`ArticleExtraction`.
    """

    name: str

    @abstractmethod
    def extract(self, article: Article) -> ArticleExtraction:
        """Parse the abstract of *article* into a structured extraction."""

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

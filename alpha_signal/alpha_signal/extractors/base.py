"""Abstract base class that every LLM extractor must implement."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from alpha_signal.models.articles import Article
from alpha_signal.models.extractions import ArticleExtraction

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a scientific-article analyst specializing in identifying commercially \
relevant technologies and trends.  Your job is to extract structured \
information from scientific article abstracts that could inform investment \
and trading decisions.

For each abstract you receive, extract:

1. TECHNOLOGIES — Identify specific technologies, materials, methods, or \
innovations mentioned.
   • technology: the precise name (e.g. "solid-state lithium-sulfur batteries")
   • sector: the broad market sector (e.g. "Energy Storage", "Quantum Computing", \
"Biotechnology", "Semiconductors", "Artificial Intelligence", "Aerospace")
   • maturity: how close to commercial reality — theoretical, lab_scale, pilot, \
or commercial
   • relevance: one sentence on why this matters commercially

2. CLAIMS — Key quantitative or qualitative findings.

3. NOVELTY — Is this research novel, incremental, or a review?

4. SENTIMENT — Is the overall tone optimistic, neutral, cautious, or negative?

5. SUMMARY — One sentence focused on commercial / trading relevance.

Guidelines:
• Only extract technologies that are *explicitly* mentioned in the abstract.
• Do NOT infer or speculate about technologies not discussed.
• If the abstract has no commercially relevant technologies, return an empty \
technologies list.
• Be precise with maturity levels — most academic research is theoretical or \
lab_scale.
• Prefer specificity: "perovskite tandem solar cells" is better than "solar energy".\
"""


def build_user_message(article: Article) -> str:
    """Build the user-message content from an article for LLM extraction."""
    parts = [f"Title: {article.title}"]
    if article.venue:
        parts.append(f"Venue: {article.venue}")
    if article.publication_date:
        parts.append(f"Date: {article.publication_date.isoformat()}")
    parts.append(f"\nAbstract:\n{article.abstract}")
    return "\n".join(parts)


class BaseExtractor(ABC):
    """Interface for extracting structured data from article abstracts.

    Subclasses wrap a specific LLM provider (OpenAI, Anthropic, etc.) and
    must implement :meth:`extract`, which takes an :class:`Article` and
    returns an :class:`ArticleExtraction`. When *system_prompt* is provided,
    it overrides the default :data:`SYSTEM_PROMPT` for that call.
    """

    name: str

    @abstractmethod
    def extract(self, article: Article, system_prompt: str | None = None) -> ArticleExtraction:
        """Parse the abstract of *article* into a structured extraction.

        If *system_prompt* is None, use the default :data:`SYSTEM_PROMPT`.
        """

    async def extract_async(
        self, article: Article, system_prompt: str | None = None
    ) -> ArticleExtraction:
        """Async version of :meth:`extract`.

        Subclasses should override this with a native async implementation.
        The default falls back to running the sync method in a thread executor.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.extract(article, system_prompt=system_prompt)
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

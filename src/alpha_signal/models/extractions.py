"""Structured extraction schema for LLM-parsed article abstracts.

Pydantic models are used here (rather than dataclasses) because OpenAI's
structured-output API can enforce a pydantic-derived JSON schema at decode
time, guaranteeing the LLM response conforms to this shape.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Maturity(str, Enum):
    """How close a technology is to commercial reality."""

    theoretical = "theoretical"
    lab_scale = "lab_scale"
    pilot = "pilot"
    commercial = "commercial"


class Novelty(str, Enum):
    """Whether the research presents something new."""

    novel = "novel"
    incremental = "incremental"
    review = "review"


class Sentiment(str, Enum):
    """Overall tone of the abstract regarding its results."""

    optimistic = "optimistic"
    neutral = "neutral"
    cautious = "cautious"
    negative = "negative"


class TechnologyMention(BaseModel):
    """A specific technology identified in an abstract, placed within a
    two-level hierarchy: broad *sector* and narrower *technology*."""

    technology: str = Field(
        description=(
            "The specific technology, material, method, or innovation mentioned. "
            "Examples: 'solid-state lithium-sulfur batteries', 'topological qubits', "
            "'CAR-T cell therapy', 'extreme ultraviolet lithography'."
        ),
    )
    sector: str = Field(
        description=(
            "The broad market sector this technology falls under. "
            "Examples: 'Energy Storage', 'Quantum Computing', 'Biotechnology', "
            "'Semiconductors', 'Artificial Intelligence', 'Aerospace'."
        ),
    )
    maturity: Maturity = Field(
        description="How close this technology is to commercial deployment.",
    )
    relevance: str = Field(
        description=(
            "One sentence on why this technology might matter commercially — "
            "e.g. 'Could displace current lithium-ion batteries in EVs if scaled.'"
        ),
    )


class Claim(BaseModel):
    """A key finding or result stated in the abstract."""

    statement: str = Field(
        description="The finding in plain language, e.g. 'achieved 23.7% power conversion efficiency'.",
    )
    quantitative: bool = Field(
        description="True if the claim includes a measurable numeric result.",
    )


class ArticleExtraction(BaseModel):
    """The complete structured extraction from a single article abstract."""

    technologies: list[TechnologyMention] = Field(
        default_factory=list,
        description=(
            "Technologies, materials, or innovations mentioned in the abstract. "
            "Empty list if nothing commercially relevant is discussed."
        ),
    )
    claims: list[Claim] = Field(
        default_factory=list,
        description="Key findings or results stated in the abstract.",
    )
    novelty: Novelty = Field(
        description="Whether this research is novel, incremental, or a review.",
    )
    sentiment: Sentiment = Field(
        description="Overall tone of the abstract regarding its findings.",
    )
    summary: str = Field(
        description=(
            "A one-sentence plain-English summary focused on commercial or "
            "trading relevance. Example: 'Demonstrates a new solid-state "
            "electrolyte that could make lithium-sulfur batteries viable for "
            "EV applications within 5 years.'"
        ),
    )

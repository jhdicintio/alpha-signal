"""Unit tests for the extraction pydantic models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from alpha_signal.models.extractions import (
    ArticleExtraction,
    Claim,
    Maturity,
    Novelty,
    Sentiment,
    TechnologyMention,
)


class TestTechnologyMention:
    def test_valid_construction(self):
        tech = TechnologyMention(
            technology="solid-state lithium-sulfur batteries",
            sector="Energy Storage",
            maturity=Maturity.lab_scale,
            relevance="Could displace lithium-ion in EVs.",
        )
        assert tech.technology == "solid-state lithium-sulfur batteries"
        assert tech.sector == "Energy Storage"
        assert tech.maturity == Maturity.lab_scale

    def test_maturity_enum_values(self):
        assert Maturity.theoretical.value == "theoretical"
        assert Maturity.lab_scale.value == "lab_scale"
        assert Maturity.pilot.value == "pilot"
        assert Maturity.commercial.value == "commercial"

    def test_invalid_maturity_rejected(self):
        with pytest.raises(ValidationError):
            TechnologyMention(
                technology="test",
                sector="test",
                maturity="mass_production",  # type: ignore[arg-type]
                relevance="test",
            )


class TestClaim:
    def test_quantitative_claim(self):
        claim = Claim(statement="Achieved 23.7% efficiency", quantitative=True)
        assert claim.quantitative is True

    def test_qualitative_claim(self):
        claim = Claim(statement="Shows promising results", quantitative=False)
        assert claim.quantitative is False


class TestArticleExtraction:
    def test_full_extraction(self):
        extraction = ArticleExtraction(
            technologies=[
                TechnologyMention(
                    technology="perovskite tandem solar cells",
                    sector="Renewable Energy",
                    maturity=Maturity.lab_scale,
                    relevance="Could surpass silicon efficiency limits.",
                )
            ],
            claims=[Claim(statement="33.9% power conversion efficiency", quantitative=True)],
            novelty=Novelty.novel,
            sentiment=Sentiment.optimistic,
            summary="New perovskite architecture breaks efficiency record.",
        )
        assert len(extraction.technologies) == 1
        assert extraction.technologies[0].sector == "Renewable Energy"
        assert extraction.novelty == Novelty.novel

    def test_empty_technologies(self):
        extraction = ArticleExtraction(
            technologies=[],
            claims=[],
            novelty=Novelty.review,
            sentiment=Sentiment.neutral,
            summary="General review with no specific technologies.",
        )
        assert extraction.technologies == []

    def test_json_round_trip(self):
        extraction = ArticleExtraction(
            technologies=[
                TechnologyMention(
                    technology="CRISPR-Cas9",
                    sector="Biotechnology",
                    maturity=Maturity.commercial,
                    relevance="Already in clinical trials for gene therapies.",
                )
            ],
            claims=[Claim(statement="90% editing efficiency in vivo", quantitative=True)],
            novelty=Novelty.incremental,
            sentiment=Sentiment.optimistic,
            summary="Improved CRISPR delivery method for in-vivo gene editing.",
        )
        json_str = extraction.model_dump_json()
        restored = ArticleExtraction.model_validate_json(json_str)
        assert restored == extraction

    def test_json_schema_is_generated(self):
        schema = ArticleExtraction.model_json_schema()
        assert "properties" in schema
        assert "technologies" in schema["properties"]
        assert "summary" in schema["properties"]

    def test_rejects_invalid_novelty(self):
        with pytest.raises(ValidationError):
            ArticleExtraction(
                technologies=[],
                claims=[],
                novelty="groundbreaking",  # type: ignore[arg-type]
                sentiment=Sentiment.neutral,
                summary="test",
            )


class TestEnumsSerialiseAsStrings:
    """Verify enums serialise to plain strings (important for OpenAI schema)."""

    def test_maturity_json(self):
        tech = TechnologyMention(
            technology="test", sector="test", maturity=Maturity.pilot, relevance="test"
        )
        data = json.loads(tech.model_dump_json())
        assert data["maturity"] == "pilot"

    def test_novelty_json(self):
        extraction = ArticleExtraction(
            technologies=[],
            claims=[],
            novelty=Novelty.novel,
            sentiment=Sentiment.cautious,
            summary="test",
        )
        data = json.loads(extraction.model_dump_json())
        assert data["novelty"] == "novel"
        assert data["sentiment"] == "cautious"

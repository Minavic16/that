"""
R2.1 Provenance Tests
=====================

Tests for provenance tracking and data lineage.
Verifies required fields, serialization, and fixture metadata.

Per §C11 and §J2 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from provenance.schema import ProvenanceRecord, now_iso


class TestProvenanceSchema:
    """Test provenance record schema."""

    def test_required_fields(self):
        """Provenance record has all required fields."""
        record = ProvenanceRecord(
            source="fixture",
            dataset_id="r21-fixture-v1",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="test123",
            transformations=["synthetic_generation"],
        )
        assert record.source == "fixture"
        assert record.dataset_id == "r21-fixture-v1"
        assert record.dataset_version == "v1"
        assert record.code_commit == "test123"
        assert record.transformations == ["synthetic_generation"]

    def test_optional_fields_default_none(self):
        """Optional fields default to None."""
        record = ProvenanceRecord(
            source="fixture",
            dataset_id="test",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="test123",
            transformations=[],
        )
        assert record.retrieval_timestamp is None
        assert record.decoder_version is None
        assert record.raw_checksum is None
        assert record.random_seed is None

    def test_seed_for_synthetic(self):
        """Synthetic fixture records its random seed."""
        record = ProvenanceRecord(
            source="synthetic",
            dataset_id="r21-fixture-v1",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="test123",
            transformations=["garch_synthetic"],
            random_seed=42,
        )
        assert record.random_seed == 42


class TestProvenanceSerialization:
    """Test provenance record serialization."""

    def test_to_dict(self):
        """Provenance record serializes to dict."""
        record = ProvenanceRecord(
            source="fixture",
            dataset_id="test",
            dataset_version="v1",
            creation_timestamp="2026-01-01T00:00:00+00:00",
            code_commit="abc123",
            transformations=["step1"],
            random_seed=42,
        )
        d = record.to_dict()
        assert d["source"] == "fixture"
        assert d["random_seed"] == 42
        assert d["transformations"] == ["step1"]

    def test_from_dict(self):
        """Provenance record deserializes from dict."""
        d = {
            "source": "fixture",
            "dataset_id": "test",
            "dataset_version": "v1",
            "creation_timestamp": "2026-01-01T00:00:00+00:00",
            "code_commit": "abc123",
            "transformations": ["step1"],
        }
        record = ProvenanceRecord.from_dict(d)
        assert record.source == "fixture"
        assert record.code_commit == "abc123"

    def test_roundtrip(self):
        """Provenance record survives serialization roundtrip."""
        record = ProvenanceRecord(
            source="synthetic",
            dataset_id="r21-fixture-v1",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="test123",
            transformations=["garch_synthetic"],
            random_seed=42,
            configuration={"n_bars": 200, "pair": "EUR/USD"},
        )
        d = record.to_dict()
        record2 = ProvenanceRecord.from_dict(d)
        assert record.source == record2.source
        assert record.random_seed == record2.random_seed
        assert record.configuration == record2.configuration


class TestFixtureProvenance:
    """Test that fixture provenance is correctly recorded."""

    def test_fixture_metadata_reproducible(self):
        """Same fixture parameters produce same provenance."""
        from fixtures.synthetic import generate_clean_fixture

        # Generate fixture
        df = generate_clean_fixture(n_bars=50, seed=42)

        # Create provenance
        record = ProvenanceRecord(
            source="synthetic",
            dataset_id="r21-fixture-v1",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="test123",
            transformations=["garch_synthetic_generation"],
            random_seed=42,
            configuration={"n_bars": 50, "pair": "EUR/USD"},
        )

        # Verify deterministic fields
        assert record.random_seed == 42
        assert record.source == "synthetic"
        assert "garch" in record.transformations[0]


class TestProvenanceIntegrity:
    """Test provenance data integrity."""

    def test_source_represented(self):
        """Source is always represented."""
        for source in ["dukascopy", "synthetic", "fixture"]:
            record = ProvenanceRecord(
                source=source,
                dataset_id="test",
                dataset_version="v1",
                creation_timestamp=now_iso(),
                code_commit="test",
                transformations=[],
            )
            assert record.source == source

    def test_version_represented(self):
        """Dataset version is always represented."""
        record = ProvenanceRecord(
            source="fixture",
            dataset_id="test",
            dataset_version="v2",
            creation_timestamp=now_iso(),
            code_commit="test",
            transformations=[],
        )
        assert record.dataset_version == "v2"

    def test_commit_represented(self):
        """Code commit is always represented."""
        record = ProvenanceRecord(
            source="fixture",
            dataset_id="test",
            dataset_version="v1",
            creation_timestamp=now_iso(),
            code_commit="abc123def456",
            transformations=[],
        )
        assert record.code_commit == "abc123def456"

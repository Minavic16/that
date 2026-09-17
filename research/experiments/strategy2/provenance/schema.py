"""
R2.1 Provenance Schema
======================

Data lineage and provenance tracking for R2.1 research datasets.
Every canonical dataset must be traceable through this schema.

Per §C11 and §J2 of R2.1_CRITICAL_INFRASTRUCTURE_SPEC.md.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ProvenanceRecord:
    """Provenance record for a research dataset.

    Required fields are marked. Optional fields use None when not applicable
    (e.g., synthetic fixtures have no raw checksum).
    """

    # Identity
    source: str                          # REQUIRED: "dukascopy", "synthetic", "fixture"
    dataset_id: str                      # REQUIRED: e.g. "dukascopy-4h-20p", "r21-fixture-v1"
    dataset_version: str                 # REQUIRED: e.g. "v1", "v2"

    # Temporal
    creation_timestamp: str              # REQUIRED: ISO 8601 UTC

    # Provenance
    code_commit: str                     # REQUIRED: git commit hash
    transformations: list[str]           # REQUIRED: list of transformation steps

    # Optional provenance fields
    retrieval_timestamp: Optional[str] = None    # When data was retrieved (Dukascopy)
    decoder_version: Optional[str] = None        # Decoder version (Dukascopy)
    raw_checksum: Optional[str] = None           # SHA-256 of raw source file
    random_seed: Optional[int] = None            # Seed for synthetic fixtures
    schema_version: str = "1.0"                  # Schema version
    configuration: dict = field(default_factory=dict)  # Relevant config

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON storage."""
        return {
            "source": self.source,
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "creation_timestamp": self.creation_timestamp,
            "code_commit": self.code_commit,
            "transformations": self.transformations,
            "retrieval_timestamp": self.retrieval_timestamp,
            "decoder_version": self.decoder_version,
            "raw_checksum": self.raw_checksum,
            "random_seed": self.random_seed,
            "schema_version": self.schema_version,
            "configuration": self.configuration,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProvenanceRecord:
        """Deserialize from dictionary."""
        return cls(
            source=d["source"],
            dataset_id=d["dataset_id"],
            dataset_version=d["dataset_version"],
            creation_timestamp=d["creation_timestamp"],
            code_commit=d["code_commit"],
            transformations=d["transformations"],
            retrieval_timestamp=d.get("retrieval_timestamp"),
            decoder_version=d.get("decoder_version"),
            raw_checksum=d.get("raw_checksum"),
            random_seed=d.get("random_seed"),
            schema_version=d.get("schema_version", "1.0"),
            configuration=d.get("configuration", {}),
        )


def compute_file_checksum(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()

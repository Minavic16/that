"""Provenance + research ledger (experiment-agnostic).

Dependency: evaluation -> provenance -> reporting (later).
Must not import production.* or Strategy 2 modules.
"""
from nestquant.research.shared.provenance.builder import build_provenance
from nestquant.research.shared.provenance.contracts import (
    DataIdentity,
    GitIdentity,
    Provenance,
)
from nestquant.research.shared.provenance.identity import (
    canonical_json,
    config_hash,
    get_git_commit,
    get_git_dirty,
    new_run_id,
    now_iso,
)
from nestquant.research.shared.provenance.ledger import (
    DEFAULT_LEDGER_PATH,
    LedgerEntry,
    ResearchLedger,
)

__all__ = [
    "DEFAULT_LEDGER_PATH",
    "DataIdentity",
    "GitIdentity",
    "LedgerEntry",
    "Provenance",
    "ResearchLedger",
    "build_provenance",
    "canonical_json",
    "config_hash",
    "get_git_commit",
    "get_git_dirty",
    "new_run_id",
    "now_iso",
]

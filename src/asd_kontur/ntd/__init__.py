"""Permanent official normative-technical documentation platform memory."""

from .identifiers import NormalizedNormativeIdentifier, normalize_identifier
from .manifest import (
    NTD_SEED_MANIFEST_PROFILE_VERSION,
    PracticeGuideNormativeReference,
    PracticeGuideNtdSeedManifest,
    build_seed_manifest,
)

__all__ = [
    "NTD_SEED_MANIFEST_PROFILE_VERSION",
    "NormalizedNormativeIdentifier",
    "PracticeGuideNormativeReference",
    "PracticeGuideNtdSeedManifest",
    "build_seed_manifest",
    "normalize_identifier",
]

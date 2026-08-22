"""Provider-neutral, Candidate-only AI/VLM verification harness."""

from .errors import HarnessError, HarnessErrorCode
from .models import (
    CandidateStatus,
    CandidateVersion,
    ExecutionIdentity,
    ExecutionRequest,
    FieldCandidate,
    Locator,
    ProviderExecutionResult,
    Route,
    Scope,
)

__all__ = [
    "CandidateStatus",
    "CandidateVersion",
    "ExecutionIdentity",
    "ExecutionRequest",
    "FieldCandidate",
    "HarnessError",
    "HarnessErrorCode",
    "Locator",
    "ProviderExecutionResult",
    "Route",
    "Scope",
]

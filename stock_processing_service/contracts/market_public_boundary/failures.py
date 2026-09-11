from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MarketBoundaryFailure:
    failure_type: str
    message: str
    details: tuple[tuple[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.failure_type, str) or not self.failure_type:
            raise ValueError("failure_type must be a non-empty string")
        if not isinstance(self.message, str):
            raise ValueError("message must be a string")


def _typed_failure(failure_type: str):
    def decorate(cls):
        def initialize(self, message: str, details=()) -> None:
            MarketBoundaryFailure.__init__(self, failure_type, message, tuple(details))

        cls.__init__ = initialize
        return cls

    return decorate


@_typed_failure("MarketUnavailable")
class MarketUnavailable(MarketBoundaryFailure):
    pass


@_typed_failure("MarketNotReady")
class MarketNotReady(MarketBoundaryFailure):
    pass


@_typed_failure("MarketContractMismatch")
class MarketContractMismatch(MarketBoundaryFailure):
    pass


@_typed_failure("MarketReleaseMismatch")
class MarketReleaseMismatch(MarketBoundaryFailure):
    pass


@_typed_failure("MarketObjectNotFound")
class MarketObjectNotFound(MarketBoundaryFailure):
    pass


@_typed_failure("MarketEvidenceUnavailable")
class MarketEvidenceUnavailable(MarketBoundaryFailure):
    pass


@_typed_failure("MarketProvenanceIncomplete")
class MarketProvenanceIncomplete(MarketBoundaryFailure):
    pass


@_typed_failure("MarketAnalysisPending")
class MarketAnalysisPending(MarketBoundaryFailure):
    pass


@_typed_failure("MarketAnalysisPartial")
class MarketAnalysisPartial(MarketBoundaryFailure):
    pass


@_typed_failure("MarketAnalysisStale")
class MarketAnalysisStale(MarketBoundaryFailure):
    pass


@_typed_failure("MarketAnalysisFailed")
class MarketAnalysisFailed(MarketBoundaryFailure):
    pass


@_typed_failure("MarketGovernanceFailure")
class MarketGovernanceFailure(MarketBoundaryFailure):
    pass


@_typed_failure("MarketAuthorizationDenied")
class MarketAuthorizationDenied(MarketBoundaryFailure):
    pass


@_typed_failure("MarketTimeout")
class MarketTimeout(MarketBoundaryFailure):
    pass


@_typed_failure("MarketInternalFailure")
class MarketInternalFailure(MarketBoundaryFailure):
    pass

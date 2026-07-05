"""M8 Phase 0 read-only market cognition services."""

from .knowledge_evidence import MarketEvidenceAdapter, MarketKnowledgeBundleBuilder
from .cognition import Phase0CognitionPipeline
from .replay import BacktestPendingRecord, MarketCognitionReplay, build_pairs
from .validation_dataset import MarketThesisValidationDataset
from .verification import MarketThesisVerificationService
from .hypothesis_source_store import FrozenHypothesisSourceStore
from .calibration import CalibrationMetricsService, CalibrationReport
from .phase1_gate import Phase1GateEvaluator, Phase1GateReport, write_graduation_report
from .registry import MarketThesisRegistry, RegistryEntry

__all__ = [
    "MarketEvidenceAdapter",
    "MarketKnowledgeBundleBuilder",
    "Phase0CognitionPipeline",
    "BacktestPendingRecord",
    "MarketCognitionReplay",
    "build_pairs",
    "MarketThesisValidationDataset",
    "MarketThesisVerificationService",
    "FrozenHypothesisSourceStore",
    "CalibrationMetricsService",
    "CalibrationReport",
    "Phase1GateEvaluator",
    "Phase1GateReport",
    "write_graduation_report",
    "MarketThesisRegistry",
    "RegistryEntry",
]

"""Phase2 T01 semantic matcher unit tests on real 76-case dataset.

Goal:
- Use the real validation dataset (76 samples) to calibrate threshold split point.
- Verify fixed threshold vs scanned best threshold.
- Provide strong/candidate/weak segmentation evidence from real similarity data.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from theme_service.matchers.semantic_matcher import TransformerSemanticMatcher


DATASET_PATH = Path("evaluate_service/data/raw/validation_dataset.json")
REPORT_PATH = Path("tmp/phase2_t01_threshold_scan.json")
LOCAL_MODEL_PATH = Path("models/text2vec-base-chinese")
FULL_DATASET_SIZE = 76
SAMPLE_COUNT = int(os.getenv("PHASE2_THRESHOLD_SAMPLE", "10"))


def _load_cases() -> list[dict[str, Any]]:
    assert DATASET_PATH.exists(), f"dataset not found: {DATASET_PATH}"
    data = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list), "validation_dataset must be list"
    assert len(data) >= FULL_DATASET_SIZE, f"expected >={FULL_DATASET_SIZE} samples, got {len(data)}"
    assert 1 <= SAMPLE_COUNT <= FULL_DATASET_SIZE, (
        f"PHASE2_THRESHOLD_SAMPLE must be in [1,{FULL_DATASET_SIZE}], got {SAMPLE_COUNT}"
    )
    return data[:SAMPLE_COUNT]


def _extract_label(item: dict[str, Any]) -> str:
    gts = item.get("ground_truth_themes") or []
    if isinstance(gts, list) and gts:
        return str(gts[0]).strip()
    return str(item.get("theme", "")).strip()


def _extract_text(item: dict[str, Any]) -> str:
    title = str(item.get("title", "")).strip()
    content = str(item.get("content", "")).strip()
    return f"{title} {content}".strip()


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(v))
    if norm == 0.0:
        return v
    return v / norm


def _build_real_matcher() -> TransformerSemanticMatcher:
    assert LOCAL_MODEL_PATH.exists(), f"local model not found: {LOCAL_MODEL_PATH}"
    matcher = TransformerSemanticMatcher(
        {
            "model_name": str(LOCAL_MODEL_PATH),
            "semantic_threshold": 0.95,
            "enable_ai_boost": False,
            "max_results": 10,
        }
    )
    # Force loading semantic model; test must not rely on random fallback.
    matcher._load_semantic_model()
    assert matcher.model is not None, "semantic model is not loaded; cannot run real 76-case calibration"
    return matcher


def _pair_arrays(embeddings: np.ndarray, labels: list[str]) -> tuple[np.ndarray, np.ndarray]:
    sim = embeddings @ embeddings.T
    n = len(labels)
    label_arr = np.array(labels, dtype=object)
    same = (label_arr[:, None] == label_arr[None, :]).astype(np.int32)
    tri = np.triu_indices(n, k=1)
    pair_sim = sim[tri]
    pair_y = same[tri]
    return pair_sim, pair_y


def _metrics_at_threshold(pair_sim: np.ndarray, pair_y: np.ndarray, threshold: float) -> dict[str, float]:
    pred = pair_sim >= threshold
    tp = int(np.sum((pred == 1) & (pair_y == 1)))
    fp = int(np.sum((pred == 1) & (pair_y == 0)))
    fn = int(np.sum((pred == 0) & (pair_y == 1)))
    tn = int(np.sum((pred == 0) & (pair_y == 0)))

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    tpr = recall
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {
        "threshold": float(threshold),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "tpr": float(tpr),
        "fpr": float(fpr),
        "youden_j": float(tpr - fpr),
    }


def _scan_best_threshold(pair_sim: np.ndarray, pair_y: np.ndarray) -> tuple[dict[str, float], dict[str, float]]:
    t_min = float(np.min(pair_sim))
    t_max = float(np.max(pair_sim))
    grid = np.linspace(t_min, t_max, 200)

    best: dict[str, float] | None = None
    for t in grid:
        m = _metrics_at_threshold(pair_sim, pair_y, float(t))
        if best is None or m["f1"] > best["f1"]:
            best = m

    assert best is not None
    fixed = _metrics_at_threshold(pair_sim, pair_y, 0.95)
    return best, fixed


def _segment_quality(pair_sim: np.ndarray, pair_y: np.ndarray, center: float, margin: float = 0.03) -> dict[str, Any]:
    strong_mask = pair_sim >= (center + margin)
    candidate_mask = (pair_sim >= (center - margin)) & (pair_sim < (center + margin))
    weak_mask = pair_sim < (center - margin)

    def _rate(mask: np.ndarray) -> float:
        if int(np.sum(mask)) == 0:
            return 0.0
        return float(np.mean(pair_y[mask]))

    return {
        "strong_count": int(np.sum(strong_mask)),
        "candidate_count": int(np.sum(candidate_mask)),
        "weak_count": int(np.sum(weak_mask)),
        "strong_positive_rate": _rate(strong_mask),
        "candidate_positive_rate": _rate(candidate_mask),
        "weak_positive_rate": _rate(weak_mask),
    }


def _run_real_76_calibration() -> dict[str, Any]:
    cases = _load_cases()
    labels = [_extract_label(c) for c in cases]
    texts = [_extract_text(c) for c in cases]
    assert all(labels), "empty label exists in 76-case dataset"
    assert all(texts), "empty text exists in 76-case dataset"

    matcher = _build_real_matcher()
    embeddings = []
    for text in texts:
        vec = np.asarray(matcher._encode_text(text), dtype=float)
        vec = _l2_normalize(vec)
        embeddings.append(vec)
    emb = np.vstack(embeddings)

    pair_sim, pair_y = _pair_arrays(emb, labels)
    best, fixed = _scan_best_threshold(pair_sim, pair_y)
    seg = _segment_quality(pair_sim, pair_y, best["threshold"], margin=0.03)

    report = {
        "dataset_path": str(DATASET_PATH),
        "sample_count": len(cases),
        "sample_count_target": SAMPLE_COUNT,
        "is_full_dataset": SAMPLE_COUNT == FULL_DATASET_SIZE,
        "theme_count": len(set(labels)),
        "pair_count": int(len(pair_sim)),
        "positive_pair_count": int(np.sum(pair_y == 1)),
        "negative_pair_count": int(np.sum(pair_y == 0)),
        "best_threshold_by_f1": best,
        "fixed_threshold_0_95": fixed,
        "segmentation": seg,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def test_t01_fixed_threshold_sensitivity_tc_p1p2_001():
    """TC-P1P2-001: scan threshold on real 76 cases and compare fixed 0.95 baseline."""
    report = _run_real_76_calibration()
    best = report["best_threshold_by_f1"]
    fixed = report["fixed_threshold_0_95"]

    assert report["sample_count"] == SAMPLE_COUNT
    assert 0.0 <= best["threshold"] <= 1.0
    assert best["f1"] >= fixed["f1"], "best threshold should not underperform fixed 0.95"
    assert Path(REPORT_PATH).exists(), "threshold scan report not generated"


def test_t01_semantic_score_segmentation_tc_p1p2_006():
    """TC-P1P2-006: strong/candidate/weak segmentation quality on real 76 cases."""
    report = _run_real_76_calibration()
    seg = report["segmentation"]

    assert seg["strong_count"] > 0, "strong segment is empty"
    assert seg["candidate_count"] > 0, "candidate segment is empty"
    # Quick mode (10 samples) may have no weak tail; full mode should have all buckets.
    if report.get("is_full_dataset"):
        assert seg["weak_count"] > 0, "weak segment is empty in full 76-case run"
    assert seg["strong_positive_rate"] >= seg["candidate_positive_rate"], (
        "segmentation invalid: strong positive rate should be >= candidate positive rate"
    )
    if seg["weak_count"] > 0:
        assert seg["candidate_positive_rate"] >= seg["weak_positive_rate"], (
            "segmentation invalid: candidate positive rate should be >= weak positive rate"
        )

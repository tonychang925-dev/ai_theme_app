import json
import os
from pathlib import Path

import pytest

from model_service.services.model_service import ModelService


DATASET_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/validation_dataset.json")
OUTPUT_JSON = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_model_service_5.preview.json")


def _load_samples(limit: int = 5) -> list[dict]:
    rows = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    out = []
    for row in rows[:limit]:
        out.append(
            {
                "news_id": row["test_id"],
                "title": row["title"],
                "content": row["content"],
                "date": row.get("date"),
                "source": "validation_dataset",
            }
        )
    return out


@pytest.mark.asyncio
async def test_model_service_outputs_phase0_structured_events_from_real_dataset():
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    service = ModelService()
    assert service.event_extractor is not None

    samples = _load_samples(5)
    results = []
    for sample in samples:
        result = await service.extract_event(sample)
        assert result["status"] == "success"
        payload = result["response"]
        assert payload["event_type"]
        assert payload["summary"]
        assert "theme_discovery_directive" in payload
        assert payload["theme_discovery_directive"]["action"] == ""
        assert isinstance(payload["entities"], list)
        assert isinstance(payload["evidence_set"], dict)
        assert "structuring_version" in payload
        results.append(
            {
                "news_id": sample["news_id"],
                "event_type": payload["event_type"],
                "summary": payload["summary"],
                "confidence": payload["confidence"],
                "structuring_version": payload["structuring_version"],
            }
        )

    OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    assert OUTPUT_JSON.exists()

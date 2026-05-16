import pytest

from database_service.streams.handlers.DecisionExecutor import DecisionExecutor


class _FakeGateway:
    def __init__(self):
        self.calls = []

    async def upsert_event_subject_relation(self, event_id, subject_key, **kwargs):
        self.calls.append((event_id, subject_key, kwargs))
        return {"id": 101, "event_id": event_id, "subject_key": subject_key}


@pytest.mark.asyncio
async def test_update_theme_match_writes_subject_map_without_theme_master_id():
    gateway = _FakeGateway()
    executor = DecisionExecutor(redis_client=None, db_gateway=gateway, consumer_name="unit")

    await executor._execute_update_theme_fixed(
        {
            "event_id": 42,
            "action": "update_theme",
            "operations": ["create_mapping"],
            "confidence": 0.86,
            "reason": "profile_hit",
            "source": "structured_theme_match",
            "theme_data": {
                "subject_key": "9030409",
                "name": "AR眼镜",
                "id": None,
            },
            "match_result": {
                "decision": "MATCH",
                "matched_subject_key": "9030409",
                "matched_theme_name": "AR眼镜",
                "matched_theme_id": None,
                "audit": {"top_candidates": []},
            },
        }
    )

    assert len(gateway.calls) == 1
    event_id, subject_key, kwargs = gateway.calls[0]
    assert event_id == 42
    assert subject_key == "9030409"
    assert kwargs["subject_name"] == "AR眼镜"
    assert kwargs["confidence"] == 0.86
    assert kwargs["relation_type"] == "primary"
    assert executor.stats["mappings_created"] == 1


@pytest.mark.asyncio
async def test_update_theme_match_writes_related_subject_maps():
    gateway = _FakeGateway()
    executor = DecisionExecutor(redis_client=None, db_gateway=gateway, consumer_name="unit")

    await executor._execute_update_theme_fixed(
        {
            "event_id": 42,
            "action": "update_theme",
            "operations": ["create_mapping"],
            "confidence": 0.86,
            "reason": "profile_hit",
            "source": "structured_theme_match",
            "theme_data": {
                "subject_key": "9030409",
                "name": "AR眼镜",
                "id": None,
            },
            "match_result": {
                "decision": "MATCH",
                "matched_subject_key": "9030409",
                "matched_theme_name": "AR眼镜",
                "matched_theme_id": None,
                "related_matches": [
                    {
                        "subject_key": "9059919",
                        "theme_name": "SpaceX",
                        "confidence": 0.78,
                        "relation_type": "related",
                        "reason": "top_candidate_evidence_related",
                    }
                ],
                "audit": {"top_candidates": []},
            },
        }
    )

    assert [(call[1], call[2]["relation_type"]) for call in gateway.calls] == [
        ("9030409", "primary"),
        ("9059919", "related"),
    ]
    assert gateway.calls[1][2]["subject_name"] == "SpaceX"
    assert gateway.calls[1][2]["confidence"] == 0.78
    assert executor.stats["mappings_created"] == 2

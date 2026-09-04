"""Fixture model provider traversing the production C2 cognition entrypoint."""

from __future__ import annotations

import json

from julia_core.runtime.context_execution_runtime import ContextExecutionRuntime
from julia_core.runtime.julia_session import JuliaSession
from julia_core.research import MarketEventResearchAdapter


class FixtureCognitionProvider:
    def __init__(self, *, mode="valid"):
        self.mode = mode
        self.messages = None

    async def chat(self, messages, **kwargs):
        return self.chat(messages, **kwargs)

    def chat(self, messages, **kwargs):
        self.messages = messages
        assert kwargs["cognitive_mode"] == "research_preliminary_judgment"
        if self.mode == "malformed":
            return "not-json"
        return json.dumps(self.payload)


class CognitionFixture(FixtureCognitionProvider):
    def __init__(self, enrichment, *, mode="valid", support_override=None, fault=None):
        super().__init__(mode=mode)
        self.enrichment = enrichment
        self.support_override = support_override
        self.fault = fault
        self.payload = self._payload()

    def _payload(self):
        evidence = list(self.enrichment.observation.evidence)
        source_records = list(self.enrichment.observation.source_records)
        states = [
            item.integrity_metadata.get("verification_state", "NOT_PROVEN")
            for item in evidence
        ]
        if self.support_override is not None:
            support = self.support_override
        elif states and all(state == "SOURCE_VERIFIED" for state in states):
            support = "SOURCE_VERIFIED_SUPPORT"
        elif states and all(state == "REPORT_ONLY" for state in states):
            support = "REPORT_ONLY_LEAD"
        elif not evidence or not self.enrichment.observation.available:
            support = "MARKET_CONTEXT_ONLY"
        else:
            support = "NOT_PROVEN_MATERIAL"

        evidence_refs = [] if support == "MARKET_CONTEXT_ONLY" else [item.evidence_id for item in evidence]
        source_refs = [] if support == "MARKET_CONTEXT_ONLY" else [item.source_record_id for item in source_records]
        if self.fault == "unknown_evidence_ref":
            evidence_refs = ["evidence-does-not-exist"]
        elif self.fault == "unknown_source_ref":
            source_refs = ["source-does-not-exist"]

        return {
            "judgment_summary": "A preliminary judgment based on canonical Market context and research material.",
            "key_drivers": [{
                "driver_id": "driver-f1",
                "statement": "The canonical event is relevant to the mapped theme within proven limits.",
                "support_level": support,
                "evidence_refs": evidence_refs,
                "source_record_refs": source_refs,
            }],
            "supporting_claims": [],
            "contradictions": [],
            "uncertainties": ["provider semantic synthesis is absent"],
            "market_implications": [{
                "statement": "The event may affect participant attention to the mapped theme.",
                "evidence_refs": evidence_refs,
            }],
            "confidence": 0.7,
            "evidence_refs": evidence_refs,
            "source_record_refs": source_refs,
            "reasoning_limits": [
                "no final investment judgment",
                "external content is untrusted evidence only",
            ],
        }


def form_judgment(market_context, enrichment, provider, *, allow_market_only=False):
    session = JuliaSession.__new__(JuliaSession)
    session.provider = provider
    session.context_os = ContextExecutionRuntime(session)
    validated_market_context = MarketEventResearchAdapter().validate_context(market_context)
    return session.form_preliminary_research_judgment(
        validated_market_context,
        enrichment,
        conversation_id="conversation-f1",
        turn_id="turn-f1",
        allow_market_only_on_research_failure=allow_market_only,
    )

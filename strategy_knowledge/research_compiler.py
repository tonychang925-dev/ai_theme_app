"""M3.2.7 Strategy Research Compiler — Card → ResearchPlan (deterministic).

Bridge between StrategyCard and CapabilityManager.
Translates: strategy-level required_data → typed CapabilityRequests.
No LLM. Pure structured compilation.

Usage:
  compiler = StrategyResearchCompiler(requirement_registry)
  plan = compiler.compile(card, context)
  # plan.capability_requests can be executed by CapabilityManager
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

CST = timezone(timedelta(hours=8))


# ── Requirement Registry (maps required_data names → capability args) ───────

REQUIREMENT_REGISTRY: dict[str, dict] = {
    "leader_5d_return": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "total_return"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_drawdown_from_peak": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "max_drawdown_from_peak"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "leader_volume_pattern": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "volume_trend"},
        "output": {"type": "categorical", "values": ["contracting", "normal", "elevated", "heavy_selling"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "key_level_status": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
            "lookback_sessions": 5,
        },
        "derive": {"metric": "key_level_status"},
        "output": {"type": "categorical", "values": ["intact", "testing", "broken"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "peer_relative_strength": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "relative_strength_rank"},
        "output": {"type": "list[dict]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "theme_breadth_change": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "breadth_change"},
        "output": {"type": "categorical", "values": ["contracting", "stable", "expanding"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "capital_persistence": {
        "capability": "market.theme.capital",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "capital_flow_trend"},
        "output": {"type": "categorical", "values": ["outflow", "persistent", "increasing"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "new_leader_candidates": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "emerging_leaders"},
        "output": {"type": "list[str]"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },

    # weak_to_strong requirements
    "auction_strength": {
        "capability": "market.stock.auction",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "auction_trend"},
        "output": {"type": "categorical", "values": ["high_open_scramble", "flat", "weak"]},
        "missing_policy": "DATA_UNAVAILABLE",
    },
    "open_gap": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "open_gap_vs_prev_close"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "intraday_volume": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "intraday_volume_vs_prev"},
        "output": {"type": "categorical", "values": ["amplified", "normal", "contracting"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "limit_up_seal_quality": {
        "capability": "market.stock.history",
        "arguments": {
            "stock_code": "$subject.leader_code",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "limit_up_seal"},
        "output": {"type": "categorical", "values": ["decisive", "weak", "no_seal"]},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
    "peer_follow_through": {
        "capability": "market.theme.constituents",
        "arguments": {
            "subject_key": "$subject.subject_key",
            "as_of": "$subject.trade_date",
        },
        "derive": {"metric": "peer_limit_up_ratio"},
        "output": {"type": "number", "unit": "ratio"},
        "missing_policy": "INSUFFICIENT_EVIDENCE",
    },
}


# ── Models ──────────────────────────────────────────────────────────────────

@dataclass
class ResearchPlan:
    research_case_id: str = field(default_factory=lambda: f"rc_{uuid4().hex}")
    subject_key: str = ""
    subject_name: str = ""
    trade_date: str = ""
    triggered_card: str = ""
    candidate_hypotheses: list[dict] = field(default_factory=list)
    capability_requests: list[dict] = field(default_factory=list)
    research_questions: list[dict] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(CST).isoformat())


# ── Compiler ────────────────────────────────────────────────────────────────

class StrategyResearchCompiler:
    """Compiles StrategyCard + SubjectContext → executable ResearchPlan.

    Deterministic. Zero LLM. Translates:
      card.required_data → requirement_registry → typed CapabilityRequests
      card.possible_states → candidate_hypotheses (all, untested)
      card.research_questions → included verbatim
    """

    def __init__(self, card_dir: str = ""):
        self.card_dir = Path(card_dir) if card_dir else Path(__file__).resolve().parent / "cards"

    def compile(self, card_id: str, subject: dict) -> ResearchPlan:
        """Compile a ResearchPlan for one subject from one StrategyCard.

        Args:
            card_id: "leader_divergence" | "weak_to_strong" | "theme_lifecycle"
            subject: {
                "subject_key": "9010270",
                "subject_name": "...",
                "trade_date": "2026-07-14",
                "leader_code": "601969",
                "julia_stage": "fading_momentum",
                "workbench_stage": "diffusion"
            }
        """
        card = json.loads((self.card_dir / f"{card_id}.json").read_text(encoding="utf-8"))

        plan = ResearchPlan(
            subject_key=subject["subject_key"],
            subject_name=subject.get("subject_name", ""),
            trade_date=subject.get("trade_date", ""),
            triggered_card=card_id,
        )

        # Step 1: All possible states → untested hypotheses
        for state in card.get("possible_states", []):
            plan.candidate_hypotheses.append({
                "state": f"{card_id}.{state['state']}",
                "canonical_state": state["state"],
                "evidence_pattern": state.get("evidence_pattern", {}),
                "strategy_guidance": {
                    "stance": state.get("action", "observe"),
                    "authority": "advisory_only",
                },
                "status": "untested",
            })

        # Step 2: required_data → CapabilityRequests via registry
        for req_name in card.get("required_data", []):
            spec = REQUIREMENT_REGISTRY.get(req_name)
            if spec is None:
                plan.missing_data.append(req_name)
                continue

            # Resolve template variables (only string templates)
            args = {}
            for k, v in spec.get("arguments", {}).items():
                args[k] = _resolve(str(v), subject) if isinstance(v, str) else v

            plan.capability_requests.append({
                "requirement_id": req_name,
                "capability": spec["capability"],
                "arguments": args,
                "derive": spec.get("derive", {}),
                "output": spec.get("output", {}),
                "missing_policy": spec.get("missing_policy", "INSUFFICIENT_EVIDENCE"),
            })

        # Step 3: Research questions (verbatim from card)
        plan.research_questions = card.get("research_questions", [])

        return plan


def _resolve(template: str, ctx: dict) -> str:
    """Resolve $subject.field references in capability argument templates."""
    result = template
    for k, v in ctx.items():
        result = result.replace(f"$subject.{k}", str(v))
    return result


def compile_for_case001():
    """Test: compile ResearchPlan for the 5 Case001 disagreement subjects."""
    base = Path("/Users/admin/Desktop/ai_theme_app/golden/2026-07-14")
    universe = json.loads((base / "outcomes/baseline_universe.json").read_text(encoding="utf-8"))

    disagreement_keys = universe["disagreement_keys"]
    compiler = StrategyResearchCompiler()

    print("=" * 70)
    print("M3.2.7 — 9010270 ResearchPlan Compilation (Leader Divergence)")
    print("=" * 70)

    for sk in disagreement_keys[:1]:  # First: just 9010270
        s = universe["subjects"].get(sk, {})
        subject = {
            "subject_key": sk,
            "subject_name": s.get("subject_name", ""),
            "trade_date": "2026-07-14",
            "leader_code": s.get("leader_codes", [""])[0] if s.get("leader_codes") else "",
            "julia_stage": s.get("julia_stage", ""),
            "workbench_stage": s.get("workbench_stage", ""),
        }

        plan = compiler.compile("leader_divergence", subject)

        print(f"\nSubject: {sk} ({subject['subject_name']})")
        print(f"  Leader: {subject['leader_code']}")
        print(f"  Julia: {subject['julia_stage']} | Workbench: {subject['workbench_stage']}")
        print(f"  Triggered Card: {plan.triggered_card}")
        print(f"\n  Candidate Hypotheses ({len(plan.candidate_hypotheses)}):")
        for h in plan.candidate_hypotheses:
            print(f"    [{h['status']:10s}] {h['state']:50s} stance={h['strategy_guidance']['stance']}")

        print(f"\n  Capability Requests ({len(plan.capability_requests)}):")
        for cr in plan.capability_requests:
            print(f"    {cr['requirement_id']:30s} → {cr['capability']}")
            print(f"      args: {cr['arguments']}")

        if plan.missing_data:
            print(f"\n  ⚠️  Missing requirements:{plan.missing_data}")

        print(f"\n  Research Questions ({len(plan.research_questions)}):")
        for rq in plan.research_questions:
            print(f"    Q: {rq['question']}")
            print(f"       probes: {', '.join(rq['probes'])}")

    print(f"\n{'=' * 70}")
    print(f"9010270 ResearchPlan compiled. {len(plan.capability_requests)} capability requests generated.")
    print(f"Next: execute via CapabilityManager → EvidenceBundle → Hypothesis Evaluation")
    print("=" * 70)


if __name__ == "__main__":
    compile_for_case001()

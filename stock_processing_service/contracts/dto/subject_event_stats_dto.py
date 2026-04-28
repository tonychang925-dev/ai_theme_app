from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubjectEventStatsDTO:
    """1:1 mapping to ThemeEventStats in enhanced_mainline_judgement_service.

    Carries per-subject event statistics aggregated from news_event + event_theme_map
    + theme_master tables in one go, avoiding N+1 reads in BuildIdentityJob.
    """

    subject_key: str
    theme_name: str
    today_event_count: int
    recent_event_count: int
    distinct_event_days: int
    key_event_count: int
    sample_summaries: list[str] = field(default_factory=list)

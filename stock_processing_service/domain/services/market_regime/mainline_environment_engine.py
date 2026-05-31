"""PR-11F: MainlineEnvironmentEngine — consumes lifecycle reviews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import MainlineEnvironmentReview


@dataclass
class MainlineEnvironmentEngine:
    def build(self, *, lifecycle_reviews: list[dict[str, Any]]) -> MainlineEnvironmentReview:
        tradable: list[dict] = []
        watch: list[dict] = []
        fading: list[dict] = []

        for r in lifecycle_reviews:
            ls = str(r.get("lifecycle_state", ""))
            alive = bool(r.get("mainline_trade_alive"))
            if alive and ls in {"start", "fermentation", "acceleration"}:
                tradable.append(r)
            elif alive and ls in {"divergence", "repair"}:
                tradable.append(r)
            elif ls in {"fade_watch"}:
                watch.append(r)
            elif ls in {"fade_confirmed", "dead"}:
                fading.append(r)

        env = "no_confirmed_mainline"
        if tradable:
            env = "mainline_tradable"
        elif watch:
            env = "mainline_watch_only"
        if fading and not tradable:
            env = "mainline_fading"

        alive_count = sum(1 for r in lifecycle_reviews if r.get("mainline_trade_alive"))
        return MainlineEnvironmentReview(
            confirmed_mainline_count=len(lifecycle_reviews),
            trade_alive_mainline_count=alive_count,
            mainline_environment=env, mainline_environment_score=min(80, alive_count * 25 + 30) if tradable else 20,
            tradable_mainlines=tradable, watch_only_mainlines=watch, fading_mainlines=fading,
        )

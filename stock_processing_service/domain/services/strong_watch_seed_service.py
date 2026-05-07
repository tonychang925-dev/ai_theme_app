from __future__ import annotations

from dataclasses import replace

from stock_processing_service.contracts.dto import SubjectStockPoolDTO


class StrongWatchSeedService:
    @staticmethod
    def _is_disallowed(stock_id: str, stock_name: str) -> bool:
        sid = str(stock_id or "").upper()
        code = sid.split(".", 1)[0]
        if code.startswith("688"):
            return True
        name = str(stock_name or "").strip().upper()
        if name.startswith("ST") or name.startswith("*ST"):
            return True
        return False

    @staticmethod
    def _old_chain_seed_gate(row: SubjectStockPoolDTO, metadata: dict) -> tuple[bool, str]:
        rank = row.pool_rank if row.pool_rank is not None else 999
        is_leader = bool(metadata.get("is_leader") or False)
        limit_up = bool(metadata.get("limit_up") or False)
        recent_limit_up_count = int(metadata.get("recent_limit_up_count") or 0)
        prior7_limitup_days = int(metadata.get("prior7_limitup_days") or 0)
        prior7_strong_days = int(metadata.get("prior7_strong_days") or 0)
        identity_status = str(metadata.get("identity_status") or "").strip().lower()
        is_main_theme = bool(metadata.get("is_main_theme") or False)
        final_mainline_alive = bool(metadata.get("final_mainline_alive") or False)
        fade_watch = bool(metadata.get("fade_watch") or False)
        final_cycle_state = str(metadata.get("final_cycle_state") or "").strip().lower()

        if identity_status != "confirmed" or not is_main_theme:
            return False, "identity_not_confirmed_mainline"
        strong_background = is_leader or limit_up or recent_limit_up_count >= 2 or rank <= 3
        if not strong_background:
            return False, "missing_strong_background"
        if prior7_limitup_days < 1:
            return False, "missing_prior7_limitup_gene"
        if prior7_strong_days < 1:
            return False, "missing_prior7_strong_history"
        if not (
            final_mainline_alive
            or fade_watch
            or final_cycle_state in {"divergence", "repair", "分歧", "修复"}
        ):
            return False, "cycle_not_observable"
        if rank > 20 and not is_leader and not limit_up and recent_limit_up_count < 3:
            return False, "rank_gt_20_without_exception"
        return True, "old_chain_static_gate"

    def seed(self, pool_rows: list[SubjectStockPoolDTO]) -> list[SubjectStockPoolDTO]:
        # Keep strong-pool candidates with old-chain compatible hard gates:
        # old-chain static gate + independent strong-gene seed + 688/ST exclusion + dedupe.
        selected: dict[str, SubjectStockPoolDTO] = {}
        for row in pool_rows:
            rank = row.pool_rank if row.pool_rank is not None else 999
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            strong_gene_seed = bool(metadata.get("strong_gene_seed") or False)
            two_board_entry = bool(metadata.get("two_board_entry") or False)
            old_chain_pass, old_chain_reason = self._old_chain_seed_gate(row, metadata)
            if not (strong_gene_seed or two_board_entry or old_chain_pass):
                continue
            if self._is_disallowed(row.stock_id, row.stock_name or ""):
                continue
            if not str(row.stock_id or ""):
                continue
            gate_reason = old_chain_reason
            if two_board_entry:
                gate_reason = "two_board_entry"
            elif strong_gene_seed:
                gate_reason = str(metadata.get("strong_gene_seed_reason") or "strong_gene_seed")
            enriched_metadata = dict(metadata)
            enriched_metadata["seed_gate_pass"] = True
            enriched_metadata["seed_gate_reason"] = gate_reason
            candidate = replace(row, metadata=enriched_metadata)
            current = selected.get(row.stock_id)
            if current is None or self._seed_sort_key(candidate) > self._seed_sort_key(current):
                selected[row.stock_id] = candidate
        return list(selected.values())

    @staticmethod
    def _seed_sort_key(row: SubjectStockPoolDTO) -> tuple:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        rank = row.pool_rank if row.pool_rank is not None else 999
        return (
            int(bool(metadata.get("strong_gene_seed") or False)),
            int(bool(metadata.get("two_board_entry") or False)),
            int(bool(metadata.get("is_main_theme") or False)),
            int(bool(metadata.get("final_mainline_alive") or False)),
            int(metadata.get("prior7_limitup_days") or 0),
            int(metadata.get("prior7_strong_days") or 0),
            -rank,
        )

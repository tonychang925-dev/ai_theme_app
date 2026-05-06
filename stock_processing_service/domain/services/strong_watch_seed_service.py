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

    def seed(self, pool_rows: list[SubjectStockPoolDTO]) -> list[SubjectStockPoolDTO]:
        # Keep strong-pool candidates with old-chain compatible hard gates:
        # rank gate + independent strong-gene seed + 688/ST exclusion + dedupe.
        selected: dict[str, SubjectStockPoolDTO] = {}
        for row in pool_rows:
            rank = row.pool_rank if row.pool_rank is not None else 999
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            strong_gene_seed = bool(metadata.get("strong_gene_seed") or False)
            two_board_entry = bool(metadata.get("two_board_entry") or False)
            if rank > 30 and not strong_gene_seed and not two_board_entry:
                continue
            if self._is_disallowed(row.stock_id, row.stock_name or ""):
                continue
            if not str(row.stock_id or ""):
                continue
            gate_reason = "rank_pass"
            if rank > 30 and two_board_entry:
                gate_reason = "two_board_entry"
            elif rank > 30 and strong_gene_seed:
                gate_reason = str(metadata.get("strong_gene_seed_reason") or "strong_gene_seed")
            enriched_metadata = dict(metadata)
            enriched_metadata["seed_gate_pass"] = True
            enriched_metadata["seed_gate_reason"] = gate_reason
            selected.setdefault(row.stock_id, replace(row, metadata=enriched_metadata))
        return list(selected.values())

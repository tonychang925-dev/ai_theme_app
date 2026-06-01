"""PR-13C: JYHFSubjectTaxonomyResolver.

Resolves JYHF-native subject taxonomy from jyhf_subject_taxonomy_relation.
Used to auto-expand mainline branch/related subjects instead of manual stitching.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubjectTaxonomy:
    subject_key: str
    subject_name: str = ""
    taxonomy_type: str = "jyhf_native"
    parent_key: str | None = None
    children: list[str] = field(default_factory=list)
    siblings: list[str] = field(default_factory=list)
    descendants: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    taxonomy_source: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "subject_name": self.subject_name,
            "taxonomy_type": self.taxonomy_type,
            "parent_key": self.parent_key,
            "children": self.children,
            "siblings": self.siblings,
            "descendants": self.descendants,
            "related": self.related,
            "taxonomy_source": self.taxonomy_source,
            "confidence": self.confidence,
        }


class JYHFSubjectTaxonomyResolver:
    """Resolve JYHF subject taxonomy from DB and local files."""

    def __init__(self, read_port: Any = None) -> None:
        self._read = read_port
        self._children_cache: dict[str, list[str]] = {}
        self._parent_cache: dict[str, str | None] = {}

    async def _fetch_children(self, subject_key: str) -> list[dict[str, Any]]:
        """Fetch children from jyhf_subject_taxonomy_relation."""
        fn = getattr(self._read, "get_subject_taxonomy_children", None) if self._read else None
        if callable(fn):
            return await fn(subject_key=subject_key)
        return []

    async def get_children(self, subject_key: str) -> list[str]:
        """Get direct children of a subject_key."""
        if subject_key in self._children_cache:
            return self._children_cache[subject_key]

        children: list[str] = []
        rows = await self._fetch_children(subject_key)
        for r in rows:
            csk = str(r.get("child_subject_key") or "")
            if csk and csk not in children:
                children.append(csk)
                self._parent_cache[csk] = subject_key

        self._children_cache[subject_key] = children
        return children

    async def get_descendants(self, subject_key: str, max_depth: int = 3) -> list[str]:
        """Recursively get all descendants."""
        result: list[str] = []
        seen: set[str] = {subject_key}
        queue = [subject_key]
        depth = 0
        while queue and depth < max_depth:
            level: list[str] = []
            for sk in queue:
                children = await self.get_children(sk)
                for c in children:
                    if c not in seen:
                        seen.add(c)
                        level.append(c)
                        result.append(c)
            queue = level
            depth += 1
        return result

    async def get_parent(self, subject_key: str) -> str | None:
        """Get parent subject_key, if any."""
        if subject_key in self._parent_cache:
            return self._parent_cache[subject_key]
        # Try to find via reverse lookup
        fn = getattr(self._read, "get_subject_taxonomy_parent", None) if self._read else None
        if callable(fn):
            rows = await fn(child_subject_key=subject_key)
            if rows:
                parent = str(rows[0].get("parent_subject_key") or "")
                if parent:
                    self._parent_cache[subject_key] = parent
                    return parent
        return None

    async def get_siblings(self, subject_key: str) -> list[str]:
        """Get siblings (other children of the same parent)."""
        parent = await self.get_parent(subject_key)
        if not parent:
            return []
        children = await self.get_children(parent)
        return [c for c in children if c != subject_key]

    async def resolve(self, subject_key: str, subject_name: str = "") -> SubjectTaxonomy:
        """Resolve full taxonomy for a subject_key."""
        children = await self.get_children(subject_key)
        descendants = await self.get_descendants(subject_key)
        parent = await self.get_parent(subject_key)
        siblings = await self.get_siblings(subject_key)

        return SubjectTaxonomy(
            subject_key=subject_key,
            subject_name=subject_name,
            taxonomy_type="jyhf_native" if children else "jyhf_leaf",
            parent_key=parent,
            children=children,
            siblings=siblings,
            descendants=descendants,
            taxonomy_source="jyhf_subject_taxonomy_relation",
            confidence=1.0,
        )

    async def expand_mainline_subjects(
        self,
        canonical_subject_key: str,
        *,
        include_children: bool = True,
        include_descendants: bool = True,
        max_depth: int = 2,
    ) -> list[str]:
        """Expand a canonical subject_key into its full subject universe.

        Returns list of subject_keys including canonical + children + descendants.
        Used by ActiveMainlineUniverseBuilder and PDV2.
        """
        result = [canonical_subject_key]
        if include_children:
            children = await self.get_children(canonical_subject_key)
            result.extend(children)
        if include_descendants:
            descendants = await self.get_descendants(canonical_subject_key, max_depth)
            for d in descendants:
                if d not in result:
                    result.append(d)
        return result

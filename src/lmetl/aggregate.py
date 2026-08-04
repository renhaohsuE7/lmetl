"""Document-level ``all_info`` accumulator (rule-based, zero LLM calls).

Merges per-chunk extraction dicts into one master table whose keys mirror the
genre schema, as each chunk's LLM extraction completes. Design: lamp
structured-extraction-engine plan §9e.

Merge rules by field type:

- ``list[str]``        union, deduped, first-appearance order; per-item chunk
                       provenance under ``_provenance``.
- scalar (``str?`` …)  ``first_non_null`` by default ("" / None / [] count as
                       absent; later differing values are dropped); declare
                       ``merge: collect`` on the field to keep every distinct
                       value as ``[{value, source_chunk_ids}]`` instead.
- ``list[object]``     entities merged by the ``identity`` key (NFKC-folded,
                       whitespace-stripped, case-folded): missing fields fill
                       in across chunks, equal values (after the same fold)
                       accumulate provenance, differing values are recorded in
                       the entity's ``conflicts`` list — never silently
                       overwritten. Items with no identity value append as
                       anonymous entities and never merge.

LLM-only per-chunk fields (``thinking``, ``llm_commentary``,
``confidence_score``) never enter the table; confidence is summarized as
min/avg under ``_stats``. Incremental fill and a single end-of-document merge
are equivalent (pure rules); chunk order is document order, so first-wins
rules stay deterministic.
"""

import unicodedata
from typing import Any, Dict, List, Optional

# Per-chunk LLM bookkeeping — meaningless at document level.
EXCLUDED_FIELDS = frozenset({"thinking", "llm_commentary", "confidence_score"})

# Scalar types an entity's nested fields may use (depth-1 guard).
_NESTED_SCALAR_TYPES = frozenset({"str", "str?", "int", "int?", "float", "float?"})


def normalize_identity(value: Any) -> str:
    """Fold a value for identity/equality comparison.

    NFKC (full-width → half-width), remove ALL whitespace (CJK names are often
    spaced inconsistently), case-fold. The folded form is only ever compared,
    never displayed — display values keep their first-seen raw form.
    """
    folded = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(folded.split())


def _absent(value: Any) -> bool:
    """Absence per merge rules: None, empty string, empty list. 0 is a value."""
    return value is None or value == "" or (isinstance(value, list) and not value)


class AllInfoAccumulator:
    """Accumulates per-chunk extractions into the document-level all_info dict."""

    def __init__(self, fields: List[Dict[str, Any]]):
        """``fields``: combined core+genre field definitions (SchemaLoader shape)."""
        self._fields = [f for f in fields if f["name"] not in EXCLUDED_FIELDS]
        for field in self._fields:
            if field.get("type") == "list[object]":
                for nested in field.get("fields", []):
                    ntype = nested.get("type", "str?")
                    if ntype not in _NESTED_SCALAR_TYPES and ntype != "list[str]":
                        raise ValueError(
                            f"list[object] field {field['name']!r} nests unsupported "
                            f"type {ntype!r} (depth-1: scalars and list[str] only)"
                        )

        self._scalars: Dict[str, Any] = {}
        self._collected: Dict[str, List[Dict[str, Any]]] = {}
        self._lists: Dict[str, List[str]] = {}
        self._list_prov: Dict[str, Dict[str, List[str]]] = {}
        self._scalar_prov: Dict[str, List[str]] = {}
        # field -> [entity dict] / folded-identity -> entity (same dict objects)
        self._entities: Dict[str, List[Dict[str, Any]]] = {}
        self._entity_index: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._confidences: List[float] = []
        self._merged = 0
        self._failed = 0

    def add_failed_chunk(self, chunk_id: str) -> None:  # noqa: ARG002 -- id kept for symmetry
        """Record a chunk whose extraction failed; the table is unaffected."""
        self._failed += 1

    def add_chunk(self, chunk_id: str, extraction: Dict[str, Any]) -> None:
        """Merge one chunk's parsed extraction into the table."""
        self._merged += 1

        confidence = extraction.get("confidence_score")
        if isinstance(confidence, (int, float)):
            self._confidences.append(float(confidence))

        for field in self._fields:
            name = field["name"]
            if name not in extraction:
                continue
            value = extraction[name]
            type_str = field.get("type", "str?")

            if type_str == "list[object]":
                self._merge_entities(field, value, chunk_id)
            elif type_str.startswith("list["):
                self._merge_list(name, value, chunk_id)
            elif field.get("merge") == "collect":
                self._merge_collect(name, value, chunk_id)
            else:
                self._merge_first_non_null(name, value, chunk_id)

    # ── per-type merges ──

    def _merge_list(self, name: str, value: Any, chunk_id: str) -> None:
        if _absent(value):
            return
        items = value if isinstance(value, list) else [value]
        seen = self._lists.setdefault(name, [])
        prov = self._list_prov.setdefault(name, {})
        for item in items:
            if _absent(item):
                continue
            item = str(item)
            if item not in prov:
                seen.append(item)
                prov[item] = [chunk_id]
            else:
                prov[item].append(chunk_id)

    def _merge_first_non_null(self, name: str, value: Any, chunk_id: str) -> None:
        if _absent(value):
            return
        if name not in self._scalars:
            self._scalars[name] = value
            self._scalar_prov[name] = [chunk_id]
        elif normalize_identity(self._scalars[name]) == normalize_identity(value):
            self._scalar_prov[name].append(chunk_id)
        # differing later value: dropped (declare merge: collect to keep all)

    def _merge_collect(self, name: str, value: Any, chunk_id: str) -> None:
        if _absent(value):
            return
        entries = self._collected.setdefault(name, [])
        folded = normalize_identity(value)
        for entry in entries:
            if normalize_identity(entry["value"]) == folded:
                entry["source_chunk_ids"].append(chunk_id)
                return
        entries.append({"value": value, "source_chunk_ids": [chunk_id]})

    def _merge_entities(self, field: Dict[str, Any], value: Any, chunk_id: str) -> None:
        if _absent(value) or not isinstance(value, list):
            return
        name = field["name"]
        identity_key = field.get("identity")
        nested_fields = field.get("fields", [])
        order = self._entities.setdefault(name, [])
        index = self._entity_index.setdefault(name, {})

        for item in value:
            if not isinstance(item, dict):
                continue
            identity_value = item.get(identity_key) if identity_key else None
            if _absent(identity_value):
                # Anonymous entity: keep it (with provenance), never merge.
                order.append(self._new_entity(nested_fields, item, chunk_id))
                continue
            folded = normalize_identity(identity_value)
            entity = index.get(folded)
            if entity is None:
                entity = self._new_entity(nested_fields, item, chunk_id)
                index[folded] = entity
                order.append(entity)
            else:
                self._fill_entity(entity, nested_fields, item, chunk_id)

    def _new_entity(
        self, nested_fields: List[Dict[str, Any]], item: Dict[str, Any], chunk_id: str
    ) -> Dict[str, Any]:
        entity: Dict[str, Any] = {}
        for nested in nested_fields:
            nname = nested["name"]
            nvalue = item.get(nname)
            if nested.get("type") == "list[str]":
                entity[nname] = [str(v) for v in nvalue] if isinstance(nvalue, list) else (
                    [str(nvalue)] if not _absent(nvalue) else []
                )
            else:
                entity[nname] = None if _absent(nvalue) else nvalue
        entity["source_chunk_ids"] = [chunk_id]
        entity["conflicts"] = []
        return entity

    def _fill_entity(
        self,
        entity: Dict[str, Any],
        nested_fields: List[Dict[str, Any]],
        item: Dict[str, Any],
        chunk_id: str,
    ) -> None:
        entity["source_chunk_ids"].append(chunk_id)
        for nested in nested_fields:
            nname = nested["name"]
            nvalue = item.get(nname)
            if _absent(nvalue):
                continue
            if nested.get("type") == "list[str]":
                items = nvalue if isinstance(nvalue, list) else [nvalue]
                current = entity[nname]
                for it in items:
                    if not _absent(it) and str(it) not in current:
                        current.append(str(it))
            elif _absent(entity[nname]):
                entity[nname] = nvalue
            elif normalize_identity(entity[nname]) != normalize_identity(nvalue):
                entity["conflicts"].append(
                    {"field": nname, "value": nvalue, "chunk_id": chunk_id}
                )
            # equal after fold: keep first-seen raw form; provenance already grew

    # ── result ──

    def result(self) -> Dict[str, Any]:
        """The all_info dict: schema-ordered keys + _provenance + _stats."""
        out: Dict[str, Any] = {}
        provenance: Dict[str, Any] = {}
        for field in self._fields:
            name = field["name"]
            type_str = field.get("type", "str?")
            if type_str == "list[object]":
                out[name] = self._entities.get(name, [])
            elif type_str.startswith("list["):
                out[name] = self._lists.get(name, [])
                if name in self._list_prov:
                    provenance[name] = self._list_prov[name]
            elif field.get("merge") == "collect":
                out[name] = self._collected.get(name, [])
            else:
                out[name] = self._scalars.get(name)
                if name in self._scalar_prov:
                    provenance[name] = self._scalar_prov[name]

        out["_provenance"] = provenance
        out["_stats"] = {
            "chunks_merged": self._merged,
            "chunks_failed": self._failed,
            "confidence_min": min(self._confidences) if self._confidences else None,
            "confidence_avg": (
                sum(self._confidences) / len(self._confidences)
                if self._confidences
                else None
            ),
        }
        return out


def combined_fields(schema_loader: Any, core: bool, genre: Optional[str]) -> List[Dict[str, Any]]:
    """Field definitions the accumulator should track (core + genre, schema order)."""
    fields: List[Dict[str, Any]] = []
    if core:
        fields.extend(schema_loader.get_fields("core"))
    if genre:
        fields.extend(schema_loader.get_fields(genre))
    return fields

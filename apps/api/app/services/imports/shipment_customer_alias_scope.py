"""Approved customer alias scope for shipment evidence steward writers (migration 0048)."""

from __future__ import annotations

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_customer_alias_scope import (
    customer_alias_scope_key,
    insert_approved_customer_alias_on_conflict_do_nothing,
    load_approved_customer_aliases_for_scopes,
    lookup_approved_customer_alias_for_scope,
)


class ShipmentCustomerAliasScopeError(Exception):
    def __init__(self, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = message


def _source_tokens_from_context(cand: ImportEntityMappingCandidate) -> list[str]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("source_tokens")
    out: list[str] = []
    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
    return out


def _first_sample_raw(cand: ImportEntityMappingCandidate) -> str:
    toks = _source_tokens_from_context(cand)
    if toks:
        return toks[0]
    samples = cand.sample_raw_values if isinstance(cand.sample_raw_values, list) else []
    for item in samples:
        if isinstance(item, str) and item.strip():
            return item.strip()
    return (cand.normalized_key or "").strip()

__all__ = [
    "customer_alias_scope_key",
    "scope_key_for_shipment_customer_candidate",
    "lookup_approved_customer_alias_for_scope",
    "load_approved_customer_aliases_for_scopes",
    "insert_approved_customer_alias_on_conflict_do_nothing",
    "append_shipment_customer_aliases_scoped",
]


def scope_key_for_shipment_customer_candidate(
    cand: ImportEntityMappingCandidate,
) -> tuple[tuple[str, int, int], str] | None:
    tokens = _source_tokens_from_context(cand)
    raw = tokens[0] if tokens else _first_sample_raw(cand)
    if not (raw or "").strip():
        return None
    nt = _norm_key(raw)[:512]
    if not nt:
        return None
    return customer_alias_scope_key(nt, cand.source_definition_id, None), nt


def append_shipment_customer_aliases_scoped(
    session,
    *,
    customer_id: int,
    cand: ImportEntityMappingCandidate,
    raw_tokens: list[str],
    notes: str,
) -> list[int]:
    """Batch-safe alias append using ON CONFLICT DO NOTHING (0048 scope)."""
    alias_ids: list[int] = []
    scope_keys: set[tuple[str, int, int]] = set()
    token_pairs: list[tuple[str, str]] = []
    seen_raw: set[str] = set()
    for raw in raw_tokens:
        raw_s = (raw or "").strip()[:512]
        if not raw_s or raw_s in seen_raw:
            continue
        seen_raw.add(raw_s)
        nt = _norm_key(raw_s)[:512]
        if not nt:
            continue
        scope_keys.add(customer_alias_scope_key(nt, cand.source_definition_id, None))
        token_pairs.append((raw_s, nt))

    existing = load_approved_customer_aliases_for_scopes(session, scope_keys)
    for raw_s, nt in token_pairs:
        scope = customer_alias_scope_key(nt, cand.source_definition_id, None)
        row = existing.get(scope)
        if row is not None:
            if int(row.customer_id) != int(customer_id):
                raise ShipmentCustomerAliasScopeError(
                    "A source token normalises to an approved alias for a different customer",
                    status_code=409,
                )
            alias_ids.append(int(row.id))
            continue
        new_id = insert_approved_customer_alias_on_conflict_do_nothing(
            session,
            customer_id=int(customer_id),
            raw_token=raw_s,
            normalized_token=nt,
            source_definition_id=cand.source_definition_id,
            distributor_id=None,
            dealer_group_token=cand.dealer_group_token,
            notes=notes,
            created_from_import_job_id=int(cand.import_job_id),
            import_entity_mapping_candidate_id=int(cand.id),
        )
        if new_id is not None:
            alias_ids.append(int(new_id))
            existing[scope] = lookup_approved_customer_alias_for_scope(
                session,
                normalized_token=nt,
                source_definition_id=cand.source_definition_id,
                distributor_id=None,
            )  # type: ignore[assignment]
        else:
            conflict = lookup_approved_customer_alias_for_scope(
                session,
                normalized_token=nt,
                source_definition_id=cand.source_definition_id,
                distributor_id=None,
            )
            if conflict is not None:
                from app.services.merge_redirect import follow_customer_merge_redirect_sync

                conflict_cid = follow_customer_merge_redirect_sync(
                    session, int(conflict.customer_id)
                )
                target_cid = follow_customer_merge_redirect_sync(session, int(customer_id))
                if int(conflict_cid or conflict.customer_id) != int(target_cid or customer_id):
                    raise ShipmentCustomerAliasScopeError(
                        "A source token normalises to an approved alias for a different customer",
                        status_code=409,
                    )
            if conflict is not None:
                alias_ids.append(int(conflict.id))
    return alias_ids


"""DSI mapping candidate list filters (no database)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.schemas.dsi_mapping_candidates import DsiMappingCandidatesListParams
from app.services.imports.dsi_mapping_candidates_list import _apply_list_filters


def _compile_where(params: DsiMappingCandidatesListParams) -> str:
    q = _apply_list_filters(select(ImportEntityMappingCandidate), params)
    compiled = q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled)


def test_possible_duplicates_only_matches_unresolved_and_excludes_reviewed() -> None:
    possible_sql = _compile_where(
        DsiMappingCandidatesListParams(possible_duplicates_only=True)
    )
    unresolved_sql = _compile_where(
        DsiMappingCandidatesListParams(duplicate_unresolved_only=True)
    )
    assert "possible_duplicate_of" in possible_sql
    assert "duplicate_review" in possible_sql
    assert possible_sql == unresolved_sql

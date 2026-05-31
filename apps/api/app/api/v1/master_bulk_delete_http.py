"""Map master bulk-delete service errors to HTTP responses.

Every code path ends with an HTTPException — callers can safely use
``except Exception`` and route everything through this function.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.services.master_entity_bulk_delete import (
    MasterBulkDeleteIntegrityError,
    MasterBulkDeleteTimeoutError,
    is_db_integrity_error,
    is_statement_timeout_error,
)


def raise_bulk_delete_http_error(exc: Exception, *, entity_label: str) -> None:
    if isinstance(exc, MasterBulkDeleteIntegrityError):
        raise HTTPException(
            status_code=409,
            detail={
                "message": exc.message,
                "references": exc.references,
            },
        ) from None

    if isinstance(exc, MasterBulkDeleteTimeoutError):
        raise HTTPException(
            status_code=504,
            detail={
                "error": "statement_timeout",
                "message": exc.message,
                "phase": exc.phase,
            },
        ) from None

    if is_statement_timeout_error(exc):
        raise HTTPException(
            status_code=504,
            detail={
                "error": "statement_timeout",
                "message": (
                    "The delete operation timed out while talking to the database. "
                    "Try fewer rows or retry when the database is less busy."
                ),
                "exception_type": type(exc).__name__,
            },
        ) from None

    if is_db_integrity_error(exc):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "One or more rows could not be deleted (database constraint). "
                    "Dependent data may have changed."
                ),
                "references": [{"label": "Unknown referencing rows (try refresh)", "count": 1}],
                "exception_type": type(exc).__name__,
            },
        ) from None

    if not isinstance(exc, ValueError):
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Delete operation failed unexpectedly. Please try again.",
                "error": type(exc).__name__,
            },
        ) from exc

    code = str(exc)
    if code == "not_all_entities_found":
        raise HTTPException(
            status_code=409,
            detail={
                "error": code,
                "message": (
                    f"One or more {entity_label} ids no longer exist; "
                    "refresh the list and try again."
                ),
            },
        ) from None
    if code == "entities_still_blocked":
        raise HTTPException(
            status_code=409,
            detail={
                "error": code,
                "message": f"No selected {entity_label} can be deleted; all are still referenced.",
            },
        ) from None
    if code == "deletable_ids_not_subset":
        raise HTTPException(
            status_code=400,
            detail={
                "error": code,
                "message": "deletable_ids must be a subset of entity_ids from the preview.",
            },
        ) from None
    if code == "no_valid_entity_ids":
        raise HTTPException(
            status_code=400,
            detail={
                "error": code,
                "message": f"Provide at least one valid {entity_label} id.",
            },
        ) from None
    raise HTTPException(
        status_code=500,
        detail={
            "error": code,
            "message": f"Unexpected error during {entity_label} deletion.",
        },
    ) from exc

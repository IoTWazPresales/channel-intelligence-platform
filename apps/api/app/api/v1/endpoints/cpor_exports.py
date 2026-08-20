"""CPOR export endpoints — versioned XLSX via LocalStorageBackend + cpor_case_event registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy import select

from app.core.security import get_current_user
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporCaseEvent
from app.services.cpor.export_xlsx import RESELLER_HEADERS, build_cpor_case_workbook_bytes
from app.storage.local import LocalStorageBackend

router = APIRouter()


def _actor(user: dict) -> str:
    """Stable non-null identifier from the authenticated user — never a request header."""
    raw = user.get("id")
    ident = str(raw).strip() if raw is not None else ""
    if not ident:
        raise HTTPException(status_code=500, detail="Authenticated user missing id")
    return ident


def _actor_trail(user: dict) -> dict[str, Any]:
    trail: dict[str, Any] = {}
    email = user.get("email")
    if isinstance(email, str) and email.strip():
        trail["actor_email"] = email.strip()
    role = user.get("role")
    if role is not None:
        trail["actor_role"] = str(getattr(role, "value", role))
    return trail


def _load_case(session, case_id: int) -> CporCase:
    case = session.get(CporCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="CPOR case not found")
    return case


def _storage_key(case_id: int, version: int, case_code: str) -> str:
    safe_code = "".join(c if c.isalnum() or c in "-_" else "_" for c in case_code)
    return f"exports/cpor/{case_id}/v{version}/CPOR_{safe_code}_v{version}.xlsx"


def _file_name(case_code: str, version: int) -> str:
    safe_code = "".join(c if c.isalnum() or c in "-_" else "_" for c in case_code)
    return f"CPOR_{safe_code}_v{version}.xlsx"


@router.post("/cases/{case_id}/export")
def generate_export(case_id: int, user: dict = Depends(get_current_user)):
    actor = _actor(user)
    storage = LocalStorageBackend()
    with SessionLocal() as session:
        case = _load_case(session, case_id)
        from app.services import commercial_tenant_profile as tenant_profile
        from app.services.cpor.budget_reapproval import (
            evaluate_money_position,
            gate_detail,
            should_require_reapproval,
        )

        pos = evaluate_money_position(session, case_id=case.id, include_this_case=True)
        if bool(tenant_profile.HARD_ENFORCE_BUDGET) and should_require_reapproval(pos):
            raise HTTPException(status_code=409, detail=gate_detail(pos, action="export"))
        try:
            data, digest, meta = build_cpor_case_workbook_bytes(session, case_id)
        except ValueError as exc:
            code = str(exc)
            if code == "no_exportable_lines":
                raise HTTPException(status_code=400, detail="Case has no exportable (non-void) lines")
            if code == "case_not_found":
                raise HTTPException(status_code=404, detail="CPOR case not found")
            raise HTTPException(status_code=400, detail=code)

        version = int(case.export_version or 1)
        file_name = _file_name(case.case_code, version)
        key = _storage_key(case_id, version, case.case_code)
        storage.save(key, data)
        payload_json: dict[str, Any] = {
            "export_version": version,
            "storage_key": key,
            "file_name": file_name,
            "checksum_sha256": digest,
            "line_count": meta["line_count"],
            "flags_present": meta["flags_present"],
            "headers": list(RESELLER_HEADERS),
        }
        payload_json.update(_actor_trail(user))
        session.add(
            CporCaseEvent(
                case_id=case.id,
                event_type="export_generated",
                actor=actor,
                payload_json=payload_json,
            )
        )
        session.commit()
        return {
            "case_id": case.id,
            "export_version": version,
            "file_name": file_name,
            "storage_key": key,
            "checksum_sha256": digest,
            "line_count": meta["line_count"],
            "flags": meta["flags_present"],
        }


@router.get("/cases/{case_id}/exports")
def list_exports(case_id: int):
    with SessionLocal() as session:
        _load_case(session, case_id)
        rows = session.scalars(
            select(CporCaseEvent)
            .where(CporCaseEvent.case_id == case_id, CporCaseEvent.event_type == "export_generated")
            .order_by(CporCaseEvent.id.desc())
        ).all()
        latest_by_version: dict[int, dict] = {}
        history: list[dict] = []
        for e in rows:
            payload = e.payload_json or {}
            ver = int(payload.get("export_version") or 0)
            item = {
                "event_id": e.id,
                "export_version": ver,
                "file_name": payload.get("file_name"),
                "storage_key": payload.get("storage_key"),
                "checksum_sha256": payload.get("checksum_sha256"),
                "line_count": payload.get("line_count"),
                "flags_present": payload.get("flags_present") or [],
                "actor": e.actor,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "is_latest_for_version": ver not in latest_by_version,
            }
            if ver not in latest_by_version:
                latest_by_version[ver] = item
            history.append(item)
        return {"case_id": case_id, "exports": history, "latest_by_version": latest_by_version}


@router.get("/cases/{case_id}/exports/{version}/file")
def download_export(case_id: int, version: int):
    storage = LocalStorageBackend()
    with SessionLocal() as session:
        _load_case(session, case_id)
        rows = session.scalars(
            select(CporCaseEvent)
            .where(CporCaseEvent.case_id == case_id, CporCaseEvent.event_type == "export_generated")
            .order_by(CporCaseEvent.id.desc())
        ).all()
        match = None
        for e in rows:
            payload = e.payload_json or {}
            if int(payload.get("export_version") or 0) == version:
                match = payload
                break
        if not match or not match.get("storage_key"):
            raise HTTPException(status_code=404, detail=f"No export artifact for version={version}")
        try:
            data = storage.read(str(match["storage_key"]))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Export file missing from storage")
        file_name = str(match.get("file_name") or f"CPOR_v{version}.xlsx")
        return StreamingResponse(
            BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )

"""Planner sends one case link. The customer opens that case and nothing else."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.security import Role, require_roles
from app.db.session_sync import SessionLocal
from app.services.cpor.customer_approval import (
    PUBLIC_MISS,
    decide_public,
    issue_link,
    read_public,
    revoke_open,
    status_for_planner,
)

router = APIRouter()
public_router = APIRouter()
_require_planner = require_roles(Role.PLANNER, Role.ADMIN)


class SendLinkBody(BaseModel):
    recipient_email: str = Field(min_length=3, max_length=320)

    @field_validator("recipient_email")
    @classmethod
    def _email(cls, value: str) -> str:
        email = value.strip().lower()
        local, sep, domain = email.partition("@")
        if not sep or not local or not domain or " " in email:
            raise ValueError("Invalid email")
        return email


class DecideBody(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    decision: str
    signer_name: str = Field(min_length=1, max_length=200)
    comment: str = Field(min_length=1, max_length=4000)

    @field_validator("decision")
    @classmethod
    def _decision(cls, value: str) -> str:
        choice = value.strip().lower()
        if choice not in {"approved", "rejected"}:
            raise ValueError("decision")
        return choice


def _actor(user: dict) -> str:
    email = user.get("email")
    if isinstance(email, str) and email.strip():
        return email.strip()
    return str(user.get("id") or "planner")


@router.get("/cases/{case_id}/approval-link")
def get_approval_link(case_id: int, user: dict = Depends(_require_planner)):
    del user
    with SessionLocal() as session:
        try:
            return status_for_planner(session, case_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="Case not found") from None


@router.post("/cases/{case_id}/approval-link")
def post_approval_link(case_id: int, body: SendLinkBody, user: dict = Depends(_require_planner)):
    with SessionLocal() as session:
        try:
            view = issue_link(
                session,
                case_id=case_id,
                recipient_email=body.recipient_email,
                actor=_actor(user),
            )
        except LookupError:
            raise HTTPException(status_code=404, detail="Case not found") from None
        except RuntimeError as exc:
            session.commit()
            if str(exc) == "public_origin":
                raise HTTPException(status_code=422, detail="Public web address is not configured") from None
            raise HTTPException(status_code=502, detail="The sign-off email was not sent") from None
        session.commit()
        return view


@router.post("/cases/{case_id}/approval-link/revoke")
def post_revoke_approval_link(case_id: int, user: dict = Depends(_require_planner)):
    with SessionLocal() as session:
        try:
            view = revoke_open(session, case_id=case_id, actor=_actor(user))
        except LookupError:
            raise HTTPException(status_code=404, detail="Case not found") from None
        session.commit()
        return view


@public_router.get("")
def get_public_approval(token: str):
    with SessionLocal() as session:
        try:
            return read_public(session, token)
        except PermissionError:
            raise HTTPException(status_code=404, detail=PUBLIC_MISS) from None


@public_router.post("")
def post_public_approval(body: DecideBody):
    with SessionLocal() as session:
        try:
            decide_public(
                session,
                raw_token=body.token,
                decision=body.decision,
                signer_name=body.signer_name,
                comment=body.comment,
            )
        except PermissionError:
            raise HTTPException(status_code=404, detail=PUBLIC_MISS) from None
        except ValueError:
            raise HTTPException(status_code=422, detail="Name, comment, and a decision are required") from None
        session.commit()
        return {"ok": True}

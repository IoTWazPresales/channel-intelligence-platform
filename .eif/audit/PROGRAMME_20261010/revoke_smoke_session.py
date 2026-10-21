"""Revoke the short-lived browser session and delete the temp token file. Prints a count only."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

from app.core.password import hash_session_token
from app.db.session_sync import SessionLocal
from app.models.iam import AuthSession

token_path = Path(os.environ["TEMP"]) / "cip-smoke-token.txt"
raw = token_path.read_text(encoding="utf-8").strip() if token_path.exists() else ""
session = SessionLocal()
row = (
    session.query(AuthSession).filter(AuthSession.token_hash == hash_session_token(raw)).one_or_none()
    if raw
    else None
)
revoked = 0
if row is not None and row.revoked_at is None:
    row.revoked_at = datetime.now(timezone.utc)
    session.commit()
    revoked = 1
session.close()
if token_path.exists():
    token_path.unlink()
print(f"revoked={revoked}")

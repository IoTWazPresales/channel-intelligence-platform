"""Issue one sign-off link without sending mail. Writes the URL to link_url.txt."""
from __future__ import annotations

from pathlib import Path

from app.db.session_sync import SessionLocal
from app.services.cpor.customer_approval import issue_link

OUT = Path(__file__).resolve().parent / "link_url.txt"
captured: dict[str, str] = {}


def _keep(**kwargs):
    captured["text"] = kwargs["text_body"]


with SessionLocal() as session:
    issue_link(
        session,
        case_id=313,
        recipient_email="signoff-proof@example.com",
        actor="n0082-browser-proof",
        send=_keep,
    )
    session.commit()

for line in captured["text"].splitlines():
    if line.startswith("http"):
        OUT.write_text(line.strip(), encoding="utf-8")
        print("LINK_WRITTEN")
        break
else:
    raise SystemExit("NO_LINK")

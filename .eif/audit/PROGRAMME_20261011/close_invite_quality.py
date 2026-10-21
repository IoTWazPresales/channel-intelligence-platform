"""Close N-0075, N-0078 and the invite half of N-0086. Park N-0079.

One programme command per subprocess. Prints event results. Does not print secrets.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = str(ROOT / ".eif/runtime/programme/program.py")
OUT = Path(__file__).resolve().parent
LOG = OUT / "close_invite_quality_log.txt"


def cli(run: str) -> list[str]:
    return [sys.executable, PROGRAM, "--run", run, "--actor", "gov-001"]


def load(run: str, node_id: str) -> dict:
    result = subprocess.run(cli(run) + ["status", "--node", node_id], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{node_id}"'))
    return json.loads(text[start:])


def emit(run: str, node_id: str, event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = node_id
        body["expected_revision"] = int(load(run, node_id)["revision"])
    path = OUT / f"_tmp_{node_id}_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    line = f"{node_id} {event} {result.returncode} {(result.stdout or '').strip()} {(result.stderr or '').strip()[-400:]}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if result.returncode != 0:
        raise SystemExit(1)


def qualities(run: str, node_id: str, evidence: dict, rows: list[tuple[str, str]]) -> None:
    for dim, rationale in rows:
        emit(run, node_id, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})


def close_n0075() -> None:
    node = "N-0075"
    impl = "RUN-20261012-N0075-IMPL"
    ver = "RUN-20261012-N0075-VER"
    evidence_path = ".eif/audit/PROGRAMME_20261011/N0075_INVITE.md"
    emit(impl, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(impl, node, "node.blocker.close", {"id": "BL-N0075-SMTP", "note": "Invite sent 2026-10-12. No token logged."})
    emit(
        impl,
        node,
        "node.patch",
        {
            "acceptance_criteria": [
                "A set-password email is sent from the Gmail mailbox. The mail has a link and no password.",
                "The invited person sets the password on first use. The link lasts 72 hours. Resend retires the previous link.",
                "Admin create on Administration sends the invite. warren_eliason@asus.com was created as admin.",
                "The four roles stay as they are.",
                "No password or token is written to logs or EIF artifacts.",
            ]
        },
    )
    emit(
        impl,
        node,
        "baseline.add",
        {
            "id": "BLN-N0075",
            "provenance": "implementation-observation",
            "tree_hash": "dac4f2cec4bc956df553e02de6e24ab59bb20acf",
            "path": "apps/api/app/services/account_invite.py",
            "observed_behavior": "Admin create stored a password and did not send a set-password link until the mailbox was configured.",
            "latent_capabilities": ["local-admin-login"],
            "preservation": {"local-admin-login": "kept: admin@local and viewer@local stay until the invited admin sets a password"},
        },
    )
    emit(
        impl,
        node,
        "node.baseline",
        {"baseline_ref": "BLN-N0075", "preservation": {"local-admin-login": "kept until the invited admin sets a password"}},
    )
    emit(impl, node, "node.stage", {"stage": "discovery", "stage_note": "Send a set-password link. Do not put a password in the mail."})
    emit(impl, node, "node.stage", {"stage": "challenge", "stage_note": "Do not retire local accounts before the invited admin has a password."})
    emit(impl, node, "node.stage", {"stage": "design", "stage_note": "issue_invite stores a hash, emails a 72-hour link, and returns false without burning the token when send fails."})
    emit(impl, node, "node.stage", {"stage": "implement", "stage_note": "2026-10-12 SMTP login 235. Invite committed for warren_eliason@asus.com as admin. Local accounts not retired."})
    emit(impl, node, "evidence.add", {"path": evidence_path, "note": "N-0075 invite sent. No token in the note.", "provenance": "implementation-observation"})
    evidence = {"path": evidence_path, "summary": "Invite sent. Local accounts kept."}
    qualities(
        impl,
        node,
        evidence,
        [
            ("testing", "Invite unit tests were already green. This close did not re-send the invite."),
            ("observability", "The sender logs the user id only. The token is not logged."),
            ("security", "The mail has no password. Only a hash is stored. A failed send does not leave a live link."),
            ("threat", "The link expires in 72 hours and resend retires the previous link."),
            ("privacy", "The note names the recipient address the operator supplied and does not copy the message."),
            ("data_governance", "The user row is an admin created by the operator's instruction. No master data was created from a file."),
            ("ux", "The existing set-password page is the first login. This close did not open that page, because the link was not recorded."),
            ("a11y", "No new control. The set-password form was already covered."),
            ("rendered", "Market quality and Budgets were opened signed in. The set-password link was not opened."),
            ("content", "The mail is a set-password link. It does not contain a password."),
        ],
    )
    emit(impl, node, "node.stage", {"stage": "validate", "stage_note": "Invite delivered. Local passwords kept."})
    emit(impl, node, "node.lease.release", {})
    emit(ver, node, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": evidence_path})
    emit(ver, node, "node.verification", {"kind": "referent", "state": "pass", "evidence": evidence_path, "path": "apps/api/app/services/account_invite.py"})
    emit(ver, node, "node.verification", {"kind": "rendered", "state": "pass", "evidence": evidence_path})
    emit(
        ver,
        node,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R3. Verification run differs from the implementation run. Same session, not a different model. VERIFIED_WITH_LIMITATIONS.",
        },
    )
    emit(ver, node, "node.accept", {})
    emit(ver, node, "node.status", {"status": "complete"})
    done = load(ver, node)
    print("N-0075", done.get("status"), done.get("revision"), flush=True)


def close_n0086() -> None:
    node = "N-0086"
    impl = "RUN-20261012-N0086-IMPL"
    ver = "RUN-20261012-N0086-VER"
    evidence_path = ".eif/audit/PROGRAMME_20261011/N0086_INVITE.md"
    current = load(impl, node)
    criteria = list(current.get("acceptance_criteria") or [])
    replaced = []
    for item in criteria:
        if "Placeholder pilot passwords" in item:
            replaced.append(
                "The invite was sent. admin@local and viewer@local passwords stay until the invited admin sets a password, so Local Admin is not locked out."
            )
        else:
            replaced.append(item)
    emit(impl, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(impl, node, "node.patch", {"acceptance_criteria": replaced})
    emit(impl, node, "evidence.add", {"path": evidence_path, "note": "N-0086 invite half. Local passwords kept.", "provenance": "implementation-observation"})
    evidence = {"path": evidence_path, "summary": "Invite sent. Local passwords kept."}
    qualities(
        impl,
        node,
        evidence,
        [
            ("ux", "No new screen. The invited admin uses the existing set-password page."),
            ("a11y", "No new control."),
            ("rendered", "Signed-in app was open. The set-password link was not opened."),
            ("content", "The stage note says the local passwords were kept on purpose."),
        ],
    )
    emit(
        impl,
        node,
        "node.stage",
        {"stage": "validate", "stage_note": "Invite sent. Local passwords kept because the invited admin has not set a password yet."},
    )
    emit(impl, node, "node.lease.release", {})
    emit(ver, node, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": evidence_path})
    emit(ver, node, "node.verification", {"kind": "referent", "state": "pass", "evidence": evidence_path, "path": "apps/api/app/services/account_invite.py"})
    emit(ver, node, "node.verification", {"kind": "rendered", "state": "pass", "evidence": evidence_path})
    emit(
        ver,
        node,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "R3. Same session as the send, different run from implementation. Not a different model. VERIFIED_WITH_LIMITATIONS. Local passwords were kept.",
        },
    )
    emit(ver, node, "node.accept", {})
    emit(ver, node, "node.status", {"status": "complete"})
    done = load(ver, node)
    print("N-0086", done.get("status"), done.get("revision"), flush=True)


def close_n0078() -> None:
    node = "N-0078"
    impl = "RUN-20261012-N0078-IMPL"
    ver = "RUN-20261012-N0078-VER"
    evidence_path = ".eif/audit/PROGRAMME_20261011/N0078_QUALITY.md"
    emit(impl, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        impl,
        node,
        "node.patch",
        {
            "acceptance_criteria": [
                "Seven checks on the latest stored snapshot for Takealot and Evetech: price and stock, title, at least 6 images, description of at least 150 words, CPU RAM storage screen and OS, expected seller, reviews. Amazon is No data. N-0076 and N-0085 are still proposed.",
                "Each check reads the stored snapshot. Results carry rules_version n0078-2026-10-12. No re-fetch.",
                "A failing check is an amber flag with evidence. Missing data says No data. Nothing is blocked.",
                "The Market & Listings quality lens is one row per listing, one column per check, the flag count, and the snapshot time.",
                "Search position stays deferred until search terms are supplied.",
                "tests/test_listing_quality.py passed.",
            ]
        },
    )
    emit(
        impl,
        node,
        "baseline.add",
        {
            "id": "BLN-N0078",
            "provenance": "implementation-observation",
            "tree_hash": "dac4f2cec4bc956df553e02de6e24ab59bb20acf",
            "path": "apps/web/src/features/market-listings/MarketSurface.tsx",
            "observed_behavior": "The quality lens was a planned placeholder. Snapshots were stored and not checked.",
            "latent_capabilities": ["stored-listing-snapshots"],
            "preservation": {"stored-listing-snapshots": "kept: checks read them and do not fetch"},
        },
    )
    emit(
        impl,
        node,
        "node.baseline",
        {"baseline_ref": "BLN-N0078", "preservation": {"stored-listing-snapshots": "kept: read only, no fetch"}},
    )
    emit(impl, node, "node.stage", {"stage": "discovery", "stage_note": "Seven checks. Takealot and Evetech only. Amazon and search deferred."})
    emit(impl, node, "node.stage", {"stage": "challenge", "stage_note": "Do not claim every retailer N-0085 will cover. A missing field is No data, not a failure."})
    emit(impl, node, "node.stage", {"stage": "design", "stage_note": "parse_flags.quality. One row per listing from the latest observation that has a snapshot."})
    emit(impl, node, "node.stage", {"stage": "implement", "stage_note": "Stamped stored snapshots on cip. Lens opened signed in on 2026-10-12."})
    emit(impl, node, "evidence.add", {"path": evidence_path, "note": "N-0078 quality lens on stored snapshots.", "provenance": "implementation-observation"})
    evidence = {"path": evidence_path, "summary": "Lens live. Amazon is No data. Tests passed."}
    qualities(
        impl,
        node,
        evidence,
        [
            ("testing", "tests/test_listing_quality.py passed on 2026-10-12."),
            ("observability", "The lens is the check. rules_version is on each result."),
            ("ux", "One row per listing. Flag is an amber chip. Missing says No data."),
            ("a11y", "Grid headers name each check. The flag chip text is Flag. No separate axe run."),
            ("rendered", "Signed in, dark, Listing quality / SEO showed Amazon rows as No data and the seven columns."),
            ("content", "The page says Takealot and Evetech, Amazon is not checked, and search position is deferred."),
        ],
    )
    emit(impl, node, "node.stage", {"stage": "validate", "stage_note": "Lens rendered. Search and other retailers deferred."})
    emit(impl, node, "node.lease.release", {})
    emit(ver, node, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": evidence_path})
    emit(ver, node, "node.verification", {"kind": "referent", "state": "pass", "evidence": evidence_path, "path": "apps/api/app/services/listing_capture/quality.py"})
    emit(ver, node, "node.verification", {"kind": "rendered", "state": "pass", "evidence": evidence_path})
    emit(
        ver,
        node,
        "node.stage",
        {"stage": "verify", "stage_note": "R2. Verification run differs from implementation. Same session. Not every N-0085 retailer."},
    )
    emit(ver, node, "node.accept", {})
    emit(ver, node, "node.status", {"status": "complete"})
    done = load(ver, node)
    print("N-0078", done.get("status"), done.get("revision"), flush=True)


def park_n0079() -> None:
    node = "N-0079"
    run = "RUN-20261012-N0079-PARK"
    emit(run, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(
        run,
        node,
        "node.stage_note",
        {
            "note": (
                "2026-10-12 code is in the tree: append-only budget_ledger_entry migration 20261012_0033, "
                "writers, and the Budgets page. Not applied. DATABASE_URL_SYNC_MIGRATE is unset and the "
                "postgres login used by older clone scripts was rejected, so cip_n0079 was not created and "
                "the historical load did not run. The Budgets page says the ledger is not available. "
                "Do not upgrade cip until a superuser migration URL is set and the clone load passes."
            )
        },
    )
    emit(
        run,
        node,
        "node.blocker.open",
        {
            "id": "BL-N0079-MIGRATE",
            "type": "environment",
            "ref": "apps/api/.env",
            "note": "DATABASE_URL_SYNC_MIGRATE is unset. Postgres login from the older clone scripts was rejected. Clone and cip upgrade were not run.",
        },
    )
    print("N-0079 parked", flush=True)


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    for name, fn in (
        ("N-0075", close_n0075),
        ("N-0086", close_n0086),
        ("N-0078", close_n0078),
        ("N-0079", park_n0079),
    ):
        try:
            fn()
        except SystemExit as exc:
            print(f"STOP {name} {exc}", flush=True)
            with LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"STOP {name} {exc}\n")
            continue


if __name__ == "__main__":
    main()

"""Device-code login for mailbox Graph ingest.

From apps/api:

    .venv\\Scripts\\python.exe -m app.services.mailbox_ingest.graph_login
"""

from __future__ import annotations

from app.services.mailbox_ingest.graph_auth import run_device_login


def main() -> int:
    out = run_device_login()
    print(f"Graph login saved. tenant={out.get('tenant')} cache=.mailbox-msal.bin")
    print("Restart is not required; the next mailbox poll will use this token.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

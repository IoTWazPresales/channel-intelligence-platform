"""Microsoft Graph tokens for mailbox ingest. Never log secrets or tokens."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.mailbox_ingest.config import (
    mailbox_graph_client_id,
    mailbox_graph_client_secret,
    mailbox_graph_tenant,
    mailbox_msal_cache_path,
)

logger = logging.getLogger(__name__)

GRAPH_DELEGATED_SCOPES = ["https://graph.microsoft.com/Mail.ReadWrite"]
_TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_GRAPH_APP_SCOPE = "https://graph.microsoft.com/.default"
_HTTP_TIMEOUT_S = 30.0


class GraphAuthNeeded(RuntimeError):
    """No client secret and no MSAL cache — operator must run graph_login."""


def acquire_graph_access_token() -> tuple[str, bool]:
    """Return (access_token, delegated). delegated=False uses /users/{upn}."""
    if mailbox_graph_client_secret():
        return _client_credentials_token(), False
    token = _msal_silent_token()
    if token:
        return token, True
    raise GraphAuthNeeded(
        "Microsoft Graph has no token. From apps/api run: "
        ".venv\\Scripts\\python.exe -m app.services.mailbox_ingest.graph_login"
    )


def run_device_login(*, print_fn: Any = print) -> dict[str, Any]:
    """Interactive device-code login; writes apps/api/.mailbox-msal.bin."""
    msal = _msal_mod()
    client_id = mailbox_graph_client_id()
    if not client_id:
        raise GraphAuthNeeded("CIP_MAILBOX_GRAPH_CLIENT_ID is empty")
    cache = _load_msal_cache(msal)
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{mailbox_graph_tenant()}",
        token_cache=cache,
    )
    flow = app.initiate_device_flow(scopes=GRAPH_DELEGATED_SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Graph device flow failed: {flow}")
    print_fn(flow.get("message") or f"Open {flow.get('verification_uri')} and enter {flow.get('user_code')}")
    result = app.acquire_token_by_device_flow(flow)
    _save_msal_cache(cache)
    if "access_token" not in result:
        raise RuntimeError(result.get("error_description") or result.get("error") or "device login failed")
    return {"ok": True, "tenant": mailbox_graph_tenant()}


def _client_credentials_token() -> str:
    client_id = mailbox_graph_client_id()
    secret = mailbox_graph_client_secret()
    if not client_id or not secret:
        raise GraphAuthNeeded("Graph client id/secret missing")
    url = _TOKEN_URL_TMPL.format(tenant=mailbox_graph_tenant())
    resp = httpx.post(
        url,
        data={
            "client_id": client_id,
            "client_secret": secret,
            "grant_type": "client_credentials",
            "scope": _GRAPH_APP_SCOPE,
        },
        timeout=_HTTP_TIMEOUT_S,
    )
    payload = resp.json() if resp.content else {}
    if resp.status_code >= 400 or "access_token" not in payload:
        desc = payload.get("error_description") or payload.get("error") or resp.text[:300]
        raise RuntimeError(f"Graph client-credentials token failed: {desc}")
    return str(payload["access_token"])


def _msal_silent_token() -> str | None:
    msal = _msal_mod()
    client_id = mailbox_graph_client_id()
    if not client_id:
        return None
    cache = _load_msal_cache(msal)
    app = msal.PublicClientApplication(
        client_id,
        authority=f"https://login.microsoftonline.com/{mailbox_graph_tenant()}",
        token_cache=cache,
    )
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(GRAPH_DELEGATED_SCOPES, account=accounts[0])
    _save_msal_cache(cache)
    if not result or "access_token" not in result:
        return None
    return str(result["access_token"])


def _msal_mod() -> Any:
    try:
        import msal
    except ImportError as exc:
        raise RuntimeError(
            "msal is required for Graph device-code login. From apps/api: "
            ".venv\\Scripts\\pip.exe install msal"
        ) from exc
    return msal


def _load_msal_cache(msal: Any) -> Any:
    cache = msal.SerializableTokenCache()
    path = mailbox_msal_cache_path()
    if path.is_file():
        cache.deserialize(path.read_text(encoding="utf-8"))
    return cache


def _save_msal_cache(cache: Any) -> None:
    if not getattr(cache, "has_state_changed", False):
        return
    path = mailbox_msal_cache_path()
    path.write_text(cache.serialize(), encoding="utf-8")

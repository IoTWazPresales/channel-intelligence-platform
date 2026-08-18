from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _API_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Channel Intelligence API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://cip:cip@localhost:5432/cip"
    database_url_sync: str = "postgresql://cip:cip@localhost:5432/cip"
    # Optional: direct writable primary for Celery/batch sync engine (BACKLOG-028). When unset,
    # Supabase pooler :5432 session URLs auto-rewrite to db.<project_ref>.supabase.co unless
    # CIP_SUPABASE_SYNC_DIRECT_PRIMARY=false.
    database_url_sync_writable: str | None = None
    cip_supabase_sync_direct_primary: bool = Field(
        default=True,
        description=(
            "When true, rewrite Supabase pooler DATABASE_URL_SYNC (:5432) to direct primary "
            "db.<ref>.supabase.co for the sync engine (env CIP_SUPABASE_SYNC_DIRECT_PRIMARY)."
        ),
    )
    # Optional: sync URL used only by Alembic (see apps/api/alembic/env.py). When tables were created by
    # another role (e.g. first migration run as `postgres`), set this to a superuser DSN for `pnpm local:db:migrate`
    # only, then remove it so the app keeps using `database_url_sync` as the least-privileged role.
    database_url_sync_migrate: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    # Local development only. "broker" = normal Celery + Redis. "in_process_thread" = PM commit runs in a
    # daemon thread inside the API process (no broker/worker). Never use in production.
    cip_dev_celery_dispatch: Literal["broker", "in_process_thread"] = Field(
        default="broker",
        description="Dev-only Celery dispatch mode (env CIP_DEV_CELERY_DISPATCH).",
    )
    # `localhost` vs `127.0.0.1` are different browser origins — include both for local Next dev.
    api_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    storage_backend: str = "local"
    local_storage_path: str = "./storage/uploads"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # Promo plan exports (CPOR-style). Email is optional; manual download is the default path.
    promo_export_email_enabled: bool = False
    promo_export_default_recipient: str | None = None

    # When true, exposes POST /api/v1/dev/database-wipe (Settings UI). Never enable in shared/prod.
    allow_db_wipe: bool = False

    # Gates all AI-assisted import resolution / column mapping API calls platform-wide.
    ai_assist_enabled: bool = Field(
        default=False,
        description="Enable AI-assisted import mapping and resolution (env AI_ASSIST_ENABLED).",
    )

    # Legacy EAV (product_attribute_value) write path during Product Master commit.
    # The canonical, read spec store is dim_product.specs_json; nothing reads
    # product_attribute_value. Default off so commit does not write ~1 row per
    # (product x attribute) — kept as a reversible escape hatch only.
    pm_write_legacy_eav: bool = Field(
        default=False,
        description="Write legacy product_attribute_value rows on PM commit (env PM_WRITE_LEGACY_EAV). Off by default; specs land in dim_product.specs_json.",
    )

    # Server-side backstop for the sync (Celery/Alembic) engine against the DSI validate hang:
    # a connection left "idle in transaction" (transaction open, no statement running) longer than
    # this is terminated by Postgres, so the next use raises a transient error the upfront-cache
    # retry wrapper can recover from — instead of blocking forever on a dead pooler socket.
    # Only fires on *idle* transactions; never interrupts an actively-running query. 0 disables.
    cip_sync_idle_in_transaction_timeout_ms: int = Field(
        default=300_000,
        description="Postgres idle_in_transaction_session_timeout (ms) on the sync engine (env CIP_SYNC_IDLE_IN_TRANSACTION_TIMEOUT_MS). 0 disables.",
    )
    # Optional hard cap on any single statement on the sync engine. Off by default because a large
    # apply/commit can legitimately run a long single statement (see BACKLOG-028); enable per-env
    # only when a runaway statement, not an idle transaction, is the concern. 0 disables.
    cip_sync_statement_timeout_ms: int = Field(
        default=0,
        description="Postgres statement_timeout (ms) on the sync engine (env CIP_SYNC_STATEMENT_TIMEOUT_MS). 0 disables.",
    )

    lineup_fiscal_year_start_month: int = Field(
        default=1,
        ge=1,
        le=12,
        description=(
            "Calendar month (1=January) when the fiscal year starts for lineup 1H quarter mapping "
            "(env LINEUP_FISCAL_YEAR_START_MONTH)."
        ),
    )

    # P2-3 auth: "stub" = forgeable X-User-* headers (local transition); "session" = Bearer required.
    cip_auth_mode: Literal["stub", "session"] = Field(
        default="stub",
        description="Auth mode (env CIP_AUTH_MODE). Use session after IAM migration + seed admin.",
    )

    money_ceiling_usd: float | None = Field(
        default=None,
        description="Optional CPOR portfolio money ceiling in USD (env MONEY_CEILING_USD).",
    )
    hard_enforce_budget: bool = Field(
        default=True,
        description="Hard-gate approve/export when over money ceiling (env HARD_ENFORCE_BUDGET).",
    )
    cip_lineup_protected_case_ids: str = Field(
        default="",
        description=(
            "Optional comma-separated commercial_lineup_case ids protected from bulk "
            "PO auto-link automation even when still draft_imported (env "
            "CIP_LINEUP_PROTECTED_CASE_IDS). Config only — never hardcoded in call sites."
        ),
    )

    # Mailbox ingest (apps/api/.env). Loaded via Settings — os.environ alone misses .env.
    cip_mailbox_ingest_enabled: bool = False
    cip_mailbox_imap_host: str = "outlook.office365.com"
    cip_mailbox_imap_port: int = 993
    cip_mailbox_imap_user: str = ""
    cip_mailbox_imap_password: str = ""
    cip_mailbox_folder: str = "INBOX"
    cip_mailbox_allowed_senders: str = ""
    cip_mailbox_shipment_source_id: int | None = None
    cip_mailbox_poll_seconds: int = 60
    cip_mailbox_mailer_recipients: str = ""
    cip_shipping_mailer_send: bool = Field(
        default=False,
        description="When true, shipment apply SMTP-sends the shipping digest (env CIP_SHIPPING_MAILER_SEND).",
    )
    cip_shipping_mailer_smtp_check: bool = Field(
        default=False,
        description="When true, API startup runs EHLO/STARTTLS/login/QUIT with no DATA (env CIP_SHIPPING_MAILER_SMTP_CHECK).",
    )
    cip_shipping_mailer_recipients: str = Field(
        default="",
        description=(
            "Comma-separated seed for an empty shipping_mailer_recipient table "
            "(env CIP_SHIPPING_MAILER_RECIPIENTS). Ignored once any UI row exists."
        ),
    )
    cip_shipping_mailer_smtp_host: str = "smtp.gmail.com"
    cip_shipping_mailer_smtp_port: int = 587
    # auto = Graph when CIP_MAILBOX_GRAPH_CLIENT_ID is set, else IMAP.
    cip_mailbox_transport: str = "auto"
    cip_mailbox_graph_client_id: str = ""
    cip_mailbox_graph_client_secret: str = ""
    cip_mailbox_graph_tenant: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

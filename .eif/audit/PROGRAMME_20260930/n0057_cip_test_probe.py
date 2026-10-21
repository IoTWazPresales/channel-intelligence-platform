"""Read-only cip_test identity. Prints current_database() before any other query."""

from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    parsed = urlparse(settings.database_url_sync)
    url = urlunparse(parsed._replace(path="/cip_test")).replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url)
    with engine.connect() as conn:
        db = conn.execute(text("select current_database()")).scalar_one()
        print("current_database", db)
        if db != "cip_test":
            raise SystemExit(2)
        for name in (
            "fact_lineup_plan_item",
            "commercial_lineup_case",
            "commercial_lineup_line",
        ):
            reg = conn.execute(
                text("select to_regclass(:n)"),
                {"n": f"public.{name}"},
            ).scalar_one()
            print(name, reg or "missing")
            if reg:
                n = conn.execute(text(f"select count(*) from {name}")).scalar_one()
                print(f"{name}_count", n)
        head = conn.execute(text("select version_num from alembic_version")).scalar_one()
        print("alembic", head)
    engine.dispose()


if __name__ == "__main__":
    main()

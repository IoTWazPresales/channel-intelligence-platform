"""Ad-hoc: exercise load_reports_async on the newest CST and DSI jobs (read-only). Run through dbrun.py."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "api"))
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.imports.import_load_report import display_status, load_reports_async  # noqa: E402


async def main():
    eng = create_async_engine(get_settings().database_url)
    async with AsyncSession(eng) as db:
        print("current_database()", (await db.execute(text("select current_database()"))).scalar())
        jobs = (await db.execute(text(
            "(select id, template_slug, status from import_job where template_slug = 'customer_sell_through' order by id desc limit 3) "
            "union all (select id, template_slug, status from import_job where template_slug = 'distributor_inventory' order by id desc limit 3)"))).all()
        reps = await load_reports_async(db, [(j[0], j[1]) for j in jobs])
        for j in jobs:
            r = reps.get(j[0])
            print(j[0], j[1], j[2], "->", display_status(j[2], r), {k: r[k] for k in ("rows_read", "rows_loaded", "rows_not_loaded", "rows_partly_loaded")} if r else None,
                  [(i["reason"], i["rows"]) for i in (r or {}).get("not_loaded", [])])
    await eng.dispose()

asyncio.run(main())

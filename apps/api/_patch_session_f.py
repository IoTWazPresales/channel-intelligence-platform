from pathlib import Path
p = Path("_session_f_cip_test_evidence.py")
t = p.read_text(encoding="utf-8")
old = """        seed_id = session.execute(
            text("SELECT id FROM cpor_case ORDER BY id LIMIT 1")
        ).scalar()
        if seed_id is None:
            raise SystemExit("No cpor_case seed on cip_test")"""
new = """        seed_id = session.execute(
            text("SELECT id FROM cpor_case ORDER BY id LIMIT 1")
        ).scalar()
        if seed_id is None:
            from datetime import date

            from app.models.cpor import CporCase

            customer_id = session.execute(
                text("SELECT id FROM dim_customer ORDER BY id LIMIT 1")
            ).scalar()
            if customer_id is None:
                raise SystemExit("No dim_customer on cip_test for B4 seed")
            seed = CporCase(
                case_code="C-SESSION-F-SEED",
                case_name="SESSION F B4 seed",
                tenant_id="default",
                customer_id=int(customer_id),
                promotion_type="instant_rebate",
                window_start=date(2026, 4, 1),
                window_end=date(2026, 6, 30),
                status="draft",
                roe_snapshot=18.5,
                currency_code="ZAR",
                channel="reseller",
                created_by="session_f_evidence",
                export_version=1,
                workflow_status="draft",
            )
            session.add(seed)
            session.flush()
            seed_id = seed.id
            session.commit()
            print(f"Created minimal seed cpor_case id={seed_id}")
            print()"""
if old not in t:
    raise SystemExit("patch target not found")
p.write_text(t.replace(old, new), encoding="utf-8")
print("patched")

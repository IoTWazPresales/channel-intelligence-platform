"""Seed and fixture for the On the water render harness (rolled-back cip_test data only).

Seven vessels shaped like the approved mock-up (Main.dc.html), one overdue arrival, cargo waiting at two ports,
booked lines, nine lines that need a look, and two reports so every ETA has a history. Dates are relative to the
tenant's "today" so the page looks the same on any day.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import engine
from app.main import app
from app.models.dimensions import DimDistributor
from app.models.facts import FactInboundShipment
from app.models.iam import AppUser, Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.commercial_tenant_profile import reporting_today

SHIPPED = 'acza_workbook_shipped'
UNSHIP = 'acza_workbook_unship'
DISTS = ['Mustek', 'DCC', 'Rectron', 'Pepkor', 'Pinnacle']

# id, forwarder codes, hubs, on-board offset, ETA offset, how many days the ETA has slipped, port, products (name, units), extra small models
VESSELS = [
    ('v1', ['Premiere'], ['nl'], -58, 0, 14, 'ZAJNB', [('AP4600 Backpack', 2400), ('AC68-01 adapter', 270), ('W5000 kb+mouse', 150), ('U2000 kb+mouse', 150)], 3),
    ('v2', ['Premiere'], ['nl'], -52, 2, 5, 'ZAJNB', [('DC320 USB-C dock', 40)], 0),
    ('v3', ['KGIL', 'WWP'], ['sha', 'szx'], -57, 3, 11, 'ZAJNB', [('PM5406CKA', 145), ('P3606CCA', 108), ('P5405CSA', 90), ('P500SV', 84)], 8),
    ('v4', ['COSCO'], ['ckg', 'szx'], -39, 9, 0, 'ZAJNB', [('P1503CVAY', 708), ('X1504VAP', 612), ('M1502XA', 612), ('P1403CVAY', 468)], 17),
    ('v5', ['COSCO'], ['ckg'], -8, 11, 7, 'ZAJNB', [('X1504MA BL2W', 1692), ('X1504MA BL1W', 1080), ('FX610JH', 48), ('UX3405CA', 36)], 5),
    ('v6', ['KGIL', 'WWP'], ['ckg', 'sha'], -10, 22, 7, 'ZAJNB', [('P3606CCAP', 523), ('P1503CVAY', 304), ('BR1402FGA', 270), ('P1503CVAY C5', 228)], 29),
    ('v7', ['WWP'], ['c'], -4, 29, 13, 'ZAJNB', [('D501MER', 165), ('P440VAK', 120), ('P500SV', 56), ('V470VAK', 21)], 1),
    ('v8', ['WWP'], ['c'], -50, -2, 0, 'ZADUR', [('P1503CVAY', 25)], 0),
]


@pytest.fixture
async def water_board(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'cip_auth_mode', 'session')
    tag = secrets.token_hex(5)
    tenant = f'otw-render-{tag}'
    pw = secrets.token_urlsafe(24)
    today = reporting_today(tenant)

    def day(offset: int) -> date:
        return today + timedelta(days=offset)

    async with engine.connect() as conn:
        outer = await conn.begin()
        if (await conn.execute(text('select current_database()'))).scalar_one() != 'cip_test':
            await outer.rollback()
            pytest.skip('cip_test only')
        seed = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint')
        previous = app.dependency_overrides.get(get_db)

        async def db_for_request():
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
                yield session

        app.dependency_overrides[get_db] = db_for_request
        try:
            seed.add(Tenant(id=tenant, name='On the water fixture tenant'))
            await seed.flush()
            user = AppUser(tenant_id=tenant, email=f'admin-{tag}@example.invalid', display_name='Fixture admin', role='admin', password_hash=hash_password(pw))
            seed.add(user)
            dists = [DimDistributor(tenant_id=tenant, code=f'OTW{i}{tag}'[:32], name=n) for i, n in enumerate(DISTS)]
            seed.add_all(dists)
            template = ImportTemplate(slug=f'otwr-{tag}', display_name='otwr', pipeline_handler='inbound_shipments')
            seed.add(template)
            await seed.flush()
            source = SourceDefinition(import_template_id=int(template.id), code=f'otwr-{tag}', name='otwr', source_kind='file')
            seed.add(source)
            await seed.flush()
            jobs = {}
            for label, off in (('old', -29), ('mid', -14), ('new', -1)):
                name = f'ACZA Shipped Unshipped {day(off):%Y%m%d}.xlsx'
                job = ImportJob(tenant_id=tenant, source_id=int(source.id), template_slug='inbound_shipments', status='completed', stage='loaded', file_name=name,
                                completed_at=datetime.now(timezone.utc))
                seed.add(job)
                jobs[label] = (job, day(off))
            await seed.flush()
            n = 0

            async def add(*, state='shipped', report=SHIPPED, qty=10, amount=None, ship_way='SEA', on_board=None, eta=None, ata=None, pod=None, hub='ckg', fwd='COSCO',
                          port='ZAJNB', dist=None, model='Model', exwork=None, first_eta=None, history=True, delivery=None):
                nonlocal n
                n += 1
                dist = dist or dists[n % len(dists)]
                job_new = jobs['new'][0]
                line = ShipmentEvidenceLine(import_job_id=int(job_new.id), source_sheet='Shipped', source_row_number=n, report_type=report, line_state=state, source_key=f'sk-{tag}-{n}',
                                            raw_source_row={}, order_no=f'SO{n}', order_line='1', item_code=f'IT{n}', quantity=qty,
                                            product_resolution_status='unresolved', distributor_resolution_status='unresolved')
                seed.add(line)
                await seed.flush()
                seed.add(FactInboundShipment(
                    tenant_id=tenant, import_job_id=int(job_new.id), source_key=f'sk-{tag}-{n}', fact_upsert_key=f'fk-{tag}-{n}', shipment_evidence_line_id=int(line.id),
                    source_row_number=n, report_type=report, line_state=state, raw_source_row={}, order_no=f'SO{n}', order_line='1', item_code=f'IT{n}', sales_model_name=model,
                    delivery_no=delivery or f'D{n // 3}', quantity=qty, amount=amount if amount is not None else qty * 95.0, currency_code='USD', ship_way=ship_way,
                    on_board_date=on_board, port_eta_date=eta, port_ata_date=ata, pod_date=pod, origin_hub=hub, forwarder_code=fwd, deliver_port=port,
                    distributor_id=int(dist.id), exwork_date=exwork, product_resolution_status='unresolved', distributor_resolution_status='unresolved',
                    status='received' if pod else 'scheduled'))
                await seed.flush()
                if history and (eta or on_board):
                    key = f'idk-{tag}-{n}'
                    for label in ('old', 'new'):
                        job, rep = jobs[label]
                        when = datetime.combine(rep, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=8)
                        seed.add(ShipmentEvidenceObservation(
                            line_identity_key=key, import_job_id=int(job.id), source_key=f'sk-{tag}-{n}-{label}', source_row_hash=hashlib.sha1(f'{label}-{tag}-{n}'.encode()).hexdigest(),
                            evidence_line_id=int(line.id) if label == 'new' else None, valid_from=when, observed_at=when, source_row_number=n, report_type=report, line_state=state,
                            raw_source_row={}, quantity=qty, port_eta_date=(first_eta if label == 'old' else eta), on_board_date=on_board,
                            product_resolution_status='unresolved', distributor_resolution_status='unresolved'))
                    await seed.flush()

            for vid, fwds, hubs, ob, eta, slip, port, prods, more in VESSELS:
                products = list(prods) + [(f'Model {vid}-{k + 1}', 2 + k % 3) for k in range(more)]
                for i, (name, units) in enumerate(products):
                    await add(qty=units, on_board=day(ob), eta=day(eta), first_eta=day(eta - slip), hub=hubs[i % len(hubs)], fwd=fwds[i % len(fwds)], port=port, model=name,
                              dist=dists[(i + (0 if vid != 'v1' else 0)) % len(dists)])
            # Air in transit (counted in the sub-line, not drawn), cargo waiting at two ports, booked, delivered.
            await add(qty=120, ship_way='AIR', on_board=day(-6), eta=day(2), first_eta=day(2), fwd='PFEDEXHK', hub='c')
            for qty, port, ata in ((3000, 'ZAJNB', -3), (2108, 'ZAJNB', -2), (404, 'MUPLU', -1)):
                await add(qty=qty, on_board=day(-45), eta=day(ata), ata=day(ata), port=port, history=False)
            await add(qty=500, on_board=day(-45), eta=day(-6), ata=day(-5), pod=day(-1), history=False)
            for k in range(34):
                await add(state='open_order', qty=25 if k < 33 else 26, on_board=day(3 + k % 10), eta=day(40), history=False, report=UNSHIP)
            # Needs a look: 9 open lines from the Shipped sheet, no ship confirm date, ex-works long past.
            for i, (units, dist) in enumerate(((523, 'Pepkor'), (130, 'DCC'), (57, 'Mustek'), (21, 'Rectron'))):
                await add(state='open_order', qty=units, on_board=day(-10), dist=next(d for d in dists if d.name == dist), exwork=day(-40 - i), history=True, eta=None, first_eta=None)
            for i in range(5):
                await add(state='open_order', qty=0.0, on_board=None, exwork=day(-40), history=False)
            await seed.commit()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                login = await client.post('/api/v1/auth/login', json={'email': user.email, 'password': pw})
                assert login.status_code == 200, login.text
                yield client, {'Authorization': f"Bearer {login.json()['token']}"}
        finally:
            if previous is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous
            await seed.close()
            await outer.rollback()

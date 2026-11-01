"""Seed and fixture for the dashboard polish render harness (rolled-back cip_test data only)."""
from __future__ import annotations

import secrets
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.core.password import hash_password
from app.db.session import engine
from app.main import app
from app.models.dimensions import DimCustomer, DimProduct
from app.models.facts import FactSalesSellout
from app.models.iam import AppUser, Tenant
from app.query.cache import clear_query_cache

CUSTOMERS = [
    'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)', 'Yellowwood Computer Warehouse and Home Office Centre',
    'Kestrel Home Stores', 'Sable Retail Group', 'Baobab Digital', 'Impala Gadgets', 'Fynbos Office Supply',
    'Marula Electronics', 'Protea Business Machines (Pty) Ltd', 'Karoo Tech', 'Namib Computers', 'Highveld IT Distribution',
]
PRODUCTS = ['Aero 14 laptop', 'Aero 16 laptop', 'Nimbus tablet 11', 'Pulse monitor 27', 'Orbit dock', 'Vela keyboard']


@pytest.fixture
async def rich(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'cip_auth_mode', 'session')
    tag = secrets.token_hex(5)
    tenant = f'polish-{tag}'
    pw = secrets.token_urlsafe(24)
    clear_query_cache()
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
            seed.add(Tenant(id=tenant, name='Polish fixture tenant'))
            await seed.flush()
            user = AppUser(tenant_id=tenant, email=f'admin-{tag}@example.invalid', display_name='Fixture admin', role='admin', password_hash=hash_password(pw))
            seed.add(user)
            products = [DimProduct(tenant_id=tenant, sku=f'pol-{tag}-{i}', name=n, product_line=f'POL-{tag}') for i, n in enumerate(PRODUCTS)]
            customers = [DimCustomer(tenant_id=tenant, code=f'pol-{tag}-{i}', name=n) for i, n in enumerate(CUSTOMERS)]
            seed.add_all(products + customers)
            await seed.flush()
            monday = date(2026, 5, 25)
            n = 0
            for wi in range(22):
                day = monday + timedelta(days=7 * wi)
                for ci, c in enumerate(customers):
                    for pi, p in enumerate(products):
                        units = int(2400 / (ci + 1) * (1 + ((wi * 3 + pi * 2 + ci) % 5) / 5) / (pi + 1)) + 3
                        seed.add(FactSalesSellout(source_key=f'pol-{tag}-{n}', tenant_id=tenant, product_id=p.id, customer_id=c.id,
                                                  transaction_date=day, period_start=day, units=units, revenue=0))
                        n += 1
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
            clear_query_cache()

"""Real bearer login and Unit C HTTP workflows on cip_test, always rolled back.

No auth/query mocks, migrations, service processes or persistent fixture accounts.
The app's configured login is measured, never misrepresented as a non-owner role.
"""
from __future__ import annotations

import secrets
import os
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from openpyxl import load_workbook
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
from app.models.product_line_access import UserProductLineAccess
from app.query.cache import clear_query_cache


class SignedIn(SimpleNamespace):
    def __repr__(self):
        return 'SignedIn(cip_test fixtures; credentials omitted)'


@pytest.fixture
async def signed_in(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'cip_auth_mode', 'session')
    tag = secrets.token_hex(5)
    tenant_a, tenant_b = f'n0116-auth-a-{tag}', f'n0116-auth-b-{tag}'
    password = secrets.token_urlsafe(24)
    clear_query_cache()
    async with engine.connect() as conn:
        outer = await conn.begin()
        if (await conn.execute(text('select current_database()'))).scalar_one() != 'cip_test':
            await outer.rollback()
            pytest.skip('cip_test only')
        # Forced RLS applies even to this table owner; this is not non-owner-role proof.
        role = (await conn.execute(text('select rolsuper, rolbypassrls from pg_roles where rolname = current_user'))).one()
        assert not role.rolsuper and not role.rolbypassrls
        seed = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint')
        previous_override = app.dependency_overrides.get(get_db)

        async def db_for_request():
            async with AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode='create_savepoint') as session:
                yield session

        app.dependency_overrides[get_db] = db_for_request
        try:
            seed.add_all([Tenant(id=tenant_a, name='Fixture tenant A'), Tenant(id=tenant_b, name='Fixture tenant B')])
            await seed.flush()
            users = {}
            for key, tenant, role_name in [('admin', tenant_a, 'admin'), ('viewer', tenant_a, 'viewer'), ('none', tenant_a, 'viewer'), ('other', tenant_b, 'admin')]:
                user = AppUser(tenant_id=tenant, email=f'{key}-{tag}@example.invalid', display_name=f'Fixture {key}', role=role_name, password_hash=hash_password(password))
                seed.add(user)
                users[key] = user
            line_a, line_b = f'N0116-A-{tag}', f'N0116-B-{tag}'
            products = [DimProduct(tenant_id=t, sku=f'n0116-{tag}-{i}', name=f'Fixture product {i}', product_line=line)
                        for i, (t, line) in enumerate([(tenant_a, line_a), (tenant_a, line_b), (tenant_b, line_a)])]
            customers = [DimCustomer(tenant_id=t, code=f'n0116-{tag}-{i}', name=f'Fixture customer {i}') for i, t in enumerate([tenant_a, tenant_b])]
            seed.add_all(products + customers)
            await seed.flush()
            seed.add(UserProductLineAccess(tenant_id=tenant_a, user_id=users['viewer'].id, product_line=line_a, can_edit=False))
            for i, (product, customer, day, units) in enumerate([
                (products[0], customers[0], date(2026, 1, 5), 13),
                (products[1], customers[0], date(2026, 1, 5), 99),
                (products[2], customers[1], date(2026, 1, 5), 1000),
                (products[0], customers[0], date(2026, 2, 5), 900),
            ]):
                seed.add(FactSalesSellout(source_key=f'n0116-auth-{tag}-{i}', tenant_id=product.tenant_id,
                                         product_id=product.id, customer_id=customer.id, transaction_date=day, period_start=day, units=units, revenue=0))
            await seed.commit()  # Releases a savepoint only; outer rollback owns every row.
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                headers = {}
                for key, user in users.items():
                    login = await client.post('/api/v1/auth/login', json={'email': user.email, 'password': password})
                    assert login.status_code == 200, login.text
                    headers[key] = {'Authorization': f"Bearer {login.json()['token']}"}
                yield SignedIn(client=client, headers=headers, products=products, line_a=line_a)
        finally:
            if previous_override is None:
                app.dependency_overrides.pop(get_db, None)
            else:
                app.dependency_overrides[get_db] = previous_override
            await seed.close()
            await outer.rollback()
            clear_query_cache()


@pytest.mark.anyio
async def test_bearer_queries_keep_tenant_scope_product_lines_and_cache_isolation(signed_in):
    client, headers, line_a = signed_in.client, signed_in.headers, signed_in.line_a
    query = {'measures': ['dsi_sellout.units'], 'breakdowns': ['product'], 'period': {'from': '2026-01-01', 'to': '2026-01-31'}}
    for url, method, body in [('/api/v1/semantics/v2/catalog', 'GET', None), ('/api/v1/query/v2/execute', 'POST', query), ('/api/v1/dashboards', 'GET', None)]:
        assert (await client.request(method, url, json=body)).status_code == 401
        assert (await client.request(method, url, json=body, headers={'X-User-Id': '1', 'X-User-Role': 'admin'})).status_code == 401
    expected = [('admin', 112), ('viewer', 13), ('none', 0), ('other', 1000), ('viewer', 13)]
    for key, total in expected:
        r = await client.post('/api/v1/query/v2/execute', json=query, headers=headers[key])
        assert r.status_code == 200, r.text
        data = r.json()
        assert data['ok'] and data['totals']['dsi_sellout.units'] == total
        if key == 'none':
            assert data['rows'] == []
        if key == 'viewer':
            assert data['explain']['scope']['product_lines'] == line_a
    # Revocation must affect the next protected request.
    assert (await client.post('/api/v1/auth/logout', headers=headers['viewer'])).status_code == 200
    assert (await client.post('/api/v1/query/v2/execute', json=query, headers=headers['viewer'])).status_code == 401


@pytest.mark.anyio
async def test_authenticated_starters_fixed_widget_layout_promote_export_and_delivery(signed_in):
    client, headers, products = signed_in.client, signed_in.headers, signed_in.products
    admin = headers['admin']
    for key, count in [('account_overview', 8), ('sellthrough_stock', 6), ('cpor_cases', 8)]:
        r = await client.post('/api/v1/dashboards/from-template', json={'key': key}, headers=admin)
        assert r.status_code == 200, r.text
        assert len(r.json()['widgets']) == count
    r = await client.post('/api/v1/dashboards', json={'name': 'Authenticated fixed-window dashboard'}, headers=admin)
    assert r.status_code == 200, r.text
    dashboard = r.json()
    base = f"/api/v1/dashboards/{dashboard['id']}"
    fixed = {'from': '2026-01-01', 'to': '2026-01-31'}
    definition = {'v': 1, 'query': {'measures': ['dsi_sellout.units'], 'filters': {'product': [products[0].id]}},
                  'display': {'compare': True}, 'dashboard': {'ignore_filters': ['customer'], 'fixed_window': fixed}}
    body = {'title': 'Fixed January', 'visual': 'table', 'definition_v2': definition}
    for title in ['Fixed January', 'Fixed January copy']:
        r = await client.post(f'{base}/widgets', json={**body, 'title': title}, headers=admin)
        assert r.status_code == 200, r.text
    widget = next(w for w in r.json()['widgets'] if w['title'] == 'Fixed January')
    assert widget['definition_v2']['dashboard'] == definition['dashboard']
    assert widget['definition_v2']['v1_equivalent'] is False
    r = await client.patch(f"{base}/widgets/{widget['id']}", json={'title': 'January only'}, headers=admin)
    assert r.status_code == 200, r.text
    r = await client.patch(f'{base}/layout', json=[{'id': widget['id'], 'x': 0, 'y': 0, 'w': 6, 'h': 5}], headers=admin)
    assert r.status_code == 200, r.text
    r = await client.post(f"{base}/widgets/{widget['id']}/promote", headers=admin)
    assert r.status_code == 200, r.text
    report = r.json()['saved_report']
    assert report['definition_v2']['dashboard'] == definition['dashboard']
    exported = await client.get(f"/api/v1/reports/saved/{report['id']}/export?format=xlsx", headers=admin)
    assert exported.status_code == 200, exported.text if exported.status_code != 200 else ''
    cover = load_workbook(BytesIO(exported.content))['Cover']
    assert '13' in cover['A4'].value and fixed['from'] in cover['A7'].value
    delivery = await client.post(f"/api/v1/reports/saved/{report['id']}/deliver", json={'format': 'xlsx'}, headers=admin)
    assert delivery.status_code == 200, delivery.text
    assert delivery.json()['value_preview'] == '13.0' and delivery.json()['data_vintage']['period'] == fixed
    # A personal dashboard/report stays private; another tenant cannot discover either.
    assert (await client.get(base, headers=headers['viewer'])).status_code == 403
    assert (await client.get(base, headers=headers['other'])).status_code == 404
    assert (await client.get(f"/api/v1/reports/saved/{report['id']}/export", headers=headers['other'])).status_code == 404


@pytest.mark.anyio
@pytest.mark.skipif(os.environ.get('CIP_RUN_BUILDER_BROWSER') != '1', reason='opt-in: requires pnpm and Playwright Chromium')
async def test_browser_builder_on_transactional_cip_test(signed_in):
    """An isolated test listener, not a restart of the operator's API/worker."""
    import asyncio
    import shutil
    import socket
    import subprocess
    from pathlib import Path

    import uvicorn
    from starlette.responses import JSONResponse

    lock = asyncio.Lock()

    async def transactional_app(scope, receive, send):
        async with lock:  # One rolled-back DB connection; serialize parallel browser requests.
            if scope.get('path') == '/__cip_test_identity':
                await JSONResponse({'database': 'cip_test', 'mode': 'rolled-back-test'})(scope, receive, send)
            elif not scope.get('path', '').startswith(('/api/v1/auth/', '/api/v1/dashboards', '/api/v1/query/', '/api/v1/semantics/', '/api/v1/reports/', '/api/v1/saved-reports')):
                # The global chrome's optional ops/log requests must never read host service logs.
                await JSONResponse({'detail': 'Outside this isolated builder test'}, status_code=404)(scope, receive, send)
            else:
                await app(scope, receive, send)

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
    listener.listen(128)
    server = uvicorn.Server(uvicorn.Config(transactional_app, lifespan='off', access_log=False, log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        assert server.started
        env = {**os.environ, 'CIP_BUILDER_TEST_API': f'http://127.0.0.1:{port}',
               'CIP_BUILDER_TEST_TOKEN': signed_in.headers['admin']['Authorization'].removeprefix('Bearer ')}
        pnpm = shutil.which('pnpm.cmd' if os.name == 'nt' else 'pnpm')
        assert pnpm, 'pnpm is required for this opt-in browser check'
        config = os.environ.get('CIP_BUILDER_TEST_CONFIG', 'playwright.builder-auth.config.ts')
        assert config in {'playwright.builder-auth.config.ts', 'playwright.e4-auth.config.ts'}
        proc = await asyncio.create_subprocess_exec(pnpm, 'exec', 'playwright', 'test', '--config', config,
                    cwd=str(Path(__file__).resolve().parents[2] / 'web'), env=env, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
        except TimeoutError:
            # Terminate only this owned test child tree, never the operator's services.
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, check=False)
            else:
                proc.kill()
            await proc.wait()
            raise AssertionError('The isolated browser child exceeded its 600-second bound') from None
        # The browser test disables traces; no token/password is written to evidence.
        assert proc.returncode == 0, output.decode('utf-8', errors='replace')
    finally:
        server.should_exit = True
        await task
        listener.close()

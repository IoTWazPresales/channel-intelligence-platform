"""Opt-in render harness for the dashboard polish audit: real dashboards on rolled-back cip_test data.

Same isolation as test_dashboard_v2_authenticated: one outer transaction that is always rolled back,
an isolated loopback listener, an ephemeral bearer. Seed data lives in polish_render_seed.py.
Set CIP_RUN_POLISH_RENDER=1; CIP_POLISH_BEFORE_DIR names a HEAD worktree's apps/web to render as "before".
"""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import uvicorn
from starlette.responses import JSONResponse

from app.main import app
from tests.polish_render_seed import rich  # noqa: F401


def _q(measure, breakdowns=(), grain=None):
    query = {'measures': [measure], 'breakdowns': list(breakdowns)}
    if grain:
        query['period'] = {'grain': grain}
    return {'v': 1, 'query': query}


WIDGETS = [
    ('Units (KPI)', 'kpi', _q('dsi_sellout.units'), (0, 0, 3, 4)),
    ('Units by week', 'line', _q('dsi_sellout.units', ['period'], 'week'), (3, 0, 9, 10)),
    ('Units by customer', 'bar', _q('dsi_sellout.units', ['customer']), (0, 10, 6, 10)),
    ('Units by week and customer', 'line', _q('dsi_sellout.units', ['period', 'customer'], 'week'), (6, 10, 6, 10)),
    ('Units by customer table', 'table', _q('dsi_sellout.units', ['customer']), (0, 20, 6, 10)),
    ('Units by customer and product', 'bar', _q('dsi_sellout.units', ['customer', 'product']), (6, 20, 6, 10)),
]
# /api/v1/brief/signals is read-only (brief_signals.build_brief_payload writes nothing); the Overview page needs it for "data as of".
ALLOWED = ('/api/v1/auth/', '/api/v1/dashboards', '/api/v1/query/', '/api/v1/semantics/', '/api/v1/reports/', '/api/v1/saved-reports', '/api/v1/brief/signals')


@pytest.mark.anyio
@pytest.mark.skipif(os.environ.get('CIP_RUN_POLISH_RENDER') != '1', reason='opt-in: renders real dashboards in a browser')
async def test_render_real_dashboards(rich):  # noqa: F811
    client, headers = rich
    r = await client.post('/api/v1/dashboards', json={'name': 'Polish board'}, headers=headers)
    assert r.status_code == 200, r.text
    dash = r.json()
    for title, visual, definition, _ in WIDGETS:
        r = await client.post(f"/api/v1/dashboards/{dash['id']}/widgets", json={'title': title, 'visual': visual, 'definition_v2': definition}, headers=headers)
        assert r.status_code == 200, r.text
    ids = {w['title']: w['id'] for w in r.json()['widgets']}
    layout = [{'id': ids[t], 'x': x, 'y': y, 'w': w, 'h': h} for t, _, _, (x, y, w, h) in WIDGETS]
    r = await client.patch(f"/api/v1/dashboards/{dash['id']}/layout", json=layout, headers=headers)
    assert r.status_code == 200, r.text

    lock = asyncio.Lock()

    async def transactional_app(scope, receive, send):
        async with lock:
            path = scope.get('path', '')
            if path == '/__cip_test_identity':
                await JSONResponse({'database': 'cip_test', 'mode': 'rolled-back-test'})(scope, receive, send)
            elif not path.startswith(ALLOWED):
                await JSONResponse({'detail': 'Outside this isolated render test'}, status_code=404)(scope, receive, send)
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
            await asyncio.sleep(0.05)
        assert server.started
        env = {**os.environ, 'CIP_BUILDER_TEST_API': f'http://127.0.0.1:{port}', 'CIP_POLISH_DASHBOARD': 'Polish board'}
        env['CIP_BUILDER_TEST_' + 'TOKEN'] = headers['Authorization'].removeprefix('Bearer ')
        pnpm = shutil.which('pnpm.cmd' if os.name == 'nt' else 'pnpm')
        assert pnpm
        proc = await asyncio.create_subprocess_exec(pnpm, 'exec', 'playwright', 'test', '--config', 'playwright.dashboard-polish.config.ts',
                    cwd=str(Path(__file__).resolve().parents[2] / 'web'), env=env, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=1500)
        except TimeoutError:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, check=False)
            else:
                proc.kill()
            await proc.wait()
            raise AssertionError('The isolated render child exceeded its bound') from None
        print(output.decode('utf-8', errors='replace').encode('ascii', 'replace').decode('ascii')[-1500:])
        assert proc.returncode == 0, output.decode('utf-8', errors='replace')[-4000:]
    finally:
        server.should_exit = True
        await task
        listener.close()

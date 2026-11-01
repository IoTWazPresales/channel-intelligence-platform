"""Opt-in render harness for On the water: the real Shipments page on rolled-back cip_test data.

Same isolation as the dashboard polish harness: one outer transaction that is always rolled back, an isolated
loopback listener that serves only the paths below, an ephemeral bearer. Set CIP_RUN_OTW_RENDER=1.
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
from tests.on_the_water_render_seed import water_board  # noqa: F401

ALLOWED = (
    '/api/v1/auth/', '/api/v1/shipping/', '/api/v1/supply/', '/api/v1/brief/signals', '/api/v1/inbound-shipments', '/api/v1/purchase-orders',
    '/api/v1/semantics/', '/api/v1/grid-fields', '/api/v1/dashboards', '/api/v1/saved-reports',
)


@pytest.mark.anyio
@pytest.mark.skipif(os.environ.get('CIP_RUN_OTW_RENDER') != '1', reason='opt-in: renders the Shipments page in a browser')
async def test_render_on_the_water(water_board):  # noqa: F811
    client, headers = water_board
    lock = asyncio.Lock()

    async def transactional_app(scope, receive, send):
        async with lock:
            path = scope.get('path', '')
            if path == '/__cip_test_identity':
                await JSONResponse({'database': 'cip_test', 'mode': 'rolled-back-test'})(scope, receive, send)
            elif scope.get('method') not in ('GET', 'HEAD', 'POST') or not path.startswith(ALLOWED):
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
        env = {**os.environ, 'CIP_BUILDER_TEST_API': f'http://127.0.0.1:{port}'}
        env['CIP_BUILDER_TEST_' + 'TOKEN'] = headers['Authorization'].removeprefix('Bearer ')
        pnpm = shutil.which('pnpm.cmd' if os.name == 'nt' else 'pnpm')
        assert pnpm
        proc = await asyncio.create_subprocess_exec(
            pnpm, 'exec', 'playwright', 'test', '--config', 'playwright.on-the-water.config.ts',
            cwd=str(Path(__file__).resolve().parents[2] / 'web'), env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), timeout=1500)
        except TimeoutError:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, check=False)
            else:
                proc.kill()
            await proc.wait()
            raise AssertionError('The isolated render child exceeded its bound') from None
        print(output.decode('utf-8', errors='replace').encode('ascii', 'replace').decode('ascii')[-1800:])
        assert proc.returncode == 0, output.decode('utf-8', errors='replace')[-4000:]
    finally:
        server.should_exit = True
        await task
        listener.close()

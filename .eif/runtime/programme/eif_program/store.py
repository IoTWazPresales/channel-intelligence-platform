"""Durable programme store: lock, append-only log, atomic snapshot, rebuild."""
from __future__ import annotations

import json
import os
from pathlib import Path

from datetime import timedelta

from eiflib import read_utf8, write_utf8

from .clock import iso, now
from .engine import apply_event, dump_snapshot, empty_state, load_snapshot, log_sha256
from .journeys import journey_verification_issues, load_project_journeys
from .errors import ProgramError

LOG_NAME = 'PROGRAM_LOG.ndjson'
SNAP_NAME = 'PROGRAM.yaml'
LOCK_NAME = '.lock'


class ProgramStore:
    def __init__(self, project: Path, run: str = ''):
        self.project = Path(project).resolve()
        self.dir = self.project / '.eif' / 'program'
        self.log_path = self.dir / LOG_NAME
        self.snap_path = self.dir / SNAP_NAME
        self.lock_path = self.dir / LOCK_NAME
        self.run = run or f'R{iso().replace("-", "").replace(":", "")}'
        self._lock_fd = None

    def exists(self) -> bool:
        return self.log_path.exists() or self.snap_path.exists()

    def acquire(self, timeout: float = 10.0):
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self.lock_path, 'a+b')
        self._lock_fd.seek(0)
        if self._lock_fd.read(1) == b'':
            self._lock_fd.write(b'0')
            self._lock_fd.flush()
        self._lock_fd.seek(0)
        import time
        deadline = time.time() + timeout
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if time.time() > deadline:
                    self.release()
                    raise ProgramError('LOCK_TIMEOUT', f'could not acquire {self.lock_path}')
                time.sleep(0.05)

    def release(self):
        if not self._lock_fd:
            return
        try:
            self._lock_fd.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self._lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            self._lock_fd.close()
        finally:
            self._lock_fd = None

    def read_log_text(self) -> str:
        if not self.log_path.exists():
            return ''
        return read_utf8(self.log_path)

    def replay(self) -> dict:
        text = self.read_log_text()
        state = empty_state()
        seq = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            seq += 1
            if int(ev.get('seq') or 0) != seq:
                raise ProgramError('LOG_SEQ', f'expected seq {seq}, got {ev.get("seq")}')
            state = apply_event(state, ev, replay=True)
        state['programme']['log_sha256'] = log_sha256(text)
        state['programme']['snapshot_revision'] = seq
        state['journeys_catalog'] = load_project_journeys(self.project)
        return state

    def load(self) -> dict:
        if self.log_path.exists():
            return self.replay()
        if self.snap_path.exists():
            raise ProgramError('LOG_MISSING', 'PROGRAM.yaml present without PROGRAM_LOG.ndjson; cannot trust snapshot')
        return empty_state()

    def append(self, event_type: str, payload: dict | None = None, actor: str = 'gov-001') -> dict:
        self.acquire()
        try:
            state = self.load()
            text = self.read_log_text()
            seq = state['programme'].get('snapshot_revision') or 0
            seq += 1
            payload = dict(payload or {})
            if event_type.startswith('node.lease.') and 'expires_at' not in payload:
                ttl = int(payload.get('ttl_seconds') or 1800)
                payload['acquired_at'] = payload.get('acquired_at') or iso()
                payload['heartbeat_at'] = payload.get('heartbeat_at') or iso()
                payload['expires_at'] = iso(now() + timedelta(seconds=ttl))
            event = {
                'seq': seq,
                'ts': iso(),
                'run': self.run,
                'actor': actor,
                'event': event_type,
                'payload': payload or {},
            }
            state = apply_event(state, event)
            line = json.dumps(event, separators=(',', ':'), ensure_ascii=False) + '\n'
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8', newline='\n') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            new_text = text + line
            state['programme']['log_sha256'] = log_sha256(new_text)
            self._atomic_snapshot(state)
            self._append_run_log(event)
            return state
        finally:
            self.release()

    def rebuild(self) -> dict:
        self.acquire()
        try:
            state = self.replay()
            self._atomic_snapshot(state)
            return state
        finally:
            self.release()

    def verify(self) -> dict:
        log_state = self.replay()
        issues = []
        snap = None
        if self.snap_path.exists():
            snap = load_snapshot(read_utf8(self.snap_path))
            if int(snap.get('programme', {}).get('snapshot_revision') or -1) != int(log_state['programme']['snapshot_revision']):
                issues.append('snapshot_revision does not match log head')
            if snap.get('programme', {}).get('log_sha256') != log_state['programme'].get('log_sha256'):
                issues.append('snapshot log_sha256 does not match log bytes')
        else:
            issues.append('PROGRAM.yaml missing (rebuildable)')
        for line in self.read_log_text().splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get('event') != 'node.verification':
                continue
            payload = ev.get('payload') or {}
            if payload.get('kind') != 'journeys':
                continue
            if payload.get('required_ids') is None:
                issues.append(
                    f"seq {ev.get('seq')}: journey verification event missing frozen required_ids"
                )
        issues.extend(journey_verification_issues(log_state, snapshot=snap))
        return {'ok': not issues, 'issues': issues, 'revision': log_state['programme']['snapshot_revision']}

    verify = verify

    verify = verify

    def _atomic_snapshot(self, state: dict) -> None:
        body = dump_snapshot(state)
        tmp = self.snap_path.with_suffix('.yaml.tmp')
        tmp.write_text(body, encoding='utf-8', newline='\n')
        with open(tmp, 'ab') as f:
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.snap_path)

    def _append_run_log(self, event: dict) -> None:
        run_dir = self.project / '.eif' / 'runs' / self.run
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / 'RUN_LOG.ndjson'
        rec = {'ts': event['ts'], 'kind': 'programme.event', 'event': event['event'], 'seq': event['seq']}
        with open(path, 'a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(rec, separators=(',', ':')) + '\n')
            f.flush()
            os.fsync(f.fileno())

"""Durable programme store: lock, append-only log, atomic snapshot, rebuild."""
from __future__ import annotations

import json
import os
import re
import sys
import yaml
from pathlib import Path

from datetime import timedelta

from eiflib import read_utf8

from .clock import iso, now
from .independence import independence_issues
from .engine import apply_event, dump_snapshot, empty_state, gates_ok, is_leaf, load_snapshot, log_sha256
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
        # A run is an identifier, never a user-controlled relative/absolute path.
        reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}
        if (not isinstance(self.run, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}', self.run)
                or self.run.endswith('.') or self.run.split('.')[0].upper() in reserved):
            raise ProgramError('RUN_INVALID', 'run must be a portable identifier, not a filesystem path')
        self._confined(self.dir)
        self._confined(self.project / '.eif' / 'runs' / self.run / 'RUN_LOG.ndjson')
        self._lock_fd = None

    def _confined(self, path: Path) -> Path:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.project):
            raise ProgramError('RUN_INVALID', f'programme output escapes project: {path}')
        return resolved

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
        deadline = time.monotonic() + timeout
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
                if time.monotonic() > deadline:
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

    def replay(self, text: str | None = None) -> dict:
        if text is None:
            text = self.read_log_text()
        state = empty_state()
        seq = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (ValueError, TypeError) as exc:
                raise ProgramError('LOG_INVALID', f'event {seq + 1} is not valid JSON: {exc}') from exc
            if not isinstance(ev, dict):
                raise ProgramError('LOG_INVALID', f'event {seq + 1} must be an object')
            seq += 1
            if ev.get('seq') != seq:
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

    def append(self, event_type: str, payload: dict | None = None, actor: str = 'gov-001', *, request_id: str | None = None) -> dict:
        if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', request_id)):
            raise ProgramError('REQUEST_INVALID', 'request_id must be 1..128 portable identifier characters')
        self.acquire()
        try:
            text = self.read_log_text()
            if not self.log_path.exists() and self.snap_path.exists():
                raise ProgramError('LOG_MISSING', 'PROGRAM.yaml present without PROGRAM_LOG.ndjson; cannot trust snapshot')
            state = self.replay(text)
            request_payload = dict(payload or {})
            request = {'run': self.run, 'actor': actor, 'event': event_type, 'payload': request_payload}
            fingerprint = log_sha256(json.dumps(request, sort_keys=True, separators=(',', ':'), ensure_ascii=False))
            if request_id is not None:
                for old_line in text.splitlines():
                    if not old_line.strip():
                        continue
                    old = json.loads(old_line)
                    if old.get('request_id') == request_id:
                        if old.get('request_fingerprint') != fingerprint:
                            raise ProgramError('REQUEST_CONFLICT', f'request_id {request_id} already records different input')
                        # An earlier fsync may have failed after writing the full
                        # line. Re-establish durability before acknowledging it.
                        with open(self.log_path, 'ab') as committed:
                            os.fsync(committed.fileno())
                        self._materialize_committed(state, old)
                        return state
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
            if request_id is not None:
                event['request_id'] = request_id
                event['request_fingerprint'] = fingerprint
            state = apply_event(state, event)
            line = json.dumps(event, separators=(',', ':'), ensure_ascii=False) + '\n'
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, 'a', encoding='utf-8', newline='\n') as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
            new_text = text + line
            state['programme']['log_sha256'] = log_sha256(new_text)
            self._materialize_committed(state, event)
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
        self.acquire()
        try:
            return self._verify_locked()
        finally:
            self.release()

    def _verify_locked(self) -> dict:
        text = self.read_log_text()
        log_state = self.replay(text)
        integrity_issues = []
        gate_issues = []
        gate_debt = []
        snap = None
        if self.snap_path.exists():
            try:
                snap = load_snapshot(read_utf8(self.snap_path))
                if not isinstance(snap, dict):
                    raise ValueError('snapshot must be a mapping')
                programme = snap.get('programme')
                if not isinstance(programme, dict):
                    raise ValueError('snapshot programme must be a mapping')
                if programme.get('snapshot_revision') != log_state['programme']['snapshot_revision']:
                    integrity_issues.append('snapshot_revision does not match log head')
                if programme.get('log_sha256') != log_state['programme'].get('log_sha256'):
                    integrity_issues.append('snapshot log_sha256 does not match log bytes')
                expected = {k: v for k, v in log_state.items() if k != 'journeys_catalog'}
                if snap != expected:
                    integrity_issues.append('snapshot content does not match authoritative log replay (rebuildable)')
                    integrity_issues.extend(issue for issue in journey_verification_issues(log_state, snapshot=snap)
                                            if 'snapshot journey' in issue)
            except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
                integrity_issues.append(f'PROGRAM.yaml invalid or unreadable: {exc}')
        else:
            integrity_issues.append('PROGRAM.yaml missing (rebuildable)')
        if not self.log_path.exists() and self.snap_path.exists():
            integrity_issues.append('PROGRAM_LOG.ndjson missing; snapshot is not authoritative')
        events_by_seq = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            events_by_seq[ev['seq']] = ev
            if ev.get('event') != 'node.verification':
                continue
            payload = ev.get('payload') or {}
            if payload.get('kind') != 'journeys':
                continue
            if payload.get('required_ids') is None:
                integrity_issues.append(
                    f"seq {ev.get('seq')}: journey verification event missing frozen required_ids"
                )
        gate_issues.extend(journey_verification_issues(log_state))
        for key, cav in sorted((log_state.get('caveats') or {}).items()):
            prior = cav.get('prior_seq')
            try:
                prior_i = int(prior)
            except (TypeError, ValueError):
                integrity_issues.append(f'caveat {key}: prior_seq {prior!r} is not an integer')
                continue
            if prior_i not in events_by_seq:
                integrity_issues.append(f'caveat {key}: prior_seq {prior_i} not in log')
        for nid, node in sorted(log_state['nodes'].items()):
            if node.get('status') != 'complete' or not is_leaf(log_state, nid):
                continue
            if not gates_ok(log_state, nid):
                node_issues = independence_issues(node) or ['recorded complete but gates invalid']
                gate_issues.extend(f'{nid}: {msg}' for msg in node_issues)
                retro = node.get('retroactive') or {}
                acknowledged = bool(retro.get('completed') or retro.get('independence_disclaimed'))
                gate_debt.append({'node': nid, 'acknowledged': acknowledged, 'issues': node_issues})
        issues = integrity_issues + gate_issues
        return {'ok': not issues, 'issues': issues, 'integrity_ok': not integrity_issues,
                'integrity_issues': integrity_issues, 'gates_ok': not gate_issues,
                'gate_issues': gate_issues, 'gate_debt': gate_debt,
                'revision': log_state['programme']['snapshot_revision']}

    def _materialize_committed(self, state: dict, event: dict) -> None:
        # The fsynced ledger is the commit point. Derived-output failure must not
        # misreport a committed event as a failed mutation and invite duplication.
        for label, write in (('snapshot', lambda: self._atomic_snapshot(state)),
                             ('run log', lambda: self._append_run_log(event))):
            try:
                write()
            except Exception as exc:
                print(f'WARNING DERIVED_STATE_WARNING: event seq {event["seq"]} committed; {label} refresh failed: {exc}; '
                      'rebuild derived state, do not repeat the mutation', file=sys.stderr)

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
        self._confined(run_dir / 'RUN_LOG.ndjson')
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / 'RUN_LOG.ndjson'
        rec = {'ts': event['ts'], 'kind': 'programme.event', 'event': event['event'], 'seq': event['seq']}
        if path.is_file():
            # Explicit request retries refresh derived state without duplicating
            # an already materialized event in the run log.
            for line in read_utf8(path).splitlines():
                if line.strip() and json.loads(line) == rec:
                    return
        with open(path, 'a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(rec, separators=(',', ':')) + '\n')
            f.flush()
            os.fsync(f.fileno())

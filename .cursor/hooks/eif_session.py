"""Persistent retry and Git closure checks; never a grant to run a command.

Cursor may ignore lifecycle replies. Actionable pre-hooks enforce the saved
cursor. A matching success completes a retry; an external operator can explicitly
retire an abandoned obligation with a retained resolution record.
Payloads are hashed, not stored: commands and file contents can contain secrets.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from eif_state import atomic_json, contained, file_lock, remaining_timeout

LEDGER = ('.eif/program/PROGRAM.yaml', '.eif/program/PROGRAM_LOG.ndjson')
# These refusals require a different request or a reviewed boundary change;
# repeating the identical action is not useful retry work. The guard still
# denies and audits them. Existing obligations require explicit resolution.
NON_RETRYABLE_CODES = frozenset('''
FOREIGN_PATH FOREIGN_READ OUT_OF_OBSERVATION_SCOPE OUT_OF_CHANGE_SCOPE
CONTROL_PLANE_PROTECTED PROTECTED_PATH PROGRAMME_PATH_PROTECTED
PROGRAMME_GIT_WORKTREE PROGRAMME_GIT_STAGE SENSITIVE_READ SENSITIVE_TOOL_READ
SECRET_IN_READ SECRET_PREWRITE TOOL_UNSUPPORTED
MCP_DENY MCP_NOT_GRANTED MCP_OUTPUT_PATH BROWSER_OBSERVE_ONLY
'''.split())
# Only an agent tool request can be retried and cleared by its matching success.
# Callbacks, notifications and lifecycle events carry no retryable action.
REQUEST_EVENTS = frozenset({'preToolUse', 'beforeShellExecution', 'beforeMCPExecution', 'beforeReadFile'})
VERIFY_COMMAND = (r'\s*python(?:3)?\s+-B\s+\.cursor/hooks/eif_guard\.py\s+'
                  r'--verify-closure\s+[0-9a-f]{64}\s+[0-9a-f]{32}\s*')


def verifier_command(command):
    """Exact read/execute exception, never an exception for compound shell."""
    return isinstance(command, str) and re.fullmatch(VERIFY_COMMAND, command) is not None


def conversation(data):
    return str(data.get('conversation_id') or data.get('session_id') or 'unknown')


def state_path(root, data):
    key = hashlib.sha256(conversation(data).encode('utf-8')).hexdigest()
    return contained(root, f'.eif/runtime-session/{key}.json')


def read_state(path):
    if not path.exists():
        return {'version': 1, 'retry': [], 'closure_required': False, 'started': False}
    state = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(state, dict) or state.get('version') != 1
            or not isinstance(state.get('retry'), list)
            or not isinstance(state.get('closure_required'), bool)):
        raise ValueError('invalid session state; preserve and repair it')
    for item in state['retry']:
        if not isinstance(item, dict) or not re.fullmatch('[0-9a-f]{64}', item.get('fingerprint', '')):
            raise ValueError('invalid session retry cursor')
    return state


def action(data):
    event = data.get('hook_event_name')
    tool = data.get('tool_name') or ''
    inp = data.get('tool_input')
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            pass
    if event == 'beforeShellExecution':
        tool, inp = 'Shell', {'command': data.get('command', '')}
    elif event == 'beforeReadFile':
        tool, inp = 'Read', {'file_path': data.get('file_path', '')}
    if tool == 'Shell' and isinstance(inp, dict):
        # Sandbox flags, timeouts and tool-use IDs do not change the command.
        # The execution directory does: never clear a blocked command merely
        # because the same text succeeded in another directory.
        roots = data.get('workspace_roots') or []
        cwd = inp.get('cwd') or data.get('cwd') or (roots[0] if roots else '')
        inp = {'command': inp.get('command', '')}
        if cwd:
            base = Path(data.get('cwd') or (roots[0] if roots else '.'))
            inp['cwd'] = str((base / cwd).resolve())
    return tool, inp


def fingerprint(data):
    tool, inp = action(data)
    raw = json.dumps([tool, inp], sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def recovery_action(data):
    tool, inp = action(data)
    if tool in {'Read', 'ReadLints', 'Grep', 'Glob', 'List'}:
        return True
    if tool != 'Shell' or not isinstance(inp, dict):
        return False
    command = inp.get('command', '')
    if verifier_command(command):
        return True
    # These are workflow exceptions only. The normal shell/policy checks still
    # run afterwards, including control-plane and destructive-path protection.
    if not isinstance(command, str) or re.search(r'[;&|<>`\r\n]', command):
        return False
    return bool(re.fullmatch(
        r'\s*(?:git\s+(?:status|diff|log|show|rev-parse|branch|add|commit|push)(?:\s+[^\r\n]*)?'
        r'|python(?:3)?\s+(?:-B\s+)?\.eif/runtime/programme/program\.py\s+[^\r\n]+)\s*',
        command))


def retry_admissible(data, code, outside_boundary=False):
    """Admit debt only for a refusal that retrying the same request could clear.

    Adapter and tooling operations fall out structurally, not by name: they
    arrive as non-request events, as permanent refusals, or aimed outside the
    declared project roots. A target outside those roots can never become
    permissible in-session, whichever check (identity, timeout, boundary)
    refused it first. Denial and audit are unaffected.
    """
    # Never replace the original cursor with our own retry/closure rejection.
    if code.startswith('SESSION_'):
        return False
    # A native callback carries neither a trusted initiator nor proof of a
    # delivered guard decision. Actual retryable guard denials persist their
    # original reason pre-emit.
    if code == 'TOOL_PERMISSION_DENIED' or code in NON_RETRYABLE_CODES or outside_boundary:
        return False
    return data.get('hook_event_name') in REQUEST_EVENTS


def record_block(root, data, code, outside_boundary=False):
    # Existing legacy debt is never removed here, only never added.
    if not retry_admissible(data, code, outside_boundary):
        return False
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        fp = fingerprint(data)
        if not any(item['fingerprint'] == fp for item in state['retry']):
            state['retry'].append({'fingerprint': fp, 'tool': action(data)[0],
                                   'reason_code': code, 'at': int(time.time())})
        atomic_json(path, state)
    return True


def pending(root):
    directory = contained(root, '.eif/runtime-session')
    items = []
    for path in directory.glob('*.json'):
        with file_lock(path.with_suffix('.lock')):
            state = read_state(path)
        if state['retry']:
            items.append((state['retry'][0].get('at', 0), str(path), state['retry'][0]))
    return sorted(items, key=lambda item: (item[0], item[1]))


def record_success(root, data):
    if action(data)[0] == 'Shell':
        output = data.get('tool_output')
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except ValueError:
                return
        # Cursor non-streaming Shell emits postToolUse even on exit 1. A
        # background spawn {shell_id,pid} is not proof of eventual completion.
        if not isinstance(output, dict) or type(output.get('exitCode')) is not int or output['exitCode'] != 0:
            return
    items = pending(root)
    if not items or items[0][2]['fingerprint'] != fingerprint(data):
        return
    path = Path(items[0][1])
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        if state['retry'] and state['retry'][0]['fingerprint'] == fingerprint(data):
            state['retry'].pop(0)
            atomic_json(path, state)


def retry_check(root, data):
    items = pending(root)
    if not items or recovery_action(data):
        return True, '', ''
    first = items[0][2]
    if fingerprint(data) == first['fingerprint']:
        return True, '', ''
    return False, 'SESSION_RETRY_REQUIRED', (
        f"Retry the blocked {first['tool']} operation first; original code={first['reason_code']}, "
        f"fingerprint={first['fingerprint']}. Reads and policy-permitted recovery remain available. "
        'If this action is abandoned or cannot be permitted, an operator can inspect/retire this exact '
        'obligation with tools/session_retry.py from the separate EIF checkout; do not fabricate success.')


def git(root, *args, allowed=(0,)):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args],
                            capture_output=True, encoding='utf-8', errors='strict', timeout=remaining_timeout())
    if result.returncode not in allowed:
        raise RuntimeError(f'git {args[0]} exited {result.returncode}: {result.stderr.strip()[:240]}')
    return result


def closure_context(root):
    """Local-only snapshot. URLs are hashed because they may contain credentials."""
    if not any((Path(root) / path).exists() for path in LEDGER):
        return None, (True, 'SESSION_CLOSURE_OK', 'no programme ledger')
    dirty = git(root, 'status', '--porcelain', '--untracked-files=all', '--', *LEDGER).stdout
    if dirty.strip():
        return None, (False, 'SESSION_COMMIT_REQUIRED', 'Commit the programme ledger with explicit paths before closing or starting unrelated work.')
    commit = git(root, 'log', '-1', '--format=%H', '--', *LEDGER).stdout.strip()
    if not commit:
        return None, (False, 'SESSION_COMMIT_REQUIRED', 'Programme ledger has no committed history.')
    branch = git(root, 'symbolic-ref', '--short', 'HEAD', allowed=(0, 1)).stdout.strip()
    if not branch:
        return None, (False, 'SESSION_PUSH_REQUIRED', 'Detached HEAD has no verifiable upstream closure.')
    remote = git(root, 'config', '--get', f'branch.{branch}.remote', allowed=(0, 1)).stdout.strip()
    remote_ref = git(root, 'config', '--get', f'branch.{branch}.merge', allowed=(0, 1)).stdout.strip()
    if not remote or remote == '.' or not remote_ref.startswith('refs/heads/'):
        return None, (False, 'SESSION_PUSH_REQUIRED', 'Set and push an authorised upstream branch; local refs are not remote evidence.')
    url = git(root, 'remote', 'get-url', remote).stdout.strip()
    context = dict(root=os.path.normcase(str(Path(root).resolve())), ledger_commit=commit,
                   branch=branch, remote=remote, remote_ref=remote_ref,
                   remote_url_sha256=hashlib.sha256(url.encode()).hexdigest())
    for name in ('.cursor/eif-runtime-policy.json', '.cursor/eif-runtime-manifest.json'):
        path = contained(root, name)
        context[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    return context, None


def network_budget():
    value = float(os.environ.get('EIF_CLOSURE_NETWORK_SEC', '30'))
    if not math.isfinite(value) or not 1 <= value <= 120:
        raise ValueError('EIF_CLOSURE_NETWORK_SEC must be finite and between 1 and 120')
    return value


class _WindowsJob:
    """Kill only this verifier's owned tree, including on parent termination."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('job_user', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                        ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise self.ctypes.WinError(self.ctypes.get_last_error())

    def close(self):
        if self.handle:
            if not self.kernel.CloseHandle(self.handle):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            self.handle = None


def network_git(root, *args):
    """Off-hook only. File output avoids untimed pipe drainage on Windows.

    On timeout terminate the owned process tree with bounded cleanup. No fetch,
    stage, commit, push, interactive stdin, or inherited hook output handles.
    """
    deadline = time.monotonic() + network_budget()
    directory = contained(root, '.eif/runtime-session')
    directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    env.setdefault('GIT_SSH_COMMAND', 'ssh -oBatchMode=yes')
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}
    with tempfile.TemporaryFile(dir=directory) as output:
        job = _WindowsJob() if os.name == 'nt' else None
        proc = None
        try:
            command = ['git', '--no-optional-locks', '-C', str(root), *args]
            if job:
                # The isolated stdlib wrapper cannot launch Git until the job
                # assignment succeeds. This closes the child-spawn race without
                # suspended-thread/private Windows resume APIs.
                wrapper = ('import subprocess,sys; '
                           'go=sys.stdin.buffer.read(1); '
                           'sys.exit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL) if go==b"1" else 1)')
                command = [sys.executable, '-I', '-B', '-c', wrapper, *command]
            proc = subprocess.Popen(command, stdin=subprocess.PIPE if job else subprocess.DEVNULL,
                                    stdout=output, stderr=subprocess.DEVNULL, env=env, **options)
            if job:
                try:
                    job.assign(proc)
                    proc.stdin.write(b'1')
                    proc.stdin.flush()
                finally:
                    proc.stdin.close()
            proc.wait(timeout=max(0, deadline - time.monotonic()))
        finally:
            if job:
                job.close()
            elif proc:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if proc and proc.poll() is None:
                proc.kill()
            if proc:
                try:
                    proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        if proc.returncode not in (0, 2):
            raise RuntimeError(f'git ls-remote exited {proc.returncode}; check connectivity and credentials outside the hook')
        output.seek(0)
        raw = output.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('remote response exceeds closure output limit')
        return raw.decode('utf-8', errors='strict')


def closure_check(root, context=None):
    """Explicit off-hook proof; remote-tracking refs are never push evidence."""
    try:
        if context is None:
            context, result = closure_context(root)
            if result:
                return result
        output = network_git(root, 'ls-remote', '--exit-code', '--', context['remote'], context['remote_ref'])
        matches = [line.split()[0] for line in output.splitlines()
                   if len(line.split()) == 2 and line.split()[1] == context['remote_ref']]
        if len(matches) != 1 or not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', matches[0]):
            return False, 'SESSION_PUSH_REQUIRED', 'The configured remote branch is absent or ambiguous.'
        remote_head = matches[0]
        ancestor = git(root, 'merge-base', '--is-ancestor', context['ledger_commit'], remote_head, allowed=(0, 1, 128))
        if ancestor.returncode:
            return False, 'SESSION_PUSH_REQUIRED', 'Remote branch does not prove the ledger commit is present; push or reconcile authorised history.'
        current, failure = closure_context(root)
        if failure or current != context:
            return False, 'SESSION_CLOSURE_REQUIRED', 'Git or runtime context changed during verification; request a new proof.'
        return True, 'SESSION_CLOSURE_OK', f'ledger_commit={context["ledger_commit"]}; verified_remote_head={remote_head}'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return False, 'SESSION_GIT_FAILURE', f'Cannot verify Git closure: {type(exc).__name__}; retry the verifier after checking Git connectivity/configuration.'


def request_message(path, request):
    return ('Remote closure proof pending. Run from the project root, subject to shell policy: '
            f'python -B .cursor/hooks/eif_guard.py --verify-closure {path.stem} {request["id"]}. '
            'Reads and policy-permitted recovery remain available; do not claim closure yet.')


def boundary(root, data):
    """Only local work on lifecycle/pre-hooks; never wait for the network."""
    try:
        context, result = closure_context(root)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        context, result = None, (False, 'SESSION_GIT_FAILURE', 'Local Git closure inspection failed; repair Git and retry.')
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        phase = 'close' if data.get('hook_event_name') in {'stop', 'sessionEnd'} else state.get('closure_phase', 'start')
        if data.get('hook_event_name') == 'sessionStart':
            phase = 'start'
        request = state.get('closure_request')
        # Repeated stop/end delivery shares one boundary. Actual ordinary work
        # after a boundary requires a fresh close proof; no cross-session TTL.
        fresh = (not request or request.get('context') != context
                 or state.get('closure_phase') != phase
                 or (phase == 'close' and state.get('closure_activity')))
        if fresh:
            request = dict(id=uuid.uuid4().hex, context=context)
            state['closure_request'] = request
            state.pop('closure_receipt', None)
        state['closure_phase'] = phase
        state['closure_activity'] = False
        if result is None:
            receipt = state.get('closure_receipt') or {}
            if receipt.get('request') == request['id'] and receipt.get('context') == context:
                result = (True, 'SESSION_CLOSURE_OK', receipt['message'])
            else:
                result = (False, 'SESSION_CLOSURE_REQUIRED', request_message(path, request))
        state['started'] = True
        state['closure_protocol'] = 2
        state['closure_required'] = not result[0]
        state['closure_reason'] = result[1]
        atomic_json(path, state)
    return result


def pre_check(root, data):
    retry = retry_check(root, data)
    if not retry[0]:
        return retry
    # Recovery must not wait on closure, including a cold read. This is only a
    # workflow exception: the caller still executes every normal policy check.
    if recovery_action(data):
        return True, '', ''
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
    if not state.get('started') or state.get('closure_protocol') != 2 or state['closure_required']:
        result = boundary(root, data)
        if not result[0]:
            return result
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        state['closure_activity'] = True
        atomic_json(path, state)
    return True, '', ''


def verify_request(root, key, request_id):
    """One explicit verifier per project; hooks never take its network lock."""
    if not re.fullmatch('[0-9a-f]{64}', key) or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise ValueError('invalid closure request identifier')
    path = contained(root, f'.eif/runtime-session/{key}.json')
    try:
        with file_lock(contained(root, '.eif/runtime-session/closure-verifier.lock'), timeout=0.01):
            with file_lock(path.with_suffix('.lock')):
                state = read_state(path)
                request = state.get('closure_request') or {}
            if request.get('id') != request_id or not request.get('context'):
                return False, 'SESSION_CLOSURE_REQUIRED', 'Closure request is absent or superseded; retry the initiating hook.'
            current, failure = closure_context(root)
            if failure or current != request['context']:
                return False, 'SESSION_CLOSURE_REQUIRED', 'Closure context changed; retry the initiating hook.'
            receipt = state.get('closure_receipt') or {}
            if receipt.get('request') == request_id and receipt.get('context') == current:
                return True, 'SESSION_CLOSURE_OK', receipt['message']
            result = closure_check(root, current)
            with file_lock(path.with_suffix('.lock')):
                state = read_state(path)
                if (state.get('closure_request') or {}).get('id') != request_id:
                    return False, 'SESSION_CLOSURE_REQUIRED', 'Closure request superseded during verification.'
                state['closure_verification'] = dict(code=result[1], at=time.time())
                if result[0]:
                    state['closure_receipt'] = dict(request=request_id, context=current,
                                                   verified_at=time.time(), message=result[2])
                # Only the hook consuming a matching receipt clears the gate.
                atomic_json(path, state)
            return result
    except TimeoutError:
        return False, 'SESSION_CLOSURE_REQUIRED', 'Closure verifier or state is busy; retry later. Reads remain available.'

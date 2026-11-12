"""Session-local failure truth and closure; never a grant to execute.

Every guard denial, permanent or transient, is pre-execution: the action never
ran, so it creates no debt. A Windows PowerShell 5 parser rejection is also
pre-execution. Only an executed mutating failure becomes UNRESOLVED: a Shell
command that ran and failed (exit code != 0, timeout or interrupt after start),
or a failed Write/Delete. It is retired only by the exact action succeeding or by
the external operator resolver; nothing here fabricates success. Historical (v1)
denial queues in `retry` are quarantined on the session's next hook and audited
(reviews.jsonl); they are never re-admitted and never treated as success.

Execution evidence. Cursor callbacks are trusted by event and failure_type
(`permission_denied` is a denial). The Claude Code adapter states
`eif_execution_evidence` on every failure callback; only `executed` (the error
text shows the action ran or was dispatched, see
eif_claude_adapter.failure_evidence) can create debt. `none` (no error text,
input validation, a denial, a protocol error before dispatch) and `untracked`
never do.

MCP. A failed MCP call that may mutate (the guard's mcp_failure_may_mutate:
anything not proven read-only by its tool name) becomes UNRESOLVED like a Shell
failure: an error/timeout callback, or an after-hook whose result reports
isError/error. Neither host reports whether a failed or timed-out MCP call
changed the server, so a dispatched mutation (for example a partially applied
migration) is presumed possibly applied; denials, pre-dispatch protocol errors
and read-only tools are never debt. A name is read-only only when every token
is in an explicit read-only vocabulary. Any unknown verb or token is a
mutation (`search_rollback`, `find_and_restart`, `get_and_invoke`). Names such
as `get_settings` and `list_assets` stay read-only. A write word (`replace`,
`edit`, `update`, `delete`, `create`, `set`, `put`, `patch`, `move`, `rename`,
and similar) is a mutation even when the name starts with `search` or `find`.
It clears on the exact call succeeding or through the external operator resolver
after reviewing the external system.
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

import eif_state
from eif_state import atomic_json, contained, file_lock, remaining_timeout

LEDGER = ('.eif/program/PROGRAM.yaml', '.eif/program/PROGRAM_LOG.ndjson')
# The one closure verifier, bare. PowerShell/cmd spellings of the same file and
# interpreter (backslashes, `.\`, python.exe, the py launcher) name the same
# action; denying them looped agents on "Remote closure proof pending".
VERIFY_COMMAND = (r'\s*(?:python(?:3)?|py)(?:\.exe)?\s+-B\s+(?:\.[/\\])?\.cursor[/\\]hooks[/\\]eif_guard\.py\s+'
                  r'--verify-closure\s+[0-9a-f]{64}\s+[0-9a-f]{32}\s*')
# Closure-gate recovery: commit/push/inspect the programme ledger and run the
# programme CLI while SESSION_COMMIT/PUSH/CLOSURE_REQUIRED holds. Workflow
# exception only; every normal shell/policy check (remote push grant,
# control-plane and destructive-path protection) still runs afterwards. No
# chaining, redirection, substitution or expansion characters.
RECOVERY_UNSAFE = re.compile(r'[;&|<>`$\r\n]')
RECOVERY_COMMAND = re.compile(
    r'\s*(?:git\s+(?:status|diff|log|show|rev-parse|branch|add|commit|push)(?:\s+[^\r\n]*)?'
    r'|python(?:3)?\s+(?:-B\s+)?\.eif/runtime/programme/program\.py\s+[^\r\n]+)\s*')
# Permanent refusals: only a policy or runtime change could change the outcome,
# so repeating the identical action is futile. Every deny code the guard can
# emit is classified in tools/test_retry_admission.py (PERMANENT must equal this
# set; RETRYABLE must equal TRANSIENT_DENIAL_CODES); a new code in neither fails
# that test. v2: no denial class creates debt (record_block always returns
# False). The class labels the denial in the operator log (`denial_class`) and
# in the quarantine record of legacy v1 queue entries.
NON_RETRYABLE_CODES = frozenset('''
FOREIGN_PATH FOREIGN_READ OUT_OF_OBSERVATION_SCOPE OUT_OF_CHANGE_SCOPE
CONTROL_PLANE_PROTECTED PROTECTED_PATH PROGRAMME_PATH_PROTECTED
PROGRAMME_GIT_WORKTREE PROGRAMME_GIT_STAGE SENSITIVE_READ SENSITIVE_TOOL_READ
SECRET_IN_READ SECRET_PREWRITE TOOL_UNSUPPORTED NO_PROGRESS
MCP_DENY MCP_NOT_GRANTED MCP_OUTPUT_PATH BROWSER_OBSERVE_ONLY BROWSER_UNSAFE
ACTION_INFRASTRUCTURE ACTION_IDENTITY_MUTATION ACTION_FORCE_VCS ACTION_REMOTE_PUSH
ACTION_DESTRUCTIVE_DATA ACTION_DEPENDENCY ACTION_NETWORK NETWORK_DESTINATION
ACTION_ARTIFACT_WRITE ACTION_WRITE ACTION_DELETE SHELL_DENY
MCP_DESTRUCTIVE BROWSER_PUBLIC_MUTATE POST_EDIT_SECRET
PROTECTED_DATABASE_WRITE DESTRUCTIVE_LINKED_TREE SECRET_STAGE PROTECTED_BRANCH_PUSH SHIM_TOOL_UNMAPPED
POLICY_INTEGRITY SHELL_POLICY_REQUIRED MCP_POLICY_REQUIRED BOOTSTRAP BOOTSTRAP_MCP
IDENTITY_READ IDENTITY_SHELL IDENTITY_MCP IDENTITY_TOOL IDENTITY_MISMATCH IDENTITY_UNVERIFIED
HOOK_INPUT_INVALID UNKNOWN_REASON_CODE RUNTIME_INTEGRITY
'''.split())
# Transient refusals: the identical request can be admitted later under the same
# policy (fault cleared, budget renewed, origin observed). Still pre-execution,
# so still no debt; the agent may simply repeat the action later.
TRANSIENT_DENIAL_CODES = frozenset('''
HOOK_INTERNAL_ERROR HOOK_EMIT_FAILURE HOOK_LOG_FAILURE BUDGET_STATE_FAILURE
IDENTITY_GIT_FAILURE RUNTIME_LOCK_FAILURE BUDGET_EXHAUSTED BROWSER_INTERACT_ORIGIN
'''.split())
# Tools whose executed failure can leave a partial mutation. MCP tools are
# tracked by prefix (MCP:<tool>), gated by eif_executed_mutation like Shell.
FAILURE_TRACKED_TOOLS = frozenset({'Write', 'Delete', 'Shell'})
MCP_EVENTS = frozenset({'beforeMCPExecution', 'afterMCPExecution'})


# Operator session grants (tools/session_grant.py). A grant is an audited,
# time-limited admission for ONE session of one lean BLOCK class; it is written
# only by the operator tool from the separate EIF checkout, never by a hook.
GRANT_CLASSES = frozenset({'db_write'})
GRANT_MAX_SEC = 24 * 3600


def valid_grant(state, grant_class, session_key, now):
    """Newest unrevoked, unexpired grant of grant_class bound to session_key, else None."""
    grants = state.get('grants') if isinstance(state, dict) else None
    if not isinstance(grants, list) or grant_class not in GRANT_CLASSES:
        return None
    best = None
    for grant in grants:
        if not isinstance(grant, dict) or grant.get('class') != grant_class or grant.get('revoked_at'):
            continue
        if grant.get('session_key') != session_key:
            continue
        issued, expires = grant.get('issued_at'), grant.get('expires_at')
        if (not isinstance(issued, (int, float)) or not isinstance(expires, (int, float))
                or isinstance(issued, bool) or isinstance(expires, bool)
                or not math.isfinite(issued) or not math.isfinite(expires)):
            continue
        if issued > now + 60 or now >= expires or expires - issued > GRANT_MAX_SEC:
            continue
        if not isinstance(grant.get('reason'), str) or not grant['reason'].strip() or not grant.get('actor'):
            continue
        if best is None or issued > best['issued_at']:
            best = grant
    return best


def failure_tracked(tool):
    return tool in FAILURE_TRACKED_TOOLS or (isinstance(tool, str) and tool.startswith('MCP:'))


def denial_class(code):
    """permanent | transient | unclassified. Labels only; never admits debt."""
    if code in NON_RETRYABLE_CODES:
        return 'permanent'
    if code in TRANSIENT_DENIAL_CODES:
        return 'transient'
    return 'unclassified'


def verifier_command(command):
    return isinstance(command, str) and re.fullmatch(VERIFY_COMMAND, command) is not None


def conversation(data):
    return str(data.get('conversation_id') or data.get('session_id') or 'unknown')


def state_path(root, data):
    key = hashlib.sha256(conversation(data).encode('utf-8')).hexdigest()
    return contained(root, f'.eif/runtime-session/{key}.json')


def read_state(path):
    # Keep schema v1 so a release rollback can still read every migrated file.
    if not path.exists():
        return {'version': 1, 'retry': [], 'unresolved': [], 'closure_required': False, 'started': False}
    state = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(state, dict) or state.get('version') != 1
            or not isinstance(state.get('retry'), list)
            or not isinstance(state.get('closure_required'), bool)
            or not isinstance(state.get('unresolved', []), list)
            or not all(isinstance(item, dict) for item in state['retry'])
            or not all(isinstance(item, dict) for item in state.get('unresolved', []))):
        raise ValueError('invalid session state; preserve and repair it')
    for item in state['retry'] + state.get('unresolved', []):
        if not re.fullmatch('[0-9a-f]{64}', item.get('fingerprint', '')):
            raise ValueError('invalid session retry cursor')
    state.setdefault('unresolved', [])
    return state


def action(data):
    event = data.get('hook_event_name')
    tool = {'Bash':'Shell','PowerShell':'Shell','Edit':'Write','MultiEdit':'Write','NotebookEdit':'Write'}.get(data.get('tool_name'), data.get('tool_name')) or ''
    inp = data.get('tool_input')
    if isinstance(inp, str):
        try:
            inp = json.loads(inp)
        except ValueError:
            pass
    if event in {'beforeShellExecution','BeforeShellExecution'}:
        tool, inp = 'Shell', {'command': data.get('command', '')}
    elif event == 'BeforeReadFile' or event == 'beforeReadFile':
        tool, inp = 'Read', {'file_path': data.get('file_path', '')}
    elif event in MCP_EVENTS and isinstance(tool, str) and tool and not tool.startswith('MCP:'):
        # Cursor names the tool bare on MCP events and MCP:<tool> on
        # preToolUse/postToolUse*; one call must have one identity.
        tool = 'MCP:' + tool
    if tool == 'Shell' and isinstance(inp, dict):
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


def output(data):
    # Cursor Shell has delivered tool_response; other adapters use tool_output.
    value = data.get('tool_output', data.get('tool_response'))
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def successful_output(tool, data):
    result = output(data)
    if tool == 'Shell':
        # A background spawn is neither success nor an actual failure.
        return bool(result and type(result.get('exitCode')) is int
                    and result['exitCode'] == 0)
    return result is not None and not result.get('error')


def reported_error(data):
    """True when an after-hook result itself reports failure.

    Covers tool_output/tool_response and Cursor afterMCPExecution result_json:
    an MCP CallToolResult with isError, or a non-empty `error`. A Shell exit
    code is judged separately; unparseable text is not evidence either way.
    """
    values = [output(data)]
    raw = data.get('result_json')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    values.append(raw if isinstance(raw, dict) else None)
    return any(value is not None and (value.get('isError') is True or bool(value.get('error')))
               for value in values)


def static_powershell_syntax_failure(data):
    """Exempt only a complete, unexecuted Windows PowerShell 5 parser block."""
    tool, inp = action(data)
    result = output(data)
    if tool != 'Shell' or not isinstance(inp, dict) or result is None:
        return False
    if result.get('exitCode') not in {1, -1} or str(result.get('stdout') or ''):
        return False
    stderr = str(result.get('stderr') or '')
    parser = re.compile(r'^(?:[^\r\n]*:\s*)?At line:\d+ char:\d+\r?\n.*\r?\n(?:\s*\+\s*[^\r\n]*)+$', re.S)
    if not ((re.search(r"The token '&&' is not a valid statement separator in this version", stderr)
             or re.search(r"The string is missing the terminator|InvalidEndOfLine", stderr))
            and re.search(r'ParserError', stderr) and parser.fullmatch(stderr.strip())):
        return False
    command = inp.get('command', '') or data.get('command', '')
    if not isinstance(command, str) or re.search(chr(60)+chr(35)+"|@["+chr(39)+chr(34)+"]", command):
        return False
    # Existing conservative token scanner: no general ParserError exemption.
    clean=[]; quote=None; i=0
    while i < len(command):
        c=command[i]
        if quote:
            if c == quote:
                if i and command[i-1] in {'\\','`'}: return False
                quote=None
            i+=1; continue
        if c in chr(39)+chr(34): quote=c; i+=1; continue
        if c == '#':
            e=command.find('\n',i); i=len(command) if e<0 else e; continue
        clean.append(c); i+=1
    return quote is None and bool(re.search(r'(?<![&|])(?:&&|\|\|)(?![&|])', ''.join(clean)))


def verifier_action(data):
    tool, inp = action(data)
    return tool == 'Shell' and isinstance(inp, dict) and verifier_command(inp.get('command', ''))


def recovery_action(data):
    """Closure-gate workflow exception; never a policy grant (see RECOVERY_COMMAND)."""
    tool, inp = action(data)
    if tool in {'Read', 'ReadLints', 'Grep', 'Glob', 'List'}:
        return True
    if tool != 'Shell' or not isinstance(inp, dict):
        return False
    command = inp.get('command', '')
    if verifier_command(command):
        return True
    if not isinstance(command, str) or RECOVERY_UNSAFE.search(command):
        return False
    return RECOVERY_COMMAND.fullmatch(command) is not None


def record_block(root, data, code, outside_boundary=False):
    """A guard denial is pre-execution by construction, so it never creates debt.

    Returns False (no obligation admitted) for every code, permanent or
    transient, and never touches session state; denial_class() labels the code.
    """
    return False


def log_resolution(root, path, item, kind, detail):
    record = {'ts': int(time.time()), 'session_file': Path(path).name,
              'fingerprint': item.get('fingerprint'), 'kind': kind, 'detail': detail}
    contained(root, '.eif/runtime-session').mkdir(parents=True, exist_ok=True)
    review = contained(root, '.eif/runtime-session/reviews.jsonl')
    with file_lock(review.with_suffix('.lock')), review.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, separators=(',', ':')) + '\n')
        f.flush()


def executed_failure(root, data):
    """Record an executed mutating failure as UNRESOLVED; True when recorded.

    Never records a denial (failure_type permission_denied), an adapter
    callback without execution evidence, a PowerShell 5 parser rejection, or a
    read-only Shell command / MCP tool (eif_executed_mutation false).
    """
    event = str(data.get('hook_event_name') or '').casefold()
    if event not in {'posttooluse', 'posttoolusefailure', 'aftermcpexecution'}:
        return False
    tool = action(data)[0]
    if not failure_tracked(tool):
        return False
    if tool.startswith('MCP:'):
        return _mcp_failure(root, data, tool, event)
    failed_callback = event == 'posttoolusefailure'
    # The adapter states its evidence; anything but 'executed' is no debt.
    evidence = data.get('eif_execution_evidence')
    if failed_callback and (data.get('failure_type') == 'permission_denied'
                            or (evidence is not None and evidence != 'executed')):
        return False
    if static_powershell_syntax_failure(data):
        return False
    result = output(data)
    if tool == 'Shell':
        if not data.get('eif_executed_mutation'):
            return False
        # postToolUse only reports a failure through an integer nonzero exit.
        if not failed_callback and (result is None or type(result.get('exitCode')) is not int
                                    or result['exitCode'] == 0):
            return False
    elif not failed_callback:
        return False
    return _record_unresolved(root, data, tool)


def _mcp_failure(root, data, tool, event):
    """A dispatched MCP call that may mutate and did not report success."""
    if not data.get('eif_executed_mutation'):
        return False
    if event == 'posttoolusefailure':
        evidence = data.get('eif_execution_evidence')
        if data.get('failure_type') == 'permission_denied' or (evidence is not None and evidence != 'executed'):
            return False
    elif not reported_error(data):
        return False
    return _record_unresolved(root, data, tool)


def _record_unresolved(root, data, tool):
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        item = {'fingerprint': fingerprint(data), 'tool': tool,
                'reason_code': 'POST_TOOL_FAILURE', 'kind': 'EXECUTED_MUTATION_ATTEMPT',
                'attempts': 1, 'at': int(time.time())}
        state.setdefault('unresolved', [])
        # One live obligation per action; retired history stays as evidence.
        state['unresolved'] = [x for x in state['unresolved']
                               if x['fingerprint'] != item['fingerprint'] or x.get('retired')]
        state['unresolved'].append(item)
        log_resolution(root, path, item, 'EXECUTED_FAILURE', 'actual failure; no success claimed')
        atomic_json(path, state)
    return True


def pending(root, data):
    """Live legacy (v1) retry entries of THIS session only, oldest first.

    `data` is required: the v1 project-global scan is gone, and a call without
    a session would silently prove nothing. Entries are quarantined by
    legacy_denials() on the session's next hook, so a live entry here only
    exists between a v1 write and that hook. Executed failures are unresolved().
    """
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
    return [(item.get('at', 0), str(path), item) for item in state.get('retry', [])
            if not item.get('retired')]


def legacy_denials(root, data):
    """Mark current session's known legacy pre-hook denies retired durably."""
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        count = 0
        for item in state.get('retry', []):
            if item.get('retired'):
                continue
            item['retired'] = True
            item['resolution'] = 'LEGACY_PREEXECUTION_DENIAL_NEVER_EXECUTED'
            item['denial_class'] = denial_class(item.get('reason_code'))
            log_resolution(root, path, item, 'LEGACY_DENIED_QUARANTINE',
                           f'{item.get("reason_code")} ({item["denial_class"]}); no execution/success claimed')
            count += 1
        if count:
            state['retry_history'] = state.get('retry_history', []) + state['retry']
            state['retry'] = []
            atomic_json(path, state)
    return count


def record_success(root, data):
    tool = action(data)[0]
    if data.get('hook_event_name','').casefold() not in {'posttooluse', 'aftermcpexecution'}:
        return
    # For Cursor Write/Delete/MCP after hooks with no output payload, the event
    # itself carries executed success evidence. Shell still requires exit 0, and
    # postToolUseFailure or background spawn is never a successful output.
    if tool == 'Shell' and not successful_output(tool, data):
        return
    if reported_error(data):
        return
    path = state_path(root, data)
    fp = fingerprint(data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        changed = False
        for kind in ('retry', 'unresolved'):
            for item in list(state.get(kind, [])):
                if item.get('retired'):
                    continue
                if item['fingerprint'] == fp:
                    item['retired'] = True
                    item['resolution'] = 'EXACT_SUCCESS'
                    log_resolution(root, path, item, 'MATCHING_SUCCESS', 'exact successful action')
                    changed = True
            if kind == 'retry':
                # Retired legacy entries leave the v1 queue (a rollback's
                # pending() reads only `retry`) and are kept as history.
                done = [x for x in state['retry'] if x.get('retired')]
                if done:
                    state['retry_history'] = state.get('retry_history', []) + done
                    state['retry'] = [x for x in state['retry'] if not x.get('retired')]
        if changed:
            atomic_json(path, state)


def unresolved(root, data):
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
    return [item for item in state.get('unresolved', []) if not item.get('retired')]


def unresolved_report(root):
    # Explicit all-session read-only report, never admitted as a foreign gate.
    rows = []
    for path in contained(root, '.eif/runtime-session').glob('*.json'):
        with file_lock(path.with_suffix('.lock')):
            state = read_state(path)
        for item in state.get('unresolved', []):
            if not item.get('retired'):
                rows.append(dict(session_file=path.name, **item))
    return rows


def git(root, *args, allowed=(0,)):
    started = time.perf_counter()
    try:
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args],
                                capture_output=True, encoding='utf-8', errors='strict', timeout=remaining_timeout())
    finally:
        eif_state._metric('git', (time.perf_counter() - started) * 1000)
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





def operator_equivalent(root, path, original_event, successful_event):
    """Caller is an explicit operator CLI, never a tool-hook payload.

    Review both original and successful events. The original failed action identity,
    exact tool, target/cwd and success exit code must match. A non-identical Shell
    command only counts when the external reviewed operator supplies both events;
    the hook records no raw contents, only fingerprints/digests and rationale id.
    """
    new_type = action(successful_event)[0]
    success_events = {'postToolUse', 'afterMCPExecution'} if new_type.startswith('MCP:') else {'postToolUse'}
    if (fingerprint(original_event) == fingerprint(successful_event)
            or successful_event.get('hook_event_name') not in success_events):
        return 'ORIGINAL_MATCH_OR_SUCCESS_CALLBACK_INVALID'
    if (new_type == 'Shell' and not successful_output('Shell', successful_event)) or reported_error(successful_event):
        return 'OPERATOR_RESULT_NOT_SUCCESS'
    old_tool, old_action = action(original_event)
    new_tool, new_action = action(successful_event)
    if old_tool != new_tool or not failure_tracked(old_tool):
        return 'OPERATOR_TOOL_MISMATCH'
    if conversation(original_event) != conversation(successful_event):
        return 'OPERATOR_SESSION_MISMATCH'
    if (conversation(original_event) != path.stem and __import__('hashlib').sha256(conversation(original_event).encode('utf-8')).hexdigest() != path.stem) or fingerprint(original_event) == fingerprint(successful_event):
        return 'OPERATOR_SESSION_MISMATCH'
    if old_tool == 'Shell':
        if not old_action.get('command') or not isinstance(old_action.get('command'), str) or not new_action.get('command'):
            return 'OPERATOR_COMMAND_INVALID'
        if old_action.get('cwd') != new_action.get('cwd'):
            return 'OPERATOR_CWD_CHANGED'
    elif old_tool.startswith('MCP:'):
        pass  # same MCP tool and session; the operator reviewed the external system
    elif not old_action.get('file_path') or old_action.get('file_path') != new_action.get('file_path'):
        return 'OPERATOR_TARGET_CHANGED'
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        matches = [item for key in ('retry', 'unresolved') for item in state.get(key, [])
                   if item['fingerprint'] == fingerprint(original_event) and not item.get('retired')]
        live = [x for x in state.get('unresolved',[]) if x in matches]
        if live: matches = live
        if len(matches) != 1:
            return 'NO_UNIQUE_MATCHING_OBLIGATION'
        log_text = (root / '.eif/runtime-events.jsonl').read_text(encoding='utf-8') if (root / '.eif/runtime-events.jsonl').is_file() else ''
        if not successful_event.get('digest') or successful_event['digest'] not in log_text:
            return 'OPERATOR_SUCCESS_EVIDENCE_NOT_AUDITED'
        item = matches[0]
        item['retired'] = True
        item['resolution'] = 'REVIEWED_OPERATOR_EQUIVALENT'
        item['equivalence'] = {
            'old_action_sha256': hashlib.sha256(json.dumps(old_action, sort_keys=True).encode('utf-8')).hexdigest(),
            'new_action_sha256': hashlib.sha256(json.dumps(new_action, sort_keys=True).encode('utf-8')).hexdigest(),
            'successful_output_sha256': hashlib.sha256(json.dumps(output(successful_event),
                sort_keys=True).encode('utf-8')).hexdigest(),
        }
        log_resolution(root, path, item, 'OPERATOR_EQUIVALENT',
                       'two-event external review; target/cwd bound, successful digest retained')
        atomic_json(path, state)
    return 'EQUIVALENT_SUCCESS_RECORDED'


def pre_check(root, data):
    # Legacy v1 queue entries are quarantined, never enforced. Unresolved
    # executed failures gate only closure (boundary at stop/sessionEnd and
    # verify_request), never ordinary repair work in this or another session.
    legacy_denials(root, data)
    if recovery_action(data):
        return True, '', ''
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
    if not state.get('started') or state.get('closure_protocol') != 2 or state['closure_required']:
        result = boundary(root, data, quarantined=True)
        if not result[0]:
            return result
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        # Re-read under the lock; rewrite (fsync + replace) only when the flag
        # actually changes. Equal state is not written again.
        if state.get('closure_activity') is not True:
            state['closure_activity'] = True
            atomic_json(path, state)
    return True, '', ''


def boundary(root, data, quarantined=False):
    """quarantined=True: the caller ran legacy_denials() for this event already."""
    path = state_path(root, data)
    if not quarantined:
        legacy_denials(root, data)
    failed = unresolved(root, data)
    if failed and data.get('hook_event_name') in {'stop', 'sessionEnd'}:
        return False, 'SESSION_RETRY_REQUIRED', (
            f'{len(failed)} actual executed-mutation failure(s) unresolved: no closure or success '
            'is claimed. Exact success or reviewed external equivalent resolution is required; '
            'other sessions and continued repair attempts are not blocked.')
    try:
        context, result = closure_context(root)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        context, result = None, (False, 'SESSION_GIT_FAILURE', 'Local Git closure inspection failed; repair Git and retry.')
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        before = json.dumps(state, sort_keys=True)
        phase = 'close' if data.get('hook_event_name') in {'stop', 'sessionEnd'} else state.get('closure_phase', 'start')
        if data.get('hook_event_name') == 'sessionStart':
            phase = 'start'
        request = state.get('closure_request')
        # A request (and its receipt) proves one Git/runtime context for this
        # session. Ordinary work since the last boundary needs a fresh close
        # proof; a phase flip alone (resume/compact sessionStart after stop,
        # or stop after a start with no work) changes nothing that was proven,
        # so it must not supersede the id the agent was told to verify.
        fresh = (not request or request.get('context') != context
                 or (phase == 'close' and state.get('closure_activity')))
        if fresh:
            request = dict(id=uuid.uuid4().hex, context=context)
            state['closure_request'] = request
            state.pop('closure_receipt', None)
        state['closure_phase'] = phase
        # sessionStart/resume must not forget work that still needs a close
        # proof, and must not mint a new request id: that superseded the
        # command the agent was told to run ("Closure request is absent or
        # superseded") on a fresh session that had not changed the ledger.
        # Only the close phase consumes the activity flag.
        if phase == 'close' or not state.get('closure_activity'):
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
        if json.dumps(state, sort_keys=True) != before or not path.exists():
            atomic_json(path, state)
    return result


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
                if any(not x.get('retired') for x in state.get('unresolved', [])):
                    return False, 'SESSION_RETRY_REQUIRED', 'Executed mutation failure is unresolved; closure verification refused.'
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



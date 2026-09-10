#!/usr/bin/env python3
"""EIF Cursor guard.

Security model:
- File-tool path checks can be ENFORCED for Read/Write/Delete.
- Workspace shell is not a jail. On an unsandboxed host, arbitrary child
  processes are ordinary local-developer execution. Project-boundary claims
  for those children are UNAVAILABLE; high-consequence shell classifiers are
  defense-in-depth only.
- L1 denies shell. L3 workspace allows ordinary repo engineering and still
  denies identity mutation, force VCS, remote push, destructive/infra, and
  similar high-consequence classes.
- Runtime policy is DERIVED from accepted EIF policy + manifest. The agent
  must not edit the derived policy or its source control-plane files.
- compensating_sandbox metadata is never a grant.
- Browser MCP: mcp.browser none|observe|interact. In-page use of a local
  app is observation, not product-source write. public_read is research
  navigate/observe, not a UI-mutate grant.
- Agent-aimed destinations (URL-shaped tool input, including HTTP method)
  are ENFORCED. Observed page origin is updated from navigate input and
  afterMCPExecution/postToolUse results. A first in-page gesture can still
  change Chromium destination before that observation; that residual is
  UNAVAILABLE at pre-tool. App-initiated XHR from a local page is product
  behaviour, not an agent-aimed grant.
"""
from __future__ import annotations
import sys
# Do not execute a host-side stdlib shadow module before verifying the hooks.
# sys is built in; no filesystem-backed imports are needed for this bootstrap.
_bootstrap_dir = __file__.replace('\\', '/').rsplit('/', 1)[0].rstrip('/').casefold()
sys.path[:] = [entry for entry in sys.path if entry not in {'', '.'}
               and entry.replace('\\', '/').rstrip('/').casefold() != _bootstrap_dir]
import codecs, fnmatch, hashlib, json, math, os, re, subprocess, sys, threading, time, types
from pathlib import Path
from urllib.parse import unquote, urlparse

CONTROL_PLANE_DEFAULTS = [
    '.cursor/eif-runtime-policy.json', '.cursor/eif-runtime-manifest.json', '.cursor/hooks.json', '.cursor/hooks/**',
    '.cursor/rules/eif-core.mdc', '.cursor/rules/eif-project-adapter.mdc',
    '.cursor/permissions.json', '.eif/PROJECT_MANIFEST.md', '.eif/AUTONOMY_POLICY.md', '.eif/ENVIRONMENT_POLICY.md', '.eif/RUNTIME_CAPABILITIES.md',
    '.eif/runtime-events.jsonl', '.eif/runtime-budget/**', '.eif/program/**', '.eif/runtime/programme/**', '.eif/upgrade-work/**',
    '.eif/hook-guard.log', '.eif/hook-guard.json',
    '.eif/runtime-session/**', '.eif/runtime-upgrade.lock', '.eif/upgrade-history/**',
    '.eif/node-scope.json', '.eif/node-scope.lock',
]
BOOTSTRAP_SHELL = [
    r'^pwd\s*$',
    r'^git(?:\s+-C\s+[^\s]+)?\s+status(?:\s+--short)?\s*$',
    r'^git(?:\s+-C\s+[^\s]+)?\s+rev-parse\s+(?:--show-toplevel|--is-inside-work-tree|HEAD)\s*$',
    r'^git(?:\s+-C\s+[^\s]+)?\s+remote\s+-v\s*$',
    r'^git(?:\s+-C\s+[^\s]+)?\s+branch\s+--show-current\s*$',
]
SECRET_PATTERNS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
    re.compile(r'\b(?:sk|rk|pk)-(?:live|prod|test)?[-_A-Za-z0-9]{20,}\b', re.I),
    re.compile(r'(?im)^\s*(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key)\s*[:=]\s*["\']?([^\s"\']{8,})'),
]
DESTRUCTIVE_INPUT = re.compile(r'\b(drop\s+(?:database|schema|table)|truncate\s+table|delete\s+from|flushall|flushdb|terraform\s+destroy|kubectl\s+delete|helm\s+uninstall)\b', re.I)
IDENTITY_MUTATION = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+remote\s+(?:add|set-url|rename|remove)\b', re.I)
FORCE_VCS = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:push\b[^\n]*(?:--force(?:-with-lease)?|-f\b|\+\S+)|reset\s+--hard\b|clean\s+-\S*f\S*)', re.I)
REMOTE_PUSH = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+push\b', re.I)
INFRASTRUCTURE = re.compile(r'\b(?:terraform\s+|kubectl\s+|helm\s+|aws\s+|gcloud\s+|az\s+|ssh\s+|scp\s+|rsync\s+|ncat\s+|\bnc\s+)', re.I)
GIT_CLONE = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+clone\b', re.I)
GLOBAL_OR_PUBLISH = re.compile(
    r'\b(?:npm\s+publish|pnpm\s+publish|yarn\s+publish|twine\s+upload|cargo\s+publish)\b'
    r'|\b(?:npm|pnpm|yarn|pip|pip3)\b[^\n]*?(?:-g|--global)\b',
    re.I,
)
SHELL_FETCH = re.compile(r'\b(?:curl|wget|invoke-webrequest)\b', re.I)
URL_IN_TEXT = re.compile(r'https?://[^\s\'"\\]+', re.I)
REDIRECT_TARGET = re.compile(r'(?:^|[\s;|&])(?:>>?|2>>?)\s*([^\s;|&]+)')
QUOTED_PATH = re.compile(r'''['"]([^'"]+)['"]''')
ABS_PATH = re.compile(r'(?:[A-Za-z]:[\\/][^\s;|&"\']+|/(?:etc|tmp|Users|home|var|private)[^\s;|&"\']*)')
LOOPBACK_HOSTS = {'localhost','127.0.0.1','::1','0.0.0.0','[::1]'}
NETWORK_CLASSES = frozenset({'loopback','public_read'})


MAX_HOOK_INPUT_BYTES = 16 * 1024 * 1024


def read_cursor_hook_stdin(stream) -> bytes:
    """Read one JSON frame or EOF, never infer completeness from a quiet pipe.

    read1 performs one underlying pipe read rather than waiting to fill a buffer.
    Framing uses ASCII structural characters (decoded UTF-16 when BOM-marked).
    The complete bytes still go through strict JSON and encoding validation.
    An empty/incomplete pipe held open is inherently undecidable without a
    deadline; the existing watchdog handles that case, not frame completion.
    """
    raw = bytearray()
    decoder = None
    depth = 0
    started = False
    quoted = False
    escaped = False
    read = getattr(stream, 'read1', stream.read)
    while True:
        chunk = read(min(65536, MAX_HOOK_INPUT_BYTES + 1 - len(raw)))
        if not chunk:
            return bytes(raw)
        raw.extend(chunk)
        if len(raw) > MAX_HOOK_INPUT_BYTES:
            raise ValueError(f'Cursor hook input exceeds {MAX_HOOK_INPUT_BYTES} bytes')
        if decoder is None:
            if len(raw) < 2:
                continue
            encoding = 'utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'latin1'
            decoder = codecs.getincrementaldecoder(encoding)()
            text = decoder.decode(bytes(raw))
        else:
            text = decoder.decode(chunk)
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in '{[':
                started = True
                depth += 1
            elif char in '}]' and started:
                depth -= 1
                if depth == 0:
                    return bytes(raw)


def parse_cursor_hook_stdin(raw: bytes) -> dict:
    """Parse Cursor command-hook JSON from raw stdin bytes.

    Cursor 3.12.x on Windows delivers the payload by PowerShell-piping a temp
    file into the hook command. That pipe prefixes a UTF-8 BOM. Python's default
    Windows stdin encoding is the locale code page (often cp1252), so
    json.load(sys.stdin) then fails at column 1 with 'Expecting value' even
    though the JSON is present. Always read bytes and decode as UTF-8-SIG.
    """
    if not raw or not raw.strip():
        raise ValueError('empty Cursor hook stdin')
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            # Legacy Windows PowerShell pipes can use cp1252. Never interpret
            # arbitrary single-byte input as unmarked UTF-16 or replace bytes.
            text = raw.decode('cp1252')
    text = text.strip()
    if not text:
        raise ValueError('empty Cursor hook stdin')
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError('Cursor hook input must be a JSON object')
    return data

# Crash / launcher / emit failures must be distinguishable from policy denials
# such as OUT_OF_CHANGE_SCOPE. Cursor failClosed treats empty/invalid stdout as a
# mute block ("hook returned no output") with no rule name.
CRASH_REASON_CODES = frozenset({
    'HOOK_INTERNAL_ERROR', 'HOOK_LAUNCHER_ERROR', 'HOOK_INPUT_INVALID',
    'HOOK_TIMEOUT', 'HOOK_EMIT_FAILURE', 'HOOK_LOG_FAILURE',
    'UNKNOWN_REASON_CODE', 'BUDGET_STATE_FAILURE', 'SESSION_STATE_FAILURE',
    'SESSION_GIT_FAILURE', 'IDENTITY_GIT_FAILURE', 'RUNTIME_INTEGRITY', 'RUNTIME_LOCK_FAILURE',
})
WATCHDOG_DEFAULT_SEC = 8.0
_EMITTED = False
_EMIT_RC = 1
_EMIT_LOCK = threading.Lock()
_DONE = threading.Event()
_READ_ONLY = False
_DECISION_CODE = None
_AUDIT_ERROR = None
_STARTED = time.perf_counter()
_ACTIVE_DATA = None
_ACTIVE_ROOT = None
_SUPPORT_READY = False
_READ_WARNING = None
_TIMINGS = {}
_GIT_CACHE = {}
_RUNTIME_LOCK = None
_DEADLINE = None


def remaining_timeout(limit=2.0):
    """Reserve response time within the single invocation watchdog deadline."""
    if _DEADLINE is None:
        return limit
    remaining = _DEADLINE - time.perf_counter() - 0.1
    if remaining <= 0:
        raise GuardFault('HOOK_TIMEOUT', 'invocation deadline exhausted before starting another operation')
    return min(limit, remaining)


class GuardFault(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def support(name):
    """Load only shipped helpers; production calls follow integrity verification."""
    if name not in {'eif_reason_codes', 'eif_state', 'eif_session'}:
        raise ValueError('unknown guard helper')
    directory = Path(__file__).resolve().parent
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    if name == 'eif_session':
        support('eif_state')
    if name not in sys.modules:
        raw = (directory / (name + '.py')).read_bytes()
        module = types.ModuleType(name)
        module.__file__ = str(directory / (name + '.py'))
        sys.modules[name] = module
        try:
            exec(compile(raw, module.__file__, 'exec'), module.__dict__)
        except Exception:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def verified_runtime(root):
    """Hash helper bytes before execution, then lock and verify full inventory."""
    hook_dir = Path(__file__).resolve().parent
    source_root = hook_dir.parents[3]
    reference = (hook_dir == source_root / 'runtime/cursor/.cursor/hooks'
                 and (source_root / 'tools/compile_cursor.py').is_file())
    manifest_path = root / '.cursor/eif-runtime-manifest.json'
    raw = (hook_dir / 'eif_integrity.py').read_bytes()
    if not reference:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        files = manifest.get('files') if isinstance(manifest, dict) else None
        expected = files.get('.cursor/hooks/eif_integrity.py') if isinstance(files, dict) else None
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('hook integrity helper missing or digest mismatch')
    module = types.ModuleType('eif_integrity_bootstrap')
    module.__file__ = str(hook_dir / 'eif_integrity.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    lock = module.runtime_lock(root, timeout=remaining_timeout())
    lock.__enter__()
    try:
        if not reference:
            ok, message = module.verify_hook_runtime(root)
            if not ok:
                raise ValueError(message)
    except Exception:
        lock.__exit__(*sys.exc_info())
        raise
    return lock


def _project_root() -> Path:
    env = os.environ.get('CURSOR_PROJECT_DIR') or os.environ.get('CLAUDE_PROJECT_DIR')
    if env:
        return Path(env)
    try:
        return Path(__file__).resolve().parent.parent.parent
    except Exception:
        return Path.cwd()


def _operator_log_path() -> Path:
    return (_ACTIVE_ROOT or _project_root()) / '.eif' / 'hook-guard.log'


def watchdog_sec() -> float:
    """Seconds before the guard self-denies HOOK_TIMEOUT. Default 8.

    Host config (no EIF release): `.eif/hook-guard.json` `watchdog_sec`.
    Session/test override: environment variable `EIF_HOOK_WATCHDOG_SEC`.
    Invalid, nonpositive and over-budget values use the safe 8-second default.
    """
    raw = os.environ.get('EIF_HOOK_WATCHDOG_SEC')
    if raw not in (None, ''):
        try:
            value = float(raw)
            return value if math.isfinite(value) and 0 < value <= WATCHDOG_DEFAULT_SEC else WATCHDOG_DEFAULT_SEC
        except ValueError:
            pass
    cfg = _project_root() / '.eif' / 'hook-guard.json'
    try:
        if cfg.is_file():
            data = json.loads(cfg.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'watchdog_sec' in data:
                value = float(data['watchdog_sec'])
                return value if math.isfinite(value) and 0 < value <= WATCHDOG_DEFAULT_SEC else WATCHDOG_DEFAULT_SEC
    except Exception:
        pass
    return WATCHDOG_DEFAULT_SEC


def _append_operator_log(code, message, extra=None):
    """Append a line an operator can open in the editor; no CLI required."""
    try:
        p = _operator_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {'ts': int(time.time()), 'reason_code': code, 'message': message}
        if extra:
            for k, v in extra.items():
                if k not in rec:
                    rec[k] = v
        with p.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=True, separators=(',', ':')) + '\n')
            f.flush()
        return True
    except Exception:
        return False


def write_operator_log(code, message, extra=None):
    """Bound sink latency so a stalled filesystem cannot lock out the watchdog.

    A timed-out append may finish later; the decision reports unconfirmed log
    delivery and emits its diagnostic on stderr. It never invents log success.
    """
    result = []
    done = threading.Event()
    def append():
        try:
            result.append(_append_operator_log(code, message, extra))
        finally:
            done.set()
    threading.Thread(target=append, daemon=True, name='eif-log-writer').start()
    return bool(done.wait(0.25) and result and result[0])


def _write_stdout_bytes(data: bytes) -> bool:
    try:
        fd = sys.stdout.fileno()
    except Exception:
        try:
            sys.stdout.write(data.decode('ascii'))
            sys.stdout.flush()
            return True
        except Exception:
            return False
    offset = 0
    try:
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                return False
            offset += written
        return True
    except Exception:
        # Never restart the JSON after a partial write: that corrupts stdout.
        return False


def _stderr_log(record):
    try:
        sys.stderr.write(json.dumps(record, ensure_ascii=True, separators=(',', ':')) + '\n')
        sys.stderr.flush()
    except Exception:
        pass


def out(permission='allow', message=None, extra=None):
    """Emit one ASCII JSON decision on stdout.

    Allows and handled harness faults return JSON with exit 0. Policy denials
    use Cursor's explicit block exit 2 and repeat diagnostics on stderr.
    A failed stdout write is HOOK_EMIT_FAILURE with exit 1.
    """
    global _EMITTED, _EMIT_RC
    obj = {'permission': permission}
    if extra:
        obj.update(extra)
    if permission == 'allow' and _READ_ONLY and _READ_WARNING:
        obj.update(_READ_WARNING)
    if message:
        obj.setdefault('user_message', message)
        obj.setdefault('agent_message', message)
    obj.setdefault('reason_code', _DECISION_CODE or 'HOOK_ALLOW')
    reason = obj['reason_code']
    if reason not in CRASH_REASON_CODES and not support('eif_reason_codes').is_reason_code(reason):
        obj['original_reason_code'] = str(reason)
        reason = obj['reason_code'] = 'UNKNOWN_REASON_CODE'
        permission = obj['permission'] = 'deny'
        message = f'Unknown EIF reason code rejected: {obj["original_reason_code"]}'
    kind = 'harness_fault' if reason in CRASH_REASON_CODES else 'policy'
    obj['decision_kind'] = kind
    if kind == 'harness_fault':
        obj['agent_message'] = (
            f'EIF harness fault in bookkeeping; read policy checks completed and the read is allowed. {message or reason}'
            if permission == 'allow' and _READ_ONLY else
            f'EIF harness fault; authorization could not be completed. {message or reason}')
    if _SUPPORT_READY and _ACTIVE_DATA and permission == 'deny' and reason != 'HOOK_TIMEOUT':
        try:
            support('eif_session').record_block(_ACTIVE_ROOT, _ACTIVE_DATA, reason)
        except Exception as exc:
            obj['original_reason_code'] = reason
            reason = obj['reason_code'] = 'SESSION_STATE_FAILURE'
            kind = obj['decision_kind'] = 'harness_fault'
            obj['agent_message'] = f'EIF harness fault: cannot persist blocked-action cursor: {type(exc).__name__}; action remains blocked.'
    if not _EMIT_LOCK.acquire(timeout=0.25):
        _stderr_log({'reason_code': 'HOOK_EMIT_FAILURE', 'decision_kind': 'harness_fault',
                     'message': 'decision sink stalled; launcher must report delivery failure'})
        write_operator_log('HOOK_EMIT_FAILURE', 'decision sink stalled')
        return 1
    try:
        if _EMITTED:
            return _EMIT_RC
        logged = write_operator_log(reason, message or reason, extra={
            'permission': permission, 'decision_kind': kind,
            'elapsed_ms': round((time.perf_counter() - _STARTED) * 1000, 3),
            'timings_ms': _TIMINGS,
            **{key: obj[key] for key in ('enforcement', 'node', 'risk_class') if key in obj},
        })
        if not logged or _AUDIT_ERROR:
            # Validated presentation admission is deliberately nonblocking on
            # telemetry failure. Full-loop mutations retain their old behavior.
            unguarded = obj.get('enforcement') == 'UNGUARDED' and reason == 'PRESENTATION_UNGUARDED'
            if permission == 'allow' and not _READ_ONLY and not unguarded:
                obj['permission'] = 'deny'
            obj['decision_kind'] = 'harness_fault'
            obj['original_reason_code'] = reason
            obj['reason_code'] = 'HOOK_LOG_FAILURE'
            obj['log_written'] = bool(logged)
            obj['user_message'] = 'HOOK_LOG_FAILURE: guard logging failed; see hook stderr'
            obj['agent_message'] = (
                'UNGUARDED presentation action allowed; audit delivery failed. No gate or successful execution claimed.'
                if unguarded else
                'EIF harness fault: guard logging failed. Read policy checks completed; read allowed.'
                if obj['permission'] == 'allow' else
                'EIF harness fault: guard logging failed. Action remains blocked; repair the guard before retrying.'
            )
            _stderr_log(obj)
        raw = (json.dumps(obj, ensure_ascii=True, separators=(',', ':')) + '\n').encode('ascii')
        wrote = _write_stdout_bytes(raw)
        _EMITTED = True
        _DONE.set()
        if not wrote:
            write_operator_log(
                'HOOK_EMIT_FAILURE',
                message or 'stdout write failed after building a decision',
                extra={'permission': permission, 'reason_code': obj.get('reason_code')},
            )
            _EMIT_RC = 1
            _stderr_log({'reason_code': 'HOOK_EMIT_FAILURE', 'decision_kind': 'harness_fault'})
            return 1
        # Cursor consumes JSON on 0; 2 is its explicit policy-block exit.
        # Handled harness faults use 0 plus structured fault JSON, never a mute
        # interpreter exit. Transport failure alone returns 1.
        _EMIT_RC = 2 if obj['permission'] == 'deny' and obj['decision_kind'] == 'policy' else 0
        if _EMIT_RC == 2:
            _stderr_log(obj)
    finally:
        _EMIT_LOCK.release()
    return _EMIT_RC


def deny(code, message):
    return out('deny', f'{code}: {message}', extra={'reason_code': code})


def _arm_watchdog():
    """Self-deny before the host runtime kills the hook with empty stdout."""
    global _DEADLINE
    sec = watchdog_sec()
    _DEADLINE = time.perf_counter() + sec

    def run():
        if _DONE.wait(sec):
            return
        rc = deny('HOOK_TIMEOUT', 'guard did not finish before the hook watchdog; fail-closed')
        os._exit(0 if rc == 0 else (rc or 1))

    threading.Thread(target=run, daemon=True, name='eif-hook-watchdog').start()


def sha256(path: Path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1024*1024), b''): h.update(c)
    return h.hexdigest()

def normalized_remote(s):
    s=(s or '').strip().removesuffix('.git')
    if s.startswith('git@') and ':' in s: s='ssh://git@'+s[4:].replace(':','/',1)
    return s.lower().rstrip('/')

def git(root: Path, *args):
    key = (str(root.resolve()), args)
    if key in _GIT_CACHE:
        return _GIT_CACHE[key]
    started = time.perf_counter()
    try:
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args],
                                capture_output=True, encoding='utf-8', timeout=remaining_timeout())
        if result.returncode:
            raise GuardFault('IDENTITY_GIT_FAILURE', f'git {args[0]} exited {result.returncode}: {result.stderr.strip()[:200]}')
        _GIT_CACHE[key] = result.stdout.strip()
        return _GIT_CACHE[key]
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        raise GuardFault('IDENTITY_GIT_FAILURE', f'{type(exc).__name__}: {exc}') from exc
    finally:
        _TIMINGS['git'] = round(_TIMINGS.get('git', 0) + (time.perf_counter() - started) * 1000, 3)

def observed_remotes(root: Path):
    vals=[]
    for line in git(root,'remote','-v').splitlines():
        p=line.split()
        if len(p)>=2: vals.append(normalized_remote(p[1]))
    return sorted(set(vals))

def root_commit(root: Path):
    rows=git(root,'rev-list','--max-parents=0','HEAD').splitlines()
    return rows[0] if len(rows)==1 else ''

def policy_path(root: Path):
    for rel in ['.cursor/eif-runtime-policy.json','.eif/runtime-policy.json']:
        p=root/rel
        if p.exists(): return p
    return root/'.cursor/eif-runtime-policy.json'

def load_policy(root: Path):
    p=policy_path(root)
    if not p.exists(): return 'MISSING',None,p,'runtime policy absent'
    try: pol=json.loads(p.read_text(encoding='utf-8-sig'))
    except Exception as e: return 'MALFORMED',None,p,f'cannot parse runtime policy: {e}'
    try:
        if not isinstance(pol, dict):
            raise ValueError('runtime policy must be an object')
        for key in ('identity', 'action_classes', 'budgets', 'mcp'):
            if key in pol and not isinstance(pol[key], dict):
                raise ValueError(f'policy.{key} must be an object')
        for key in ('allowed_roots', 'control_plane_paths', 'protected_paths', 'sensitive_read_paths',
                    'observation_scopes', 'change_scopes', 'path_scopes', 'artifact_scopes'):
            if key in pol and (not isinstance(pol[key], list) or any(not isinstance(x, str) or not x.strip() for x in pol[key])):
                raise ValueError(f'policy.{key} must be a list of nonempty strings')
        if pol.get('state_root', '.eif') != '.eif':
            raise ValueError('only .eif state_root is supported')
        sources = pol.get('sources')
        if not isinstance(sources, dict) or not {'manifest', 'autonomy_policy'}.issubset(sources):
            raise ValueError('policy source inventory requires manifest and autonomy')
        if (root / '.eif/ENVIRONMENT_POLICY.md').exists() and 'environment_policy' not in sources:
            raise ValueError('existing environment policy is absent from source inventory')
        normalize_shell_policy(pol.get('shell') or {'mode':'deny'})
        normalize_network_policy(pol.get('network') or {})
    except ValueError as e:
        return 'INVALID',pol,p,str(e)
    # Derived-source integrity. Runtime policy cannot remain valid after its accepted sources drift.
    for item in sources.values():
        if not isinstance(item,dict): return 'INVALID',pol,p,'policy source entry must be an object'
        rel=item.get('path'); expected=item.get('sha256')
        if not isinstance(rel,str) or not rel or not isinstance(expected,str) or not re.fullmatch('[0-9a-fA-F]{64}',expected):
            return 'INVALID',pol,p,'policy source requires path and SHA-256'
        src=(root/rel).resolve()
        try:
            src.relative_to(root.resolve())
        except Exception:
            return 'INVALID',pol,p,f'source path escapes project: {rel}'
        if not src.exists(): return 'INVALID',pol,p,f'policy source missing: {rel}'
        try:
            if sha256(src).lower()!=expected.lower(): return 'INVALID',pol,p,f'policy source hash mismatch: {rel}; recompile accepted policy'
        except OSError as exc:
            return 'INVALID',pol,p,f'cannot read policy source {rel}: {type(exc).__name__}'
    return 'OK',pol,p,'ok'

def declared_roots(data, policy, root):
    """Return only roots accepted by EIF policy.

    Cursor workspace_roots are runtime context, not project authority. Treating every
    open workspace root as trusted would reopen cross-project contamination in a
    multi-root workspace. Additional repositories must therefore be compiled into
    policy.allowed_roots from PROJECT_MANIFEST.md. During bootstrap, only the active
    project root is trusted.
    """
    roots=[]
    candidates=(policy or {}).get('allowed_roots') or [str(root)]
    for x in candidates:
        try:
            p=Path(x).resolve()
            if p not in roots: roots.append(p)
        except Exception: pass
    return roots

def select_root(data):
    """Prefer the hook process/cwd project that actually owns the EIF policy.

    In a multi-root Cursor workspace, workspace_roots[0] is not a safe identity
    selector. Pick the unique/first candidate that contains an EIF runtime policy,
    preferring explicit cwd and the hook process cwd.
    """
    candidates=[]
    for x in [data.get('cwd'), os.getcwd(), *(data.get('workspace_roots') or [])]:
        if not x: continue
        try:
            p=Path(x).resolve()
            if p not in candidates: candidates.append(p)
        except Exception: pass
    for p in candidates:
        if (p/'.cursor/eif-runtime-policy.json').exists() or (p/'.eif/runtime-policy.json').exists():
            return p
    return candidates[0] if candidates else Path(os.getcwd()).resolve()

def resolve_path(path, roots):
    if not path: return None,None
    try: real=Path(path).resolve()
    except Exception: return None,None
    for r in roots:
        try: return r, str(real.relative_to(r)).replace('\\','/')
        except Exception: pass
    return None,None

def matches(rel, patterns):
    if rel is None: return False
    rel=rel.replace('\\','/')
    return any(fnmatch.fnmatch(rel,p) or fnmatch.fnmatch('/'+rel,'/'+p) for p in (patterns or []))

def tool_path(inp):
    if not isinstance(inp,dict): return None
    for k in ['file_path','path','target_file','target_path','directory']:
        if isinstance(inp.get(k),str) and inp[k].strip(): return inp[k]
    return None


def validate_tool_paths(inp):
    """Aliases may identify one target; contradictory/malformed aliases cannot."""
    values = []
    for key in ('file_path', 'path', 'target_file', 'target_path', 'directory'):
        if key not in inp:
            continue
        value = inp[key]
        if not isinstance(value, str) or not value.strip():
            raise GuardFault('HOOK_INPUT_INVALID', f'{key} must be a nonempty path string')
        values.append(value)
    if len(set(values)) > 1:
        raise GuardFault('HOOK_INPUT_INVALID', 'conflicting path aliases; supply one unambiguous target')

def strings(obj):
    if isinstance(obj,str): yield obj
    elif isinstance(obj,dict):
        for v in obj.values(): yield from strings(v)
    elif isinstance(obj,list):
        for v in obj: yield from strings(v)

# Colon form is the explicit F27 marker. Underscore form appears in synthetic
# filenames. A remote named EIF_PROBE_<runid> must not steal the probe_id.
_PROBE_COLON = re.compile(r'EIF_PROBE:([A-Z][A-Z0-9_]*)')
_PROBE_UNDER = re.compile(r'EIF_PROBE_([A-Z][A-Z0-9_]*)')
_PROBE_RUN_ONLY = re.compile(r'^R\d{6,}_[A-Z0-9]+$')
_PROBE_BLOB_KEYS = ('command','file_path','path','prompt','description','title','content')

def probe_marker_blob(data):
    parts=list(strings(data.get('tool_input') or {}))
    for k in _PROBE_BLOB_KEYS:
        v=data.get(k)
        if v is None: continue
        parts.extend(strings(v))
    return ' '.join(parts)

def extract_probe_id(*parts):
    blob=' '.join(p for p in parts if p)
    if not blob: return None
    colon=[m for m in _PROBE_COLON.findall(blob) if not _PROBE_RUN_ONLY.match(m)]
    if colon: return max(colon, key=len)
    under=[m for m in _PROBE_UNDER.findall(blob) if not _PROBE_RUN_ONLY.match(m)]
    if under: return max(under, key=len)
    return None

def has_secret(text): return any(p.search(text or '') for p in SECRET_PATTERNS)

def identity_ok(root: Path, policy):
    ident=policy.get('identity') or {}
    exp_root=ident.get('root_commit') or ''
    exp_rem=sorted(set(normalized_remote(x) for x in ident.get('expected_remotes',[]) if x))
    exp_vcs=ident.get('expected_vcs_root') or ''
    if not exp_root and not exp_rem and not exp_vcs:
        return False,'IDENTITY_UNVERIFIED: no intrinsic project anchor declared'
    observed_root=root_commit(root) if exp_root else ''
    if exp_root and observed_root!=exp_root:
        return False,f'IDENTITY_MISMATCH: root commit expected {exp_root}, observed {observed_root or "<none>"}'
    observed=observed_remotes(root) if exp_rem else []
    if exp_rem and observed!=exp_rem:
        return False,f'IDENTITY_MISMATCH: remote set expected {exp_rem}, observed {observed}'
    if exp_vcs:
        actual=Path(git(root,'rev-parse','--show-toplevel')).resolve()
        if str(actual)!=str(Path(exp_vcs).resolve()):
            return False,f'IDENTITY_MISMATCH: vcs root expected {exp_vcs}, observed {actual}'
    for anchor in ident.get('repository_anchors') or []:
        ar=Path(anchor.get('allowed_root') or '').resolve()
        if not ar.exists(): return False,f'IDENTITY_MISMATCH: declared repository root missing: {ar}'
        ev=anchor.get('expected_vcs_root') or ''; er=anchor.get('root_commit') or ''
        erm=sorted(set(normalized_remote(x) for x in anchor.get('expected_remotes',[]) if x))
        arv=git(ar,'rev-parse','--show-toplevel') if ev else ''
        arr=root_commit(ar) if er else ''
        arem=observed_remotes(ar) if erm else []
        if ev and (not arv or str(Path(arv).resolve())!=str(Path(ev).resolve())):
            return False,f'IDENTITY_MISMATCH: repository {ar} vcs root expected {ev}, observed {arv or "<none>"}'
        if er and arr!=er: return False,f'IDENTITY_MISMATCH: repository {ar} root commit expected {er}, observed {arr or "<none>"}'
        if erm and arem!=erm: return False,f'IDENTITY_MISMATCH: repository {ar} remotes expected {erm}, observed {arem}'
    return True,'identity anchors matched'

def control_plane(rel, policy):
    pats=list(CONTROL_PLANE_DEFAULTS)+(policy.get('control_plane_paths') or [])
    return matches(rel,pats)

def action_allowed(policy, name): return bool((policy.get('action_classes') or {}).get(name,False))

def observation_scopes(policy):
    # path_scopes is a compatibility fallback for pre-split policies.
    return policy.get('observation_scopes') or policy.get('path_scopes') or []

def change_scopes(policy):
    return policy.get('change_scopes') or policy.get('path_scopes') or []

def audit_artifact_prefix(policy):
    root=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/')
    return root+'/audit/'

def is_audit_artifact_rel(rel, policy=None):
    """Hard-coded audit artifact tree. Canonical .eif state files are never in this tree."""
    if not rel: return False
    rel=rel.replace('\\','/')
    prefix=audit_artifact_prefix(policy)
    return rel.startswith(prefix) and '..' not in rel.split('/')

def artifact_scope_match(rel, patterns):
    """Match artifact_scopes. Treat trailing /** as a directory prefix (POSIX-safe)."""
    rel=(rel or '').replace('\\','/')
    for p in (patterns or []):
        pat=str(p).replace('\\','/').lstrip('/')
        if pat.endswith('/**'):
            base=pat[:-3]
            if rel==base or rel.startswith(base+'/'): return True
            continue
        if fnmatch.fnmatch(rel,pat) or fnmatch.fnmatch('/'+rel,'/'+pat): return True
    return False

def artifact_write_allowed(rel, policy):
    if not action_allowed(policy,'artifact_write'): return False
    if not is_audit_artifact_rel(rel, policy): return False
    scopes=policy.get('artifact_scopes') or []
    if not scopes or not artifact_scope_match(rel, scopes): return False
    return True

def audit(root: Path, data, decision, code, rel=None, extra=None):
    global _DECISION_CODE, _AUDIT_ERROR
    _DECISION_CODE = code
    try:
        state=root/'.eif'; state.mkdir(exist_ok=True)
        p=state/'runtime-events.jsonl'
        event=data.get('hook_event_name')
        tool=data.get('tool_name')
        if not tool and event=='beforeShellExecution': tool='Shell'
        if not tool and event=='beforeReadFile': tool='Read'
        rec={
          'ts':int(time.time()), 'event':event, 'tool':tool,
          'decision':decision, 'code':code, 'path':rel,
          'cursor_version':data.get('cursor_version'), 'conversation_id':data.get('conversation_id'),
          'sandbox':data.get('sandbox') if 'sandbox' in data else None,
        }
        if extra:
            for k,v in extra.items():
                if k not in rec: rec[k]=v
        # Probe markers are safe synthetic identifiers; do not log command/tool payloads.
        pid=extract_probe_id(probe_marker_blob(data), str(rel or ''))
        if pid: rec['probe_id']=pid
        with p.open('a', encoding='utf-8') as f: f.write(json.dumps(rec,separators=(',',':'))+'\n')
    except Exception as exc:
        _AUDIT_ERROR = type(exc).__name__

PROGRESS_EVENTS = frozenset({'node.stage', 'evidence.add', 'node.accept', 'node.status'})
WRAP_CHECKPOINT_EVENTS = frozenset({'node.stage_note'})
MUTATING_TOOLS = frozenset({'Write', 'Delete'})

def _budget_dir(root: Path, policy) -> Path:
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    return support('eif_state').contained(root, Path(sr)/'runtime-budget')

def _programme_log_path(root: Path, policy) -> Path:
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    return root/sr/'program'/'PROGRAM_LOG.ndjson'

def _programme_progress(root: Path, policy, after_seq: int):
    """Missing log means no programme; unreadable/malformed progress is a fault."""
    path=_programme_log_path(root, policy)
    if not path.is_file():
        return after_seq, set()
    head=after_seq; kinds=set()
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if not line: continue
            ev=json.loads(line)
            seq=int(ev.get('seq') or 0)
            if seq>head: head=seq
            if seq>after_seq:
                kinds.add(str(ev.get('event') or ''))
    except Exception as exc:
        raise ValueError(f'cannot read programme progress: {type(exc).__name__}') from exc
    return head, kinds

def _mutating_fingerprint(data):
    """Identify a repeated mutating file action.

    Path-key order matches tool_path(): file_path, path, target_file,
    target_path, directory, cwd. Blank strings are skipped so an empty
    preferred key does not hide a real fallback path. None does not
    become the literal 'None'. Separators use a single-backslash replace.
    If no path can be resolved, return None: the call is not a repeat.
    """
    tool=str(data.get('tool_name') or '')
    if tool not in MUTATING_TOOLS:
        return None
    inp=data.get('tool_input') if isinstance(data.get('tool_input'), dict) else {}
    path=''
    for k in ('file_path','path','target_file','target_path','directory','cwd'):
        v=inp.get(k)
        if isinstance(v,str) and v.strip():
            path=v
            break
    if not path:
        return None
    return f'{tool}:{path.replace("\\","/").lower()}'


def _persist_budget(path: Path, state):
    try:
        support('eif_state').atomic_json(path, state)
        return True,''
    except Exception:
        return False,'BUDGET_STATE_FAILURE: cannot persist runtime budget state'

def budget_ok(root: Path, data, policy):
    if data.get('hook_event_name') != 'preToolUse':
        return True, '', None
    try:
        conv = str(data.get('conversation_id') or 'unknown')
        # Preserve existing ordinary IDs; hash unsafe names instead of colliding
        # after character substitution/truncation or accepting dot traversal.
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,119}', conv):
            conv = hashlib.sha256(conv.encode('utf-8')).hexdigest()
        directory = _budget_dir(root, policy)
        with support('eif_state').file_lock(directory / (conv + '.lock')):
            return _budget_ok_locked(root, data, policy, directory / (conv + '.json'))
    except Exception as exc:
        return False, f'BUDGET_STATE_FAILURE: {type(exc).__name__}: {exc}', None


def _budget_ok_locked(root: Path, data, policy, p):
    """Burst tool-call cap is fail-closed. Session wall-clock is wrap-up, not a permanent deny."""
    if data.get('hook_event_name')!='preToolUse': return True,'',None
    b=policy.get('budgets') or {}
    max_calls=b.get('tool_calls')
    max_minutes=b.get('wall_clock_minutes')
    repeat_limit=b.get('repeat_mutating_limit')
    if repeat_limit is None: repeat_limit=12
    wrap_ratio=float(b.get('wrap_up_ratio') or 0.85)
    if not max_calls and not max_minutes and not repeat_limit:
        return True,'',None
    now=time.time()
    state={'session_first_ts':now,'burst_first_ts':now,'burst_id':1,'tool_calls':0,
           'wrap_up_signaled':False,'last_progress_seq':0,'last_mut_fp':'','repeat_mut':0}
    if p.exists():
        saved = json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(saved, dict) or not set(state).issubset(saved):
            raise ValueError('budget state is incomplete; preserve and repair it')
        for key in ('burst_id', 'tool_calls', 'last_progress_seq', 'repeat_mut'):
            if type(saved[key]) is not int or saved[key] < 0:
                raise ValueError(f'invalid budget {key}')
        for key in ('session_first_ts', 'burst_first_ts'):
            if not isinstance(saved[key], (int, float)) or not math.isfinite(saved[key]):
                raise ValueError(f'invalid budget {key}')
        if not isinstance(saved['last_mut_fp'], str) or type(saved['wrap_up_signaled']) is not bool:
            raise ValueError('invalid budget fingerprint/wrap state')
        state.update(saved)
    head, kinds=_programme_progress(root, policy, int(state.get('last_progress_seq') or 0))
    renewed=False
    if head>int(state.get('last_progress_seq') or 0):
        state['last_progress_seq']=head
        if kinds & PROGRESS_EVENTS or ((kinds & WRAP_CHECKPOINT_EVENTS) and state.get('wrap_up_signaled')):
            state['burst_id']=int(state.get('burst_id') or 1)+1
            state['burst_first_ts']=now
            state['tool_calls']=0
            state['wrap_up_signaled']=False
            state['repeat_mut']=0
            state['last_mut_fp']=''
            renewed=True
    state['tool_calls']=int(state.get('tool_calls') or 0)+1
    fp=_mutating_fingerprint(data)
    if fp:
        if fp==state.get('last_mut_fp'):
            state['repeat_mut']=int(state.get('repeat_mut') or 0)+1
        else:
            state['repeat_mut']=1
            state['last_mut_fp']=fp
    ok,msg=_persist_budget(p, state)
    if not ok: return False,msg,None
    if fp and repeat_limit and int(state.get('repeat_mut') or 0)>int(repeat_limit):
        return False,f'NO_PROGRESS: repeated mutating action {fp} x{state["repeat_mut"]}',None
    if max_calls and state['tool_calls']>int(max_calls):
        if support('eif_session').recovery_action(data):
            return True, '', {'additional_context': 'BUDGET_READ_RECOVERY: execution burst exhausted; policy-checked reads and closure/recovery operations remain available.'}
        return False,f'BUDGET_EXHAUSTED: tool calls {state["tool_calls"]}>{max_calls} in execution burst {state.get("burst_id")}',None
    extra=None
    session_min=(now-float(state.get('session_first_ts') or now))/60.0
    wrap_needed=False
    if max_minutes and session_min>=float(max_minutes):
        wrap_needed=True
    if max_calls and state['tool_calls']>=max(1, int(int(max_calls)*wrap_ratio)):
        wrap_needed=True
    if wrap_needed and not state.get('wrap_up_signaled'):
        state['wrap_up_signaled']=True
        ok,msg=_persist_budget(p, state)
        if not ok: return False,msg,None
        extra={'additional_context': (
            'WRAP_UP: park programme stage_note/evidence via python .eif/runtime/programme/program.py and continue. '
            'Session wall-clock is advisory wrap-up, not a permanent tool deny. '
            f'session_minutes={session_min:.1f} burst_tool_calls={state["tool_calls"]} renewed={renewed}.'
        )}
    return True,'',extra

COMPENSATING_SANDBOX_REJECT = (
    'compensating_sandbox is not an isolation control. A policy field is not a sandbox. '
    'host_os_isolation / container / wsl2 labels do not constrain the launched process. '
    'On an unsandboxed host, L3 workspace mode accepts ordinary local-developer execution '
    'risk as telemetry; it does not mint COMPENSATING or ENFORCED containment.'
)

def reject_compensating_sandbox_field(obj, *, loc='shell'):
    """A compensating_sandbox field is never a grant. Presence fails compile."""
    if not isinstance(obj, dict):
        return
    raw=obj.get('compensating_sandbox')
    if raw in (None, {}, []):
        return
    raise ValueError(f'{loc}: {COMPENSATING_SANDBOX_REJECT}')

def parse_compensating_sandbox(entry):
    """Present compensating_sandbox is never a grant.

    Returns None if absent. Raises ValueError if present (any shape).
    """
    if not isinstance(entry, dict) or 'compensating_sandbox' not in entry:
        return None
    raw=entry.get('compensating_sandbox')
    if raw in (None, {}, []):
        return None
    raise ValueError(COMPENSATING_SANDBOX_REJECT)

def normalize_shell_policy(shell):
    """Workspace or deny only. Exact-command allowlists and require_sandbox are obsolete."""
    if not isinstance(shell, dict):
        raise ValueError('shell policy must be an object')
    reject_compensating_sandbox_field(shell, loc='shell')
    if 'require_sandbox' in shell:
        raise ValueError('shell.require_sandbox is obsolete; sandbox is telemetry, not an L3 admission gate')
    if 'allowed' in shell:
        raise ValueError('shell.allowed exact-command allowlists are obsolete; use shell.mode workspace or deny')
    mode=str(shell.get('mode') or 'deny').lower()
    if mode in {'allowlist','unrestricted','all','allow'}:
        raise ValueError('shell.mode must be deny or workspace; exact-command allowlists are not an EIF control')
    if mode not in {'deny','workspace'}:
        raise ValueError(f'unsupported shell.mode {mode!r}')
    return {'mode': mode}

def normalize_network_policy(network):
    if network in (None, {}, []):
        return {'classes':[], 'destinations':[]}
    if not isinstance(network, dict):
        raise ValueError('network policy must be an object')
    if 'mode' in network and str(network.get('mode') or '') not in {'', 'none'}:
        raise ValueError('network.mode is obsolete; use network.classes: [loopback, public_read]')
    if network.get('mode') in {'none','deny'} and not network.get('classes'):
        # L1 default shape {mode:none} compiles to no destination classes.
        pass
    classes=[]
    for c in network.get('classes') or []:
        n=str(c).lower().strip()
        if n not in NETWORK_CLASSES:
            raise ValueError(f'unsupported network class {c!r}; use loopback and/or public_read')
        if n not in classes: classes.append(n)
    dests=[str(x).strip() for x in (network.get('destinations') or []) if str(x).strip()]
    return {'classes':classes,'destinations':dests}

def _shell_result(ok, code, msg, extra=None):
    return ok, code, msg, extra or {}

def network_classes(policy):
    net=policy.get('network') or {}
    return {str(c).lower() for c in (net.get('classes') or [])}

def url_destination_class(url, policy=None, roots=None):
    raw=str(url or '').strip()
    parsed=urlparse(raw)
    host=(parsed.hostname or '').lower()
    scheme=(parsed.scheme or '').lower()
    if scheme in {'http','https'}:
        if host in LOOPBACK_HOSTS or host.endswith('.localhost'):
            return 'loopback'
        return 'public_read'
    if scheme=='data' and raw.lower().startswith('data:text/html'):
        return 'local_fixture'
    if scheme=='file':
        path=file_url_to_path(raw)
        if path and _path_under_any_root(path, roots or _policy_root_paths(policy)):
            return 'local_fixture'
        return 'other'
    return 'other'

def network_destination_allowed(url, policy, roots=None):
    """HTTP(S)/local-fixture destination vs destination classes. Defense-in-depth, not a parser."""
    net=policy.get('network') or {}
    dests=net.get('destinations') or []
    host=(urlparse(url).hostname or '').lower()
    for raw in dests:
        pat=str(raw or '').strip()
        if not pat: continue
        if fnmatch.fnmatch(url, pat) or fnmatch.fnmatch(host, pat.lower().removeprefix('https://').removeprefix('http://')):
            return True,'NETWORK_OK','destination explicitly listed'
    cls=url_destination_class(url, policy, roots)
    granted=network_classes(policy)
    if cls=='local_fixture' and 'loopback' in granted:
        return True,'NETWORK_OK','local fixture treated as loopback'
    if cls in granted:
        return True,'NETWORK_OK',f'{cls} destination class granted'
    if not granted:
        return False,'ACTION_NETWORK','no network destination class is granted'
    return False,'NETWORK_DESTINATION',f'destination class {cls} is not granted for {host or url}'

def _path_under_any_root(path, roots) -> bool:
    try: target=Path(path).resolve()
    except Exception: return False
    for r in roots or []:
        try:
            target.relative_to(Path(r).resolve()); return True
        except Exception:
            continue
    return False

def _policy_root_paths(policy):
    out=[]
    for x in (policy or {}).get('allowed_roots') or []:
        try: out.append(Path(x).resolve())
        except Exception: pass
    return out

def file_url_to_path(url):
    parsed=urlparse(str(url or ''))
    if parsed.scheme.lower()!='file': return None
    path=unquote(parsed.path or '')
    if os.name=='nt' and parsed.netloc:
        return '\\\\'+parsed.netloc+path.replace('/','\\')
    if os.name=='nt' and path.startswith('/') and len(path)>=3 and path[2]==':':
        path=path.lstrip('/')
    return path or None

def _path_under_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False

def _path_candidates(cmd: str):
    found=[]
    for m in REDIRECT_TARGET.finditer(cmd):
        found.append(m.group(1).strip('\'"'))
    for m in QUOTED_PATH.finditer(cmd):
        found.append(m.group(1))
    for m in ABS_PATH.finditer(cmd):
        found.append(m.group(0))
    for tok in re.findall(r'(?:\.\./)+[^\s;|&"\']+', cmd):
        found.append(tok)
    for tok in re.findall(r'(?:[A-Za-z]:)?(?:\.{1,2}[\\/]|[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+', cmd):
        found.append(tok.replace('\\','/'))
    return found

PROGRAMME_ENTRY_REL = '.eif/runtime/programme/program.py'
PROGRAMME_LEDGER_FILES = frozenset({'PROGRAM.yaml', 'PROGRAM_LOG.ndjson'})
GIT_INVOCATION = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+', re.I)
GIT_WORKTREE_PROGRAMME = re.compile(
    r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+(?:restore\b|checkout\s+--|rm\b|clean\b|stash\b)',
    re.I,
)
GIT_RESET = re.compile(r'\bgit(?:\s+-C\s+\S+|\s+-c\s+\S+)*\s+reset\b', re.I)
GIT_ADD_BROAD_TOKENS = frozenset({'.', '-A', '--all', '-u', '--update', ':', '*'})

def _normalize_shell_rel(raw):
    rel=str(raw or '').replace('\\','/')
    while rel.startswith('./'):
        rel=rel[2:]
    return rel

def programme_ledger_rels(policy):
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    return {f'{sr}/program/{name}' for name in PROGRAMME_LEDGER_FILES}

def is_programme_ledger_rel(rel, policy):
    if not rel:
        return False
    return _normalize_shell_rel(rel) in programme_ledger_rels(policy)

def _git_subcommand_tokens(cmd):
    m=GIT_INVOCATION.search(cmd)
    if not m:
        return None, []
    rest=cmd[m.end():].strip()
    if not rest:
        return None, []
    parts=re.split(r'\s+', rest)
    return parts[0].lower(), parts[1:]

def _git_add_explicit_paths(cmd):
    sub, tokens=_git_subcommand_tokens(cmd)
    if sub!='add':
        return None
    paths=[]; after_dd=False
    for tok in tokens:
        if tok=='--':
            after_dd=True
            continue
        if not after_dd and tok.startswith('-'):
            continue
        paths.append(_normalize_shell_rel(tok))
    return paths

def _git_add_is_broad(cmd):
    sub, tokens=_git_subcommand_tokens(cmd)
    if sub!='add':
        return False
    for tok in tokens:
        if tok in GIT_ADD_BROAD_TOKENS:
            return True
        if tok.startswith('-') and tok in {'-p', '--patch', '-N', '--intent-to-add'}:
            return True
    return False

def _git_add_is_programme_ledger_only(cmd, policy):
    paths=_git_add_explicit_paths(cmd)
    if not paths:
        return False
    rels=programme_ledger_rels(policy)
    return all(p in rels for p in paths)

def _git_add_programme_consequence(cmd, policy):
    paths=_git_add_explicit_paths(cmd)
    if paths is None:
        return None
    if _git_add_is_broad(cmd):
        return _shell_result(
            False, 'PROGRAMME_GIT_STAGE',
            'git add with broad path selectors is denied; stage programme ledger files explicitly',
        )
    if not paths:
        return None
    rels=programme_ledger_rels(policy)
    ledger=[p for p in paths if p in rels]
    if not ledger:
        return None
    if all(p in rels for p in paths):
        return None
    return _shell_result(
        False, 'PROGRAMME_GIT_STAGE',
        'git add mixing programme ledger with other paths is denied; stage ledger files explicitly',
    )

def _command_touches_programme_paths(cmd, policy):
    norm=cmd.replace('\\', '/')
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    prog_prefix=f'{sr}/program'
    if prog_prefix in norm:
        return True
    for cand in _path_candidates(cmd):
        rel=_normalize_shell_rel(cand)
        if is_programme_ledger_rel(rel, policy) or matches(rel, [f'{prog_prefix}/**', prog_prefix]):
            return True
    return False

def _git_programme_worktree_deny(cmd, policy):
    norm=cmd.replace('\\', '/')
    if not GIT_INVOCATION.search(norm):
        return None
    if not (GIT_WORKTREE_PROGRAMME.search(norm) or GIT_RESET.search(norm)):
        return None
    if _command_touches_programme_paths(cmd, policy):
        return _shell_result(
            False, 'PROGRAMME_GIT_WORKTREE',
            'git command would mutate protected programme ledger in the worktree',
        )
    return None

def _git_branch_switch_note(cmd):
    """Branch switch rewrites tracked files without naming them; surface the consequence."""
    sub, tokens=_git_subcommand_tokens(cmd)
    if sub not in {'checkout', 'switch'} or not tokens:
        return None
    i=0
    while i < len(tokens) and tokens[i].startswith('-'):
        if tokens[i]=='--':
            return None
        i+=1
    if i >= len(tokens) or tokens[i]=='--':
        return None
    target=tokens[i]
    if '/' in target or target.startswith('.') or target.startswith('-'):
        return None
    return (
        'git branch switch may rewrite tracked programme ledger files when they differ between '
        'branches; run programme verify after switching'
    )

def _programme_runtime_shell_invoke(cmd: str) -> bool:
    """True when shell is invoking the installed programme entry point (read/execute, not mutate)."""
    norm = cmd.replace('\\', '/')
    # A substring must not exempt the rest of a compound command or redirect.
    if re.search(r'[;&|<>`\r\n]|\$\(', norm):
        return False
    return bool(re.fullmatch(
        r'\s*python(?:3)?\s+(?:-B\s+)?(?:["\'])?(?:\./)?\.eif/runtime/programme/program\.py(?:["\'])?(?:\s+[^\r\n]*)?\s*',
        norm,
        re.I,
    ))

def shell_path_consequence(cmd, policy):
    """Defense-in-depth only. Does not contain arbitrary child processes."""
    programme_invoke = _programme_runtime_shell_invoke(cmd)
    closure_invoke = support('eif_session').verifier_command(cmd)
    for m in REDIRECT_TARGET.finditer(cmd):
        rel=_normalize_shell_rel(m.group(1).strip('\'"'))
        if is_programme_ledger_rel(rel, policy):
            return _shell_result(
                False, 'PROGRAMME_PATH_PROTECTED',
                'shell redirection to programme ledger path is denied',
            )
    add_hit=_git_add_programme_consequence(cmd, policy)
    if add_hit:
        return add_hit
    wt_hit=_git_programme_worktree_deny(cmd, policy)
    if wt_hit:
        return wt_hit
    staging_only=_git_add_is_programme_ledger_only(cmd, policy)
    ledger_rels=programme_ledger_rels(policy) if staging_only else set()
    roots=[Path(x) for x in (policy.get('allowed_roots') or []) if x]
    protected=policy.get('protected_paths') or []
    base=roots[0] if roots else None
    for cand in _path_candidates(cmd):
        rel=_normalize_shell_rel(cand)
        if programme_invoke and rel == PROGRAMME_ENTRY_REL:
            continue
        if closure_invoke and rel == '.cursor/hooks/eif_guard.py':
            continue
        if staging_only and rel in ledger_rels:
            continue
        if control_plane(rel, policy) or any(s in rel for s in ('.cursor/eif-runtime-policy.json','.cursor/hooks','.eif/AUTONOMY_POLICY.md','.eif/RUNTIME_CAPABILITIES.md')):
            return _shell_result(False,'CONTROL_PLANE_PROTECTED','shell text names a control-plane path; defense-in-depth deny (not process containment)')
        if matches(rel, protected):
            return _shell_result(False,'PROTECTED_PATH','shell text names a protected path; defense-in-depth deny (not process containment)')
        try:
            p=Path(cand)
            if p.is_absolute():
                resolved=p
            elif base is not None and (cand.startswith('..') or cand.startswith('/') or (len(cand)>1 and cand[1]==':')):
                resolved=(base/cand)
            else:
                continue
            resolved=resolved.resolve()
            if roots and not any(_path_under_root(resolved, r) for r in roots):
                return _shell_result(False,'FOREIGN_PATH','shell text names a path outside declared roots; defense-in-depth deny (not process containment)')
        except Exception:
            continue
    return None

def shell_decision(cmd, sandbox, policy):
    """sandbox is recorded by the caller; it is not an allow/deny input."""
    del sandbox
    if IDENTITY_MUTATION.search(cmd) and not action_allowed(policy,'identity_mutation'):
        return _shell_result(False,'ACTION_IDENTITY_MUTATION','git remote identity mutation is not granted')
    prog_git=_git_programme_worktree_deny(cmd, policy)
    if prog_git:
        return prog_git
    add_git=_git_add_programme_consequence(cmd, policy)
    if add_git:
        return add_git
    if FORCE_VCS.search(cmd) and not action_allowed(policy,'force_vcs'):
        return _shell_result(False,'ACTION_FORCE_VCS','force/history-rewriting VCS operation is not granted')
    if REMOTE_PUSH.search(cmd) and not action_allowed(policy,'remote_push'):
        return _shell_result(False,'ACTION_REMOTE_PUSH','remote push is not granted')
    if DESTRUCTIVE_INPUT.search(cmd) and not action_allowed(policy,'destructive_data'):
        return _shell_result(False,'ACTION_DESTRUCTIVE_DATA','destructive data/infrastructure operation is not granted')
    if INFRASTRUCTURE.search(cmd) and not action_allowed(policy,'infrastructure_control'):
        return _shell_result(False,'ACTION_INFRASTRUCTURE','external infrastructure / remote-shell mutation is not granted')
    if GIT_CLONE.search(cmd) and not action_allowed(policy,'infrastructure_control'):
        return _shell_result(False,'ACTION_NETWORK','cloning an external repository is not ordinary workspace verification')
    if GLOBAL_OR_PUBLISH.search(cmd) and not action_allowed(policy,'infrastructure_control'):
        return _shell_result(False,'ACTION_DEPENDENCY','global install or package publish is not granted')
    if SHELL_FETCH.search(cmd):
        urls=URL_IN_TEXT.findall(cmd)
        if not urls:
            return _shell_result(False,'ACTION_NETWORK','fetch tool without a classifiable destination is denied')
        for url in urls:
            good,code,msg=network_destination_allowed(url, policy)
            if not good: return _shell_result(False,code,msg)
    path_hit=shell_path_consequence(cmd, policy)
    if path_hit: return path_hit
    sh=policy.get('shell') or {}; mode=str(sh.get('mode') or 'deny').lower()
    if mode=='deny': return _shell_result(False,'SHELL_DENY','shell execution disabled by policy')
    if mode=='workspace':
        branch_note=_git_branch_switch_note(cmd)
        extra={'programme_branch_switch': True} if branch_note else {}
        msg=branch_note or 'ordinary workspace shell; not process containment'
        return _shell_result(True,'SHELL_WORKSPACE',msg,extra)
    return _shell_result(False,'SHELL_DENY','shell execution disabled by policy')

MCP_URL_KEYS = {
    'url','uri','href','start_url','target_url','navigation_url','navigate_url',
    'pageurl','page_url','currenturl','current_url','finalurl','final_url','starturl',
}
MCP_NON_DEST_KEYS = {
    'element','ref','text','value','content','selector','name','description',
    'title','html','innertext','accessible_name','snapshot','code','script',
}
MUTATING_HTTP = frozenset({'POST','PUT','PATCH','DELETE','CONNECT'})
INTERACT_ORIGINS = frozenset({'loopback','local_fixture'})
PAGE_URL_RE = re.compile(r'(?im)(?:page\s*url|current\s*url)\s*[:=]\s*(\S+)')

def mcp_tool_input_object(data):
    """Return tool_input as a dict/list/str. MCP server `url` is not tool input."""
    inp=data.get('tool_input')
    if isinstance(inp,str):
        try: return json.loads(inp)
        except Exception: return inp
    return inp

def _looks_like_page_url(value):
    s=str(value or '').strip()
    return s.lower().startswith(('http://','https://','file://','data:text/html'))

def destination_urls_from_mcp(data):
    """Agent-aimed destinations from URL-shaped *tool_input* keys only.

    Accessible names (`element`) may contain https:// without being a destination.
    MCP server `url` is identity, not user egress.
    """
    inp=mcp_tool_input_object(data)
    urls=[]
    def take(value):
        if isinstance(value,str) and _looks_like_page_url(value):
            urls.append(value.strip())
    if isinstance(inp,str):
        take(inp); return urls
    if isinstance(inp,dict):
        for k,v in inp.items():
            key=str(k).lower()
            if key in MCP_NON_DEST_KEYS: continue
            if key in MCP_URL_KEYS or key.endswith('_url') or key.endswith('url'):
                take(v)
    return urls

def mcp_aimed_http_method(data):
    inp=mcp_tool_input_object(data)
    if isinstance(inp,dict):
        for k in ('method','http_method','verb'):
            if inp.get(k): return str(inp.get(k)).upper()
    n=str(data.get('tool_name') or '').lower().removeprefix('mcp:')
    if any(x in n for x in ('network_request','http_request','fetch')):
        return 'GET'
    return None

def _parse_jsonish(raw):
    if raw is None: return None
    if isinstance(raw,(dict,list)): return raw
    if not isinstance(raw,str): return None
    s=raw.strip()
    if not s: return None
    try: return json.loads(s)
    except Exception: return s

def _page_url_from_mapping(obj):
    if not isinstance(obj,dict): return None
    for k,v in obj.items():
        key=str(k).lower()
        if key in MCP_NON_DEST_KEYS: continue
        if key in MCP_URL_KEYS or key.replace('-','') in {'pageurl','currenturl','finalurl'}:
            if isinstance(v,str) and _looks_like_page_url(v): return v.strip()
    page=obj.get('page')
    if isinstance(page,dict):
        u=page.get('url')
        if isinstance(u,str) and _looks_like_page_url(u): return u.strip()
    for key in ('tabs','targets','pages'):
        tabs=obj.get(key)
        if not isinstance(tabs,list): continue
        active=None; lone=[]
        for t in tabs:
            if not isinstance(t,dict): continue
            u=t.get('url') or t.get('uri')
            if not (isinstance(u,str) and _looks_like_page_url(u)): continue
            lone.append(u.strip())
            if t.get('active') or t.get('selected') or t.get('current'): active=u.strip()
        if active: return active
        if len(lone)==1: return lone[0]
    return None

def harvest_page_url(data):
    """Current page URL from MCP result/output, not from accessibility-tree hrefs."""
    for field in ('result_json','tool_output','output','result'):
        parsed=_parse_jsonish(data.get(field))
        if isinstance(parsed,dict):
            for candidate in (parsed, parsed.get('result'), parsed.get('data'), parsed.get('payload')):
                u=_page_url_from_mapping(candidate) if isinstance(candidate,dict) else None
                if u: return u
        if isinstance(parsed,str):
            m=PAGE_URL_RE.search(parsed)
            if m:
                cand=m.group(1).strip('`"\'')
                if _looks_like_page_url(cand): return cand
    inp=mcp_tool_input_object(data)
    if isinstance(inp,dict) and any(str(k).lower() in MCP_URL_KEYS or str(k).lower().endswith('url') for k in inp):
        u=_page_url_from_mapping(inp)
        if u: return u
    return None

def _mcp_tool_entry(raw):
    if isinstance(raw,str): return {'tool_pattern':raw,'server_pattern':'*'}
    e=dict(raw or {})
    if 'pattern' in e and 'tool_pattern' not in e: e['tool_pattern']=e.get('pattern')
    e.setdefault('server_pattern','*')
    return e

def mcp_tool_granted(policy, tool_name):
    m=policy.get('mcp') or {}
    if m.get('mode','none')!='allowlist' or not tool_name: return False
    for raw in m.get('tools') or []:
        e=_mcp_tool_entry(raw)
        tp=e.get('tool_pattern') or ''
        if tp and fnmatch.fnmatch(tool_name, tp): return True
    return False

def _mcp_glob(pattern: str) -> bool:
    return bool(pattern) and any(c in pattern for c in '*?[]')

def normalize_browser_mode(raw):
    m=str(raw or 'none').lower()
    if m not in {'none','observe','interact'}:
        raise ValueError(f'unsupported mcp.browser {raw!r}; use none, observe, or interact')
    return m

def browser_mode(policy):
    try: return normalize_browser_mode(((policy or {}).get('mcp') or {}).get('browser'))
    except ValueError: return 'none'

def is_browser_tool(name):
    n=str(name or '').lower().removeprefix('mcp:')
    return n.startswith('browser_') or n.startswith('browser-')

def browser_action_kind(name):
    n=str(name or '').lower().removeprefix('mcp:')
    if 'run_code_unsafe' in n or n in {'browser_cdp','browser_run_code'} or n.endswith('_cdp'):
        return 'unsafe'
    if any(k in n for k in ('click','type','fill','select','press','drag','drop','upload','dialog','evaluate','hover')):
        return 'interact'
    if any(k in n for k in ('navigate','goto','open_url')) and 'navigate_back' not in n and not n.endswith('_back'):
        return 'navigate'
    if 'network_request' in n or 'http_request' in n or n.endswith('_fetch'):
        return 'aimed_request'
    return 'observe'

def _browser_state_path(root: Path, data):
    conv=re.sub(r'[^A-Za-z0-9_.-]','_',str(data.get('conversation_id') or 'unknown'))[:120]
    d=root/'.eif'/'runtime-budget'; d.mkdir(parents=True, exist_ok=True)
    return d/f'browser-{conv}.json'

def load_browser_origin(root: Path, data):
    if root is None: return None
    p=_browser_state_path(root, data)
    try:
        return str((json.loads(p.read_text(encoding='utf-8')) or {}).get('origin') or '') or None
    except Exception:
        return None

def record_browser_origin_class(root: Path, data, origin, policy=None, url=None):
    if root is None or not origin: return
    payload={'origin':origin}
    if url: payload['url']=str(url)[:500]
    try:
        _browser_state_path(root, data).write_text(json.dumps(payload), encoding='utf-8')
    except Exception:
        pass

def record_browser_origin(root: Path, data, dests, policy=None, roots=None):
    if root is None: return
    origin='none'
    chosen=None
    for url in dests or []:
        cls=url_destination_class(url, policy, roots)
        chosen=url
        if cls in INTERACT_ORIGINS: origin=cls; break
        if cls=='public_read': origin='public_read'
        elif cls=='other': origin='other'
    record_browser_origin_class(root, data, origin, policy, chosen)

def note_observed_browser_page(root, data, policy, roots=None, *, after=False):
    """Update page origin from agent-aimed input or after-tool page URL harvest."""
    if root is None or not is_browser_tool(data.get('tool_name') or ''):
        return
    aimed=destination_urls_from_mcp(data)
    if aimed and not after:
        record_browser_origin(root, data, aimed, policy, roots)
        return
    harvested=harvest_page_url(data)
    if harvested:
        cls=url_destination_class(harvested, policy, roots)
        record_browser_origin_class(root, data, cls, policy, harvested)

def browser_interact_origin_ok(root, data, policy):
    """In-page interaction is local-app use. Proven public origin is never a mutate grant."""
    last=load_browser_origin(root, data)
    if last in INTERACT_ORIGINS: return True,'',''
    if last in {'public_read','other'}:
        return False,'BROWSER_INTERACT_ORIGIN','in-page interaction is limited to the current local application page; public/external origins are observe/navigate only'
    classes=network_classes(policy)
    extra=[d for d in ((policy.get('network') or {}).get('destinations') or []) if str(d).strip()]
    if 'public_read' in classes or extra:
        return False,'BROWSER_INTERACT_ORIGIN','in-page interaction requires a current loopback/local-fixture page; public_read is not a UI-mutate grant'
    return True,'',''

def mcp_decision(data, policy, root=None, roots=None):
    m=policy.get('mcp') or {}
    if m.get('mode','none')!='allowlist' or not (m.get('tools') or []):
        return False,'MCP_DENY','MCP disabled unless explicitly granted'
    tool=str(data.get('tool_name') or '').removeprefix('MCP:')
    server=str(data.get('url') or data.get('command') or '')
    tool_input=data.get('tool_input') or ''
    if not isinstance(tool_input,str): tool_input=json.dumps(tool_input,sort_keys=True)
    matched=None
    for raw in m.get('tools') or []:
        e=_mcp_tool_entry(raw)
        tp=e.get('tool_pattern') or ''; sp=e.get('server_pattern') or '*'
        if not tp or not fnmatch.fnmatch(tool,tp): continue
        if server and not fnmatch.fnmatch(server,sp): continue
        matched=e; break
    if not matched:
        return False,'MCP_NOT_GRANTED',f'MCP tool {tool or "<unknown>"} is not in the granted set'
    if DESTRUCTIVE_INPUT.search(tool_input) and not action_allowed(policy,'destructive_data'):
        return False,'MCP_DESTRUCTIVE','MCP payload appears destructive and is not granted'
    dests=destination_urls_from_mcp(data)
    roots=roots or _policy_root_paths(policy)
    for dest in dests:
        good,code,msg=network_destination_allowed(dest, policy, roots)
        if not good: return False,code,msg
        cls=url_destination_class(dest, policy, roots)
        method=mcp_aimed_http_method(data)
        if method in MUTATING_HTTP and cls=='public_read':
            return False,'BROWSER_PUBLIC_MUTATE','public_read is GET-shaped research; it is not permission to POST/PUT/PATCH/DELETE a public origin'
        if method in MUTATING_HTTP and browser_mode(policy)=='observe':
            return False,'BROWSER_OBSERVE_ONLY','mutating HTTP via an agent-aimed browser request is not observe-only'
    kind=browser_action_kind(tool) if is_browser_tool(tool) else None
    if kind=='unsafe' and not action_allowed(policy,'infrastructure_control'):
        return False,'BROWSER_UNSAFE','browser evaluate/unsafe execution is not ordinary UI interaction'
    if kind=='interact':
        mode=browser_mode(policy)
        tp=matched.get('tool_pattern') or ''
        if mode=='observe' or (mode=='none' and _mcp_glob(tp)):
            return False,'BROWSER_OBSERVE_ONLY','in-page interaction is not granted; set mcp.browser: interact for local-app use'
        ok,code,msg=browser_interact_origin_ok(root, data, policy)
        if not ok: return False,code,msg
    if kind in {'navigate','aimed_request'} and dests:
        record_browser_origin(root, data, dests, policy, roots)
    return True,'MCP_ALLOW','granted MCP tool'

def presentation_profile(root):
    """Protected operator projection; payload flags cannot select this mode.

    No Git, session state, reducer replay, budget or network on this path.
    Invalid/stale projections grant nothing; the full policy route remains.
    """
    path = support('eif_state').contained(root, '.eif/node-scope.json')
    if not path.is_file():
        return None
    try:
        scope = json.loads(path.read_text(encoding='utf-8'))
        if (scope.get('version') != 1 or scope.get('mode') != 'presentation'
                or scope.get('root') != str(root.resolve()) or not re.fullmatch(r'N-[0-9]+', scope.get('node', ''))):
            return None
        for key, rel in [('policy_sha256', '.cursor/eif-runtime-policy.json'),
                         ('runtime_sha256', '.cursor/eif-runtime-manifest.json')]:
            if scope.get(key) != hashlib.sha256((root / rel).read_bytes()).hexdigest():
                return None
        charter = scope.get('charter')
        if (not isinstance(charter, dict) or charter.get('effects') != ['presentation']
                or not isinstance(charter.get('statement'), str) or not charter['statement'].strip()
                or not isinstance(charter.get('change_paths'), list) or not charter['change_paths']
                or not isinstance(charter.get('commands'), list)):
            return None
        for pattern in charter['change_paths']:
            if (not isinstance(pattern, str) or not pattern or pattern.startswith(('/', '*', '?', '['))
                    or (pattern.startswith('.') and not pattern.startswith('.eif/audit/'))
                    or re.search(r'[\\:\x00-\x1f]', pattern) or any(p in {'', '.', '..'} for p in pattern.split('/'))):
                return None
        if any(not isinstance(cmd, str) for cmd in charter['commands']):
            return None
        # Bind the accepted ledger prefix, then inspect only later event headers
        # for revocation. Ordinary evidence/stage updates do not expire a charter.
        ledger = support('eif_state').contained(root, '.eif/program/PROGRAM_LOG.ndjson').read_bytes()
        count = scope.get('ledger_bytes')
        if (type(count) is not int or count <= 0 or len(ledger) < count
                or hashlib.sha256(ledger[:count]).hexdigest() != scope.get('ledger_sha256')):
            return None
        seq = scope.get('ledger_seq')
        if type(seq) is not int:
            return None
        for line in ledger[count:].splitlines():
            entry = json.loads(line)
            seq += 1
            if entry.get('seq') != seq:
                return None
            payload = entry.get('payload') or {}
            if entry.get('event') == 'programme.status' and payload.get('status', payload.get('to')) != 'active':
                return None
            if (payload.get('node') or payload.get('id')) != scope['node']:
                continue
            if entry.get('event') == 'node.patch' and any(key in payload for key in
                    ('risk_class', 'execution_charter', 'risk', 'class', 'facets', 'title', 'acceptance_criteria')):
                return None
            if entry.get('event') in {'node.retroactive_complete', 'node.independence.disclaim'}:
                return None
            if entry.get('event') == 'node.status' and (payload.get('to') or payload.get('status')) in {'complete', 'split', 'rejected', 'deferred'}:
                return None
        return scope
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def presentation_action(root, data, policy, scope):
    event = data.get('hook_event_name')
    if event in {'sessionStart', 'stop', 'sessionEnd'}:
        return True
    tool, inp = support('eif_session').action(data)
    if event == 'afterFileEdit':
        tool, inp = 'Write', {'file_path': data.get('file_path')}
    roots = declared_roots(data, policy, root)
    if tool in {'Read', 'ReadLints', 'Grep', 'Glob', 'List', 'Write'} and isinstance(inp, dict):
        path = tool_path(inp)
        rr, rel = resolve_path(path, roots) if path else (root, '')
        if not rr or Path(rr).resolve() != root.resolve():
            return False
        if tool == 'Write':
            if (not path or control_plane(rel, policy) or matches(rel, policy.get('protected_paths') or [])
                    or not matches(rel, scope['charter']['change_paths'])):
                return False
        elif observation_scopes(policy) and not matches(rel or '**', observation_scopes(policy)):
            return False
        if matches(rel, policy.get('sensitive_read_paths') or []) or any(has_secret(value) for value in strings(inp)):
            return False
        if event == 'beforeReadFile' and has_secret(str(data.get('content') or '')):
            return False
        return True
    if tool == 'Shell' and isinstance(inp, dict):
        cmd = inp.get('command', '')
        if cmd not in scope['charter']['commands'] or Path(inp.get('cwd') or root).resolve() != root.resolve():
            return False
        # Even an explicitly listed destructive/migration/remote command keeps
        # the full workflow. Shell children remain operator-trusted, not jailed.
        if (re.search(r'[;&|<>`\r\n]|\$\(', cmd)
                or re.search(r'\b(?:rm|del|erase|rmdir|remove-item|move-item|mv|unlink|migrat\w*|prisma|knex|alembic)\b', cmd, re.I)
                or any(pattern.search(cmd) for pattern in (FORCE_VCS, REMOTE_PUSH, DESTRUCTIVE_INPUT,
                       IDENTITY_MUTATION, INFRASTRUCTURE, GIT_CLONE, GLOBAL_OR_PUBLISH))):
            return False
        return shell_decision(cmd, False, policy)[0]
    name = tool.removeprefix('MCP:')
    if name in {'browser_snapshot', 'browser_take_screenshot', 'browser_console_messages', 'browser_network_requests'}:
        if isinstance(inp, dict) and any(inp.get(key) for key in ('filename', 'file_path', 'path', 'download_path')):
            return False
        request = dict(data, tool_name=name)
        return mcp_decision(request, policy, root, roots)[0]
    return False  # Delete, unknown tools and MCP mutations retain full admission.


def presentation_audit(root, data, extra):
    """Bound the advisory event sink; it cannot turn charter work into a gate."""
    global _AUDIT_ERROR, _DECISION_CODE
    _DECISION_CODE = 'PRESENTATION_UNGUARDED'
    done = threading.Event()
    def record():
        try:
            audit(root, data, 'allow', 'PRESENTATION_UNGUARDED', extra=extra)
        finally:
            done.set()
    threading.Thread(target=record, daemon=True, name='eif-presentation-audit').start()
    if not done.wait(0.1):
        _AUDIT_ERROR = 'presentation audit delivery unconfirmed'


def main():
    global _RUNTIME_LOCK
    try:
        try:
            return _main()
        except GuardFault as exc:
            return deny(exc.code, str(exc))
    finally:
        if _RUNTIME_LOCK is not None:
            _RUNTIME_LOCK.__exit__(None, None, None)
            _RUNTIME_LOCK = None


def _main():
    global _READ_ONLY, _ACTIVE_ROOT, _ACTIVE_DATA, _SUPPORT_READY, _RUNTIME_LOCK, _READ_WARNING
    started = time.perf_counter()
    try:
        data = parse_cursor_hook_stdin(read_cursor_hook_stdin(sys.stdin.buffer))
    except Exception as e:
        return deny('HOOK_INPUT_INVALID', f'cannot parse Cursor hook input: {type(e).__name__}: {e}')
    _TIMINGS['input'] = round((time.perf_counter() - started) * 1000, 3)
    event=data.get('hook_event_name','')
    if not isinstance(event, str) or not event:
        return deny('HOOK_INPUT_INVALID', 'hook_event_name must be a nonempty string')
    if event == 'preToolUse' and (not isinstance(data.get('tool_name'), str) or not isinstance(data.get('tool_input'), dict)):
        return deny('HOOK_INPUT_INVALID', 'preToolUse requires tool_name and object tool_input')
    if event == 'preToolUse' and data.get('tool_name') in {'Read', 'Write', 'Delete', 'ReadLints', 'Grep', 'Glob', 'List'}:
        validate_tool_paths(data['tool_input'])
    if event == 'beforeReadFile' and (not isinstance(data.get('file_path'), str) or not data['file_path'].strip()):
        return deny('HOOK_INPUT_INVALID', 'Read has no identifiable path')
    if event == 'preToolUse' and data.get('tool_name') in {'Read', 'Write', 'Delete'}:
        if not tool_path(data.get('tool_input')):
            return deny('HOOK_INPUT_INVALID', f'{data["tool_name"]} has no identifiable path')
    _READ_ONLY = event == 'beforeReadFile' or (
        event == 'preToolUse' and data.get('tool_name') in {'Read', 'ReadLints', 'Grep', 'Glob', 'List'}
    )
    root=select_root(data)
    _ACTIVE_ROOT, _ACTIVE_DATA = root, data
    started = time.perf_counter()
    try:
        _RUNTIME_LOCK = verified_runtime(root)
    except TimeoutError as exc:
        return deny('RUNTIME_LOCK_FAILURE', str(exc))
    except Exception as exc:
        return deny('RUNTIME_INTEGRITY', f'{type(exc).__name__}: {exc}')
    _SUPPORT_READY = True
    support('eif_state').DEADLINE = _DEADLINE
    _TIMINGS['integrity'] = round((time.perf_counter() - started) * 1000, 3)
    started = time.perf_counter()
    state,policy,pp,pmsg=load_policy(root)
    _TIMINGS['policy'] = round((time.perf_counter() - started) * 1000, 3)

    if state in {'MALFORMED', 'INVALID'}:
        audit(root, data, 'deny', 'POLICY_INTEGRITY')
        return deny('POLICY_INTEGRITY', pmsg)

    scope = presentation_profile(root) if state == 'OK' else None
    if scope and presentation_action(root, data, policy, scope):
        # The normal runtime/policy integrity checks above remain mandatory.
        # No success is fabricated and no full-loop session debt is changed.
        extra = {'enforcement': 'UNGUARDED', 'node': scope['node'],
                 'risk_class': 'presentation', 'charter': scope['charter']['statement']}
        presentation_audit(root, data, extra)
        return out(message='UNGUARDED presentation charter; workflow gates not enforced', extra=extra)

    # sessionStart is context only on Cursor; it is never used as a blocking boundary.
    if event=='sessionStart':
        if state=='OK':
            ok,msg=identity_ok(root,policy)
            started = time.perf_counter()
            closed, code, closure = support('eif_session').boundary(root, data)
            _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
            text=(f'EIF runtime policy loaded for {policy.get("project_id","<unset>")}; '
                  f'identity preflight: {msg}; {code}: {closure}. '
                  'Pending retry and closure are enforced at actionable hooks; lifecycle replies cannot prevent forced closure.')
            audit(root, data, 'allow', 'SESSION_READY' if ok and closed else code)
            return out(extra={'additional_context':text})
        return out(extra={'additional_context':f'EIF runtime policy state: {state}. {pmsg}. Do not treat sessionStart as a blocking control.'})

    # Observation only. Used to harvest the current page URL after click/navigation.
    # Cannot block the just-completed tool; subsequent interact uses the updated origin.
    if event in {'afterMCPExecution','postToolUse'}:
        support('eif_session').record_success(root, data)
        if state=='OK' and policy:
            note_observed_browser_page(root, data, policy, declared_roots(data,policy,root), after=True)
        audit(root,data,'allow','MCP_AFTER' if event=='afterMCPExecution' else 'POST_TOOL')
        return out()

    if event == 'postToolUseFailure':
        # An ordinary failed test is not a guard block. Cursor identifies a
        # permission denial separately; our own harness faults are saved pre-emit.
        if data.get('failure_type') == 'permission_denied':
            support('eif_session').record_block(root, data, 'TOOL_PERMISSION_DENIED')
        audit(root, data, 'allow', 'POST_TOOL_FAILURE')
        return out()

    if event in {'stop', 'sessionEnd'}:
        started = time.perf_counter()
        closed, code, message = support('eif_session').boundary(root, data)
        pending = support('eif_session').pending(root)
        _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
        if pending:
            message += f'; retry blocked {pending[0][2]["tool"]} first (fingerprint={pending[0][2]["fingerprint"]})'
        audit(root, data, 'allow', code)
        extra = {'additional_context': f'{code}: {message}'}
        if event == 'stop' and (not closed or pending):
            extra['followup_message'] = f'EIF closure pending. {message}. Use only policy-permitted recovery; do not claim the session is closed.'
        return out(extra=extra)

    # Unconditional control-plane file denials precede workflow obligations.
    # This can only reject; no session name, probe flag, or permission bypass is
    # introduced. It keeps a protected-Write health proof meaningful even while
    # unrelated work is gated. Normal admission still runs every check below.
    if state == 'OK' and event == 'preToolUse' and data.get('tool_name') in {'Write', 'Delete'}:
        path = tool_path(data.get('tool_input'))
        rr, rel = resolve_path(path, declared_roots(data, policy, root)) if path else (None, None)
        if rr and control_plane(rel, policy):
            audit(root, data, 'deny', 'CONTROL_PLANE_PROTECTED', rel)
            return deny('CONTROL_PLANE_PROTECTED', f'agent may not directly modify generated/accepted control-plane path {rel}')

    if event in {'preToolUse', 'beforeShellExecution', 'beforeMCPExecution', 'beforeReadFile', 'subagentStart'}:
        started = time.perf_counter()
        try:
            ready, code, message = support('eif_session').pre_check(root, data)
        except Exception as exc:
            ready, code, message = False, 'SESSION_STATE_FAILURE', f'{type(exc).__name__}: {exc}'
        _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
        if not ready:
            if code == 'SESSION_STATE_FAILURE' and _READ_ONLY:
                _READ_WARNING = {'reason_code': code, 'additional_context': message + '; session bookkeeping needs repair. Read permission checks still apply.'}
            else:
                audit(root, data, 'deny', code)
                return deny(code, message)

    # Malformed/invalid installed policy is different from cold-start absence.
    if state in {'MALFORMED','INVALID'}:
        audit(root,data,'deny','POLICY_INTEGRITY')
        return deny('POLICY_INTEGRITY',pmsg)

    roots=declared_roots(data,policy,root)
    actions=(policy or {}).get('action_classes') or {}

    if event=='beforeReadFile':
        path=data.get('file_path'); rr,rel=resolve_path(path,roots)
        if not rr:
            audit(root,data,'deny','FOREIGN_READ')
            return deny('FOREIGN_READ','read target resolves outside all declared project roots')
        if state=='OK':
            ok,msg=identity_ok(root,policy)
            if not ok:
                audit(root,data,'deny','IDENTITY_READ',rel); return deny('IDENTITY_READ',msg)
            scopes=observation_scopes(policy)
            if scopes and not matches(rel,scopes):
                audit(root,data,'deny','OUT_OF_OBSERVATION_SCOPE',rel); return deny('OUT_OF_OBSERVATION_SCOPE',f'read target outside accepted observation scope: {rel}')
        sensitive=(policy.get('sensitive_read_paths') if policy else ['.env','.env.*','**/*.pem','**/*secret*','**/*credential*']) or []
        if matches(rel,sensitive):
            audit(root,data,'deny','SENSITIVE_READ',rel); return deny('SENSITIVE_READ',f'direct model read blocked: {rel}')
        # High-confidence content scan before it enters model context.
        if has_secret(str(data.get('content') or '')):
            audit(root,data,'deny','SECRET_IN_READ',rel); return deny('SECRET_IN_READ',f'high-confidence secret-like content detected in {rel}; use a scoped secure mechanism')
        audit(root,data,'allow','READ_OK',rel); return out()

    if event=='afterFileEdit':
        # Detection/audit only. It occurs after the edit; do not present it as the primary pre-write boundary.
        path=data.get('file_path'); rr,rel=resolve_path(path,roots)
        if rr:
            try:
                text=Path(path).read_text(errors='replace')
                if has_secret(text):
                    audit(root,data,'deny','POST_EDIT_SECRET',rel)
                    return deny('POST_EDIT_SECRET',f'secret-like content detected after edit in {rel}; remove/redact immediately and review exposure')
            except Exception: pass
        audit(root,data,'allow','POST_EDIT_OK',rel); return out()

    if event=='beforeShellExecution':
        if state!='OK':
            cmd=str(data.get('command') or '')
            if state=='MISSING' and any(re.fullmatch(p,cmd.strip(),re.I) for p in BOOTSTRAP_SHELL):
                audit(root,data,'allow','BOOTSTRAP_SHELL'); return out()
            audit(root,data,'deny','SHELL_POLICY_REQUIRED'); return deny('SHELL_POLICY_REQUIRED','accepted runtime policy/identity required before shell execution')
        ok,msg=identity_ok(root,policy)
        if not ok: audit(root,data,'deny','IDENTITY_SHELL'); return deny('IDENTITY_SHELL',msg)
        good,code,msg,extra=shell_decision(str(data.get('command') or ''),bool(data.get('sandbox')),policy)
        audit(root,data,'allow' if good else 'deny',code, extra=extra)
        if good:
            note=msg if msg and msg!='ordinary workspace shell; not process containment' else None
            return out(message=note, extra=extra or None)
        return deny(code,msg)

    if event=='beforeMCPExecution':
        if state!='OK': audit(root,data,'deny','MCP_POLICY_REQUIRED'); return deny('MCP_POLICY_REQUIRED','accepted runtime policy required before MCP execution')
        ok,msg=identity_ok(root,policy)
        if not ok: audit(root,data,'deny','IDENTITY_MCP'); return deny('IDENTITY_MCP',msg)
        good,code,msg=mcp_decision(data,policy,root,roots); audit(root,data,'allow' if good else 'deny',code)
        return out() if good else deny(code,msg)

    if event=='preToolUse':
        tool=str(data.get('tool_name') or ''); inp=data.get('tool_input') or {}
        supported = {'Read', 'ReadLints', 'Grep', 'Glob', 'List', 'Write', 'Delete', 'Shell',
                     'Fetch', 'WebFetch', 'WebSearch', 'ListMcpResources', 'FetchMcpResource'}
        if tool not in supported and not tool.startswith('MCP:'):
            audit(root, data, 'deny', 'TOOL_UNSUPPORTED')
            return deny('TOOL_UNSUPPORTED', f'No verified permission adapter for {tool}; opaque side effects cannot be authorised.')
        # Cold start: no project state-changing action. Only manifest bootstrap write is tolerated.
        if state=='MISSING':
            if tool=='Shell':
                cmd=str(inp.get('command','')) if isinstance(inp,dict) else ''
                good=any(re.fullmatch(p,cmd.strip(),re.I) for p in BOOTSTRAP_SHELL)
                audit(root,data,'allow' if good else 'deny','BOOTSTRAP_SHELL')
                return out() if good else deny('BOOTSTRAP','only minimal identity shell commands are allowed before policy installation')
            if tool in {'Write','Delete'}:
                path=tool_path(inp); rr,rel=resolve_path(path,roots)
                if tool=='Write' and rel in {'.eif/PROJECT_MANIFEST.md','PROJECT_MANIFEST.md'}:
                    audit(root,data,'allow','BOOTSTRAP_MANIFEST',rel); return out()
                audit(root,data,'deny','BOOTSTRAP_WRITE',rel); return deny('BOOTSTRAP','state-changing writes require accepted manifest + compiled runtime policy')
            if tool.startswith('MCP:'): audit(root,data,'deny','BOOTSTRAP_MCP'); return deny('BOOTSTRAP_MCP','MCP disabled during bootstrap')
            return out()

        ok,msg=identity_ok(root,policy)
        if not ok:
            audit(root,data,'deny','IDENTITY_TOOL'); return deny('IDENTITY_TOOL',msg)
        bok,bmsg,bextra=budget_ok(root,data,policy)
        if not bok:
            code = bmsg.split(':', 1)[0]
            if code == 'BUDGET_STATE_FAILURE' and _READ_ONLY:
                # Defer emission until identity, source integrity, scope and
                # sensitive-path checks below have authorised this read.
                bextra = {'reason_code': code, 'additional_context': bmsg + '; read policy checks completed; repair budget state before mutations.'}
            else:
                audit(root,data,'deny',code)
                return deny(code,bmsg)

        # Generic path-bound tools: reads/writes cannot escape declared roots, including symlink escapes.
        path=tool_path(inp); rr,rel=resolve_path(path,roots) if path else (None,None)
        if path and not rr:
            audit(root,data,'deny','FOREIGN_PATH'); return deny('FOREIGN_PATH','tool target resolves outside all declared project roots')

        if tool in {'Write','Delete'}:
            if control_plane(rel,policy):
                audit(root,data,'deny','CONTROL_PLANE_PROTECTED',rel); return deny('CONTROL_PLANE_PROTECTED',f'agent may not directly modify generated/accepted control-plane path {rel}')
            if matches(rel,policy.get('protected_paths') or []):
                audit(root,data,'deny','PROTECTED_PATH',rel); return deny('PROTECTED_PATH',f'protected path: {rel}')
            # Audit artifact writes are a separate grant from implementation write/change_scopes.
            if tool=='Write' and artifact_write_allowed(rel,policy):
                for st in strings(inp):
                    if has_secret(st):
                        audit(root,data,'deny','SECRET_PREWRITE',rel); return deny('SECRET_PREWRITE','high-confidence secret-like literal blocked before file write')
                audit(root,data,'allow','ARTIFACT_WRITE_OK',rel); return out(extra=bextra)
            if tool=='Write' and is_audit_artifact_rel(rel,policy) and not action_allowed(policy,'artifact_write'):
                audit(root,data,'deny','ACTION_ARTIFACT_WRITE',rel); return deny('ACTION_ARTIFACT_WRITE','artifact_write is not granted; .eif/audit/** is not implementation change scope')
            scopes=change_scopes(policy)
            if scopes and not matches(rel,scopes):
                audit(root,data,'deny','OUT_OF_CHANGE_SCOPE',rel); return deny('OUT_OF_CHANGE_SCOPE',f'path outside accepted change scope: {rel}')
            cls='write' if tool=='Write' else 'delete'
            if not action_allowed(policy,cls):
                audit(root,data,'deny','ACTION_'+cls.upper(),rel); return deny('ACTION_'+cls.upper(),f'{cls} action class not granted')
            if tool=='Write':
                for st in strings(inp):
                    if has_secret(st):
                        audit(root,data,'deny','SECRET_PREWRITE',rel); return deny('SECRET_PREWRITE','high-confidence secret-like literal blocked before file write')

        if tool in {'Read','ReadLints','Grep','Glob','List'} and path:
            scopes=observation_scopes(policy)
            if scopes and not matches(rel,scopes):
                audit(root,data,'deny','OUT_OF_OBSERVATION_SCOPE',rel); return deny('OUT_OF_OBSERVATION_SCOPE',f'read/search outside accepted observation scope: {rel}')
            sensitive=policy.get('sensitive_read_paths') or []
            if matches(rel,sensitive):
                audit(root,data,'deny','SENSITIVE_TOOL_READ',rel); return deny('SENSITIVE_TOOL_READ',f'read/search blocked on sensitive path {rel}')

        if tool=='Shell':
            cmd=str(inp.get('command','')) if isinstance(inp,dict) else ''
            # preToolUse is a backup to beforeShellExecution. Sandbox is telemetry, not a deny input.
            good,code,why,extra=shell_decision(cmd, bool(inp.get('sandbox')) if isinstance(inp,dict) else False, policy)
            if not good:
                audit(root,data,'deny',code, extra=extra); return deny(code,why)
        if tool.startswith('MCP:'):
            d=dict(data); d['tool_name']=tool.removeprefix('MCP:')
            good,code,why=mcp_decision(d,policy,root,roots)
            if not good: audit(root,data,'deny',code); return deny(code,why)
        if tool in {'Fetch', 'WebFetch'}:
            url = inp.get('url')
            if not isinstance(url, str) or not url:
                return deny('HOOK_INPUT_INVALID', 'Fetch requires its destination URL')
            good, code, why = network_destination_allowed(url, policy, roots)
            if not good:
                audit(root, data, 'deny', code)
                return deny(code, why)
        if tool == 'WebSearch' and 'public_read' not in network_classes(policy):
            audit(root, data, 'deny', 'ACTION_NETWORK')
            return deny('ACTION_NETWORK', 'WebSearch requires the public_read research class')
        if tool in {'ListMcpResources', 'FetchMcpResource'}:
            if inp.get('download_path'):
                audit(root, data, 'deny', 'TOOL_UNSUPPORTED')
                return deny('TOOL_UNSUPPORTED', 'MCP resource download needs a verified file-write adapter; inspect the resource without download_path.')
            good, code, why = mcp_decision(data, policy, root, roots)
            if not good:
                audit(root, data, 'deny', code)
                return deny(code, why)

        audit(root,data,'allow',(bextra or {}).get('reason_code', 'TOOL_OK'),rel)
        return out(extra=bextra)

    # stop/subagent/workspace lifecycle are audit surfaces, not blocking budgets unless separately proven.
    audit(root,data,'allow','EVENT_OBSERVED')
    return out()

def verify_closure_cli(arguments):
    """Installed, explicit off-hook command; no hook watchdog or stdin read."""
    global _ACTIVE_ROOT, _ACTIVE_DATA
    root = Path(__file__).resolve().parents[2]
    _ACTIVE_ROOT = root
    _ACTIVE_DATA = {'hook_event_name': 'closureVerify', 'cwd': str(root)}
    lock = None
    try:
        if len(arguments) != 2 or not re.fullmatch('[0-9a-f]{64}', arguments[0]) or not re.fullmatch('[0-9a-f]{32}', arguments[1]):
            raise ValueError('expected a session key and closure request identifier')
        lock = verified_runtime(root)
        state, policy, _, message = load_policy(root)
        if state != 'OK':
            result = False, 'POLICY_INTEGRITY', 'An accepted, valid project policy is required.'
        else:
            ok, message = identity_ok(root, policy)
            result = (support('eif_session').verify_request(root, *arguments) if ok else
                      (False, 'IDENTITY_MISMATCH', message))
    except Exception as exc:
        result = False, 'SESSION_STATE_FAILURE', f'Verifier could not complete: {type(exc).__name__}; inspect runtime integrity and local state.'
    finally:
        if lock is not None:
            lock.__exit__(None, None, None)
    ok, code, message = result
    payload = dict(ok=ok, reason_code=code, decision_kind='harness_fault' if code in CRASH_REASON_CODES else 'policy', message=message)
    logged = write_operator_log(code, message, extra={'closure_verified': ok,
                                'decision_kind': payload['decision_kind'],
                                'elapsed_ms': round((time.perf_counter() - _STARTED) * 1000, 3)})
    if not logged:
        payload['log_delivery'] = 'unconfirmed'
        _stderr_log({'reason_code': 'HOOK_LOG_FAILURE', 'decision_kind': 'harness_fault',
                     'message': 'Closure verifier log delivery unconfirmed; inspect its receipt and JSON result.'})
    wrote = _write_stdout_bytes((json.dumps(payload, ensure_ascii=True) + '\n').encode('ascii'))
    return 0 if ok and wrote else 1


if __name__=='__main__' and len(sys.argv) > 1:
    if sys.argv[1] != '--verify-closure':
        raise SystemExit('Only --verify-closure is supported outside hook mode')
    raise SystemExit(verify_closure_cli(sys.argv[2:]))

if __name__=='__main__':
    try:
        _arm_watchdog()
        rc=main()
    except BrokenPipeError:
        rc=deny('HOOK_INTERNAL_ERROR', 'BrokenPipeError while producing a decision')
    except GuardFault as e:
        rc=deny(e.code, str(e))
    except Exception as e:
        try:
            rc=deny('HOOK_INTERNAL_ERROR', f'{type(e).__name__}: {e}')
        except Exception:
            fallback=(
                '{"permission":"deny","reason_code":"HOOK_EMIT_FAILURE",'
                '"user_message":"HOOK_EMIT_FAILURE: unrecoverable guard crash",'
                '"agent_message":"HOOK_EMIT_FAILURE: unrecoverable guard crash"}\n'
            ).encode('ascii')
            wrote=_write_stdout_bytes(fallback)
            write_operator_log('HOOK_EMIT_FAILURE', f'{type(e).__name__}: {e}', extra={'stdout_wrote': wrote})
            rc=0 if wrote else 1
    try:
        raise SystemExit(0 if rc is None else rc)
    except BrokenPipeError:
        raise SystemExit(1 if rc else 0)

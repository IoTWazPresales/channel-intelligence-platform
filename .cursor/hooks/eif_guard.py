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
- Enforcement profile (policy `enforcement.profile`, Volume 22.10): `strict`
  (default) is unchanged. `lean` denies only B1-B5 (protected database
  writes, destructive local operations and linked trees, secrets publishing
  and protected-branch pushes, control-plane mutation, tool writes outside
  every root) and logs every other heuristic finding as an advisory.
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
import codecs, fnmatch, glob, hashlib, json, math, os, re, stat, subprocess, sys, threading, time, types
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
# A redirect target ends where the shell word ends: `)` closes `$( ... )` and
# `<( ... )`, a backquote closes a substitution. `x=$(cmd 2>/dev/null)` names
# /dev/null, not `/dev/null)`.
REDIRECT_TARGET = re.compile(r'(?:^|[\s;|&])(?:>>?|2>>?)\s*([^\s;|&)`]+)')
QUOTED_PATH = re.compile(r'''['"]([^'"]+)['"]''')
ABS_PATH = re.compile(r'(?:[A-Za-z]:[\\/][^\s;|&"\']+|/(?:etc|tmp|Users|home|var|private)[^\s;|&"\']*)')
# A shell word that is a plain relative path: starts with a path character
# and holds no expansion (`$`, `%`, `~`, `{`, `` ` ``). `/Users` inside
# `apps/UsersWorkspace.tsx` is part of such a word, not the /Users root.
_PLAIN_RELATIVE_WORD = re.compile(r'[A-Za-z0-9_.@+-][^\s;|&"\'$%~{}`()<>=,]*')
_WORD_BREAK = frozenset(' \t\r\n;|&"\'()<>=,`')
# PowerShell environment-drive paths (`$env:LOCALAPPDATA\x`, `${env:X}/y`).
# Their target is set outside the project; they cannot be shown inside a root.
ENV_ROOTED_PATH = re.compile(r'\$\{?env:[A-Za-z_][A-Za-z0-9_()]*\}?[\\/]', re.I)
# UNC and extended-length paths. The boundary keeps `src//pkg/a.py` a relative
# path; `\\server\share`, `//server/share`, `\\?\UNC\...` and `\\.\C:\...` are
# absolute on every host.
_WIN_UNC = re.compile(
    r'(?:^|[\s;|&\'"=])('
    r'(?:\\\\[?]\\(?:UNC\\)?|//\?/(?:UNC/)?|\\\\[.]\\|//\./)[^\s;|&"\']+'
    r'|\\\\[^\s;|&"\']+'
    r'|//[A-Za-z0-9_.$~-]+/[^\s;|&"\']+'
    r')',
    re.IGNORECASE,
)
# Network URLs are destinations governed by network classes, not filesystem
# paths; a scheme is never a drive letter. file: URLs stay in the path scan.
NETWORK_URL = re.compile(r'(?<![A-Za-z0-9+.-])(?!file:)[A-Za-z][A-Za-z0-9+.-]+://[^\s\'"`;|&<>]*', re.I)
NULL_DEVICES = frozenset({'/dev/null', '/dev/stdout', '/dev/stderr', 'nul', '$null'})
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


# Built from code points so no editor/codepage round-trip can corrupt them.
_BOM_CHAR = chr(0xFEFF)
_BOM_CP1252 = chr(0xEF) + chr(0xBB) + chr(0xBF)
_BOM_MARKERS = (_BOM_CHAR, _BOM_CP1252)


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
    # A UTF-8 console code page makes the PowerShell pipe add its own BOM
    # ahead of the codec's, so several BOMs can lead: utf-8-sig removes only
    # the first, leaving U+FEFF. The cp1252 fallback renders BOM bytes as the
    # three characters U+00EF U+00BB U+00BF. A BOM is never JSON content.
    # Escapes keep this independent of this file's own encoding.
    text = text.strip()
    while text.startswith(_BOM_MARKERS):
        text = text[1:] if text[0] == _BOM_CHAR else text[len(_BOM_CP1252):]
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
_OUTSIDE_BOUNDARY = False
_READ_WARNING = None
_TIMINGS = {}
_GIT_CACHE = {}
_RUNTIME_LOCK = None
_DEADLINE = None
# Lean profile: advisory findings of this invocation (logged, never denied),
# and whether the pre-bookkeeping B1-B5 precheck found nothing to block.
_ADVISORIES = []
_LEAN_TIMEOUT_CLEAR = False
# Harness faults that bookkeeping raises when it runs out of the invocation
# deadline (lock waits, git under the session phase, the watchdog itself).
BOOKKEEPING_TIMEOUT_CODES = frozenset({'HOOK_TIMEOUT', 'SESSION_STATE_FAILURE', 'SESSION_GIT_FAILURE',
                                       'IDENTITY_GIT_FAILURE', 'BUDGET_STATE_FAILURE'})


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


def framework_runtime_locator(hook_dir):
    """Find the framework root by marker file, not by a hard-coded parent depth.

    Host installs live at {project}/.cursor/hooks (three parents to the project,
    IndexError at parents[3] on a drive-root host). The reviewed checkout lives
    at runtime/cursor/.cursor/hooks. A fixed parents[N] is correct in only one
    of those layouts and silently wrong in the other.
    """
    hook_dir = Path(hook_dir).resolve()
    source_root = None
    for candidate in hook_dir.parents:
        if (candidate / 'tools' / 'compile_cursor.py').is_file():
            source_root = candidate
            break
    reference = (
        source_root is not None
        and hook_dir == source_root / 'runtime' / 'cursor' / '.cursor' / 'hooks'
    )
    return source_root, reference


def host_project_root(hook_dir):
    """Walk to the EIF host delivery contract, not .git.

    Hosts receive `.cursor/eif-runtime-manifest.json` from write_hook_manifest
    (HOOK_MANIFEST_REL). verified_runtime already requires that file on a host
    copy. .git is not EIF-specific and can be a parent worktree or decoy.
    """
    hook_dir = Path(hook_dir).resolve()
    for candidate in hook_dir.parents:
        if (candidate / '.cursor' / 'eif-runtime-manifest.json').is_file():
            return candidate
    return None


def verified_runtime(root):
    """Hash helper bytes before execution, then lock and verify full inventory."""
    hook_dir = Path(__file__).resolve().parent
    source_root, reference = framework_runtime_locator(hook_dir)
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
    hook_dir = Path(__file__).resolve().parent
    source_root, reference = framework_runtime_locator(hook_dir)
    if reference:
        return source_root
    host = host_project_root(hook_dir)
    if host is not None:
        return host
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
    advisories = list(_ADVISORIES)
    if advisories:
        obj.setdefault('advisories', [a['reason_code'] for a in advisories])
        if permission == 'allow':
            obj.setdefault('enforcement', 'advisory')
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
    retry_admitted = False
    denial_class = None
    if _SUPPORT_READY and _ACTIVE_DATA and permission == 'deny' and reason != 'HOOK_TIMEOUT':
        try:
            # Pre-execution: never debt. The class tells the operator whether
            # repeating the identical action could ever be admitted.
            denial_class = support('eif_session').denial_class(reason)
            retry_admitted = support('eif_session').record_block(_ACTIVE_ROOT, _ACTIVE_DATA, reason, _OUTSIDE_BOUNDARY)
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
        # Lean advisories first, one line each with the code it would have had,
        # so the decision record stays the last line of this invocation.
        advisory_logged = True
        for item in advisories:
            advisory_logged = write_operator_log(item['reason_code'], item['message'], extra={
                'permission': 'allow', 'decision_kind': 'policy',
                'enforcement': item.get('enforcement', 'advisory'),
                'final_permission': obj['permission'], 'final_reason_code': reason,
                **({'grant': item['grant']} if item.get('grant') else {}),
            }) and advisory_logged
        logged = advisory_logged and write_operator_log(reason, message or reason, extra={
            'permission': permission, 'decision_kind': kind,
            'elapsed_ms': round((time.perf_counter() - _STARTED) * 1000, 3),
            'timings_ms': _logged_timings(),
            **({'retry_admitted': bool(retry_admitted)} if permission == 'deny' else {}),
            **({'denial_class': denial_class} if denial_class else {}),
            **{key: obj[key] for key in ('enforcement', 'node', 'risk_class', 'advisories') if key in obj},
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
    global _LEAN_TIMEOUT_CLEAR
    # A decided denial must never be overtaken by a lean timeout allow.
    _LEAN_TIMEOUT_CLEAR = False
    return out('deny', f'{code}: {message}', extra={'reason_code': code})


def _deadline_exhausted(margin=0.25):
    return _DEADLINE is not None and time.perf_counter() >= _DEADLINE - margin


def lean_timeout_allow(code, detail):
    """Lean HOOK_TIMEOUT path: the B1-B5 precheck was clear and bookkeeping
    exhausted the deadline. Allow, flag HOOK_TIMEOUT_ADVISORY, no retry debt."""
    _ADVISORIES.append({'reason_code': 'HOOK_TIMEOUT', 'enforcement': 'advisory',
                        'message': f'{code} during session bookkeeping after a clear lean precheck: {detail}'})
    return out('allow', 'HOOK_TIMEOUT_ADVISORY: bookkeeping exceeded the hook deadline; no lean block '
                        'class matched, so the action is allowed and recorded',
               extra={'reason_code': 'HOOK_TIMEOUT_ADVISORY', 'enforcement': 'advisory'})


def _watchdog_fire():
    """Decision when the watchdog fires; fail closed unless the lean precheck was clear."""
    if _LEAN_TIMEOUT_CLEAR:
        return lean_timeout_allow('HOOK_TIMEOUT', 'watchdog fired')
    return deny('HOOK_TIMEOUT', 'guard did not finish before the hook watchdog; fail-closed')


def _logged_timings():
    """Phase timings; a decision taken mid-phase (HOOK_TIMEOUT) carries the
    counters accumulated so far, so the operator can see where time went."""
    timings = dict(_TIMINGS)
    if _SUPPORT_READY and 'eif_state' in sys.modules and 'session_detail' not in timings:
        try:
            metrics = dict(sys.modules['eif_state'].METRICS)
            if any(metrics.values()):
                timings['partial_detail'] = metrics
        except Exception:
            pass
    return timings


def _reset_session_metrics():
    metrics = support('eif_state').METRICS
    for key in metrics:
        metrics[key] = 0 if key.endswith('_count') else 0.0


def _session_metrics():
    """Where the session phase spent its time: git, lock waits, state writes."""
    return dict(support('eif_state').METRICS)


def _arm_watchdog():
    """Self-deny before the host runtime kills the hook with empty stdout."""
    global _DEADLINE
    sec = watchdog_sec()
    _DEADLINE = time.perf_counter() + sec

    def run():
        if _DONE.wait(sec):
            return
        rc = _watchdog_fire()
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
                                capture_output=True, encoding='utf-8', timeout=remaining_timeout(6.0))
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
        normalize_enforcement_policy(pol.get('enforcement'))
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

# Directory a tool resolves a relative path against: the session's own tool cwd
# (the Claude Code adapter passes eif_tool_cwd) or the selected project root,
# never this hook process's cwd. Set once per hook invocation in _main.
_TOOL_BASE = None


def _looks_windows_path(text):
    return bool(re.match(r'^(?:[A-Za-z]:[\\/]|\\\\|//)', text.lstrip()))


def normalize_tool_path_text(text, windows=None):
    """One host spelling of a tool path, before filesystem resolution.

    Strips leading BOM/CRLF, `file:` URIs, the ``\\\\?\\`` prefix and the
    VS Code ``/c:/repo`` form. ``windows`` defaults to this process; tests pass
    True so Windows spellings are checked on any host. PowerShell 5 pipes
    CRLF and a UTF-8 BOM onto paths the same way they do onto hook JSON.
    """
    if not isinstance(text, str):
        return ''
    text = text.strip().lstrip('\ufeff')
    if windows is None:
        windows = os.name == 'nt'
    if text[:5].lower() == 'file:':
        text = file_url_to_path(text, windows=windows) or ''
    if not text:
        return ''
    if windows:
        # Prefixes are recognized with either slash. `\\?\UNC\`, `//?/UNC/`,
        # `\\.\C:\` and `//server/share` are one path; `/c:/repo` stays a drive.
        slashified = text.replace('/', '\\')
        upper = slashified.upper()
        if upper.startswith('\\\\?\\UNC\\') or upper.startswith('\\\\.\\UNC\\'):
            text = '\\\\' + slashified[8:]
        elif upper.startswith('\\\\?\\') or upper.startswith('\\\\.\\'):
            text = slashified[4:]
        elif text.startswith('//'):
            text = '\\\\' + slashified[2:]
        if re.match(r'[\\/][A-Za-z]:[\\/]', text):
            text = text[1:]
    return text


def _fold_windows_parts(parts, *, climb_is_escape):
    """Collapse `.` and `..`. A climb with an empty stack is an escape when asked.

    Drive roots ignore a leftover `..` (it cannot leave the drive). A UNC
    share must not: `..` above the share is how `ntpath.normpath` hides a
    traversal inside the share.
    """
    folded, original = [], []
    for part in parts:
        if part in ('', '.'):
            continue
        if part == '..':
            if folded:
                folded.pop()
                original.pop()
            elif climb_is_escape:
                return [], [], True
            continue
        folded.append(part.casefold())
        original.append(part)
    return folded, original, False


def _windows_parts(text):
    """(casefolded drive or UNC share anchor, casefolded parts, original parts).

    The UNC anchor is ``\\\\server\\share`` and stays in the prefix, so lexical
    normalisation cannot pop the server or the share. Components under the
    share still collapse (`foo\\..\\src` is `src`). A `..` that would climb
    above that anchor is an escape: the anchor comes back empty and containment
    fails. Windows ``normpath`` / ``Path.resolve`` drop that `..` and leave the
    path looking inside the share; callers must reject the climb before they
    resolve.
    """
    text = normalize_tool_path_text(text, windows=True).replace('/', '\\')
    # Collapse repeated separators without turning a UNC root into a drive path.
    unc = text.startswith('\\\\')
    body = text[2:] if unc else text
    body = re.sub(r'\\+', r'\\', body).lstrip('\\')
    text = ('\\\\' + body) if unc else body
    if re.match(r'^[A-Za-z]:(?:\\|$)', text):
        folded, original, _escaped = _fold_windows_parts(text[2:].split('\\'), climb_is_escape=False)
        return text[:2].casefold(), folded, original
    if text.startswith('\\\\'):
        pieces = body.split('\\') if body else []
        server = pieces[0] if pieces else ''
        share = pieces[1] if len(pieces) > 1 else ''
        if not server or not share or server in {'.', '..'} or share in {'.', '..'}:
            return '', [], []
        folded, original, escaped = _fold_windows_parts(pieces[2:], climb_is_escape=True)
        if escaped:
            return '', [], []
        return '\\\\' + server.casefold() + '\\' + share.casefold(), folded, original
    folded, original, _escaped = _fold_windows_parts(body.split('\\') if body else [], climb_is_escape=False)
    return '', folded, original


def _unc_climbs_above_anchor(text):
    """True when a UNC spelling climbs above its ``\\\\server\\share`` anchor.

    Judged on the original spelling, before ``Path.resolve`` or ``normpath``.
    """
    raw = normalize_tool_path_text(str(text), windows=True)
    if not raw.startswith('\\\\'):
        return False
    prefix, _folded, _original = _windows_parts(raw)
    return not prefix


def _windows_relative(real, root):
    """Repo-relative POSIX path, or None. Drive-letter case is not a new file."""
    real_drive, real_parts, real_orig = _windows_parts(str(real))
    root_drive, root_parts, _root_orig = _windows_parts(str(root))
    if not real_drive or real_drive != root_drive or real_parts[:len(root_parts)] != root_parts:
        return None
    if len(real_parts) == len(root_parts):
        return '.'
    return '/'.join(real_orig[len(root_parts):])


def relative_to_root(real, root):
    """POSIX path of `real` inside `root`, else None.

    `Path.relative_to` is case-sensitive on Windows, so a new file whose drive
    letter differs from `allowed_roots` (`c:\\repo\\new.py` vs `C:\\repo`) was
    FOREIGN_PATH. Extended-length prefixes and `file:` URIs are the same file.
    A junction or symlink is judged after resolution, so the lexical fallback
    cannot treat the link spelling as inside the root when its target is not.
    """
    on_windows = os.name == 'nt'
    real_text = normalize_tool_path_text(str(real), windows=on_windows)
    root_text = normalize_tool_path_text(str(root), windows=on_windows)
    windowsish = on_windows or _looks_windows_path(real_text) or _looks_windows_path(root_text)
    if not windowsish:
        try:
            real_p = Path(real_text)
            root_p = Path(root_text)
            if not real_p.is_absolute():
                real_p = Path(_TOOL_BASE if _TOOL_BASE is not None else Path.cwd()) / real_p
            return str(real_p.resolve().relative_to(root_p.resolve())).replace('\\', '/')
        except Exception:
            return None
    if on_windows:
        # `\\server\share\..\other` normpaths to `\\server\share\other` and then
        # looks contained. Reject the climb on the spelling we were given.
        if _unc_climbs_above_anchor(real) or _unc_climbs_above_anchor(root):
            return None
        try:
            real_p = Path(normalize_tool_path_text(str(real), windows=True))
            root_p = Path(normalize_tool_path_text(str(root), windows=True))
            if not real_p.is_absolute():
                real_p = Path(_TOOL_BASE if _TOOL_BASE is not None else Path.cwd()) / real_p
            resolved = real_p.resolve()
            root_resolved = root_p.resolve()
        except Exception:
            # Resolution itself failed (a missing UNC host, for example). The
            # spelling is all we have; do not pretend a later resolve succeeded.
            return _windows_relative(real, root)
        try:
            return str(resolved.relative_to(root_resolved)).replace('\\', '/')
        except ValueError:
            # Case-only mismatch of the same file, or a junction/symlink whose
            # target left the root. Compare the resolved paths: falling back to
            # the link's own spelling would call an outside target in-project.
            return _windows_relative(resolved, root_resolved)
    return _windows_relative(real, root)


def tool_path_identity(path, base=None):
    """The one absolute, symlink-resolved target a tool gives `path`, else None.

    Host spellings of the same file are one identity: file: URIs, the
    VS Code/Cursor `/c:/repo/x` form and the `\\\\?\\C:\\` long-path prefix.
    Spellings whose target depends on who expands them (`~`, drive-relative
    `D:x`) have no single identity and stay unresolved (fail closed).
    """
    if not isinstance(path, str) or not path.strip():
        return None
    # Before resolve: a UNC `..` above the share would otherwise collapse into it.
    if _unc_climbs_above_anchor(path):
        return None
    text = normalize_tool_path_text(path, windows=os.name == 'nt')
    # `~` and `D:x` depend on who expands them. Fail closed rather than guess.
    if not text or text == '~' or text.startswith(('~/', '~\\')) or re.match(r'^[A-Za-z]:(?![\\/])', text):
        return None
    try:
        candidate = Path(text)
        if candidate.drive and not candidate.root:
            return None
        if not candidate.is_absolute():
            anchor = base if base is not None else (_TOOL_BASE if _TOOL_BASE is not None else Path.cwd())
            candidate = Path(anchor) / candidate
        return candidate.resolve()
    except Exception:
        return None


def tool_base(data, root):
    """Directory a relative tool path resolves against.

    Prefer the session tool directory the Claude Code adapter passes as
    `eif_tool_cwd` when that directory exists inside the selected project
    root. Otherwise use the selected project root. Never this hook process's
    cwd: Cursor launches the hook from outside the workspace, and a relative
    in-project path then resolved as FOREIGN_PATH.
    """
    try:
        fallback = Path(root).resolve()
    except Exception:
        fallback = Path(os.getcwd()).resolve()
    raw = data.get('eif_tool_cwd') if isinstance(data, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        return fallback
    candidate = tool_path_identity(raw, base=fallback)
    if candidate is None or not candidate.is_dir() or relative_to_root(candidate, fallback) is None:
        return fallback
    return candidate


def resolve_path(path, roots, base=None):
    if not path: return None,None
    real=tool_path_identity(path, base)
    if real is None: return None,None
    for r in roots:
        rel = relative_to_root(real, r)
        if rel is not None:
            return r, rel
    return None,None

# Filename globs that name a secret. Folded on every OS: fnmatch folds case
# only on Windows, so ``SECRET`` missed ``**/*secret*`` on Linux. Scope and
# protected-path globs stay case-sensitive on POSIX and fold on Windows,
# which is what fnmatch already did.
_CASEFOLD_GLOBS = re.compile(r'secret|credential|\.env|\.pem', re.I)


def matches(rel, patterns):
    if rel is None: return False
    rel=rel.replace('\\','/')
    for pattern in patterns or []:
        raw=str(pattern).replace('\\','/')
        left, right = (rel.casefold(), raw.casefold()) if os.name == 'nt' or _CASEFOLD_GLOBS.search(raw) else (rel, raw)
        if fnmatch.fnmatchcase(left, right) or fnmatch.fnmatchcase('/'+left, '/'+right):
            return True
    return False

# Committed placeholders that document variable names, never values.
ENV_TEMPLATE_NAMES = frozenset({'.env.example', '.env.sample', '.env.template'})

def _env_file_name(name):
    name = name.lower()
    return name == '.env' or name.startswith('.env.')

def sensitive_read(rel, patterns):
    """Policy sensitive paths, plus .env / .env.* at any depth.

    A bare policy pattern such as `.env` matches only at the root (see
    matches()), which left nested env files such as apps/api/.env readable.
    Env templates stay readable unless a non-env pattern also names them.
    """
    if rel is None: return False
    name = rel.replace('\\','/').rsplit('/',1)[-1]
    if name.lower() in ENV_TEMPLATE_NAMES:
        return matches(rel, [p for p in (patterns or []) if not _env_file_name(str(p).replace('\\','/').rsplit('/',1)[-1])])
    return _env_file_name(name) or matches(rel, patterns)

def tool_path(inp):
    if not isinstance(inp,dict): return None
    for k in ['file_path','path','target_file','target_path','directory']:
        if isinstance(inp.get(k),str) and inp[k].strip(): return inp[k]
    return None


def target_outside_roots(data, roots):
    """A path-bound request aimed outside every declared root; never a grant."""
    event = data.get('hook_event_name')
    path = (data.get('file_path') if event == 'beforeReadFile' else
            tool_path(data.get('tool_input')) if event == 'preToolUse' else None)
    return isinstance(path, str) and bool(path.strip()) and resolve_path(path, roots)[0] is None


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

IDENTITY_CACHE_REL = '.eif/runtime-budget/identity-verified.json'
GIT_REPO_ENV = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR')

def _repo_state(repo: Path):
    """File-only inputs that fix identity facts, or None to verify with git.

    A commit id fixes its whole history (so the root commit), config fixes
    the remotes, and a checkout with its own .git is its own top level.
    """
    try:
        if any(os.environ.get(name) for name in GIT_REPO_ENV):
            return None
        repo = repo.resolve()
        gitdir = repo / '.git'
        if gitdir.is_file():
            text = gitdir.read_text(encoding='utf-8').strip()
            if not text.startswith('gitdir:'):
                return None
            gitdir = (repo / text[7:].strip()).resolve()
        common = gitdir
        if (gitdir / 'commondir').is_file():
            common = (gitdir / (gitdir / 'commondir').read_text(encoding='utf-8').strip()).resolve()
        sha = (gitdir / 'HEAD').read_text(encoding='utf-8').strip()
        if sha.startswith('ref: '):
            ref = sha[5:].strip()
            loose = common / ref
            sha = loose.read_text(encoding='utf-8').strip() if loose.is_file() else ''
            if not sha and (common / 'packed-refs').is_file():
                for line in (common / 'packed-refs').read_text(encoding='utf-8').splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1] == ref:
                        sha = parts[0]
                        break
        if not re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', sha):
            return None
        config = (common / 'config').stat()
        return [str(repo), sha, config.st_mtime_ns, config.st_size]
    except (OSError, UnicodeError, ValueError):
        return None

def _identity_cache_key(root: Path, policy):
    """Key over everything but HEAD, plus each repository's HEAD commit id."""
    ident = policy.get('identity') or {}
    repos = [root] + [Path(a.get('allowed_root') or '') for a in ident.get('repository_anchors') or []]
    states = [_repo_state(repo) for repo in repos]
    if any(state is None for state in states):
        return None, None, None
    stable = [[state[0], state[2], state[3]] for state in states]
    key = hashlib.sha256(json.dumps([ident, stable], sort_keys=True, default=str).encode('utf-8')).hexdigest()
    return key, [state[1] for state in states], [state[0] for state in states]

def _identity_reusable(cached, key, heads, repos):
    if not isinstance(cached, dict) or cached.get('version') != 2 or cached.get('key') != key:
        return False
    before = cached.get('heads')
    if not isinstance(before, list) or len(before) != len(heads):
        return False
    for repo, old, new in zip(repos, before, heads):
        if old == new:
            continue
        # A commit id fixes its history, so HEAD's root commit changes only if
        # the new commits bring in another root. Walk just old..new.
        try:
            if git(Path(repo), 'rev-list', '--max-parents=0', f'{old}..{new}'):
                return False
        except GuardFault:
            return False  # Rewritten or pruned history: verify in full.
    return True

def _read_identity_cache(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        return None

def identity_ok(root: Path, policy):
    """Reuse a verified identity while the declared identity, checkout path and
    git config are unchanged and no new root commit has appeared since the
    verified HEAD. Concurrent cold hooks verify once. Unreadable inputs
    re-verify with git; failures are never stored."""
    key, heads, repos = _identity_cache_key(root, policy)
    if not key:
        return _identity_check(root, policy)
    state = support('eif_state')
    path = state.contained(root, IDENTITY_CACHE_REL)
    cached = _read_identity_cache(path)
    if _identity_reusable(cached, key, heads, repos):
        if cached.get('heads') != heads:
            _store_identity(state, path, key, heads)
        return True, 'identity anchors matched'
    try:
        lock = state.file_lock(path.with_suffix('.lock'), timeout=6.0)
        lock.__enter__()
    except (OSError, TimeoutError):
        lock = None  # Verify without waiting; reuse is an optimisation.
    try:
        cached = _read_identity_cache(path)
        if lock is not None and _identity_reusable(cached, key, heads, repos):
            return True, 'identity anchors matched'
        ok, msg = _identity_check(root, policy)
        if ok:
            _store_identity(state, path, key, heads)
        return ok, msg
    finally:
        if lock is not None:
            lock.__exit__(None, None, None)

def _store_identity(state, path, key, heads):
    try:
        state.atomic_json(path, {'version': 2, 'key': key, 'heads': heads})
    except (OSError, ValueError):
        pass  # Reuse is an optimisation; verification already completed.

def _identity_check(root: Path, policy):
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
        if _ADVISORIES:
            rec['advisories']=[a['reason_code'] for a in _ADVISORIES]
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
    if data.get('hook_event_name') not in {'preToolUse', 'beforeShellExecution', 'beforeMCPExecution'}:
        return True, '', None
    try:
        # Never use the shared anonymous pool; identity fallback must match sessions.
        conv = support('eif_session').conversation(data)
        if conv == 'unknown':
            # Reads and the closure verifier only: closure-gate git recovery
            # (add/commit/push) is a mutation and needs a stable identity.
            if _READ_ONLY or support('eif_session').verifier_action(data):
                return True, '', None
            return False, 'IDENTITY_TOOL: stable session identity required for mutations and scoped budget', None
        if not re.fullmatch(r'[A-Za-z0-9_-][A-Za-z0-9_.-]{0,119}', conv):
            conv = hashlib.sha256(conv.encode('utf-8')).hexdigest()
        directory = _budget_dir(root, policy)
        with support('eif_state').file_lock(directory / (conv + '.lock')):
            return _budget_ok_locked(root, data, policy, directory / (conv + '.json'))
    except Exception as exc:
        return False, f'BUDGET_STATE_FAILURE: {type(exc).__name__}: {exc}', None


# A failed shell command creates closure debt unless it is PROVEN read-only.
# Any character that can substitute, chain, redirect, expand, glob or escape in
# bash, PowerShell or cmd.exe withdraws the proof: $( ) and backticks run
# commands; PowerShell evaluates ( ), @( ) and { }; cmd.exe expands %VAR% and
# !VAR! and ^ escapes; a glob can expand to a file named like an option.
SHELL_READONLY_UNSAFE = re.compile(r'[$`;&|<>(){}@^%!*?\[\]\r\n]')
SHELL_READONLY_GIT = frozenset({'status', 'diff', 'log', 'show', 'rev-parse', 'ls-files'})
# Options that write files, edit sources, install, publish or run watchers.
# Matched on the option name, case-insensitively, after shell unquoting.
SHELL_READONLY_WRITERS = {
    'git': (frozenset({'output', 'output-directory', 'ext-diff', 'textconv'}), ('output',), ()),
    'pytest': (frozenset({'junitxml', 'junit-xml', 'resultlog', 'result-log', 'report-log', 'html',
                          'self-contained-html', 'basetemp', 'pastebin', 'debug', 'o', 'override-ini',
                          'log-file', 'cache-clear', 'nunit-xml', 'nunitxml'}),
               ('cov', 'json-report'), ()),
    'mypy': (frozenset({'install-types', 'junit-xml'}), (), ('-report',)),
    'ruff': (frozenset({'fix', 'fix-only', 'unsafe-fixes', 'add-noqa', 'output-file', 'o', 'watch', 'w'}), (), ()),
    'tsc': (frozenset({'build', 'b', 'init', 'watch', 'w', 'incremental', 'tsbuildinfofile',
                       'generatetrace', 'composite', 'emitdeclarationonly'}), ('out', 'declarationdir'), ()),
}
# A ruff `--config` value that turns fixes on, or that we cannot prove does not.
# `--no-fix` disables `fix` from config (including a config file). It does not
# disable `--unsafe-fixes` or an inline `unsafe-fixes = true`.
_RUFF_CONFIG_ASSIGNMENT = re.compile(
    r"""^\s*(?:\[(?P<table>[A-Za-z0-9_.-]+)\]\s*)?
        (?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(?P<value>.*?)\s*(?:\#.*)?$""",
    re.VERBOSE,
)
_RUFF_FIX_OFF = frozenset({'false', 'off', 'no', '0'})


def _program_name(token):
    name = token.casefold()
    return name[:-4] if name.endswith('.exe') else name


def _writer_option(kind, token):
    if not token.startswith('-') or token in {'-', '--'}:
        return False
    names, prefixes, suffixes = SHELL_READONLY_WRITERS[kind]
    name = token.lstrip('-').split('=', 1)[0].casefold()
    # -o<value> or a short-flag cluster: the first letter is the option.
    if not token.startswith('--') and name[:1] in names:
        return True
    return (name in names or (bool(prefixes) and name.startswith(prefixes))
            or (bool(suffixes) and name.endswith(suffixes)))


def _dashdash_option(token):
    """(name, inline value or None) for a `--name` or `--name=value` token."""
    if not isinstance(token, str) or not token.startswith('--') or token == '--':
        return None, None
    name, sep, value = token[2:].partition('=')
    return name.casefold(), (value if sep else None)


def _unquote_toml(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def _ruff_config_class(value):
    """How a ruff `--config` value affects fixes: safe, fix, unsafe, or unknown.

    `fix` is cancelled by `--no-fix`. `unsafe` is an unsafe-fixes override and
    is mutating on its own. `unknown` is a config path, `extend`, or a value
    we cannot parse: it can carry `fix = true`, so it is mutating unless
    `--no-fix` is also present (a config file cannot add `--add-noqa` or
    `--output-file`).
    """
    text = str(value or '').strip()
    if not text or '=' not in text:
        return 'unknown'
    match = _RUFF_CONFIG_ASSIGNMENT.match(text)
    if not match:
        return 'unknown'
    key = match.group('key').casefold().replace('_', '-')
    leaf = key.split('.')[-1]
    raw = _unquote_toml(match.group('value')).casefold()
    if leaf == 'unsafe-fixes' or key == 'unsafe-fixes':
        return 'safe' if raw in _RUFF_FIX_OFF else 'unsafe'
    if leaf == 'fix' or key == 'fix':
        return 'safe' if raw in _RUFF_FIX_OFF else 'fix'
    if leaf == 'extend' or key == 'extend':
        return 'unknown'
    return 'safe'


def _ruff_args_may_mutate(args):
    """True when ruff check options or config can rewrite source or write output."""
    no_fix = False
    fix_on = False
    unknown = False
    i = 0
    while i < len(args):
        token = args[i]
        if token == '--':
            break
        if _writer_option('ruff', token):
            return True
        name, inline = _dashdash_option(token)
        if name == 'no-fix':
            no_fix = True
        elif name == 'config':
            if inline is None:
                if i + 1 < len(args) and not str(args[i + 1]).startswith('-'):
                    kind = _ruff_config_class(args[i + 1])
                    i += 1
                else:
                    kind = 'unknown'
            else:
                kind = _ruff_config_class(inline)
            if kind == 'unsafe':
                return True
            if kind == 'fix':
                fix_on = True
            elif kind == 'unknown':
                unknown = True
        i += 1
    return (fix_on or unknown) and not no_fix


def _shell_words(cmd, escapes):
    """POSIX word split; escapes=False keeps backslashes literal (PowerShell, cmd)."""
    import shlex
    lexer = shlex.shlex(cmd, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ''
    if not escapes:
        lexer.escape = ''
    return list(lexer)


def shell_failure_may_mutate(data):
    """True unless the command is proven read-only (then its failure is no debt).

    Proven read-only: exactly pytest / python -m pytest, mypy, ruff check,
    tsc --noEmit, or git with only -C <dir> / --no-pager / --no-optional-locks
    before status|diff|log|show|rev-parse|ls-files; no unsafe shell character
    and no writer option. Ruff `--config` that sets `fix` or `unsafe-fixes`,
    or a config path / `extend` we cannot prove leaves fixes off, is a writer
    (`--no-fix` cancels `fix` and a config file, not `unsafe-fixes`). The words
    are checked as bash would split them and as PowerShell/cmd would (backslash
    literal); both must be read-only. Test code that pytest itself runs is
    outside this proof (documented limitation): a failing test run is a
    verification result, not a mutation.
    """
    _, inp=support('eif_session').action(data)
    if not isinstance(inp,dict) or not isinstance(inp.get('command'),str): return True
    cmd=inp['command'].strip()
    # The exact closure verifier writes only EIF session state. Its refusal
    # (push required, superseded request) is a closure answer, not a partial
    # project mutation; as debt it would block the closure it reports on.
    if support('eif_session').verifier_command(cmd):
        return False
    if not cmd or SHELL_READONLY_UNSAFE.search(cmd):
        return True
    for escapes in (True, False):
        try:
            tokens=_shell_words(cmd, escapes)
        except ValueError:
            return True
        if _words_may_mutate(tokens):
            return True
    return False


def _words_may_mutate(tokens):
    if not tokens:
        return True
    program=_program_name(tokens[0])
    if program in {'py', 'python', 'python3'}:
        rest=tokens[1:]
        if rest[:1]==['-B']:
            rest=rest[1:]
        if rest[:2]!=['-m', 'pytest']:
            return True
        kind, args='pytest', rest[2:]
    elif program in {'pytest', 'py.test'}:
        kind, args='pytest', tokens[1:]
    elif program=='mypy':
        kind, args='mypy', tokens[1:]
    elif program=='ruff':
        if tokens[1:2]!=['check']:
            return True
        return _ruff_args_may_mutate(tokens[2:])
    elif program=='tsc':
        lowered=[t.casefold() for t in tokens[1:]]
        if '--noemit' not in lowered:
            return True
        after=lowered[lowered.index('--noemit')+1:lowered.index('--noemit')+2]
        if after in (['false'], ['true']) or any(t.startswith('--noemit=') for t in lowered):
            return True
        kind, args='tsc', tokens[1:]
    elif program=='git':
        rest=tokens[1:]
        while rest and rest[0] in {'-C', '--no-pager', '--no-optional-locks'}:
            # Case-sensitive: lowercase -c sets config (core.pager, alias.*,
            # core.fsmonitor ...) and can run arbitrary commands.
            if rest[0]=='-C':
                if len(rest)<2 or rest[1].startswith('-'):
                    return True
                rest=rest[2:]
            else:
                rest=rest[1:]
        if not rest or rest[0] not in SHELL_READONLY_GIT:
            return True
        kind, args='git', rest[1:]
    else:
        return True
    return any(_writer_option(kind, token) for token in args)


# A name is read-only only when every token is in this vocabulary. An unknown
# verb or noun (rollback, restart, invoke, ...) is mutating. Absence of a
# known write word is not proof of a read.
MCP_READ_VERBS = frozenset('''get list read search find describe view show fetch inspect
lookup count snapshot screenshot'''.split())
MCP_READ_CONNECTORS = frozenset('and or of the a an for to from by with in on'.split())
# Nouns already proven not to be writes. `settings` is not `set`; `assets` is
# not a stem of a write word. Anything else is unknown and therefore mutating.
MCP_READ_NOUNS = frozenset('''migrations files file symbol user table page settings
input offset assets commits'''.split())
MCP_READ_VOCABULARY = MCP_READ_VERBS | MCP_READ_CONNECTORS | MCP_READ_NOUNS
MCP_WRITE_WORDS = frozenset('''create update delete remove set write put post patch apply
run exec execute insert upsert drop deploy merge push pull reset restore pause resume rebase
migrate migration commit add edit modify rename move copy send publish upload download
install uninstall enable disable start stop kill cancel grant revoke submit approve close
save import export sync clear purge archive invite assign transfer pay charge refund
generate build compile mutate replace overwrite append truncate unlink erase wipe destroy
rewrite touch mkdir chmod chown format amend alter setup'''.split())
# Longer stems also match inside a concatenated name (`searchreplace`).
# `set`, `put` and `move` stay whole words: `settings`, `input`, `output`,
# `offset` and `assets` are not writes.
MCP_MUTATING_STEMS = (
    'replace', 'write', 'edit', 'update', 'delete', 'create', 'patch', 'rename',
    'overwrite', 'append', 'truncate', 'upsert', 'unlink', 'mutate', 'modify',
    'insert', 'destroy',
)


def _mcp_name_words(name):
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(name or '').removeprefix('MCP:'))
    return [w for w in re.split(r'[^a-z0-9]+', name.casefold()) if w]


def _mcp_name_mutates(words):
    if MCP_WRITE_WORDS.intersection(words):
        return True
    compact = ''.join(words)
    return any(stem in compact for stem in MCP_MUTATING_STEMS)


def mcp_failure_may_mutate(data):
    """True unless the MCP tool is proven read-only (then its failure is no debt).

    Review/observe browser tools (CURSOR_REVIEW_TOOLS, browser_tabs list only,
    observe-kind browser_*) stay as classified. Every other name is read-only
    only when each token is in MCP_READ_VOCABULARY. An unknown verb or token
    (`search_rollback`, `find_and_restart`, `get_and_invoke`) is a mutation.
    A write word or stem (`replace`, `edit`, `update`, `delete`, `create`,
    `set`, `put`, `patch`, `move`, `rename`, and similar) is a mutation even
    when the name starts with `search` or `find`. `get_settings` and
    `list_assets` stay read-only. A destructive-looking payload never is.
    """
    tool = support('eif_session').action(data)[0].removeprefix('MCP:')
    raw = data.get('tool_input')
    text = raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True, default=str)
    if not tool or DESTRUCTIVE_INPUT.search(text or ''):
        return True
    inp = mcp_tool_input_object(data)
    if tool == 'browser_tabs':
        return not (isinstance(inp, dict) and inp.get('action', 'list') == 'list')
    if tool in CURSOR_REVIEW_TOOLS:
        return False
    if is_browser_tool(tool):
        return browser_action_kind(tool) != 'observe'
    words = _mcp_name_words(tool)
    if not words or any(word not in MCP_READ_VOCABULARY for word in words) or _mcp_name_mutates(words):
        return True
    return False


def record_executed_failure(root, data):
    """True when an executed mutating failure was recorded as unresolved."""
    data = dict(data)
    tool = support('eif_session').action(data)[0]
    if tool == 'Shell':
        data['eif_executed_mutation'] = (shell_failure_may_mutate(data)
            and not support('eif_session').static_powershell_syntax_failure(data))
    elif tool.startswith('MCP:'):
        data['eif_executed_mutation'] = mcp_failure_may_mutate(data)
    return bool(support('eif_session').executed_failure(root, data))


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
        return False,(f'NO_PROGRESS: repeated mutating action {fp} x{state["repeat_mut"]}; this path is '
                      'capped for the rest of this execution burst. Retrying the same action cannot succeed: '
                      'mutate a different path, or record programme progress to renew the burst.'),None
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

ENFORCEMENT_PROFILES = ('strict', 'lean')
_ENFORCEMENT_LIST_KEYS = ('protected_databases', 'protected_branches', 'protected_database_flags')


def normalize_enforcement_policy(raw):
    """`enforcement` block: profile strict (default) or lean, plus lean's lists.

    Absent means strict. Anything malformed is a policy error, never a silent
    fallback to a weaker profile.
    """
    if raw in (None, {}):
        return {'profile': 'strict', **{key: [] for key in _ENFORCEMENT_LIST_KEYS}}
    if not isinstance(raw, dict):
        raise ValueError('enforcement must be an object')
    unknown = set(raw) - {'profile', *_ENFORCEMENT_LIST_KEYS}
    if unknown:
        raise ValueError(f'unknown enforcement keys: {sorted(unknown)}')
    profile = raw.get('profile', 'strict')
    if profile not in ENFORCEMENT_PROFILES:
        raise ValueError(f'unsupported enforcement.profile {profile!r}; use strict or lean')
    out = {'profile': profile}
    for key in _ENFORCEMENT_LIST_KEYS:
        value = raw.get(key, [])
        if value is None:
            value = []
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            raise ValueError(f'enforcement.{key} must be a list of nonempty strings')
        out[key] = [x.strip() for x in value]
    return out


def enforcement(policy):
    try:
        return normalize_enforcement_policy((policy or {}).get('enforcement'))
    except ValueError:
        # load_policy already rejected this; never weaken on a malformed block.
        return normalize_enforcement_policy(None)


def lean_profile(policy):
    return enforcement(policy)['profile'] == 'lean'


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
    return any(relative_to_root(path, r) is not None for r in (roots or []))

def _policy_root_paths(policy):
    out=[]
    for x in (policy or {}).get('allowed_roots') or []:
        try: out.append(Path(x).resolve())
        except Exception: pass
    return out

def file_url_to_path(url, windows=None):
    if windows is None:
        windows = os.name == 'nt'
    parsed=urlparse(str(url or ''))
    if parsed.scheme.lower()!='file': return None
    path=unquote(parsed.path or '')
    if windows and parsed.netloc:
        # `file://localhost/C:/repo/a.py` is a drive path. A real UNC host stays
        # `\\host\share`, including `file://localhost/share/a.py`.
        if parsed.netloc.lower() in {'localhost', '127.0.0.1'} and re.match(r'[\\/][A-Za-z]:', path):
            path = path.lstrip('/')
            return path or None
        return '\\\\'+parsed.netloc+path.replace('/','\\')
    if windows and path.startswith('/') and len(path)>=3 and path[2]==':':
        path=path.lstrip('/')
    return path or None

def _path_under_root(path: Path, root: Path) -> bool:
    return relative_to_root(path, root) is not None

def _path_candidates(cmd: str):
    found=[]
    for m in REDIRECT_TARGET.finditer(cmd):
        found.append(m.group(1).strip('\'"'))
    for m in QUOTED_PATH.finditer(cmd):
        found.append(m.group(1))
    for m in ABS_PATH.finditer(cmd):
        if m.group(0).startswith('/') and _inside_plain_relative_word(cmd, m.start()):
            # The relative word itself is scanned below like any relative path.
            continue
        found.append(m.group(0))
    for tok in re.findall(r'(?:\.\./)+[^\s;|&"\']+', cmd):
        found.append(tok)
    # A drive letter starts a word. In `HEAD:docs/a.md` or `main:docs/a.md`
    # the letter before the colon ends a git revision; it is not drive D: or N:.
    for m in re.finditer(r'(?:(?<![A-Za-z0-9_.-])[A-Za-z]:)?(?:\.{1,2}[\\/]|[A-Za-z0-9_.-]+[\\/])+[A-Za-z0-9_.-]+', cmd):
        tok = m.group(0).replace('\\', '/')
        start = m.start()
        # The token regex does not consume a leading slash, so `/workspace/x`
        # arrived as the relative token `workspace/x` and skipped the
        # outside-root check. Keep that slash. A second slash stays a UNC root.
        # Keep a UNC root (`//server` or `\\server`) only when it begins a
        # token. `src//dir/a.py` is an empty segment, not a UNC path.
        if start >= 2 and cmd[start - 2:start] in {'//', '\\\\'}:
            if start == 2 or cmd[start - 3] in ' \t;|&\'"=':
                tok = cmd[start - 2:start] + tok
        elif start > 0 and cmd[start - 1] == '/' and not tok.startswith('/'):
            tok = '/' + tok
        found.append(tok)
    # `\\server\share\file` and `\\?\UNC\server\share\file` are absolute. The
    # token regex above drops a leading backslash, so the UNC root is kept only
    # when it is its own match. A boundary stops `src//dir/a.py` matching `//`.
    for m in _WIN_UNC.finditer(cmd):
        found.append(m.group(1))
    return found

def _inside_plain_relative_word(cmd: str, index: int) -> bool:
    """True when cmd[index] continues a shell word that is a plain relative path."""
    if index <= 0 or cmd[index - 1] in _WORD_BREAK:
        return False
    start = index
    while start > 0 and cmd[start - 1] not in _WORD_BREAK:
        start -= 1
    end = index
    while end < len(cmd) and cmd[end] not in _WORD_BREAK:
        end += 1
    word = cmd[start:end]
    # `rev:/abs` or `X:\\abs` carries an absolute part; only `rev:rel` stays plain.
    return _PLAIN_RELATIVE_WORD.fullmatch(word) is not None and re.search(r':[\\/]', word) is None

def _quote_segments(cmd: str):
    """[(text, quoted, start, end)] with quote characters excluded from text.

    None when quoting is unbalanced or a backslash precedes a quote: shells
    disagree on those (POSIX escapes, PowerShell does not), so callers must
    fall back to treating the whole text as unquoted.
    """
    if re.search(r'\\[\'"]', cmd):
        return None
    segs=[]; i=0; n=len(cmd)
    while i < n:
        if cmd[i] in '\'"':
            q=cmd[i]; j=cmd.find(q, i+1)
            if j < 0:
                return None
            segs.append((cmd[i+1:j], True, i, j+1)); i=j+1
        else:
            j=i
            while j < n and cmd[j] not in '\'"':
                j+=1
            segs.append((cmd[i:j], False, i, j)); i=j
    return segs

GREP_COMMANDS = frozenset({'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack', 'select-string', 'sls'})
GREP_PATTERN_OPTIONS = frozenset({'-e', '--regexp', '-pattern'})
GREP_NO_VALUE_SHORT = frozenset('EFGPirRnlLcovwxsqHhIaz')
GREP_NO_VALUE_LONG = frozenset({
    '--extended-regexp', '--fixed-strings', '--basic-regexp', '--perl-regexp', '--ignore-case',
    '--smart-case', '--case-sensitive', '--recursive', '--line-number', '--files-with-matches',
    '--files-without-match', '--count', '--only-matching', '--invert-match', '--word-regexp',
    '--line-regexp', '--no-messages', '--quiet', '--silent', '--with-filename', '--no-filename',
    '--hidden', '--no-ignore', '--fixed', '-simplematch', '-casesensitive', '-allmatches', '-notmatch',
})

def _grep_no_value_flag(tok: str) -> bool:
    low=tok.lower()
    if low in GREP_NO_VALUE_LONG:
        return True
    return bool(re.fullmatch(r'-[A-Za-z]+', tok)) and all(c in GREP_NO_VALUE_SHORT for c in tok[1:])

def _grep_pattern_spans(cmd: str):
    """Spans of fully quoted grep-family *pattern* arguments that contain '|'.

    A regex alternation such as "x|/tmp" names no file; scanned as shell text
    each alternative was read as a standalone path. Only the pattern argument
    qualifies: the value after -e/--regexp/-Pattern, or the first positional
    after flags known to take no value. Any other quoted argument (an option
    value such as --pre, a path, a glob) is scanned exactly as before.
    """
    segs=_quote_segments(cmd)
    if segs is None:
        return []
    words=[]; cur=[]; start=None
    def flush():
        nonlocal cur, start
        if cur: words.append((''.join(t for t, _q, _s, _e in cur), cur))
        cur=[]; start=None
    commands=[]
    for text, quoted, s0, e0 in segs:
        if quoted:
            cur.append((text, True, s0, e0)); continue
        pos=s0
        for m in re.finditer(r'[;&|\n]|\s+|[^\s;&|\n]+', text):
            piece=m.group(0); a=pos+m.start(); b=pos+m.end()
            if piece.isspace():
                flush()
            elif piece in ';&|\n':
                flush(); commands.append(words); words=[]
            else:
                cur.append((piece, False, a, b))
    flush(); commands.append(words)
    spans=[]
    for words in commands:
        if not words:
            continue
        head=re.split(r'[\\/]', words[0][0])[-1].lower()
        if head.endswith('.exe'):
            head=head[:-4]
        rest=words[1:]
        if head=='git' and rest and rest[0][0].lower()=='grep':
            head, rest='grep', rest[1:]
        if head not in GREP_COMMANDS:
            continue
        prev=None
        for text, parts in rest:
            whole=len(parts)==1 and parts[0][1]
            if whole and '|' in text and (
                    (prev is not None and prev.lower() in GREP_PATTERN_OPTIONS)
                    or prev is None or _grep_no_value_flag(prev)):
                spans.append((parts[0][2], parts[0][3], text))
                break
            if prev is not None and prev.lower() in GREP_PATTERN_OPTIONS:
                break
            if not (text.startswith('-') and (_grep_no_value_flag(text) or text.lower() in GREP_PATTERN_OPTIONS)):
                break
            prev=text
    return spans

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

_COMMAND_SEPARATOR = re.compile(r'&&|\|\||[;&|\r\n]')

def _command_segments(cmd):
    """Simple commands of a compound shell text, split at unquoted ; & | && || and newlines.

    Quoted text never splits. Unbalanced or backslash-escaped quoting returns
    the whole text as one segment, which is the stricter reading for git add
    (every later token still counts against the first `git add`).
    """
    segs=_quote_segments(cmd)
    if segs is None:
        return [cmd]
    out=[]; cur=''
    for text, quoted, start, end in segs:
        if quoted:
            cur+=cmd[start:end]
            continue
        pieces=_COMMAND_SEPARATOR.split(text)
        cur+=pieces[0]
        for piece in pieces[1:]:
            out.append(cur); cur=piece
    out.append(cur)
    return [seg for seg in out if seg.strip()]

def _git_add_token_lists(cmd):
    """Arguments of every `git add` in cmd, one list per simple command."""
    found=[]
    for seg in _command_segments(cmd):
        sub, tokens=_git_subcommand_tokens(seg)
        if sub=='add':
            found.append(tokens)
    return found

def _git_add_explicit_paths(cmd):
    lists=_git_add_token_lists(cmd)
    if not lists:
        return None
    paths=[]
    for tokens in lists:
        after_dd=False
        for tok in tokens:
            if tok=='--':
                after_dd=True
                continue
            if not after_dd and tok.startswith('-'):
                continue
            paths.append(_normalize_shell_rel(tok))
    return paths

def _git_add_is_broad(cmd):
    for tokens in _git_add_token_lists(cmd):
        for tok in tokens:
            if tok in GIT_ADD_BROAD_TOKENS:
                return True
            if tok.startswith('-') and tok in {'-p', '--patch', '-N', '--intent-to-add'}:
                return True
    return False

def _git_add_is_programme_ledger_only(cmd, policy):
    # The ledger-staging exemption covers one simple command only; it must not
    # carry over to other commands chained after it.
    if len(_command_segments(cmd)) != 1:
        return False
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
    # Redirection and substitution disqualify anywhere (substitution still
    # expands inside double quotes); ; & | only outside quotes, where they chain.
    if re.search(r'[<>`\r\n]|\$\(', norm):
        return False
    segs = _quote_segments(cmd)
    if segs is None or any(re.search(r'[;&|]', text) for text, quoted, _s, _e in segs if not quoted):
        return False
    return bool(re.fullmatch(
        r'\s*python(?:3)?\s+(?:-B\s+)?(?:["\'])?(?:\./)?\.eif/runtime/programme/program\.py(?:["\'])?(?:\s+[^\r\n]*)?\s*',
        norm,
        re.I,
    ))

def _rooted_head_exists(cand, base):
    head = cand.lstrip('/').split('/', 1)[0]
    anchor = Path(base.anchor) if base is not None and base.anchor else Path('/')
    try:
        return not head or (anchor / head).exists()
    except OSError:
        return True

def shell_path_consequence(cmd, policy, lean=False):
    """Defense-in-depth only. Does not contain arbitrary child processes.

    lean=True (enforcement profile lean): control-plane naming is judged by
    _lean_control_plane_mutation instead, and broad staging by the lean caller;
    the FOREIGN_PATH / PROTECTED_PATH findings returned here become advisories.
    """
    programme_invoke = _programme_runtime_shell_invoke(cmd)
    closure_invoke = support('eif_session').verifier_command(cmd)
    for m in REDIRECT_TARGET.finditer(cmd):
        rel=_normalize_shell_rel(m.group(1).strip('\'"'))
        if is_programme_ledger_rel(rel, policy):
            return _shell_result(
                False, 'PROGRAMME_PATH_PROTECTED',
                'shell redirection to programme ledger path is denied',
            )
    add_hit=None if lean else _git_add_programme_consequence(cmd, policy)
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
    if ENV_ROOTED_PATH.search(cmd):
        return _shell_result(False,'FOREIGN_PATH','shell text names a path under a PowerShell environment drive; it cannot be shown inside declared roots (defense-in-depth deny, not process containment)')
    scan=NETWORK_URL.sub(' ', cmd)
    # A quoted grep alternation is a pattern: blank it out of the path scan, but
    # a control-plane name inside it is still shell text naming the control plane.
    for a, b, pattern in reversed(_grep_pattern_spans(scan)):
        for cand in _path_candidates(pattern):
            rel=_normalize_shell_rel(cand)
            if not lean and (control_plane(rel, policy) or any(s in rel for s in ('.cursor/eif-runtime-policy.json','.cursor/hooks','.eif/AUTONOMY_POLICY.md','.eif/RUNTIME_CAPABILITIES.md'))):
                return _shell_result(False,'CONTROL_PLANE_PROTECTED','shell text names a control-plane path; defense-in-depth deny (not process containment)')
        scan=scan[:a]+' '*(b-a)+scan[b:]
    redirects={m.group(1).strip('\'"') for m in REDIRECT_TARGET.finditer(scan)}
    for cand in _path_candidates(scan):
        if cand.lower() in NULL_DEVICES:
            continue
        # "/api/x" on its own is a route or pattern unless its top-level
        # directory exists; write redirects and known system roots stay strict.
        if (cand.startswith('/') and not cand.startswith('//') and cand not in redirects
                and not ABS_PATH.match(cand) and not _rooted_head_exists(cand, base)):
            continue
        rel=_normalize_shell_rel(cand)
        if programme_invoke and rel == PROGRAMME_ENTRY_REL:
            continue
        if closure_invoke and rel == '.cursor/hooks/eif_guard.py':
            continue
        if staging_only and rel in ledger_rels:
            continue
        if not lean and (control_plane(rel, policy) or any(s in rel for s in ('.cursor/eif-runtime-policy.json','.cursor/hooks','.eif/AUTONOMY_POLICY.md','.eif/RUNTIME_CAPABILITIES.md'))):
            return _shell_result(False,'CONTROL_PLANE_PROTECTED','shell text names a control-plane path; defense-in-depth deny (not process containment)')
        if matches(rel, protected):
            return _shell_result(False,'PROTECTED_PATH','shell text names a protected path; defense-in-depth deny (not process containment)')
        try:
            # `C:\temp\x`, `\\server\share\x` and `//server/share/x` are absolute
            # on Windows and outside the project on any host. Joining them onto
            # the POSIX cwd, or collapsing `//server` to `/server`, made them
            # look in-project. A UNC `..` above the share is foreign before
            # resolve: normpath would hide it inside the share.
            if _unc_climbs_above_anchor(cand):
                return _shell_result(False,'FOREIGN_PATH','shell text names a path outside declared roots; defense-in-depth deny (not process containment)')
            if re.match(r'^[A-Za-z]:[\\/]', cand) or cand.startswith(('\\\\', '//')):
                if os.name != 'nt':
                    if not any(relative_to_root(cand, r) is not None for r in roots):
                        return _shell_result(False,'FOREIGN_PATH','shell text names a path outside declared roots; defense-in-depth deny (not process containment)')
                    continue
            p=Path(cand)
            if p.is_absolute():
                resolved=p
            elif len(cand) > 1 and cand[1] == ':':
                # `D:name` is the cwd of drive D, not a path inside this project.
                return _shell_result(False,'FOREIGN_PATH','shell text names a path outside declared roots; defense-in-depth deny (not process containment)')
            elif base is not None and (cand.startswith('..') or cand.startswith('/')):
                resolved=(base/cand)
            else:
                continue
            resolved=resolved.resolve()
            if roots and not any(_path_under_root(resolved, r) for r in roots):
                return _shell_result(False,'FOREIGN_PATH','shell text names a path outside declared roots; defense-in-depth deny (not process containment)')
        except Exception:
            continue
    return None

# ---------------------------------------------------------------------------
# Lean enforcement profile (runtime policy `enforcement.profile: lean`).
# Volume 22.10. BLOCK classes B1-B5 deny. Every other shell-text heuristic,
# out-of-change-scope write, out-of-root read, burst budget and broad-staging
# finding is an advisory: the action is allowed and the finding is written to
# the operator log with the reason code it would have had. Strict (the
# default) never reaches this code.
# ---------------------------------------------------------------------------

READ_TOOLS = frozenset({'Read', 'ReadLints', 'Grep', 'Glob', 'List'})
CP_SUBSTRINGS = ('.cursor/eif-runtime-policy.json', '.cursor/hooks', '.eif/AUTONOMY_POLICY.md',
                 '.eif/RUNTIME_CAPABILITIES.md')


def _lean_ctx(root=None, data=None, base=None, grants=True):
    """Per-decision context: where relative shell paths resolve, and the sink
    for advisory findings. grants=False never consults session grants."""
    return {'root': root, 'data': data, 'base': base, 'grants': grants, 'advisories': []}


def _advise(ctx, code, message, enforcement='advisory', **extra):
    if ctx is not None:
        ctx['advisories'].append({'reason_code': code, 'message': message, 'enforcement': enforcement, **extra})


def _segment_words(seg):
    for escapes in (False, True):
        try:
            return _shell_words(seg, escapes)
        except ValueError:
            continue
    return seg.split()


def _basename(token):
    return re.split(r'[\\/]', str(token))[-1]


_COMMAND_WRAPPERS = frozenset({'env', 'sudo', 'command', 'exec', 'time', 'nice', 'nohup', 'builtin', 'call'})


def _program_words(seg):
    """Words of one simple command, without leading env assignments/wrappers."""
    words = _segment_words(seg.strip())
    i = 0
    while i < len(words):
        word = words[i]
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', word):
            i += 1
            continue
        if _program_name(_basename(word)) in _COMMAND_WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith('-'):
                i += 1
            continue
        break
    return words[i:]


def _prog(words):
    return _program_name(_basename(words[0])) if words else ''


_GIT_GLOBAL_VALUE = frozenset({'-c', '--git-dir', '--work-tree', '--namespace', '--exec-path', '--super-prefix'})


def _git_parts(words):
    """([-C dirs], subcommand, args) for a git invocation, else None."""
    if not words or _prog(words) != 'git':
        return None
    i, cdirs = 1, []
    while i < len(words):
        word = words[i]
        if word == '-C' and i + 1 < len(words):
            cdirs.append(words[i + 1])
            i += 2
            continue
        if word in _GIT_GLOBAL_VALUE and i + 1 < len(words):
            i += 2
            continue
        if word.startswith('-'):
            i += 1
            continue
        break
    if i >= len(words):
        return None
    return cdirs, words[i].lower(), words[i + 1:]


def _ctx_base(ctx):
    base = (ctx or {}).get('base') or (ctx or {}).get('root')
    try:
        return Path(base) if base is not None else Path.cwd()
    except Exception:
        return Path.cwd()


def _parsed_segments(cmd, ctx):
    """[(segment, words, base dir)] tracking `cd`/`Set-Location` between segments."""
    base = _ctx_base(ctx)
    out = []
    for seg in _command_segments(cmd):
        words = _program_words(seg)
        out.append((seg, words, base))
        if words and _prog(words) in {'cd', 'set-location', 'sl', 'chdir', 'pushd'}:
            target = next((w for w in words[1:] if not w.startswith('-')), None)
            if target and not re.search(r'[$%`~]', target):
                base = base / target
    return out


def _git_repo_dir(cdirs, base):
    for d in cdirs:
        base = base / d
    return base


_LEAN_GIT_CACHE = {}


def _lean_git(cwd, *args):
    """Read-only git query for a lean BLOCK matcher; failure is the caller's
    fail-closed signal. Bounded by the invocation deadline. Cached for this
    invocation only, so the timeout precheck and the decision share one answer."""
    key = (str(cwd), args)
    if key in _LEAN_GIT_CACHE:
        return _LEAN_GIT_CACHE[key]
    _LEAN_GIT_CACHE[key] = _lean_git_uncached(cwd, *args)
    return _LEAN_GIT_CACHE[key]


def _lean_git_uncached(cwd, *args):
    started = time.perf_counter()
    try:
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(cwd), *args],
                                capture_output=True, timeout=remaining_timeout(2.0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('git query timed out') from exc
    finally:
        _TIMINGS['lean_git'] = round(_TIMINGS.get('lean_git', 0) + (time.perf_counter() - started) * 1000, 3)
    if result.returncode:
        raise RuntimeError(f'git {args[0]} exited {result.returncode}')
    return result.stdout.decode('utf-8', errors='surrogateescape')


# --- B4: control-plane mutation (reads and read-only naming are allowed) ----

LEAN_READ_ONLY_PROGRAMS = frozenset('''
cat type get-content gc head tail less more grep egrep fgrep rg ag ack select-string sls findstr
ls dir get-childitem gci tree wc stat file diff cmp sha256sum sha1sum md5sum get-filehash test [
echo printf write-output write-host jq sort uniq cut tr column nl od xxd hexdump strings realpath
readlink basename dirname pwd true false test-path resolve-path get-item gi measure-object
select-object where-object format-list format-table out-string convertfrom-json du
'''.split())
LEAN_READ_ONLY_GIT = frozenset('''status diff log show blame ls-files ls-tree cat-file rev-parse grep
shortlog describe check-ignore check-attr show-ref for-each-ref'''.split())
LEAN_COPY_PROGRAMS = frozenset({'cp', 'copy', 'copy-item', 'cpi', 'xcopy', 'robocopy'})
FIND_WRITERS = frozenset({'-delete', '-exec', '-execdir', '-ok', '-okdir', '-fprint', '-fprint0', '-fprintf', '-fls'})


def _segment_read_only(words):
    prog = _prog(words)
    if prog in LEAN_READ_ONLY_PROGRAMS:
        return True
    if prog == 'find':
        return not any(w in FIND_WRITERS for w in words[1:])
    if prog == 'sed':
        return not any(w.startswith(('-i', '--in-place')) or (re.fullmatch(r'-[A-Za-z]+', w) and 'i' in w[1:])
                       for w in words[1:])
    git = _git_parts(words)
    if git:
        return git[1] in LEAN_READ_ONLY_GIT and not any(_writer_option('git', w) for w in git[2])
    return False


def _names_control_plane(rel, policy):
    return control_plane(rel, policy) or any(s in rel for s in CP_SUBSTRINGS)


def _cp_mentions(text, policy, exempt):
    roots = [Path(x) for x in (policy.get('allowed_roots') or []) if x]
    hits = []
    # Path-shaped tokens, plus every bare shell word: a root-level governed
    # file such as CLAUDE.md has no slash for the path scanner to find.
    words = [w for seg in _command_segments(text) for w in _segment_words(seg)]
    for cand in list(_path_candidates(text)) + words:
        raw = cand.strip('\'"')
        rel = _normalize_shell_rel(raw)
        for root in roots:
            inside = relative_to_root(raw, root) if (raw.startswith('/') or _looks_windows_path(raw)) else None
            if inside:
                rel = inside
                break
        if rel in exempt:
            continue
        if _names_control_plane(rel, policy):
            hits.append(rel)
    return hits


def _copy_destination(words):
    args = words[1:]
    for i, word in enumerate(args):
        low = word.casefold()
        if low in {'-t', '--target-directory'} or (low.startswith('-dest') and _prog(words) in {'copy-item', 'cpi'}):
            return args[i + 1] if i + 1 < len(args) else ''
        if low.startswith('--target-directory='):
            return word.split('=', 1)[1]
    positional = [w for w in args if not w.startswith('-') and not re.fullmatch(r'/[A-Za-z]{1,3}', w)]
    return positional[-1] if len(positional) >= 2 else ''


def _lean_control_plane_mutation(cmd, policy):
    """B4 for shell: deny a shell command that could modify a governed path.

    Naming, reading or grepping a control-plane path is allowed. A command that
    names one is admitted only when every simple command in it is a known
    read-only program (or a copy whose destination is outside the control
    plane), with no substitution and no redirect onto the control plane.
    """
    deny = _shell_result(False, 'CONTROL_PLANE_PROTECTED',
                         'shell command could modify a governed control-plane path; reads are allowed, '
                         'mutation needs the operator (lean profile B4)')
    exempt = set()
    if _programme_runtime_shell_invoke(cmd):
        exempt.add(PROGRAMME_ENTRY_REL)
    if support('eif_session').verifier_command(cmd):
        exempt.add('.cursor/hooks/eif_guard.py')
    if _git_add_is_programme_ledger_only(cmd, policy):
        exempt |= programme_ledger_rels(policy)
    for m in REDIRECT_TARGET.finditer(cmd):
        rel = _normalize_shell_rel(m.group(1).strip('\'"'))
        if rel not in exempt and _names_control_plane(rel, policy):
            return deny
    if not _cp_mentions(cmd, policy, exempt):
        return None
    if re.search(r'\$\(|`|<\(|>\(', cmd):
        return deny
    for seg in _command_segments(cmd):
        words = _program_words(seg)
        if not words or _segment_read_only(words):
            continue
        if _prog(words) in LEAN_COPY_PROGRAMS:
            destination = _copy_destination(words)
            if destination and not _cp_mentions(destination, policy, exempt) and destination.strip('\'"'):
                continue
            return deny
        # A non-read-only program anywhere in a command that names the control
        # plane (directly, via a pipe into xargs, ...) cannot be shown read-only.
        return deny
    return None


# --- B3: secrets publishing ------------------------------------------------

SECRET_STAGE_SUFFIXES = ('.dump', '.pem', '.key')
LINK_SCAN_CAP = 4000


def secret_publish_name(rel):
    """A file name EIF never stages or commits: env files (templates excepted),
    database dumps, private keys and a Postgres PG_VERSION marker."""
    name = str(rel).replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
    low = name.lower()
    if low in ENV_TEMPLATE_NAMES:
        return False
    return _env_file_name(name) or low.endswith(SECRET_STAGE_SUFFIXES) or low == 'pg_version'


def _pg_data_ancestor(path, top, cache):
    """True when `path` lies in a directory holding PG_VERSION (a Postgres data dir)."""
    current = path.parent
    seen = []
    while True:
        key = str(current)
        if key in cache:
            hit = cache[key]
            break
        seen.append(key)
        try:
            hit = (current / 'PG_VERSION').is_file()
        except OSError:
            hit = True
        if hit or current == top or current.parent == current:
            break
        current = current.parent
    for key in seen:
        cache[key] = cache.get(key, False) or hit
    return hit


def _secret_in_tree(directory, budget):
    """Bounded walk of an untracked/ignored directory entry; fail closed on cap."""
    stack = [directory]
    while stack:
        current = stack.pop()
        try:
            names = os.listdir(current)
        except OSError:
            return str(current)
        for name in names:
            budget[0] -= 1
            if budget[0] < 0:
                return f'{directory} (scan cap)'
            child = current / name
            if secret_publish_name(name):
                return str(child)
            try:
                if stat.S_ISDIR(os.lstat(child).st_mode):
                    stack.append(child)
            except OSError:
                return str(child)
    return None


_ADD_VALUE = frozenset({'--chmod'})
_COMMIT_VALUE = frozenset({'-m', '-F', '-C', '-c', '-t', '--message', '--file', '--author', '--date', '--template',
                           '--reuse-message', '--reedit-message', '--fixup', '--squash', '--cleanup', '--trailer'})


def _split_git_args(args, value_options, value_letters=''):
    flags, paths, after = [], [], False
    i = 0
    while i < len(args):
        word = args[i]
        if after:
            paths.append(word)
        elif word == '--':
            after = True
        elif word.startswith('-') and word != '-':
            flags.append(word)
            if '=' not in word and (word in value_options or (
                    re.fullmatch(r'-[A-Za-z]+', word) and word[-1] in value_letters)):
                i += 1
        else:
            paths.append(word)
        i += 1
    return flags, paths


def _status_entries(raw, tracked_only=False):
    entries = []
    for item in raw.split('\0'):
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if tracked_only and code in {'??', '!!'}:
            continue
        entries.append(path)
    return entries


def lean_staged_secret(repo, sub, args):
    """First repo-relative path a git add/commit would publish that B3 forbids.

    Asks git itself which paths the command can reach (read-only queries);
    raises on any git failure so the caller fails closed.
    """
    if sub in {'add', 'stage'}:
        flags, paths = _split_git_args(args, _ADD_VALUE)
        if any(f in {'-n', '--dry-run'} for f in flags):
            return None
        broad = any(f in {'-A', '--all', '-u', '--update'} or f.startswith('--pathspec-from-file') for f in flags)
        if not paths and not broad:
            return None
        force = any(f in {'-f', '--force'} for f in flags)
        tracked = any(f in {'-u', '--update'} for f in flags)
        query = ['status', '--porcelain=v1', '-z', '--no-renames', '--untracked-files=all']
        if force:
            query.append('--ignored=traditional')
        if paths and not any(f.startswith('--pathspec-from-file') for f in flags):
            query += ['--', *paths]
        candidates = _status_entries(_lean_git(repo, *query), tracked_only=tracked)
    elif sub == 'commit':
        flags, paths = _split_git_args(args, _COMMIT_VALUE, 'mFCct')
        candidates = [p for p in _lean_git(repo, 'diff', '--cached', '--name-only', '-z', '--no-renames').split('\0') if p]
        if any(f in {'-a', '--all'} or (re.fullmatch(r'-[A-Za-z]+', f) and 'a' in f[1:]) for f in flags):
            candidates += [p for p in _lean_git(repo, 'diff', '--name-only', '-z', '--no-renames').split('\0') if p]
        if paths:
            candidates += _status_entries(_lean_git(repo, 'status', '--porcelain=v1', '-z', '--no-renames',
                                                    '--untracked-files=all', '--', *paths),
                                          tracked_only=not any(f in {'-i', '--include'} for f in flags))
    else:
        return None
    if not candidates:
        return None
    top = Path(_lean_git(repo, 'rev-parse', '--show-toplevel').strip())
    cache, budget = {}, [LINK_SCAN_CAP]
    for rel in candidates:
        if secret_publish_name(rel):
            return rel
        path = top / rel.rstrip('/')
        if _pg_data_ancestor(path, top, cache):
            return rel
        if rel.endswith('/'):
            if (path / 'PG_VERSION').is_file():
                return rel
            found = _secret_in_tree(path, budget)
            if found:
                return found
    return None


_PUSH_VALUE = frozenset({'-o', '--push-option', '--repo', '--receive-pack', '--exec'})


def lean_protected_push(repo, args, protected):
    """Protected branch a git push would update, or None. Unknown => a reason (fail closed)."""
    if not protected:
        return None
    wanted = {p.casefold() for p in protected}
    flags, positional = _split_git_args(args, _PUSH_VALUE)
    if any(f in {'--all', '--mirror', '--branches'} for f in flags):
        return 'every branch (--all/--mirror)'
    refspecs = positional[1:]
    current = None

    def current_branch():
        nonlocal current
        if current is None:
            try:
                current = _lean_git(repo, 'symbolic-ref', '--short', '-q', 'HEAD').strip()
            except RuntimeError:
                current = ''
        return current

    targets = set()
    if not refspecs:
        branch = current_branch()
        if not branch:
            return 'the current HEAD (detached or unreadable; push target cannot be shown)'
        targets.add(branch)
        try:
            upstream = _lean_git(repo, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}').strip()
            if '/' in upstream:
                targets.add(upstream.split('/', 1)[1])
        except RuntimeError:
            pass
    for spec in refspecs:
        spec = spec.lstrip('+')
        if '*' in spec:
            return f'wildcard refspec {spec}'
        dst = spec.split(':', 1)[1] if ':' in spec else spec
        dst = dst or spec.split(':', 1)[0]
        if dst in {'HEAD', '@'}:
            dst = current_branch()
            if not dst:
                return 'HEAD (detached or unreadable)'
        if dst.startswith('refs/heads/'):
            dst = dst[len('refs/heads/'):]
        elif dst.startswith('refs/'):
            continue
        targets.add(dst)
    hit = sorted(t for t in targets if t.casefold() in wanted)
    return hit[0] if hit else None


# --- B2: destructive local operations --------------------------------------

_LSTAT = os.lstat
_LISTDIR = os.listdir
_REPARSE_POINT = 0x400


def _is_link(st):
    return (stat.S_ISLNK(st.st_mode) or bool(getattr(st, 'st_file_attributes', 0) & _REPARSE_POINT)
            or bool(getattr(st, 'st_reparse_tag', 0)))


def linked_tree_scan(target, cap=LINK_SCAN_CAP):
    """('clear'|'linked'|'error', detail). lstat only; never follows a link.

    Scans the target itself, its node_modules (and those of its children and
    grandchildren, for monorepo packages), every node_modules child and every
    @scope/* child. Errors and the fixed entry cap fail closed.
    """
    count = [0]

    def lstat(path):
        count[0] += 1
        if count[0] > cap:
            raise OverflowError
        return _LSTAT(path)

    def listdir(path):
        names = _LISTDIR(path)
        count[0] += len(names)
        if count[0] > cap:
            raise OverflowError
        return names

    target = Path(target)
    try:
        try:
            st = lstat(target)
        except FileNotFoundError:
            return 'clear', ''
        if _is_link(st):
            return 'linked', str(target)
        if not stat.S_ISDIR(st.st_mode):
            return 'clear', ''
        modules = [target] if target.name == 'node_modules' else [target / 'node_modules']
        if target.name != 'node_modules':
            level = [target]
            for _depth in range(2):
                following = []
                for parent in level:
                    for name in listdir(parent):
                        if name in {'.git', 'node_modules'}:
                            continue
                        child = parent / name
                        cst = lstat(child)
                        if _is_link(cst):
                            continue  # a link here is removed as a link; node_modules scan is the risk
                        if stat.S_ISDIR(cst.st_mode):
                            following.append(child)
                            modules.append(child / 'node_modules')
                level = following
        for directory in modules:
            try:
                mst = lstat(directory)
            except FileNotFoundError:
                continue
            if _is_link(mst):
                return 'linked', str(directory)
            if not stat.S_ISDIR(mst.st_mode):
                continue
            for name in listdir(directory):
                child = directory / name
                cst = lstat(child)
                if _is_link(cst):
                    return 'linked', str(child)
                if name.startswith('@') and stat.S_ISDIR(cst.st_mode):
                    for inner in listdir(child):
                        if _is_link(lstat(child / inner)):
                            return 'linked', str(child / inner)
        return 'clear', ''
    except OverflowError:
        return 'error', f'scan exceeded {cap} entries under {target}'
    except OSError as exc:
        return 'error', f'{type(exc).__name__} while scanning {target}'


def _lean_force_git(git):
    """(reason, worktree remove target or None) for B2 git forms not in FORCE_VCS."""
    _cdirs, sub, args = git
    if sub == 'branch':
        short = ''.join(a[1:] for a in args if re.fullmatch(r'-[A-Za-z]+', a))
        if 'D' in short or (('d' in short or '--delete' in args) and ('f' in short or '--force' in args)):
            return 'git branch force delete', None
    if sub == 'worktree' and args:
        if args[0] == 'remove':
            _flags, paths = _split_git_args(args[1:], frozenset())
            return 'git worktree remove', (paths[0] if paths else '')
        if args[0] == 'prune':
            rest = args[1:]
            if '--expire=now' in rest or any(a == '--expire' and rest[i + 1:i + 2] == ['now'] for i, a in enumerate(rest)):
                return 'git worktree prune --expire now', None
    return None, None


_POSIX_RM_SHORT = set('rRfivdI')
_PS_REMOVE = frozenset({'remove-item', 'ri', 'del', 'erase', 'rd', 'rmdir', 'rm'})
_PS_VALUE_PARAMS = ('-filter', '-include', '-exclude', '-credential', '-stream')


def _recursive_delete_targets(words):
    """Raw target words of a recursive delete, else None."""
    prog = _prog(words)
    args = words[1:]
    if prog == 'rimraf' or (prog in {'npx', 'pnpx', 'bunx'} and args and _program_name(_basename(args[0])) == 'rimraf'):
        rest = args[1:] if prog != 'rimraf' else args
        return [a for a in rest if not a.startswith('-')]
    if prog in {'pnpm', 'yarn'} and args[:2] in (['dlx', 'rimraf'], ['exec', 'rimraf']):
        return [a for a in args[2:] if not a.startswith('-')]
    if prog not in _PS_REMOVE:
        return None
    cmd_switch = prog in {'rmdir', 'rd', 'del', 'erase'} and any(a.casefold() == '/s' for a in args)
    posix = prog == 'rm' and any(
        a in {'-r', '-R', '--recursive'} or (re.fullmatch(r'-[A-Za-z]+', a) and set(a[1:]) <= _POSIX_RM_SHORT
                                              and ({'r', 'R'} & set(a[1:])))
        for a in args)
    powershell = any(re.fullmatch(r'-rec?(?:u(?:r(?:s(?:e)?)?)?)?(?::\$?true)?', a, re.I) or a.casefold() == '-r'
                     for a in args)
    if not (cmd_switch or posix or powershell):
        return None
    targets, i = [], 0
    while i < len(args):
        word = args[i]
        low = word.casefold()
        if low in {'-path', '-literalpath', '-lp'}:
            if i + 1 < len(args):
                targets.append(args[i + 1])
            i += 2
            continue
        if low.startswith(_PS_VALUE_PARAMS):
            i += 2
            continue
        if word.startswith('-') or (prog in {'rmdir', 'rd', 'del', 'erase'} and re.fullmatch(r'/[A-Za-z]', word)):
            i += 1
            continue
        targets.append(word.rstrip(','))
        i += 1
    return targets


def _resolve_targets(raw, base):
    """Concrete paths, or None when a target cannot be shown (variables, too many globs)."""
    out = []
    for word in raw:
        text = word.strip().strip('\'"')
        if not text:
            continue
        text = os.path.expanduser(text) if text.startswith('~') else text
        if re.search(r'[$%`]', text) or text.startswith('~'):
            return None
        path = Path(text)
        if not path.is_absolute():
            path = base / path
        if any(c in text for c in '*?['):
            found = glob.glob(str(path))
            if len(found) > 64:
                return None
            out.extend(Path(x) for x in found)
        else:
            out.append(path)
    return out


def _is_worktrees_root(path):
    parts = Path(os.path.normpath(str(path))).parts
    return bool(parts) and (parts[-1] == '.worktrees' or (len(parts) >= 2 and parts[-2] == '.worktrees'))


def _linked_tree_denial(target, status, detail):
    if status == 'linked':
        why = f'{target} holds a symlink/junction/reparse point at {detail}'
    else:
        why = f'cannot show {target} is free of links ({detail})'
    return _shell_result(False, 'DESTRUCTIVE_LINKED_TREE', (
        f'{why}; a recursive delete or `git worktree remove` can follow it and empty the linked tree '
        '(a shared pnpm node_modules). No grant admits this. Safe order: remove the links/junctions first '
        'without recursion (POSIX `rm <link>`; Windows `cmd /c rmdir <junction>` without /s), confirm none '
        'remain, then run `git worktree remove <path>` without --force.'))


def lean_destructive(cmd, policy, ctx):
    """B2: force VCS, branch -D, worktree remove/prune, recursive deletes."""
    for seg, words, base in _parsed_segments(cmd, ctx):
        git = _git_parts(words)
        if git:
            reason, worktree = _lean_force_git(git)
            if worktree is not None:
                repo = _git_repo_dir(git[0], base)
                paths = _resolve_targets([worktree], repo) if worktree else None
                if not paths:
                    return _linked_tree_denial(worktree or '<missing path>', 'error', 'worktree path not shown literally')
                for path in paths:
                    status, detail = linked_tree_scan(path)
                    if status != 'clear':
                        return _linked_tree_denial(path, status, detail)
            if reason and not action_allowed(policy, 'force_vcs'):
                return _shell_result(False, 'ACTION_FORCE_VCS', f'{reason} is destructive and force_vcs is not granted')
            continue
        raw = _recursive_delete_targets(words)
        if raw is None:
            continue
        paths = _resolve_targets(raw, base)
        if paths is None:
            return _linked_tree_denial(' '.join(raw), 'error', 'target uses a variable or too many glob matches')
        for path in paths:
            status, detail = linked_tree_scan(path)
            if status != 'clear':
                return _linked_tree_denial(path, status, detail)
            if _is_worktrees_root(path) and not action_allowed(policy, 'destructive_data'):
                return _shell_result(False, 'ACTION_DESTRUCTIVE_DATA',
                                     f'recursive delete of worktree root {path} needs destructive_data')
    if FORCE_VCS.search(cmd) and not action_allowed(policy, 'force_vcs'):
        return _shell_result(False, 'ACTION_FORCE_VCS', 'force/history-rewriting VCS operation is not granted')
    return None


# --- B1: protected database writes -----------------------------------------

DB_CLIENTS = frozenset({'psql', 'pgcli', 'pg_restore', 'dropdb', 'createdb', 'mysql', 'sqlcmd'})
DB_ALWAYS_MUTATING = frozenset({'pg_restore', 'dropdb', 'createdb'})
DB_COMMAND_OPTIONS = frozenset({'-c', '--command', '-e', '--execute', '-Q', '-q', '-l', '--list',
                                '--version', '-V', '--help', '-?'})
DB_VALUE_OPTIONS = frozenset('''-c -d -f -h -L -o -p -P -R -T -U -v -F -e -Q -q -S -E -O -D -W
--command --dbname --file --host --log-file --output --port --pset --username --set --variable
--execute --maintenance-db --owner --template --encoding --locale --tablespace --user --password
--server --database'''.split())
SQL_MUTATION = re.compile(r'''\b(?:insert\s+into|update\s+[A-Za-z0-9_."]+\s+set|delete\s+from
    |drop\s+(?:table|schema|database|index|view|type|function|sequence|extension|materialized|trigger|role|owned)
    |alter\s+(?:table|schema|database|index|view|type|sequence|role|user|function)
    |truncate\b|create\s+(?:table|schema|database|index|unique|view|type|function|sequence|extension
    |materialized|or\s+replace|trigger|role|user|temp|temporary)|grant\s|revoke\s|copy\s+[A-Za-z0-9_."]+\s+from)''',
    re.I | re.X)
DROP_DATABASE = re.compile(r'\bdrop\s+database\b', re.I)
DB_DSN = re.compile(r'''\b(?:postgres(?:ql)?|mysql|mariadb|mssql|sqlserver|cockroachdb|redshift)(?:\+[A-Za-z0-9_]+)?://[^\s'"`;|&()<>]+''', re.I)
SHELL_ASSIGN = re.compile(r'''(?:^|[\s;&|(])(?:export\s+|set\s+|\$env:)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>"[^"]*"|'[^']*'|[^\s;&|]*)''')
DB_ENV_NAME = re.compile(r'^(?:\w*DATABASE_URL\w*|PGDATABASE|POSTGRES_DB|DB_NAME|DATABASE_NAME)$', re.I)
DB_FLAG_VALUE = re.compile(r'''(?:^|\s)--(?:dbname|database|db|target-db)(?:=|\s+)(?P<v>"[^"]*"|'[^']*'|[^\s;&|]+)''', re.I)
EXPECT_DB = re.compile(r'''(?:^|\s)--expect-db(?:=|\s+)(?P<v>"[^"]*"|'[^']*'|[^\s;&|]+)''', re.I)
LIBPQ_DBNAME = re.compile(r'''\bdbname\s*=\s*(?P<v>"[^"]*"|'[^']*'|[^\s;&|'"]+)''', re.I)
APPLY_FLAG = re.compile(r'(?:^|\s)--(?:apply|confirm)(?:=\S*)?(?=\s|$)', re.I)
ALLOW_FLAG = re.compile(r'(?:^|\s)--allow-(?P<name>[A-Za-z0-9_.-]+)', re.I)
ALEMBIC_MUTATION = re.compile(r'\balembic(?:\.exe)?\b[^;&|\n]*?\b(?:upgrade|downgrade|stamp)\b', re.I)
_FALSY = frozenset({'', '0', 'false', 'no', 'off'})


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '\'"':
        return value[1:-1]
    return value


def _dsn_database(dsn):
    try:
        path = urlparse(dsn).path
    except ValueError:
        return ''
    return unquote(path.lstrip('/').split('/')[-1].split('?')[0])


def _dsn_fragment(entry):
    return any(c in entry for c in ':/@?')


def lean_database_write(cmd, policy):
    """B1: (reason) when a mutating command targets, or may target, a protected database."""
    rules = enforcement(policy)
    protected = rules['protected_databases']
    names = {p.casefold() for p in protected if not _dsn_fragment(p)}
    fragments = [p.casefold() for p in protected if _dsn_fragment(p)]
    low = cmd.casefold()
    targets = set()
    for dsn in DB_DSN.findall(cmd):
        name = _dsn_database(dsn)
        if name:
            targets.add(name.casefold())
    for m in SHELL_ASSIGN.finditer(cmd):
        value = _unquote(m.group('value'))
        if DB_ENV_NAME.match(m.group('name')) and value and '://' not in value and not re.search(r'[$%`]', value):
            targets.add(value.casefold())
    for pattern in (DB_FLAG_VALUE, LIBPQ_DBNAME):
        for m in pattern.finditer(cmd):
            value = _unquote(m.group('v'))
            if value and '://' not in value:
                targets.add(value.casefold())
    expect = {_unquote(m.group('v')).casefold() for m in EXPECT_DB.finditer(cmd)}
    targets |= expect
    flag_hit = None
    for m in SHELL_ASSIGN.finditer(cmd):
        if m.group('name') in rules['protected_database_flags'] and _unquote(m.group('value')).casefold() not in _FALSY:
            flag_hit = m.group('name')
    client_mutation = False
    for seg in _command_segments(cmd):
        words = _program_words(seg)
        prog = _prog(words)
        if prog not in DB_CLIENTS:
            continue
        positional, has_command, i = [], False, 1
        while i < len(words):
            word = words[i]
            if word in {'-d', '--dbname', '--database'} and i + 1 < len(words):
                if '://' not in words[i + 1]:
                    targets.add(words[i + 1].casefold())
                i += 2
                continue
            if word in {'-f', '--file'} or word.startswith('--file='):
                client_mutation = True
            if word in DB_COMMAND_OPTIONS or word.startswith('--command='):
                has_command = True
            if word in DB_VALUE_OPTIONS:
                i += 2
                continue
            if not word.startswith('-'):
                positional.append(word)
            i += 1
        if positional and prog in {'psql', 'pgcli', 'createdb', 'dropdb', 'mysql'} and '://' not in positional[0]:
            targets.add(positional[0].casefold())
        if prog in DB_ALWAYS_MUTATING or not has_command or SQL_MUTATION.search(seg):
            client_mutation = True
    drop_database = bool(DROP_DATABASE.search(cmd))
    alembic = bool(ALEMBIC_MUTATION.search(cmd))
    apply_flag = bool(APPLY_FLAG.search(cmd))
    allow_protected = any(m.group('name').casefold() in names for m in ALLOW_FLAG.finditer(cmd))
    protected_hit = bool(targets & names) or any(f in low for f in fragments) or allow_protected or bool(flag_hit)
    unknown_target_mutation = alembic or apply_flag or client_mutation
    mutating = (drop_database or unknown_target_mutation or allow_protected or bool(flag_hit)
                or bool(expect & names) or (protected_hit and bool(SQL_MUTATION.search(cmd))))
    if not mutating:
        return None
    if drop_database:
        return 'DROP DATABASE'
    if protected_hit:
        hit = sorted(targets & names) or [flag_hit or 'a protected DSN']
        return f'mutating database command targets protected database {hit[0]}'
    if unknown_target_mutation and not targets:
        return ('mutating migration/apply command states no target database; the default environment '
                'may point at a protected database (fail closed)')
    return None


def lean_db_grant(ctx):
    """A valid unexpired db_write grant for the calling session, else None."""
    if not ctx or not ctx.get('grants') or not ctx.get('root') or not ctx.get('data'):
        return None
    session = support('eif_session')
    if session.conversation(ctx['data']) == 'unknown':
        return None
    try:
        path = session.state_path(ctx['root'], ctx['data'])
        if not path.is_file():
            return None
        with support('eif_state').file_lock(path.with_suffix('.lock')):
            saved = session.read_state(path)
        return session.valid_grant(saved, 'db_write', path.stem, time.time())
    except Exception:
        return None


def _session_key(ctx):
    try:
        return support('eif_session').state_path(ctx['root'], ctx['data']).stem
    except Exception:
        return '<session-key>'


def lean_shell_decision(cmd, policy, ctx):
    """Shell decision under the lean profile. Order: identity mutation, B4, B3,
    B2, remote push grant, B1, the unchanged high-consequence classes, then
    path heuristics as advisories."""
    if IDENTITY_MUTATION.search(cmd) and not action_allowed(policy, 'identity_mutation'):
        return _shell_result(False, 'ACTION_IDENTITY_MUTATION', 'git remote identity mutation is not granted')
    # B4: governed control plane (programme ledger included).
    for m in REDIRECT_TARGET.finditer(cmd):
        if is_programme_ledger_rel(_normalize_shell_rel(m.group(1).strip('\'"')), policy):
            return _shell_result(False, 'PROGRAMME_PATH_PROTECTED', 'shell redirection to programme ledger path is denied')
    prog_git = _git_programme_worktree_deny(cmd, policy)
    if prog_git:
        return prog_git
    cp = _lean_control_plane_mutation(cmd, policy)
    if cp:
        return cp
    stage = _git_add_programme_consequence(cmd, policy)
    if stage:
        _advise(ctx, stage[1], stage[2])
    # B3: secrets and protected branches.
    rules = enforcement(policy)
    for seg, words, base in _parsed_segments(cmd, ctx):
        git = _git_parts(words)
        if not git:
            continue
        repo = _git_repo_dir(git[0], base)
        if git[1] in {'add', 'stage', 'commit'}:
            try:
                found = lean_staged_secret(repo, git[1], git[2])
            except Exception as exc:
                return _shell_result(False, 'SECRET_STAGE',
                                     f'cannot show git {git[1]} publishes no secret file ({type(exc).__name__}); fail closed')
            if found:
                return _shell_result(False, 'SECRET_STAGE', (
                    f'git {git[1]} would stage or commit {found}: env files, dumps, private keys and Postgres '
                    'data directories are never published (lean profile B3)'))
        if git[1] == 'push':
            branch = lean_protected_push(repo, git[2], rules['protected_branches'])
            if branch:
                return _shell_result(False, 'PROTECTED_BRANCH_PUSH',
                                     f'git push would update protected branch {branch}; promotion is an operator action')
    # B2: destructive local operations.
    destructive = lean_destructive(cmd, policy, ctx)
    if destructive:
        return destructive
    if REMOTE_PUSH.search(cmd) and not action_allowed(policy, 'remote_push'):
        return _shell_result(False, 'ACTION_REMOTE_PUSH', 'remote push is not granted')
    # B1: protected databases.
    database = lean_database_write(cmd, policy)
    if database:
        grant = lean_db_grant(ctx)
        if grant is None:
            key = _session_key(ctx)
            return _shell_result(False, 'PROTECTED_DATABASE_WRITE', (
                f'{database}. Read-only SQL is allowed; name a non-protected target (DSN, -d, --expect-db) for '
                'disposable databases. To admit this session, the operator runs from the EIF checkout: '
                f'python tools/session_grant.py <project> grant --session-key {key} --minutes 60 --reason "<why>"'))
        _advise(ctx, 'PROTECTED_DATABASE_WRITE', f'{database}; admitted by operator grant', enforcement='granted',
                grant={k: grant.get(k) for k in ('class', 'expires_at', 'actor', 'reason')})
    if DESTRUCTIVE_INPUT.search(cmd) and not action_allowed(policy, 'destructive_data'):
        return _shell_result(False, 'ACTION_DESTRUCTIVE_DATA', 'destructive data/infrastructure operation is not granted')
    if INFRASTRUCTURE.search(cmd) and not action_allowed(policy, 'infrastructure_control'):
        return _shell_result(False, 'ACTION_INFRASTRUCTURE', 'external infrastructure / remote-shell mutation is not granted')
    if GIT_CLONE.search(cmd) and not action_allowed(policy, 'infrastructure_control'):
        return _shell_result(False, 'ACTION_NETWORK', 'cloning an external repository is not ordinary workspace verification')
    if GLOBAL_OR_PUBLISH.search(cmd) and not action_allowed(policy, 'infrastructure_control'):
        return _shell_result(False, 'ACTION_DEPENDENCY', 'global install or package publish is not granted')
    if SHELL_FETCH.search(cmd):
        urls = URL_IN_TEXT.findall(cmd)
        if not urls:
            return _shell_result(False, 'ACTION_NETWORK', 'fetch tool without a classifiable destination is denied')
        for url in urls:
            good, code, msg = network_destination_allowed(url, policy)
            if not good:
                return _shell_result(False, code, msg)
    path_hit = shell_path_consequence(cmd, policy, lean=True)
    if path_hit:
        if path_hit[1] in {'PROGRAMME_PATH_PROTECTED', 'PROGRAMME_GIT_WORKTREE', 'PROGRAMME_GIT_STAGE'}:
            return path_hit
        _advise(ctx, path_hit[1], path_hit[2])
    mode = str((policy.get('shell') or {}).get('mode') or 'deny').lower()
    if mode != 'workspace':
        return _shell_result(False, 'SHELL_DENY', 'shell execution disabled by policy')
    branch_note = _git_branch_switch_note(cmd)
    extra = {'programme_branch_switch': True} if branch_note else {}
    return _shell_result(True, 'SHELL_WORKSPACE', branch_note or 'ordinary workspace shell; not process containment', extra)


def lean_outside_secret(path, policy):
    """B3 for reads outside every root: env files, keys and credential stores stay denied."""
    ident = tool_path_identity(path) if isinstance(path, str) else None
    text = str(ident if ident is not None else path or '').replace('\\', '/')
    name = text.rstrip('/').rsplit('/', 1)[-1]
    low = name.lower()
    parts = {p.casefold() for p in text.split('/')}
    if low not in ENV_TEMPLATE_NAMES and _env_file_name(name):
        return True
    if low.endswith(('.pem', '.key', '.p12', '.pfx', '.jks', '.keystore', '.kdbx')):
        return True
    if re.match(r'id_(?:rsa|dsa|ecdsa|ed25519)', low) or re.search(r'secret|credential', low):
        return True
    if parts & {'.ssh', '.aws', '.gnupg', '.azure', '.kube', '.docker', 'gcloud', '.pgpass'} or low == '.pgpass':
        return True
    return matches(text.lstrip('/'), (policy or {}).get('sensitive_read_paths') or [])


def lean_timeout_precheck(root, data, policy, roots):
    """True when no lean BLOCK matcher (B1-B5) or other pure denial applies.

    Runs before session bookkeeping. Only a clear request may be allowed as
    HOOK_TIMEOUT_ADVISORY if bookkeeping then exhausts the deadline. Tools the
    precheck does not cover (MCP, network, unknown) are never clear.
    """
    event = data.get('hook_event_name')
    if event == 'subagentStart':
        return True
    if event == 'beforeShellExecution':
        cmd = str(data.get('command') or '')
        return lean_shell_decision(cmd, policy, _lean_ctx(root, data, _TOOL_BASE, grants=False))[0]
    if event == 'beforeReadFile':
        tool, inp = 'Read', {'file_path': data.get('file_path')}
        if has_secret(str(data.get('content') or '')):
            return False
    elif event == 'preToolUse':
        tool, inp = str(data.get('tool_name') or ''), data.get('tool_input') or {}
    else:
        return False
    if tool.startswith('Unmapped:'):
        return True
    if tool == 'Shell':
        cmd = str(inp.get('command', '')) if isinstance(inp, dict) else ''
        return lean_shell_decision(cmd, policy, _lean_ctx(root, data, _TOOL_BASE, grants=False))[0]
    if tool in READ_TOOLS:
        path = tool_path(inp)
        if not path:
            return True
        rr, rel = resolve_path(path, roots)
        if not rr:
            return not lean_outside_secret(path, policy)
        scopes = observation_scopes(policy)
        if scopes and not matches(rel, scopes):
            return False
        return not sensitive_read(rel, policy.get('sensitive_read_paths') or [])
    if tool in {'Write', 'Delete'}:
        path = tool_path(inp)
        rr, rel = resolve_path(path, roots) if path else (None, None)
        if not rr or control_plane(rel, policy) or matches(rel, policy.get('protected_paths') or []):
            return False
        if tool == 'Write' and any(has_secret(value) for value in strings(inp)):
            return False
        if is_audit_artifact_rel(rel, policy):
            return artifact_write_allowed(rel, policy)
        return action_allowed(policy, 'write' if tool == 'Write' else 'delete')
    return False


def shell_decision(cmd, sandbox, policy, ctx=None):
    """sandbox is recorded by the caller; it is not an allow/deny input.

    Under the lean profile the decision is lean_shell_decision; advisories go
    to ctx['advisories'] (a throwaway sink when no ctx is given).
    """
    del sandbox
    if lean_profile(policy):
        return lean_shell_decision(cmd, policy, ctx if ctx is not None else _lean_ctx())
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

CURSOR_REVIEW_TOOLS = ('rename_chat', 'browser_navigate', 'browser_tabs', 'browser_snapshot',
                      'browser_take_screenshot', 'browser_console_messages', 'browser_network_requests')


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
    inp = mcp_tool_input_object(data)
    if inp in (None, ''):
        inp = {}
    if tool in CURSOR_REVIEW_TOOLS:
        # MCP output files are not file-tool writes with verified confinement.
        if not isinstance(inp, dict):
            return False,'MCP_OUTPUT_PATH','review MCP input must be a JSON object so output paths can be checked'
        if any(inp.get(key) for key in ('filename', 'file_path', 'path', 'download_path')):
            return False,'MCP_OUTPUT_PATH','review MCP output must return through the tool; save evidence with scoped file tools'
        if tool == 'browser_tabs' and inp.get('action', 'list') != 'list' and browser_mode(policy) != 'interact':
            return False,'BROWSER_OBSERVE_ONLY','browser observation grants tab listing only'
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
        if sensitive_read(rel, policy.get('sensitive_read_paths') or []) or any(has_secret(value) for value in strings(inp)):
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
        return shell_decision(cmd, False, policy, _lean_ctx(root, data, root, grants=False))[0]
    name = tool.removeprefix('MCP:')
    if name in CURSOR_REVIEW_TOOLS:
        if isinstance(inp, dict) and any(inp.get(key) for key in ('filename', 'file_path', 'path', 'download_path')):
            return False
        if name == 'browser_tabs' and (not isinstance(inp, dict) or inp.get('action', 'list') != 'list'):
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
            if _LEAN_TIMEOUT_CLEAR and exc.code in BOOKKEEPING_TIMEOUT_CODES and _deadline_exhausted():
                return lean_timeout_allow(exc.code, str(exc))
            return deny(exc.code, str(exc))
    finally:
        if _RUNTIME_LOCK is not None:
            _RUNTIME_LOCK.__exit__(None, None, None)
            _RUNTIME_LOCK = None


def _main():
    global _READ_ONLY, _ACTIVE_ROOT, _ACTIVE_DATA, _SUPPORT_READY, _RUNTIME_LOCK, _READ_WARNING, _OUTSIDE_BOUNDARY, _TOOL_BASE
    global _LEAN_TIMEOUT_CLEAR
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
    _TOOL_BASE = tool_base(data, root)
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
    # Retry admission only. Checked before identity/budget so a fault there
    # cannot turn a permanently foreign target into debt; untrusted policy
    # keeps the prior admission.
    if state in {'OK', 'MISSING'}:
        _OUTSIDE_BOUNDARY = target_outside_roots(data, declared_roots(data, policy, root))

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
            _reset_session_metrics()
            started = time.perf_counter()
            closed, code, closure = support('eif_session').boundary(root, data)
            _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
            _TIMINGS['session_detail'] = _session_metrics()
            text=(f'EIF runtime policy loaded for {policy.get("project_id","<unset>")}; '
                  f'identity preflight: {msg}; {code}: {closure}. '
                  'Closure is enforced at actionable hooks; unresolved executed failures gate closure only; '
                  'lifecycle replies cannot prevent forced closure.')
            audit(root, data, 'allow', 'SESSION_READY' if ok and closed else code)
            return out(extra={'additional_context':text})
        return out(extra={'additional_context':f'EIF runtime policy state: {state}. {pmsg}. Do not treat sessionStart as a blocking control.'})

    # Observation only. Used to harvest the current page URL after click/navigation.
    # Cannot block the just-completed tool; subsequent interact uses the updated origin.
    if event in {'afterMCPExecution','postToolUse'}:
        record_executed_failure(root, data)
        support('eif_session').record_success(root, data)
        if state=='OK' and policy:
            note_observed_browser_page(root, data, policy, declared_roots(data,policy,root), after=True)
        audit(root,data,'allow','MCP_AFTER' if event=='afterMCPExecution' else 'POST_TOOL')
        return out()

    if event == 'postToolUseFailure':
        recorded = record_executed_failure(root, data)
        # A denial (native permission_denied, or an adapter callback with no
        # execution evidence) is never debt; an executed mutating failure is.
        audit(root, data, 'allow', 'POST_TOOL_FAILURE', extra={
            'failure_type': data.get('failure_type'),
            'execution_evidence': data.get('eif_execution_evidence'),
            'unresolved_recorded': recorded})
        return out()

    if event in {'stop', 'sessionEnd'}:
        _reset_session_metrics()
        started = time.perf_counter()
        # boundary() quarantines legacy v1 queue entries first and reports
        # SESSION_RETRY_REQUIRED while an executed failure is unresolved,
        # otherwise the commit/push/closure-proof result.
        legacy_count = support('eif_session').legacy_denials(root, data)
        closed, code, message = support('eif_session').boundary(root, data, quarantined=True)
        if legacy_count:
            write_operator_log('LEGACY_DENIED_QUARANTINE',
                f'{legacy_count} current-session legacy denial(s) retired without execution/success claim')
        failed = support('eif_session').unresolved(root, data)
        _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
        _TIMINGS['session_detail'] = _session_metrics()
        audit(root, data, 'allow', code)
        extra = {'additional_context': f'{code}: {message}'}
        if failed:
            extra['additional_context'] += (
                f'; {len(failed)} executed mutation failure(s) remain unresolved for this session only. '
                'No success/closure may be inferred. '
                'Use the explicit operator report/resolver rather than automatic retry loops.')
        if event == 'stop' and (not closed or failed):
            # Commit/push/closure-proof requirements need a follow-up even
            # when nothing failed; an executed failure takes precedence.
            # sessionEnd has no agent turn left to prompt.
            extra['followup_message'] = (
                'EIF unresolved executed mutation failure: repair or resolve it; do not claim closure.'
                if failed else
                f'EIF closure incomplete ({code}): {message} Do not claim closure.')
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

    lean = state == 'OK' and lean_profile(policy)
    if lean and event in {'preToolUse', 'beforeShellExecution', 'beforeReadFile', 'subagentStart'}:
        # Lean B1-B5 matchers run before session bookkeeping, so a deadline hit
        # during bookkeeping can be judged (HOOK_TIMEOUT_ADVISORY vs fail closed).
        started = time.perf_counter()
        try:
            _LEAN_TIMEOUT_CLEAR = bool(lean_timeout_precheck(root, data, policy, declared_roots(data, policy, root)))
        except Exception:
            _LEAN_TIMEOUT_CLEAR = False
        _TIMINGS['lean_precheck'] = round((time.perf_counter() - started) * 1000, 3)

    if event in {'preToolUse', 'beforeShellExecution', 'beforeMCPExecution', 'beforeReadFile', 'subagentStart'}:
        _reset_session_metrics()
        started = time.perf_counter()
        try:
            ready, code, message = support('eif_session').pre_check(root, data)
        except Exception as exc:
            ready, code, message = False, 'SESSION_STATE_FAILURE', f'{type(exc).__name__}: {exc}'
        _TIMINGS['session'] = round((time.perf_counter() - started) * 1000, 3)
        _TIMINGS['session_detail'] = _session_metrics()
        if not ready and _LEAN_TIMEOUT_CLEAR and code in BOOKKEEPING_TIMEOUT_CODES and _deadline_exhausted():
            return lean_timeout_allow(code, message)
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
        if not rr and lean:
            # Lean: a read outside every root is flagged, never blocked, except
            # env files, keys and credential stores (B3) and secret content.
            if lean_outside_secret(path, policy):
                audit(root,data,'deny','SENSITIVE_READ'); return deny('SENSITIVE_READ','direct model read of a secret outside the project is blocked')
            if has_secret(str(data.get('content') or '')):
                audit(root,data,'deny','SECRET_IN_READ'); return deny('SECRET_IN_READ','high-confidence secret-like content detected; use a scoped secure mechanism')
            _ADVISORIES.append({'reason_code':'FOREIGN_READ','enforcement':'advisory','message':'read target resolves outside all declared project roots'})
            audit(root,data,'allow','READ_OK'); return out()
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
        if sensitive_read(rel,sensitive):
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
        ctx=_lean_ctx(root, data, _TOOL_BASE)
        good,code,msg,extra=shell_decision(str(data.get('command') or ''),bool(data.get('sandbox')),policy,ctx)
        _ADVISORIES.extend(ctx['advisories'])
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
        if tool.startswith('Unmapped:'):
            # Claude Code tools the adapter reviewed as having no file/shell side
            # effect of their own. Strict keeps the adapter's fail-closed denial;
            # lean allows and flags them below, after identity and budget.
            if not lean:
                audit(root, data, 'deny', 'SHIM_TOOL_UNMAPPED')
                return deny('SHIM_TOOL_UNMAPPED', f'no verified guard adapter mapping for Claude Code tool {tool.removeprefix("Unmapped:")!r}; '
                            'opaque side effects cannot be authorised')
        elif tool not in supported and not tool.startswith('MCP:'):
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
            if _LEAN_TIMEOUT_CLEAR and code == 'BUDGET_STATE_FAILURE' and _deadline_exhausted():
                return lean_timeout_allow(code, bmsg)
            if lean and code in {'BUDGET_EXHAUSTED', 'NO_PROGRESS'}:
                # FLAG != BLOCK: the burst budget is a wrap-up signal, not a stop.
                _ADVISORIES.append({'reason_code': code, 'enforcement': 'advisory', 'message': bmsg})
                bextra = {'additional_context': (
                    f'WRAP_UP (advisory, lean profile): {bmsg}. This call is allowed. Park programme stage_note/'
                    'evidence via python .eif/runtime/programme/program.py, then continue or stop deliberately.')}
            elif code == 'BUDGET_STATE_FAILURE' and _READ_ONLY:
                # Defer emission until identity, source integrity, scope and
                # sensitive-path checks below have authorised this read.
                bextra = {'reason_code': code, 'additional_context': bmsg + '; read policy checks completed; repair budget state before mutations.'}
            else:
                audit(root,data,'deny',code)
                return deny(code,bmsg)

        if tool.startswith('Unmapped:'):
            _ADVISORIES.append({'reason_code': 'SHIM_TOOL_UNMAPPED', 'enforcement': 'advisory',
                                'message': f'reviewed no-side-effect Claude Code tool {tool.removeprefix("Unmapped:")} allowed'})
            audit(root, data, 'allow', 'TOOL_OK')
            return out(extra=bextra)

        # Generic path-bound tools: reads/writes cannot escape declared roots, including symlink escapes.
        path=tool_path(inp); rr,rel=resolve_path(path,roots) if path else (None,None)
        if path and not rr and lean and tool in READ_TOOLS:
            # Lean B5 judges writes only; an out-of-root read is flagged unless it is a secret (B3).
            if lean_outside_secret(path, policy):
                audit(root,data,'deny','SENSITIVE_TOOL_READ'); return deny('SENSITIVE_TOOL_READ','read/search of a secret outside the project is blocked')
            _ADVISORIES.append({'reason_code':'FOREIGN_PATH','enforcement':'advisory','message':'read/search target resolves outside all declared project roots'})
        elif path and not rr:
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
            if scopes and not matches(rel,scopes) and lean:
                _ADVISORIES.append({'reason_code':'OUT_OF_CHANGE_SCOPE','enforcement':'advisory','message':f'path outside accepted change scope: {rel}'})
            elif scopes and not matches(rel,scopes):
                audit(root,data,'deny','OUT_OF_CHANGE_SCOPE',rel); return deny('OUT_OF_CHANGE_SCOPE',f'path outside accepted change scope: {rel}')
            cls='write' if tool=='Write' else 'delete'
            if not action_allowed(policy,cls):
                audit(root,data,'deny','ACTION_'+cls.upper(),rel); return deny('ACTION_'+cls.upper(),f'{cls} action class not granted')
            if tool=='Write':
                for st in strings(inp):
                    if has_secret(st):
                        audit(root,data,'deny','SECRET_PREWRITE',rel); return deny('SECRET_PREWRITE','high-confidence secret-like literal blocked before file write')

        if tool in {'Read','ReadLints','Grep','Glob','List'} and path and rr:
            scopes=observation_scopes(policy)
            if scopes and not matches(rel,scopes):
                audit(root,data,'deny','OUT_OF_OBSERVATION_SCOPE',rel); return deny('OUT_OF_OBSERVATION_SCOPE',f'read/search outside accepted observation scope: {rel}')
            sensitive=policy.get('sensitive_read_paths') or []
            if sensitive_read(rel,sensitive):
                audit(root,data,'deny','SENSITIVE_TOOL_READ',rel); return deny('SENSITIVE_TOOL_READ',f'read/search blocked on sensitive path {rel}')

        if tool=='Shell':
            cmd=str(inp.get('command','')) if isinstance(inp,dict) else ''
            # preToolUse is a backup to beforeShellExecution. Sandbox is telemetry, not a deny input.
            ctx=_lean_ctx(root, data, _TOOL_BASE)
            good,code,why,extra=shell_decision(cmd, bool(inp.get('sandbox')) if isinstance(inp,dict) else False, policy, ctx)
            _ADVISORIES.extend(ctx['advisories'])
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

def operator_equivalent_cli(arguments):
    """External operator-only non-identical success resolver, no shell execution."""
    root = Path(__file__).resolve().parents[2]
    if len(arguments) != 4:
        raise ValueError('session-key, original-fingerprint and two reviewed event JSON files required')
    key, fp, old_file, new_file = arguments
    if not re.fullmatch(r'[0-9a-f]{64}', key) or not re.fullmatch(r'[0-9a-f]{64}', fp):
        raise ValueError('invalid operator session/fingerprint')
    old = json.loads(Path(old_file).read_text(encoding='utf-8'))
    new = json.loads(Path(new_file).read_text(encoding='utf-8'))
    if support('eif_session').fingerprint(old) != fp:
        raise ValueError('original event fingerprint mismatch')
    if support('eif_session').state_path(root, old).name != key + '.json':
        raise ValueError('session key does not match original event conversation/session')
    lock = verified_runtime(root)
    try:
        result = support('eif_session').operator_equivalent(
            root, root / '.eif/runtime-session' / (key + '.json'), old, new)
    finally:
        lock.__exit__(None, None, None)
    write_operator_log('SESSION_REVIEW', result, extra={
        'fingerprint':fp, 'review_kind':'EQUIVALENT_SUCCESS'})
    print(json.dumps({'ok': result == 'EQUIVALENT_SUCCESS_RECORDED', 'reason_code': 'SESSION_REVIEW',
                      'message': result}))
    return 0 if result == 'EQUIVALENT_SUCCESS_RECORDED' else 1


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
    if sys.argv[1] == '--report':
        print(json.dumps(support('eif_session').unresolved_report(_project_root()), indent=2))
        raise SystemExit(0)
    if sys.argv[1] == '--resolve-equivalent':
        raise SystemExit(operator_equivalent_cli(sys.argv[2:]))
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


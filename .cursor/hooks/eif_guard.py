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
import fnmatch, hashlib, json, os, re, subprocess, sys, threading, time
from pathlib import Path
from urllib.parse import unquote, urlparse

CONTROL_PLANE_DEFAULTS = [
    '.cursor/eif-runtime-policy.json', '.cursor/hooks.json', '.cursor/hooks/**',
    '.cursor/rules/eif-core.mdc', '.cursor/rules/eif-project-adapter.mdc',
    '.cursor/permissions.json', '.eif/PROJECT_MANIFEST.md', '.eif/AUTONOMY_POLICY.md', '.eif/ENVIRONMENT_POLICY.md', '.eif/RUNTIME_CAPABILITIES.md',
    '.eif/runtime-events.jsonl', '.eif/runtime-budget/**', '.eif/program/**', '.eif/runtime/programme/**', '.eif/upgrade-work/**',
    '.eif/hook-guard.log', '.eif/hook-guard.json',
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


HOOK_STDIN_MAX_BYTES = 1_048_576


def _hook_bytes_complete_json(raw: bytes) -> bool:
    """True when raw bytes contain at least one complete JSON value.

    Cursor may hold the hook pipe open after writing the payload. A complete
    object is a finished payload; waiting for EOF is the silent-kill path.
    """
    if not raw or not raw.strip():
        return False
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        try:
            text = raw.decode('utf-16')
        except UnicodeDecodeError:
            return False
    else:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            try:
                text = raw.decode('utf-16')
            except UnicodeDecodeError:
                return False
    text = text.strip()
    if not text:
        return False
    try:
        json.JSONDecoder().raw_decode(text)
        return True
    except json.JSONDecodeError:
        return False


def _read_hook_stdin_chunks(read_chunk) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        try:
            chunk = read_chunk()
        except InterruptedError:
            continue
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        joined = b''.join(chunks)
        if _hook_bytes_complete_json(joined):
            return joined
        if total >= HOOK_STDIN_MAX_BYTES:
            raise TimeoutError(
                'hook stdin exceeded max bytes without a complete JSON object; fail-closed'
            )
    return b''.join(chunks)


def read_hook_stdin_eof() -> bytes:
    """Read the Cursor hook pipe until a complete JSON value or EOF.

    Windows anonymous pipes return the first available chunk from a single
    os.read / FileIO.read. Stopping there is payload-size-dependent truncation
    and surfaces as HOOK_INPUT_INVALID (JSONDecodeError). Loop across chunks,
    but treat a complete JSON object as finished — do not wait for EOF.

    The decision watchdog must already be armed. A held-open pipe that never
    delivers a complete object is HOOK_TIMEOUT, never a silent host kill.
    """
    fd = None
    try:
        fd = sys.stdin.fileno()
    except Exception:
        fd = None
    if fd is None:
        buf = getattr(sys.stdin, 'buffer', None)
        if buf is None:
            try:
                return (sys.stdin.read() or '').encode('utf-8')
            except Exception:
                return b''
        return _read_hook_stdin_chunks(lambda: buf.read(65536))
    if os.name == 'nt':
        try:
            import msvcrt
            msvcrt.setmode(fd, os.O_BINARY)
        except Exception:
            pass
    return _read_hook_stdin_chunks(lambda: os.read(fd, 65536))


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
            text = raw.decode('utf-16')
    text = text.strip()
    if not text:
        raise ValueError('empty Cursor hook stdin')
    return json.loads(text)

# Crash / launcher / emit failures must be distinguishable from policy denials.
# Cursor failClosed treats empty/invalid stdout as a mute block with no rule name.
# deny() prefixes agent_message with EIF_GUARD_CRASH: or EIF_GUARD_POLICY: and
# sets eif_guard_class. PROGRAMME_GIT_STAGE is not a reason code in this tree.
# CONSULT 2026-09-04 (claude-opus CLI, sdk-cli): beforeReadFile failClosed must
# stay true. failClosed:false would allow SENSITIVE_READ / SECRET_IN_READ /
# FOREIGN_READ / OUT_OF_OBSERVATION_SCOPE into model context on hook crash.
# Verdict FAILCLOSED_BEFORE_READ: keep_true. Residual not acceptable.

CRASH_REASON_CODES = frozenset({
    'HOOK_INTERNAL_ERROR', 'HOOK_LAUNCHER_ERROR', 'HOOK_INPUT_INVALID',
    'HOOK_TIMEOUT', 'HOOK_EMIT_FAILURE',
})
# Live policy deny() / shell_decision / mcp_decision reason_code values in this file.
POLICY_REASON_CODES = frozenset({
    'ACTION_ARTIFACT_WRITE', 'ACTION_DELETE', 'ACTION_DEPENDENCY',
    'ACTION_DESTRUCTIVE_DATA', 'ACTION_FORCE_VCS', 'ACTION_IDENTITY_MUTATION',
    'ACTION_INFRASTRUCTURE', 'ACTION_NETWORK', 'ACTION_REMOTE_PUSH', 'ACTION_WRITE',
    'BOOTSTRAP', 'BOOTSTRAP_MCP', 'BROWSER_INTERACT_ORIGIN', 'BROWSER_OBSERVE_ONLY',
    'BROWSER_PUBLIC_MUTATE', 'BROWSER_UNSAFE', 'BUDGET', 'CONTROL_PLANE_PROTECTED',
    'FOREIGN_PATH', 'FOREIGN_READ', 'IDENTITY_MCP', 'IDENTITY_SHELL', 'IDENTITY_TOOL',
    'MCP_DENY', 'MCP_DESTRUCTIVE', 'MCP_NOT_GRANTED', 'MCP_POLICY_REQUIRED',
    'NETWORK_DESTINATION', 'OUT_OF_CHANGE_SCOPE', 'OUT_OF_OBSERVATION_SCOPE',
    'POLICY_INTEGRITY', 'POST_EDIT_SECRET', 'PROTECTED_PATH', 'SECRET_IN_READ',
    'SECRET_PREWRITE', 'SENSITIVE_READ', 'SENSITIVE_TOOL_READ', 'SHELL_DENY',
    'SHELL_POLICY_REQUIRED',
})
OBSERVATION_EVENTS = frozenset({
    'beforeReadFile', 'afterFileEdit', 'afterMCPExecution', 'postToolUse',
    'sessionStart', 'stop', 'subagentStart', 'subagentStop',
})
WATCHDOG_DEFAULT_SEC = 8.0
_EMITTED = False
_EMIT_RC = 1
_EMIT_LOCK = threading.Lock()
_DONE = threading.Event()
_WATCHDOG_ARMED = False


def _project_root() -> Path:
    env = os.environ.get('CURSOR_PROJECT_DIR') or os.environ.get('CLAUDE_PROJECT_DIR')
    if env:
        return Path(env)
    try:
        return Path(__file__).resolve().parent.parent.parent
    except Exception:
        return Path.cwd()


def _operator_log_path() -> Path:
    return _project_root() / '.eif' / 'hook-guard.log'


def watchdog_sec() -> float:
    """Seconds before the guard self-denies HOOK_TIMEOUT. Default 8.

    Host config (no EIF release): `.eif/hook-guard.json` `watchdog_sec`.
    Session/test override: environment variable `EIF_HOOK_WATCHDOG_SEC`.
    `<= 0` disables the watchdog. This is not Cursor's `hooks.json` `timeout`.
    """
    raw = os.environ.get('EIF_HOOK_WATCHDOG_SEC')
    if raw not in (None, ''):
        try:
            return float(raw)
        except ValueError:
            pass
    cfg = _project_root() / '.eif' / 'hook-guard.json'
    try:
        if cfg.is_file():
            data = json.loads(cfg.read_text(encoding='utf-8'))
            if isinstance(data, dict) and 'watchdog_sec' in data:
                return float(data['watchdog_sec'])
    except Exception:
        pass
    return WATCHDOG_DEFAULT_SEC


def write_operator_log(code, message, extra=None):
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
    except Exception:
        pass


def _write_stdout_bytes(data: bytes) -> bool:
    try:
        os.write(sys.stdout.fileno(), data)
        return True
    except Exception:
        pass
    try:
        buf = getattr(sys.stdout, 'buffer', None)
        if buf is not None:
            buf.write(data)
            buf.flush()
            return True
    except Exception:
        pass
    try:
        sys.stdout.write(data.decode('ascii'))
        sys.stdout.flush()
        return True
    except Exception:
        return False


def out(permission='allow', message=None, extra=None):
    """Emit one ASCII JSON decision on stdout.

    A successful permission JSON is exit 0 so failClosed does not treat an EIF
    deny/allow as a hook crash. A failed stdout write is HOOK_EMIT_FAILURE:
    log it and return non-zero. Mute exit-0 with empty stdout is the original bug.
    """
    global _EMITTED, _EMIT_RC
    obj = {'permission': permission}
    if extra:
        obj.update(extra)
    if message:
        obj.setdefault('user_message', message)
        obj.setdefault('agent_message', message)
    raw = (json.dumps(obj, ensure_ascii=True, separators=(',', ':')) + '\n').encode('ascii')
    with _EMIT_LOCK:
        if _EMITTED:
            return _EMIT_RC
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
            return 1
        _EMIT_RC = 0
    reason = obj.get('reason_code')
    if permission == 'deny' and reason in CRASH_REASON_CODES:
        write_operator_log(reason, message or '', extra={'permission': permission, 'stdout_wrote': True})
    return 0


def deny(code, message):
    crash = code in CRASH_REASON_CODES
    klass = 'crash' if crash else 'policy'
    prefix = 'EIF_GUARD_CRASH' if crash else 'EIF_GUARD_POLICY'
    return out(
        'deny',
        f'{prefix}: {code}: {message}',
        extra={'reason_code': code, 'eif_guard_class': klass},
    )


def _arm_watchdog():
    """Self-deny before the host runtime kills the hook with empty stdout.

    Must run before stdin is read. A held-open pipe never reaches EOF, so
    arming after the read made the host kill mute (no HOOK_TIMEOUT).
    """
    global _WATCHDOG_ARMED
    if _WATCHDOG_ARMED:
        return
    sec = watchdog_sec()
    if sec <= 0:
        return
    _WATCHDOG_ARMED = True

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
    env=os.environ.copy()
    env['GIT_OPTIONAL_LOCKS']='0'
    try:
        return subprocess.check_output(
            ['git','-C',str(root),*args],
            text=True, stderr=subprocess.DEVNULL, timeout=1.5, env=env,
        ).strip()
    except Exception:
        return ''

# Per-process cache: a same-repo repository_anchor must not spawn a second trio
# of git subprocesses. Quiet-path identity was six calls / ~1.5s on this project.
_GIT_SNAP = {}

def git_snapshot(root: Path):
    """Return (toplevel, remotes_text, root_commit_text). At most 3 git calls per repo per process."""
    try:
        key=str(Path(root).resolve())
    except Exception:
        key=str(root)
    hit=_GIT_SNAP.get(key)
    if hit is not None:
        return hit
    toplevel=git(root,'rev-parse','--show-toplevel')
    remotes=git(root,'remote','-v')
    rootc=git(root,'rev-list','--max-parents=0','HEAD')
    snap=(toplevel, remotes, rootc)
    _GIT_SNAP[key]=snap
    if toplevel:
        try:
            _GIT_SNAP.setdefault(str(Path(toplevel).resolve()), snap)
        except Exception:
            pass
    return snap

def observed_remotes(root: Path):
    vals=[]
    for line in git_snapshot(root)[1].splitlines():
        p=line.split()
        if len(p)>=2: vals.append(normalized_remote(p[1]))
    return sorted(set(vals))

def root_commit(root: Path):
    rows=git_snapshot(root)[2].splitlines()
    return rows[0] if len(rows)==1 else ''

def policy_path(root: Path):
    for rel in ['.cursor/eif-runtime-policy.json','.eif/runtime-policy.json']:
        p=root/rel
        if p.exists(): return p
    return root/'.cursor/eif-runtime-policy.json'

def load_policy(root: Path):
    p=policy_path(root)
    if not p.exists(): return 'MISSING',None,p,'runtime policy absent'
    try: pol=json.loads(p.read_text())
    except Exception as e: return 'MALFORMED',None,p,f'cannot parse runtime policy: {e}'
    try:
        normalize_shell_policy(pol.get('shell') or {'mode':'deny'})
        normalize_network_policy(pol.get('network') or {})
    except ValueError as e:
        return 'INVALID',pol,p,str(e)
    # Derived-source integrity. Runtime policy cannot remain valid after its accepted sources drift.
    for item in (pol.get('sources') or {}).values():
        if not isinstance(item,dict): continue
        rel=item.get('path'); expected=item.get('sha256')
        if not rel or not expected: continue
        src=(root/rel).resolve()
        try:
            src.relative_to(root.resolve())
        except Exception:
            return 'INVALID',pol,p,f'source path escapes project: {rel}'
        if not src.exists(): return 'INVALID',pol,p,f'policy source missing: {rel}'
        if sha256(src)!=expected: return 'INVALID',pol,p,f'policy source hash mismatch: {rel}; recompile accepted policy'
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
    for k in ['file_path','path','target_file','target_path','directory','cwd']:
        if isinstance(inp.get(k),str): return inp[k]
    return None

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
    observed_root=root_commit(root)
    if exp_root and observed_root!=exp_root:
        return False,f'IDENTITY_MISMATCH: root commit expected {exp_root}, observed {observed_root or "<none>"}'
    observed=observed_remotes(root)
    if exp_rem and observed!=exp_rem:
        return False,f'IDENTITY_MISMATCH: remote set expected {exp_rem}, observed {observed}'
    if exp_vcs:
        actual=Path(git_snapshot(root)[0] or root).resolve()
        if str(actual)!=str(Path(exp_vcs).resolve()):
            return False,f'IDENTITY_MISMATCH: vcs root expected {exp_vcs}, observed {actual}'
    for anchor in ident.get('repository_anchors') or []:
        ar=Path(anchor.get('allowed_root') or '').resolve()
        if not ar.exists(): return False,f'IDENTITY_MISMATCH: declared repository root missing: {ar}'
        # Same-repo duplicate of the primary identity block: reuse snapshot (0 extra git).
        arv=git_snapshot(ar)[0]
        arr=root_commit(ar)
        arem=observed_remotes(ar)
        ev=anchor.get('expected_vcs_root') or ''; er=anchor.get('root_commit') or ''
        erm=sorted(set(normalized_remote(x) for x in anchor.get('expected_remotes',[]) if x))
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
    except Exception: pass

PROGRESS_EVENTS = frozenset({'node.stage', 'evidence.add', 'node.accept', 'node.status'})
WRAP_CHECKPOINT_EVENTS = frozenset({'node.stage_note'})
MUTATING_TOOLS = frozenset({'Write', 'Delete'})

def _budget_dir(root: Path, policy) -> Path:
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    return root/sr/'runtime-budget'

def _programme_log_path(root: Path, policy) -> Path:
    sr=str((policy or {}).get('state_root') or '.eif').replace('\\','/').strip('/') or '.eif'
    return root/sr/'program'/'PROGRAM_LOG.ndjson'

def _programme_progress(root: Path, policy, after_seq: int):
    """Return (head_seq, new_event_types). Never fail-closed on a missing/unreadable log."""
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
    except Exception:
        return after_seq, set()
    return head, kinds

def _mutating_fingerprint(data):
    """Identify a repeated mutating file action.

    Path-key order matches tool_path(): file_path, path, target_file,
    target_path, directory, cwd. Blank strings are skipped so an empty
    preferred key does not hide a real fallback path. None does not
    become the literal 'None'. Separators use a single-backslash replace.
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
    return f'{tool}:{path.replace("\\","/").lower()}'


def _persist_budget(path: Path, state):
    try:
        path.write_text(json.dumps(state), encoding='utf-8')
        return True,''
    except Exception:
        return False,'BUDGET_GUARD_FAILURE: cannot persist runtime budget state'

def budget_ok(root: Path, data, policy):
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
    conv=re.sub(r'[^A-Za-z0-9_.-]','_',str(data.get('conversation_id') or 'unknown'))[:120]
    d=_budget_dir(root, policy); d.mkdir(parents=True, exist_ok=True); p=d/f'{conv}.json'
    now=time.time()
    state={'session_first_ts':now,'burst_first_ts':now,'burst_id':1,'tool_calls':0,
           'wrap_up_signaled':False,'last_progress_seq':0,'last_mut_fp':'','repeat_mut':0}
    try:
        if p.exists(): state.update(json.loads(p.read_text(encoding='utf-8')))
    except Exception:
        pass
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
    if repeat_limit and int(state.get('repeat_mut') or 0)>int(repeat_limit):
        return False,f'NO_PROGRESS: repeated mutating action {fp} x{state["repeat_mut"]}',None
    if max_calls and state['tool_calls']>int(max_calls):
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

def _programme_runtime_shell_invoke(cmd: str) -> bool:
    """True when shell is invoking the installed programme entry point (read/execute, not mutate)."""
    norm = cmd.replace('\\', '/')
    return bool(re.search(
        r'python(?:3)?\s+(?:["\'])?(?:\./)?\.eif/runtime/programme/program\.py(?:\s|["\']|$)',
        norm,
        re.I,
    ))

def shell_path_consequence(cmd, policy):
    """Defense-in-depth only. Does not contain arbitrary child processes."""
    if _programme_runtime_shell_invoke(cmd):
        return None
    roots=[Path(x) for x in (policy.get('allowed_roots') or []) if x]
    protected=policy.get('protected_paths') or []
    base=roots[0] if roots else None
    for cand in _path_candidates(cmd):
        rel=cand.replace('\\','/')
        while rel.startswith('./'):
            rel=rel[2:]
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
        return _shell_result(True,'SHELL_WORKSPACE','ordinary workspace shell; not process containment')
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

def main(raw=None):
    try:
        if raw is None:
            _arm_watchdog()
            raw = read_hook_stdin_eof()
        data = parse_cursor_hook_stdin(raw)
    except TimeoutError as e:
        return deny('HOOK_TIMEOUT', str(e) or 'unbounded hook stdin; fail-closed')
    except Exception as e:
        return deny('HOOK_INPUT_INVALID', f'cannot parse Cursor hook input: {type(e).__name__}: {e}')
    event=data.get('hook_event_name','')
    root=select_root(data)
    state,policy,pp,pmsg=load_policy(root)

    # sessionStart is context only on Cursor; it is never used as a blocking boundary.
    if event=='sessionStart':
        if state=='OK':
            text=(f'EIF runtime policy loaded for {policy.get("project_id","<unset>")}. '
                  f'Blocking identity is re-checked at actionable hooks; sessionStart does not spawn git.')
            return out(extra={'additional_context':text})
        return out(extra={'additional_context':f'EIF runtime policy state: {state}. {pmsg}. Do not treat sessionStart as a blocking control.'})

    # Observation only. Used to harvest the current page URL after click/navigation.
    # Cannot block the just-completed tool; subsequent interact uses the updated origin.
    if event in {'afterMCPExecution','postToolUse'}:
        if state=='OK' and policy:
            note_observed_browser_page(root, data, policy, declared_roots(data,policy,root), after=True)
        audit(root,data,'allow','MCP_AFTER' if event=='afterMCPExecution' else 'POST_TOOL')
        return out()

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
            # beforeReadFile is observation. Do not spawn git-identity here
            # (duplicate same-repo anchors were six subprocesses / ~1.5s). Blocking
            # identity is re-checked at beforeShellExecution / preToolUse / beforeMCPExecution.
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
        return out() if good else deny(code,msg)

    if event=='beforeMCPExecution':
        if state!='OK': audit(root,data,'deny','MCP_POLICY_REQUIRED'); return deny('MCP_POLICY_REQUIRED','accepted runtime policy required before MCP execution')
        ok,msg=identity_ok(root,policy)
        if not ok: audit(root,data,'deny','IDENTITY_MCP'); return deny('IDENTITY_MCP',msg)
        good,code,msg=mcp_decision(data,policy,root,roots); audit(root,data,'allow' if good else 'deny',code)
        return out() if good else deny(code,msg)

    if event=='preToolUse':
        tool=str(data.get('tool_name') or ''); inp=data.get('tool_input') or {}
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
        if not bok: audit(root,data,'deny','BUDGET'); return deny('BUDGET',bmsg)

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

        if tool in {'Read','Grep'} and path:
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

        audit(root,data,'allow','TOOL_OK',rel); return out(extra=bextra)

    # stop/subagent/workspace lifecycle are audit surfaces, not blocking budgets unless separately proven.
    audit(root,data,'allow','EVENT_OBSERVED')
    return out()

if __name__=='__main__':
    _arm_watchdog()
    raw=b''
    try:
        raw=read_hook_stdin_eof()
    except TimeoutError as e:
        rc=deny('HOOK_TIMEOUT', str(e) or 'unbounded hook stdin; fail-closed')
        raise SystemExit(0 if rc is None else rc)
    except Exception as e:
        try:
            rc=deny('HOOK_INPUT_INVALID', f'cannot read Cursor hook stdin: {type(e).__name__}: {e}')
        except Exception:
            rc=0
        raise SystemExit(0 if rc is None else rc)
    try:
        rc=main(raw)
    except BrokenPipeError:
        rc=deny('HOOK_INTERNAL_ERROR', 'BrokenPipeError while producing a decision')
    except Exception as e:
        try:
            rc=deny('HOOK_INTERNAL_ERROR', f'{type(e).__name__}: {e}')
        except Exception:
            fallback=(
                '{"permission":"deny","reason_code":"HOOK_EMIT_FAILURE","eif_guard_class":"crash",'
                '"user_message":"EIF_GUARD_CRASH: HOOK_EMIT_FAILURE: unrecoverable guard crash",'
                '"agent_message":"EIF_GUARD_CRASH: HOOK_EMIT_FAILURE: unrecoverable guard crash"}\n'
            ).encode('ascii')
            wrote=_write_stdout_bytes(fallback)
            write_operator_log('HOOK_EMIT_FAILURE', f'{type(e).__name__}: {e}', extra={'stdout_wrote': wrote, 'eif_guard_class': 'crash'})
            rc=0 if wrote else 1
    try:
        raise SystemExit(0 if rc is None else rc)
    except BrokenPipeError:
        raise SystemExit(1 if rc else 0)

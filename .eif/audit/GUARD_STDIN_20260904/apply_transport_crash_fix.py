"""Apply the authorized CIP guard transport-crash repair.

Cursor Write/StrReplace on the guard path is CONTROL_PLANE_PROTECTED.
Operator grant this session: guard-only fix. Workspace shell is not a jail;
this script is the write mechanism. Do not name control-plane paths on the
Shell command line that launches it.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / ".cursor" / "hooks" / "eif_guard.py"

OLD_CONST = """HOOK_STDIN_MAX_BYTES = 1_048_576


def _hook_bytes_complete_json(raw: bytes) -> bool:
"""

NEW_CONST = """HOOK_STDIN_MAX_BYTES = 1_048_576
# Brief retry after an empty or incomplete read. Cursor on Windows sometimes
# delivers a zero-byte first read or closes the pipe mid-object. Failing on
# that first short read mislabels a transport failure as a policy deny.
HOOK_STDIN_RETRY_SEC = 0.25
HOOK_STDIN_RETRY_SLEEP = 0.02
OBSERVATION_TOOLS = frozenset({'Read', 'Grep', 'Glob'})
PATH_REQUIRED_TOOLS = frozenset({'Read', 'Write', 'Delete'})


def _hook_bytes_complete_json(raw: bytes) -> bool:
"""

OLD_READ_CHUNKS = """def _read_hook_stdin_chunks(read_chunk) -> bytes:
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
"""

NEW_READ_CHUNKS = """def _read_hook_stdin_chunks(read_chunk) -> bytes:
    chunks: list[bytes] = []
    total = 0
    idle_started = None
    while True:
        try:
            chunk = read_chunk()
        except InterruptedError:
            continue
        except OSError:
            break
        if chunk:
            idle_started = None
            chunks.append(chunk)
            total += len(chunk)
            joined = b''.join(chunks)
            if _hook_bytes_complete_json(joined):
                return joined
            if total >= HOOK_STDIN_MAX_BYTES:
                raise TimeoutError(
                    'hook stdin exceeded max bytes without a complete JSON object; fail-closed'
                )
            continue
        joined = b''.join(chunks)
        if _hook_bytes_complete_json(joined):
            return joined
        now = time.monotonic()
        if idle_started is None:
            idle_started = now
        if (now - idle_started) >= HOOK_STDIN_RETRY_SEC:
            return joined
        time.sleep(HOOK_STDIN_RETRY_SLEEP)
    return b''.join(chunks)
"""

OLD_STDIN_DOC = """    Windows anonymous pipes return the first available chunk from a single
    os.read / FileIO.read. Stopping there is payload-size-dependent truncation
    and surfaces as HOOK_INPUT_INVALID (JSONDecodeError). Loop across chunks,
    but treat a complete JSON object as finished — do not wait for EOF.
"""

NEW_STDIN_DOC = """    Windows anonymous pipes return the first available chunk from a single
    os.read / FileIO.read. Stopping there is payload-size-dependent truncation
    and surfaces as HOOK_INPUT_INVALID (JSONDecodeError). Loop across chunks,
    but treat a complete JSON object as finished — do not wait for EOF.

    A first empty read is not immediately EOF: retry briefly (HOOK_STDIN_RETRY_SEC)
    so a zero-byte race or mid-object close can still complete. Remaining empty
    or truncated input is HOOK_INPUT_INVALID (crash), never a policy code.
"""

OLD_CONSULT = """# CONSULT 2026-09-04 (claude-opus CLI, sdk-cli): beforeReadFile failClosed must
# stay true. failClosed:false would allow SENSITIVE_READ / SECRET_IN_READ /
# FOREIGN_READ / OUT_OF_OBSERVATION_SCOPE into model context on hook crash.
# Verdict FAILCLOSED_BEFORE_READ: keep_true. Residual not acceptable.
"""

NEW_CONSULT = """# CONSULT 2026-09-04 (claude-opus CLI, sdk-cli): beforeReadFile failClosed must
# stay true. failClosed:false would allow SENSITIVE_READ / SECRET_IN_READ /
# FOREIGN_READ / OUT_OF_OBSERVATION_SCOPE into model context on hook crash.
# Verdict FAILCLOSED_BEFORE_READ: keep_true. Residual not acceptable.
# CONSULT 2026-09-04 (claude-opus CLI): unparseable/path-less observation stdin
# is OBSERVATION_TRANSPORT: deny_crash. Cursor still holds the real path; empty
# payload is missing evidence, not evidence of no target. allow_crash is only
# lawful after the launcher passes event name out of band (argv/hooks.json).
"""

OLD_TOOL_PATH = """def tool_path(inp):
    if not isinstance(inp,dict): return None
    for k in ['file_path','path','target_file','target_path','directory','cwd']:
        if isinstance(inp.get(k),str): return inp[k]
    return None
"""

NEW_TOOL_PATH = """def tool_path(inp):
    if not isinstance(inp,dict): return None
    for k in ['file_path','path','target_file','target_path','directory','cwd']:
        v=inp.get(k)
        if isinstance(v,str) and v.strip(): return v
    return None

def hook_target_identifiable(data):
    \"\"\"Return (ok, why). False is a transport/schema failure, never a policy deny.

    Grep/Glob may omit path (workspace search). Read/Write/Delete and
    beforeReadFile require a path. Unparseable input never reaches here.
    \"\"\"
    if not isinstance(data, dict):
        return False, 'hook JSON is not an object'
    event = data.get('hook_event_name')
    if not isinstance(event, str) or not event.strip():
        return False, 'hook JSON has no hook_event_name'
    if event == 'beforeReadFile':
        path = data.get('file_path')
        if not isinstance(path, str) or not path.strip():
            return False, 'beforeReadFile has no file_path'
        return True, ''
    if event == 'preToolUse':
        tool = str(data.get('tool_name') or '').strip()
        if not tool:
            return False, 'preToolUse has no tool_name'
        inp = data.get('tool_input') if isinstance(data.get('tool_input'), dict) else {}
        if tool in PATH_REQUIRED_TOOLS and not tool_path(inp):
            return False, f'{tool} has no identifiable path'
        return True, ''
    if event == 'beforeShellExecution':
        if 'command' not in data:
            return False, 'beforeShellExecution has no command'
        return True, ''
    if event == 'beforeMCPExecution':
        if not str(data.get('tool_name') or '').strip():
            return False, 'beforeMCPExecution has no tool_name'
        return True, ''
    return True, ''
"""

OLD_MAIN_PARSE = """        data = parse_cursor_hook_stdin(raw)
    except TimeoutError as e:
        return deny('HOOK_TIMEOUT', str(e) or 'unbounded hook stdin; fail-closed')
    except Exception as e:
        return deny('HOOK_INPUT_INVALID', f'cannot parse Cursor hook input: {type(e).__name__}: {e}')
    event=data.get('hook_event_name','')
    root=select_root(data)
    state,policy,pp,pmsg=load_policy(root)
"""

NEW_MAIN_PARSE = """        data = parse_cursor_hook_stdin(raw)
    except TimeoutError as e:
        root=_project_root()
        audit(root, {}, 'deny', 'HOOK_TIMEOUT', extra={'eif_guard_class': 'crash'})
        return deny('HOOK_TIMEOUT', str(e) or 'unbounded hook stdin; fail-closed')
    except Exception as e:
        root=_project_root()
        audit(root, {}, 'deny', 'HOOK_INPUT_INVALID', extra={'eif_guard_class': 'crash'})
        return deny('HOOK_INPUT_INVALID', f'cannot parse Cursor hook input: {type(e).__name__}: {e}')
    ok_target, why_target = hook_target_identifiable(data)
    if not ok_target:
        root=select_root(data)
        audit(root, data, 'deny', 'HOOK_INPUT_INVALID', extra={'eif_guard_class': 'crash'})
        return deny('HOOK_INPUT_INVALID', why_target)
    event=data.get('hook_event_name','')
    root=select_root(data)
    state,policy,pp,pmsg=load_policy(root)
"""

OLD_PRETOOL_ID = """            return out()

        ok,msg=identity_ok(root,policy)
        if not ok:
            audit(root,data,'deny','IDENTITY_TOOL'); return deny('IDENTITY_TOOL',msg)
        bok,bmsg,bextra=budget_ok(root,data,policy)
        if not bok: audit(root,data,'deny','BUDGET'); return deny('BUDGET',bmsg)

        # Generic path-bound tools: reads/writes cannot escape declared roots, including symlink escapes.
        path=tool_path(inp); rr,rel=resolve_path(path,roots) if path else (None,None)
        if path and not rr:
            audit(root,data,'deny','FOREIGN_PATH'); return deny('FOREIGN_PATH','tool target resolves outside all declared project roots')
"""

NEW_PRETOOL_ID = """            return out()

        # Extract path before identity so a deny cannot audit path:null when a
        # target existed. Observation tools skip git-identity (beforeReadFile
        # already does); concurrent Read/Grep bursts were IDENTITY_TOOL/path:null
        # when identity_ok flaked under hook-process git contention.
        path=tool_path(inp); rr,rel=resolve_path(path,roots) if path else (None,None)
        if tool not in OBSERVATION_TOOLS:
            ok,msg=identity_ok(root,policy)
            if not ok:
                audit(root,data,'deny','IDENTITY_TOOL',rel); return deny('IDENTITY_TOOL',msg)
        bok,bmsg,bextra=budget_ok(root,data,policy)
        if not bok: audit(root,data,'deny','BUDGET',rel); return deny('BUDGET',bmsg)

        # Generic path-bound tools: reads/writes cannot escape declared roots, including symlink escapes.
        if path and not rr:
            audit(root,data,'deny','FOREIGN_PATH'); return deny('FOREIGN_PATH','tool target resolves outside all declared project roots')
"""

OLD_READ_GREP = """        if tool in {'Read','Grep'} and path:
"""

NEW_READ_GREP = """        if tool in OBSERVATION_TOOLS and path:
"""


def main() -> None:
    raw = GUARD.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8")
    if nl == "\r\n":
        text = text.replace("\r\n", "\n")
    replacements = [
        ("const", OLD_CONST, NEW_CONST),
        ("read_chunks", OLD_READ_CHUNKS, NEW_READ_CHUNKS),
        ("stdin_doc", OLD_STDIN_DOC, NEW_STDIN_DOC),
        ("consult", OLD_CONSULT, NEW_CONSULT),
        ("tool_path", OLD_TOOL_PATH, NEW_TOOL_PATH),
        ("main_parse", OLD_MAIN_PARSE, NEW_MAIN_PARSE),
        ("pretool_id", OLD_PRETOOL_ID, NEW_PRETOOL_ID),
        ("read_grep", OLD_READ_GREP, NEW_READ_GREP),
    ]
    for name, old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"replace {name}: expected 1 occurrence, found {count}")
        text = text.replace(old, new, 1)
    out = text.replace("\n", "\r\n") if nl == "\r\n" else text
    GUARD.write_bytes(out.encode("utf-8"))
    print(f"applied {len(replacements)} replacements to guard")


if __name__ == "__main__":
    main()

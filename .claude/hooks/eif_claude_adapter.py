#!/usr/bin/env python3
"""Claude Code hook shim for eif_guard.py.

Translates Claude Code's hook JSON (PascalCase hook_event_name, Bash/Edit/
MultiEdit/... tool_name vocabulary, mcp__<server>__<tool> naming) into the
Cursor-shaped payload eif_guard.py expects, invokes the project's already
-installed .cursor/hooks/eif_guard.py UNCHANGED as a subprocess (never
imported, never edited), and translates its allow/deny decision back into
Claude Code's PreToolUse hookSpecificOutput schema.

FAIL-CLOSED CONTRACT (see BACKLOG-204):
  - Any tool_name this module has not explicitly reviewed and mapped is
    denied by the shim itself (SHIM_TOOL_UNMAPPED) without ever reaching
    the guard subprocess.
  - Any hook_event_name this module has not explicitly mapped is denied
    (SHIM_EVENT_UNMAPPED).
  - Any failure to parse input, locate the guard, spawn python, or obtain
    a single well-formed decision JSON from the guard is a fail-closed
    deny (bare stderr reason + exit 2, per Claude Code's documented rule
    that exit code 2 alone blocks regardless of stdout).
  - Exactly one JSON object is ever written to stdout, and only on the
    success path; every fail-closed path writes stderr only.

Guard's internal self-denial watchdog defaults to 8s (WATCHDOG_DEFAULT_SEC
in eif_guard.py) and cannot be configured above that ceiling. SHIM_TIMEOUT_SEC
below must stay above it (headroom for process spawn + I/O) and the Claude
Code hook `timeout` configured in .claude/settings.json must stay above
SHIM_TIMEOUT_SEC (headroom for OS process-spawn latency). See BACKLOG-204
for the recommended settings.json timeout value.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAX_HOOK_INPUT_BYTES = 10 * 1024 * 1024

# Guard's own watchdog self-denies at <=8s (WATCHDOG_DEFAULT_SEC in eif_guard.py).
# This must stay above that so the guard's own structured HOOK_TIMEOUT deny
# normally wins; it is a belt-and-suspenders backstop for the case where the
# interpreter hangs before the guard's watchdog thread even starts.
SHIM_TIMEOUT_SEC = 9.5

ADAPTER_VERSION = 'eif-claude-adapter/3'


def shim_timeout_sec() -> float:
    """Test-only override, mirroring eif_guard.py's EIF_HOOK_WATCHDOG_SEC pattern.

    Can only shrink the timeout below SHIM_TIMEOUT_SEC, never raise it above
    the documented safe default; an invalid or out-of-range value is ignored.
    """
    raw = os.environ.get('EIF_CLAUDE_ADAPTER_TIMEOUT_SEC')
    if raw:
        try:
            value = float(raw)
            if 0 < value <= SHIM_TIMEOUT_SEC:
                return value
        except ValueError:
            pass
    return SHIM_TIMEOUT_SEC

# --- tool_name translation -------------------------------------------------

# Claude Code tool_name -> Cursor tool_name eif_guard.py understands.
# Every value here is one eif_guard.py already lists in its `supported` set
# (preToolUse) at eif_guard.py ~line 2096-2097.
DIRECT_TOOL_MAP = {
    'Bash': 'Shell',
    # Same tool_input shape as Bash (command/description/timeout/
    # run_in_background, per the Claude Code hooks reference); on Windows it can
    # be the only shell tool registered, so it must be gated exactly like Bash.
    'PowerShell': 'Shell',
    'Read': 'Read',
    'Edit': 'Write',
    'MultiEdit': 'Write',
    'Write': 'Write',
    'Glob': 'Glob',
    'Grep': 'Grep',
    'WebFetch': 'WebFetch',
    'WebSearch': 'WebSearch',
}

# tool_path() in eif_guard.py (line ~662-666) only reads these keys, in this
# order: file_path, path, target_file, target_path, directory. NotebookEdit's
# tool_input carries notebook_path, which is not in that list, so it must be
# aliased or every control-plane/protected-path/sensitive-path check silently
# stops seeing NotebookEdit writes.
NOTEBOOK_PATH_KEYS = ('notebook_path',)

# Tools with no filesystem/exec/network side effect of their own: spawning a
# subagent or prompting the user does not read, write, execute, or reach the
# network. (A subagent's own tool calls each re-enter PreToolUse separately,
# carrying agent_id/agent_type, and are gated there like any other call.)
# Agent is Claude Code's current name for the subagent tool (formerly Task).
# ToolSearch only loads deferred tool schemas into the session; every tool it
# surfaces is still gated here by name when it is actually called.
# Keep this list narrow and add to it only after the same review this file's
# header documents for every other entry.
NO_SIDE_EFFECT_TOOLS = frozenset({'Task', 'Agent', 'ToolSearch', 'AskUserQuestion', 'EnterPlanMode', 'ExitPlanMode'})

EVENT_MAP = {
    'PreToolUse': 'preToolUse',
    'PostToolUse': 'postToolUse',
    'PostToolUseFailure': 'postToolUseFailure',
    'Stop': 'stop',
    'SessionStart': 'sessionStart',
    'SessionEnd': 'sessionEnd',
    'SubagentStart': 'subagentStart',
}

# Events Claude Code will actually block on via hookSpecificOutput.permissionDecision.
# Per the Claude Code hooks reference: only PreToolUse's permissionDecision is
# honored as a block; every other mapped event is informational there too, so a
# shim bug on those paths cannot become a false-allow of a side-effecting action.
BLOCKING_EVENTS = frozenset({'PreToolUse'})


class ShimDenial(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _stderr(text):
    sys.stderr.write(text.rstrip('\n') + '\n')
    sys.stderr.flush()


def fail_closed(code, message):
    """The only path allowed to exit without a stdout decision. Never writes stdout."""
    _stderr(f'EIF claude-code adapter fault {code}: {message}')
    return 2


_EMITTED = False


def emit(obj):
    """Write exactly one JSON decision to stdout. Calling this twice is a bug."""
    global _EMITTED
    if _EMITTED:
        raise RuntimeError('eif_claude_adapter emitted twice in one process')
    _EMITTED = True
    sys.stdout.write(json.dumps(obj, ensure_ascii=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()


def read_stdin_bytes(stream) -> bytes:
    raw = stream.read(MAX_HOOK_INPUT_BYTES + 1)
    if len(raw) > MAX_HOOK_INPUT_BYTES:
        raise ValueError(f'claude-code hook input exceeds {MAX_HOOK_INPUT_BYTES} bytes')
    return raw


def resolve_guard(payload: dict):
    """(root, guard_path, searched) for the project whose guard must decide this call.

    CLAUDE_PROJECT_DIR (the session's project root, which Claude Code exports to
    every hook command) first; then the payload cwd and each of its parents, so a
    session whose shell has moved into a subfolder still reaches the project's
    guard. The shim's own process cwd is never a candidate: a hook launched from
    an unrelated folder must not borrow whatever guard happens to sit there.
    root and guard_path are None when no candidate holds a guard.
    """
    searched = []
    env_root = os.environ.get('CLAUDE_PROJECT_DIR')
    if env_root:
        try:
            root = Path(env_root).resolve()
            searched.append(str(root))
            guard_path = discover_guard(root)
            if guard_path is not None:
                return root, guard_path, searched
        except Exception:
            pass
    cwd = payload.get('cwd')
    if isinstance(cwd, str) and cwd.strip():
        try:
            start = Path(cwd).resolve()
        except Exception:
            start = None
        if start is not None:
            for candidate in (start, *start.parents):
                searched.append(str(candidate))
                guard_path = discover_guard(candidate)
                if guard_path is not None:
                    return candidate, guard_path, searched
    return None, None, searched


def mcp_tool_split(tool_name: str):
    """mcp__<server>__<tool> -> (server, tool). Malformed names return (None, None)."""
    if not tool_name.startswith('mcp__'):
        return None, None
    rest = tool_name[len('mcp__'):]
    if '__' not in rest:
        return None, None
    server, tool = rest.split('__', 1)
    if not server or not tool:
        return None, None
    return server, tool


# --- post-execution evidence -------------------------------------------------
#
# eif_session.record_success clears a retry obligation only for a Shell call
# whose tool_output carries an integer exitCode == 0. Claude Code reports no
# exit code on success, so it is derived from the event itself. Evidence, from
# the Claude Code hooks reference (code.claude.com/docs/en/hooks.md, read
# 2026-09-23):
#   - PostToolUse hooks "fire after a tool has already executed successfully";
#     Bash's tool_response is {stdout, stderr, interrupted, isImage}.
#   - PostToolUseFailure: "For Bash and PowerShell, a command that ran and
#     exited produces a first line `Exit code N`" in `error`; the documented
#     failing `npm test` example (Exit code 1) arrives on that event.
# So exit 0 is recorded only for a foreground Bash or PowerShell PostToolUse
# that was not interrupted (both translate to Shell). Anything else carries no exitCode and the obligation stays.
# backgroundTaskId / returnCodeInterpretation are not in the reference; their
# presence can only withhold success, never grant it.
EXIT_CODE_LINE = re.compile(r'Exit code (-?\d+)')


def shell_success_output(payload: dict):
    response = payload.get('tool_response')
    tool_input = payload.get('tool_input') if isinstance(payload.get('tool_input'), dict) else {}
    if not isinstance(response, dict) or response.get('interrupted') is not False:
        return None
    if tool_input.get('run_in_background') is True:
        return None
    if response.get('backgroundTaskId') or response.get('returnCodeInterpretation'):
        return None
    return {'exitCode': 0}


def failure_summary(payload: dict) -> str:
    """The guard audits this label; the raw error text can hold command output."""
    if payload.get('is_interrupt') is True:
        return 'interrupt'
    error = payload.get('error')
    match = EXIT_CODE_LINE.match(error) if isinstance(error, str) else None
    return f'exit_code_{match.group(1)}' if match else 'error'


def translate_pretooluse(payload: dict) -> dict:
    tool_name = payload.get('tool_name')
    tool_input = payload.get('tool_input')
    if not isinstance(tool_name, str) or not tool_name:
        raise ShimDenial('SHIM_INPUT_INVALID', 'PreToolUse requires a nonempty tool_name')
    if not isinstance(tool_input, dict):
        tool_input = {}

    if tool_name in NO_SIDE_EFFECT_TOOLS:
        return {'bypass': True}

    if tool_name in DIRECT_TOOL_MAP:
        return {'tool_name': DIRECT_TOOL_MAP[tool_name], 'tool_input': dict(tool_input)}

    if tool_name == 'NotebookEdit':
        translated_input = dict(tool_input)
        if 'file_path' not in translated_input:
            for key in NOTEBOOK_PATH_KEYS:
                if isinstance(translated_input.get(key), str) and translated_input[key].strip():
                    translated_input['file_path'] = translated_input[key]
                    break
        return {'tool_name': 'Write', 'tool_input': translated_input}

    server, sub_tool = mcp_tool_split(tool_name)
    if server is not None:
        extra = {'tool_name': f'MCP:{sub_tool}', 'tool_input': dict(tool_input),
                  'command': f'mcp__{server}'}
        return extra

    raise ShimDenial(
        'SHIM_TOOL_UNMAPPED',
        f'no verified guard adapter mapping for Claude Code tool {tool_name!r}; '
        'opaque side effects cannot be authorised (see eif_claude_adapter.py NO_SIDE_EFFECT_TOOLS '
        'and DIRECT_TOOL_MAP to extend this deliberately)',
    )


def translate_request(payload: dict) -> dict:
    event = payload.get('hook_event_name')
    if not isinstance(event, str) or event not in EVENT_MAP:
        raise ShimDenial('SHIM_EVENT_UNMAPPED', f'no verified guard mapping for hook_event_name {event!r}')

    cursor_event = EVENT_MAP[event]
    base = {
        'hook_event_name': cursor_event,
        'cwd': payload.get('cwd'),
        'conversation_id': payload.get('session_id'),
        'cursor_version': ADAPTER_VERSION,
    }
    for passthrough in ('agent_id', 'agent_type'):
        if payload.get(passthrough) is not None:
            base[passthrough] = payload[passthrough]

    if event == 'PreToolUse':
        result = translate_pretooluse(payload)
        if result.get('bypass'):
            return {'bypass': True, 'cc_event': event}
        base.update({k: v for k, v in result.items()})
    elif event in ('PostToolUse', 'PostToolUseFailure'):
        # Same translation as PreToolUse, so the guard fingerprints the
        # completed call exactly as it fingerprinted the request (a success
        # clears only the obligation whose fingerprint it matches). These
        # events never block, so an unmapped tool passes through by name.
        try:
            result = translate_pretooluse(payload)
        except ShimDenial:
            result = {'bypass': True}
        if result.get('bypass'):
            tool_name = payload.get('tool_name')
            tool_input = payload.get('tool_input')
            result = {'tool_name': tool_name if isinstance(tool_name, str) else '',
                      'tool_input': tool_input if isinstance(tool_input, dict) else {}}
        base.update(result)
        if event == 'PostToolUse' and base['tool_name'] == 'Shell':
            output = shell_success_output(payload)
            if output is not None:
                base['tool_output'] = output
        if event == 'PostToolUseFailure':
            base['failure_type'] = failure_summary(payload)
    # Stop / SessionStart / SessionEnd / SubagentStart need no extra fields:
    # eif_guard.py's handlers for these read only hook_event_name/cwd/conversation_id
    # and (for subagentStart) agent_id/agent_type, already copied above.

    base['cc_event'] = event
    return base


def discover_guard(root: Path):
    guard_path = root / '.cursor' / 'hooks' / 'eif_guard.py'
    return guard_path if guard_path.is_file() else None


def invoke_guard(root: Path, guard_path: Path, translated: dict):
    # cwd is the root resolved above, not the session's shell folder:
    # eif_guard.select_root() tries the payload cwd before its own process cwd,
    # so a shell sitting in another project with its own policy would otherwise
    # have that project's policy decide a call this project's guard was chosen for.
    request = {k: v for k, v in translated.items() if k != 'cc_event'}
    request['cwd'] = str(root)
    payload_bytes = json.dumps(request).encode('utf-8')
    env = dict(os.environ)
    env['CLAUDE_PROJECT_DIR'] = str(root)
    return subprocess.run(
        [sys.executable, '-u', '-X', 'utf8', str(guard_path)],
        input=payload_bytes,
        cwd=str(root),
        env=env,
        capture_output=True,
        timeout=shim_timeout_sec(),
    )


def validate_guard_response(raw: bytes, exit_code: int):
    """Same schema check eif_guard.cmd/.sh apply before trusting guard stdout."""
    try:
        obj = json.loads(raw.decode('utf-8'))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get('permission') not in ('allow', 'deny'):
        return None
    if obj.get('decision_kind') not in ('policy', 'harness_fault'):
        return None
    reason = obj.get('reason_code')
    if not isinstance(reason, str) or not reason:
        return None
    is_policy_block = obj['permission'] == 'deny' and obj['decision_kind'] == 'policy'
    if (exit_code == 2) != is_policy_block:
        return None
    return obj


def _prefixed_reason(reason, message):
    # eif_guard.py's own deny() already renders message as f'{code}: {msg}';
    # avoid re-prefixing when that already happened.
    if not reason:
        return message
    if message.startswith(f'{reason}:'):
        return message
    return f'{reason}: {message}'


def to_claude_output(decision: dict, cc_event: str):
    permission = decision['permission']
    reason = decision.get('reason_code', '')
    message = decision.get('user_message') or decision.get('agent_message') or reason

    if cc_event in BLOCKING_EVENTS:
        permission_decision = 'deny' if permission == 'deny' else 'allow'
        obj = {
            'hookSpecificOutput': {
                'hookEventName': cc_event,
                'permissionDecision': permission_decision,
                'permissionDecisionReason': _prefixed_reason(reason, message),
            }
        }
        exit_code = 2 if permission_decision == 'deny' else 0
        return obj, exit_code

    # Informational events: Claude Code does not honor a block here (V1), so
    # surface the reason for visibility and always exit 0.
    if permission == 'deny':
        return {'systemMessage': f'EIF {_prefixed_reason(reason, message)}'}, 0
    return {}, 0


def main() -> int:
    try:
        raw = read_stdin_bytes(sys.stdin.buffer)
        if not raw.strip():
            raise ValueError('empty stdin')
        payload = json.loads(raw.decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('hook input must be a JSON object')
    except Exception as exc:
        return fail_closed('SHIM_INPUT_INVALID', f'cannot parse Claude Code hook input: {type(exc).__name__}: {exc}')

    try:
        translated = translate_request(payload)
    except ShimDenial as exc:
        return fail_closed(exc.code, exc.message)

    cc_event = translated.get('cc_event', payload.get('hook_event_name'))

    if translated.get('bypass'):
        emit({'hookSpecificOutput': {'hookEventName': cc_event, 'permissionDecision': 'allow',
                                      'permissionDecisionReason': 'EIF_CLAUDE_ADAPTER: no-side-effect tool, guard not invoked'}})
        return 0

    root, guard_path, searched = resolve_guard(payload)
    if guard_path is None:
        return fail_closed('SHIM_GUARD_NOT_INSTALLED',
                           f'no .cursor/hooks/eif_guard.py in CLAUDE_PROJECT_DIR or the payload cwd or its parents '
                           f'(searched: {", ".join(searched) or "nothing: no CLAUDE_PROJECT_DIR and no payload cwd"})')

    try:
        completed = invoke_guard(root, guard_path, translated)
    except subprocess.TimeoutExpired:
        return fail_closed('SHIM_TIMEOUT', f'guard subprocess exceeded {shim_timeout_sec()}s; fail-closed')
    except Exception as exc:
        return fail_closed('SHIM_GUARD_SPAWN_FAILURE', f'{type(exc).__name__}: {exc}')

    if completed.returncode not in (0, 2):
        return fail_closed('SHIM_GUARD_CRASH', f'guard subprocess exited {completed.returncode}')

    decision = validate_guard_response(completed.stdout, completed.returncode)
    if decision is None:
        return fail_closed('SHIM_GUARD_INVALID_OUTPUT', 'guard subprocess produced no valid decision JSON')

    obj, exit_code = to_claude_output(decision, cc_event)
    emit(obj)
    return exit_code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - last-resort fail-closed, never fail-open
        sys.exit(fail_closed('SHIM_INTERNAL_ERROR', f'{type(exc).__name__}: {exc}'))

"""Persistent retry and Git closure checks; never a grant to run a command.

Cursor may ignore lifecycle replies. Actionable pre-hooks enforce the saved
cursor. Only a successful matching post-tool event clears a blocked action.
Payloads are hashed, not stored: commands and file contents can contain secrets.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from eif_state import atomic_json, contained, file_lock, remaining_timeout

LEDGER = ('.eif/program/PROGRAM.yaml', '.eif/program/PROGRAM_LOG.ndjson')


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
    # These are workflow exceptions only. The normal shell/policy checks still
    # run afterwards, including control-plane and destructive-path protection.
    if not isinstance(command, str) or re.search(r'[;&|<>`\r\n]', command):
        return False
    return bool(re.fullmatch(
        r'\s*(?:git\s+(?:status|diff|log|show|rev-parse|branch|add|commit|push)(?:\s+[^\r\n]*)?'
        r'|python(?:3)?\s+(?:-B\s+)?\.eif/runtime/programme/program\.py\s+[^\r\n]+)\s*',
        command))


def record_block(root, data, code):
    # Never replace the original cursor with our own retry/closure rejection.
    if code.startswith('SESSION_'):
        return
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        fp = fingerprint(data)
        if not any(item['fingerprint'] == fp for item in state['retry']):
            state['retry'].append({'fingerprint': fp, 'tool': action(data)[0],
                                   'reason_code': code, 'at': int(time.time())})
        atomic_json(path, state)


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
        f"fingerprint={first['fingerprint']}. Reads and policy-permitted recovery remain available.")


def git(root, *args, allowed=(0,)):
    result = subprocess.run(['git', '--no-optional-locks', '-C', str(root), *args],
                            capture_output=True, encoding='utf-8', errors='strict', timeout=remaining_timeout())
    if result.returncode not in allowed:
        raise RuntimeError(f'git {args[0]} exited {result.returncode}: {result.stderr.strip()[:240]}')
    return result


def closure_check(root):
    """Require ledger in HEAD and a remote branch containing its latest commit.

    Remote-tracking refs alone are not push evidence. ls-remote is read-only;
    the guard never fetches, stages, commits or pushes on an agent's behalf.
    """
    if not any((Path(root) / path).exists() for path in LEDGER):
        return True, 'SESSION_CLOSURE_OK', 'no programme ledger'
    try:
        dirty = git(root, 'status', '--porcelain', '--untracked-files=all', '--', *LEDGER).stdout
        if dirty.strip():
            return False, 'SESSION_COMMIT_REQUIRED', 'Commit the programme ledger with explicit paths before closing or starting unrelated work.'
        commit = git(root, 'log', '-1', '--format=%H', '--', *LEDGER).stdout.strip()
        if not commit:
            return False, 'SESSION_COMMIT_REQUIRED', 'Programme ledger has no committed history.'
        branch = git(root, 'symbolic-ref', '--short', 'HEAD', allowed=(0, 1)).stdout.strip()
        if not branch:
            return False, 'SESSION_PUSH_REQUIRED', 'Detached HEAD has no verifiable upstream closure.'
        remote = git(root, 'config', '--get', f'branch.{branch}.remote', allowed=(0, 1)).stdout.strip()
        remote_ref = git(root, 'config', '--get', f'branch.{branch}.merge', allowed=(0, 1)).stdout.strip()
        if not remote or remote == '.' or not remote_ref.startswith('refs/heads/'):
            return False, 'SESSION_PUSH_REQUIRED', 'Set and push an authorised upstream branch; local refs are not remote evidence.'
        output = git(root, 'ls-remote', '--exit-code', remote, remote_ref, allowed=(0, 2)).stdout
        matches = [line.split()[0] for line in output.splitlines()
                   if len(line.split()) == 2 and line.split()[1] == remote_ref]
        if len(matches) != 1:
            return False, 'SESSION_PUSH_REQUIRED', 'The configured remote branch is absent or ambiguous.'
        remote_head = matches[0]
        ancestor = git(root, 'merge-base', '--is-ancestor', commit, remote_head, allowed=(0, 1, 128))
        if ancestor.returncode:
            return False, 'SESSION_PUSH_REQUIRED', 'Remote branch does not prove the ledger commit is present; push or reconcile authorised history.'
        return True, 'SESSION_CLOSURE_OK', f'ledger_commit={commit}; verified_remote_head={remote_head}'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        return False, 'SESSION_GIT_FAILURE', f'Cannot verify Git closure: {type(exc).__name__}: {exc}'


def boundary(root, data):
    result = closure_check(root)
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
        state['started'] = True
        state['closure_required'] = not result[0]
        state['closure_reason'] = result[1]
        atomic_json(path, state)
    return result


def pre_check(root, data):
    path = state_path(root, data)
    with file_lock(path.with_suffix('.lock')):
        state = read_state(path)
    if not state.get('started'):
        boundary(root, data)
        with file_lock(path.with_suffix('.lock')):
            state = read_state(path)
    retry = retry_check(root, data)
    if not retry[0]:
        return retry
    if state['closure_required'] and not recovery_action(data):
        result = boundary(root, data)
        if not result[0]:
            return result
    return True, '', ''

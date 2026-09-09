"""Bounded OS locks and atomic JSON replacement for guard-owned state."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import time

DEADLINE = None


def remaining_timeout(limit=2.0):
    if DEADLINE is None:
        return limit
    remaining = DEADLINE - time.perf_counter() - 0.1
    if remaining <= 0:
        raise TimeoutError('guard invocation deadline exhausted')
    return min(limit, remaining)


def contained(root, relative):
    def canonical(path):
        value = str(Path(path).resolve())
        # Windows can retain the extended prefix when a concurrently created
        # descendant did not exist during realpath's final prefix probe.
        if os.name == 'nt' and value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif os.name == 'nt' and value.startswith('\\\\?\\'):
            value = value[4:]
        return Path(value)
    root = canonical(root)
    target = canonical(root / relative)
    target.relative_to(root)
    return target


@contextmanager
def file_lock(path, timeout=2.0):
    timeout = remaining_timeout(timeout)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b'\0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f'guard state lock timeout: {path.name}')
                time.sleep(0.01)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def atomic_json(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(state, stream, ensure_ascii=True, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

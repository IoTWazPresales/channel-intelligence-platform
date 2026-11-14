#!/usr/bin/env python3
"""Small shared helpers for EIF tooling."""
from __future__ import annotations
import hashlib, os, re, time
from pathlib import Path
import yaml

# Windows delete/copy is not atomic against the indexer or antivirus.
# 2/3: the file or its parent disappeared mid-walk (the skill-copy race).
# 5/32: access denied / sharing violation while a scanner holds the new file.
# 145: directory not empty because a child was still being released.
_TRANSIENT_WINERRORS = frozenset({2, 3, 5, 32, 145})

ANCHOR_RE = re.compile(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', re.I)
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+?)\s*$', re.M)

# EIF-authored text artifacts are UTF-8. Never rely on the Windows locale
# code page (often cp1252); that cannot decode bytes such as UTF-8 U+201D.
UTF8 = 'utf-8'
UTF8_SIG = 'utf-8-sig'


def read_utf8(path, *, encoding=UTF8, errors=None) -> str:
    kw={'encoding':encoding}
    if errors is not None: kw['errors']=errors
    return Path(path).read_text(**kw)

def write_utf8(path, text: str, *, encoding=UTF8, newline='\n') -> None:
    """Write UTF-8 text with LF line endings on every OS.

    EIF hashes exact bytes (policy sources, runtime policy, manifests). A
    platform newline would give a Windows install CRLF bytes that a Linux
    checkout of the same commit cannot match (BACKLOG-225). Pass
    newline=None only for a file that must follow the host convention.
    """
    kw={'encoding':encoding}
    if newline is not None: kw['newline']=newline
    Path(path).write_text(text, **kw)

def retry_transient_io(action, *, attempts=8):
    """Run `action`. On Windows, retry a short list of transient IO errors.

    A persistent failure, and every failure on other systems, is raised
    unchanged. This does not treat a missing source or a bad path as success.
    """
    delay = 0.02
    for attempt in range(attempts):
        try:
            return action()
        except OSError as exc:
            winerror = getattr(exc, 'winerror', None)
            if os.name != 'nt' or winerror not in _TRANSIENT_WINERRORS or attempt + 1 == attempts:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.25)

def sha256_path(path: Path) -> str:
    h=hashlib.sha256();
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def frontmatter(text: str):
    if not text.startswith('---\n'): return {}, text
    end=text.find('\n---\n',4)
    if end<0: return {}, text
    return yaml.safe_load(text[4:end]) or {}, text[end+5:]

def render_frontmatter(fm: dict, body: str) -> str:
    return '---\n'+yaml.safe_dump(fm,sort_keys=False,width=120).strip()+'\n---\n'+body

def contract_target(root: Path, ref: str):
    if '#' not in ref: raise ValueError(f'contract_ref lacks anchor: {ref}')
    rel,anchor=ref.split('#',1); p=root/rel
    if not p.exists(): raise FileNotFoundError(p)
    text=read_utf8(p)
    marker=f'<a id="{anchor}"></a>'
    pos=text.find(marker)
    if pos<0: raise ValueError(f'anchor #{anchor} not found in {rel}')
    return p,text,pos,anchor

def load_cursor_hook_adapter(root: Path):
    """Load the Cursor runtime hook adapter without installing the package."""
    import importlib.util
    path = root / 'runtime/cursor/hook_adapter.py'
    spec = importlib.util.spec_from_file_location('eif_cursor_hook_adapter', path)
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot load Cursor hook adapter from {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def extract_contract(root: Path, ref: str) -> str:
    p,text,pos,anchor=contract_target(root,ref)
    after=pos+len(f'<a id="{anchor}"></a>')
    # Contract ends at the next explicit specialist anchor or EOF.
    m=ANCHOR_RE.search(text, after)
    end=m.start() if m else len(text)
    section=text[after:end].strip()
    if not section: raise ValueError(f'empty contract at {ref}')
    return section+'\n'

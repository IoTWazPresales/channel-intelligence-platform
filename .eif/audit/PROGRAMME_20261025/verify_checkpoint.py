"""Read-only provenance check for the 25 October independent review.

Reads repository/Git evidence only. Writes its own audit JSON; never opens a DB,
mutates the EIF programme, or modifies source. Run from the repository root.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / '.eif/audit/PROGRAMME_20261024'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8').strip()


def check_hashes(manifest):
    return {path: {'expected': expected,
                   'actual': hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
            for path, expected in manifest.items()}


def main():
    handoff = json.loads((PRIOR / 'HANDOFF_PERSISTENCE.json').read_text(encoding='utf-8-sig'))
    source = check_hashes(json.loads((PRIOR / 'original-scope-source-sha256.json').read_text(encoding='utf-8-sig')))
    inherited = check_hashes(handoff['modified_tracked_sha256'])
    local = [json.loads(line) for line in (ROOT / '.eif/program/PROGRAM_LOG.ndjson').read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    committed = [json.loads(line) for line in git('show', 'HEAD:.eif/program/PROGRAM_LOG.ndjson').splitlines() if line.strip()]
    state = yaml.safe_load((ROOT / '.eif/program/PROGRAM.yaml').read_text(encoding='utf-8-sig'))
    results = {}
    for name in ['web-original-scope.json', 'unit-c-original-final.json']:
        obj = json.loads((PRIOR / name).read_text(encoding='utf-8-sig'))
        results[name] = {k: obj.get(k) for k in ['success', 'numTotalTests', 'numPassedTests', 'numFailedTests', 'numPendingTests']}
        results[name]['files'] = len(obj.get('testResults', []))
    for name in ['browser-original-final.json', 'browser-authenticated.json']:
        obj = json.loads((PRIOR / name).read_text(encoding='utf-8-sig'))
        results[name] = obj.get('stats')
    for name in ['api-original-scope.xml', 'auth-export-final.xml', 'authenticated-browser-harness-corrected.xml']:
        tree = ET.parse(PRIOR / name)
        results[name] = [element.attrib for element in tree.getroot().iter('testsuite')]
    node_fields = ['revision', 'status', 'stage', 'lease', 'risk', 'acceptance_state', 'depends_on', 'implementation_run', 'implementation_actor', 'acceptance_criteria', 'quality', 'verification']
    out = {
        'scope': 'read-only independent provenance check; implementation change scope NONE',
        'head': git('rev-parse', 'HEAD'), 'branch': git('branch', '--show-current'),
        'upstream': git('rev-parse', '@{u}'),
        'remote': git('ls-remote', 'origin', 'refs/heads/feat/ns-2-brief-nav-collapse'),
        'root_commit': git('rev-list', '--max-parents=0', 'HEAD'),
        'source_hashes': source, 'inherited_hashes': inherited,
        'source_mismatches': [k for k, v in source.items() if v['expected'] != v['actual']],
        'inherited_mismatches': [k for k, v in inherited.items() if v['expected'] != v['actual']],
        'ledger': {'committed_revision': committed[-1]['seq'], 'local_revision': local[-1]['seq'],
                   'committed_prefix_unchanged': local[:len(committed)] == committed,
                   'local_only_count': len(local)-len(committed),
                   'local_only_range': [local[len(committed)]['seq'], local[-1]['seq']],
                   'last_event': local[-1]['event']},
        'programme_revision': state['programme']['snapshot_revision'],
        'leases': {k:v['lease'] for k,v in state['nodes'].items() if v.get('lease')},
        'nodes': {k:{f:state['nodes'][k].get(f) for f in node_fields} for k in ['N-0114','N-0115','N-0116']},
        'decisions': {k:v for k,v in state['decisions'].items() if 'D-0116' <= k <= 'D-0131'},
        'historical_test_artifacts_parsed_not_rerun': results,
        'git_status': git('status', '--short').splitlines(),
    }
    (HERE / 'checkpoint.json').write_text(json.dumps(out, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(json.dumps({k:out[k] for k in ['head','branch','upstream','remote','source_mismatches','inherited_mismatches','ledger','programme_revision','leases','historical_test_artifacts_parsed_not_rerun']}, indent=2))


if __name__ == '__main__':
    main()

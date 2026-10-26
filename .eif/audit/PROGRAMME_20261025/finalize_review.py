"""Persist final supported EIF verification and preservation checks; no product edits."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import yaml

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
command=[sys.executable,str(ROOT/'.eif/runtime/programme/program.py'),
         '--run','RUN-20261025-N0116-ASTRA','--actor','codex','verify']
result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=240)
verify=json.loads(result.stdout)
(HERE/'programme-final-verify.json').write_text(json.dumps(verify,indent=2)+'\n',encoding='utf-8')
entry=json.loads((HERE/'checkpoint.json').read_text(encoding='utf-8'))
handoff=json.loads((ROOT/'.eif/audit/PROGRAMME_20261024/HANDOFF_PERSISTENCE.json').read_text(encoding='utf-8-sig'))
raw=(ROOT/'.eif/program/PROGRAM_LOG.ndjson').read_bytes()
lines=raw.splitlines(keepends=True)
prefix=b''.join(lines[:2767])
state=yaml.safe_load((ROOT/'.eif/program/PROGRAM.yaml').read_text(encoding='utf-8-sig'))
events=[json.loads(line) for line in lines if line.strip()]
source=json.loads((ROOT/'.eif/audit/PROGRAMME_20261024/original-scope-source-sha256.json').read_text(encoding='utf-8-sig'))
source_mismatches=[p for p,h in source.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
inherited_non_views={p:h for p,h in handoff['modified_tracked_sha256'].items()
                     if p not in ['.eif/CURRENT.md','.eif/ESCALATION.md','.eif/PROGRAM.md','.eif/ROADMAP.md',
                                  '.eif/program/PROGRAM.yaml','.eif/program/PROGRAM_LOG.ndjson']}
runtime_mismatches=[p for p,h in inherited_non_views.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
out={
    'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'programme_revision':state['programme']['snapshot_revision'],
    'verify_exit_code':result.returncode,'integrity_ok':verify.get('integrity_ok'),
    'gate_issues':verify.get('gate_issues'),'gate_debt':verify.get('gate_debt'),
    'original_2767_event_prefix_sha256':hashlib.sha256(prefix).hexdigest(),
    'original_event_prefix_unchanged':hashlib.sha256(prefix).hexdigest()==handoff['ledger_sha256'],
    'git_ledger_revision':2679,'local_only_event_count':len(events)-2679,
    'new_events':events[2767:],
    'leases':{k:v['lease'] for k,v in state['nodes'].items() if v.get('lease')},
    'nodes':{k:{f:state['nodes'][k].get(f) for f in ['revision','status','stage','acceptance_state','lease']}
             for k in ['N-0114','N-0115','N-0116']},
    'source_hash_mismatches':source_mismatches,'inherited_runtime_policy_mismatches':runtime_mismatches,
    'product_diff':subprocess.check_output(['git','diff','--name-only','HEAD','--','apps','packages'],cwd=ROOT,text=True).splitlines(),
    'audit_delivery':'local artifacts and memory updates only; no commit/push',
    'independence':'R2 fresh-context review; R3 model separation unattested; no operator acceptance',
    'evidence_only_mutation':'supported evidence.add event; no node, decision, quality, stage, acceptance or lease change',
    'earlier_cli_attempt':'event --type rejected by argparse before mutation; event help consulted, corrected to positional event evidence.add once',
}
assert out['original_event_prefix_unchanged']
assert not source_mismatches and not runtime_mismatches and not out['product_diff']
assert out['integrity_ok'] and len(out['gate_issues'])==9
assert out['nodes']=={k:{f:entry['nodes'][k].get(f) for f in ['revision','status','stage','acceptance_state','lease']}
                     for k in ['N-0114','N-0115','N-0116']}
(HERE/'closeout.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))

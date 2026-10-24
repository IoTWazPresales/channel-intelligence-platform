"""Snapshot code-defined starters for browser fixtures; no sessions, SQL, migrations or API calls."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / 'apps/api'))
from app.services.dashboard_templates import TEMPLATES

boards = []
for ti, template in enumerate(TEMPLATES):
    board_id = 1000 + ti
    widgets = []
    for wi, w in enumerate(template.widgets):
        widgets.append(dict(id=board_id * 100 + wi, dashboard_id=board_id, title=w.title,
                            visual=w.visual, metric_key=w.measures[0], grains=list(w.breakdowns),
                            filters={}, period_grain=w.grain, layout_json=w.layout_json(),
                            saved_report_id=None, sort_order=wi, definition_v2=w.definition()))
    boards.append(dict(id=board_id, name=template.title, description=template.description,
                       visibility='personal', shared_roles=[], widgets=widgets,
                       filters_json=template.filters_json, template_key=template.key))
target = root / 'apps/web/src/design-lab/fixtures/builderStarters.json'
target.write_text(json.dumps(boards, indent=2) + '\n', encoding='utf-8')
print(f'Snapshotted {len(boards)} starter definitions / {sum(len(b["widgets"]) for b in boards)} widgets; no database accessed.')

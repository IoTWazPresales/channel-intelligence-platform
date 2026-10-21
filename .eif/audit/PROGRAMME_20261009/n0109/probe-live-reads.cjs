const fs = require('fs');
const os = require('os');
const path = require('path');

const token = fs.readFileSync(path.join(os.tmpdir(), 'cip-smoke-token.txt'), 'utf8').trim();

async function probe(pathname) {
  const res = await fetch('http://127.0.0.1:8001' + pathname, {
    headers: { Authorization: 'Bearer ' + token },
  });
  const text = await res.text();
  let summary = text.slice(0, 240).replace(/\s+/g, ' ');
  if (pathname.endsWith('/signals')) {
    try {
      const body = JSON.parse(text);
      const rows = (body.signals || []).map((s) => `${s.id}|${s.severity}|${s.title}|${s.action_href}`);
      summary = `count=${(body.signals || []).length} ` + rows.join(' || ');
    } catch {
      summary = 'parse_fail ' + summary;
    }
  }
  if (pathname.endsWith('/dashboards')) {
    try {
      const body = JSON.parse(text);
      if (Array.isArray(body.items)) summary = `items=${body.items.length}`;
      else if (body.detail) summary = JSON.stringify(body.detail).slice(0, 240);
    } catch {
      summary = 'parse_fail ' + summary;
    }
  }
  console.log(res.status, pathname, summary);
}

(async () => {
  await probe('/api/v1/dashboards');
  await probe('/api/v1/brief/signals');
  await probe('/api/v1/semantics/catalog');
})();

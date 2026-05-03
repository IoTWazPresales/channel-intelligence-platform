/**
 * Print listeners on common dev ports (3000 web, 8001 API, plus stale 8000) to debug stale processes.
 */
const { execSync } = require('child_process');

const ports = [3000, 8001, 8000];

for (const port of ports) {
  console.log(`\n=== Port ${port} ===`);
  try {
    if (process.platform === 'win32') {
      const out = execSync(`netstat -ano | findstr ":${port}"`, { encoding: 'utf8' });
      console.log(out.trim() || '(no matches)');
    } else {
      const out = execSync(`lsof -nP -iTCP:${port} -sTCP:LISTEN 2>/dev/null || true`, {
        encoding: 'utf8',
        shell: '/bin/bash',
      });
      console.log(out.trim() || '(no listeners)');
    }
  } catch {
    console.log('(no matches)');
  }
}
console.log('\nTip: free Docker app ports with `pnpm docker:stop:app` from the repo root.\n');

// Dev utility: capture the running Electron renderer via CDP.
// Usage: node scripts/capture-ui.mjs <output.png> [http://127.0.0.1:9222]
import { writeFileSync } from 'node:fs';

const out = process.argv[2] ?? 'data/logs/dashboard.png';
const base = process.argv[3] ?? 'http://127.0.0.1:9222';

const targets = await (await fetch(`${base}/json`)).json();
const page = targets.find((t) => t.type === 'page');
if (!page) throw new Error('no page target');

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = rej;
});

const result = await new Promise((resolve, reject) => {
  const id = 1;
  ws.onmessage = (ev) => {
    const msg = JSON.parse(String(ev.data));
    if (msg.id === id) resolve(msg.result);
  };
  ws.send(JSON.stringify({ id, method: 'Page.captureScreenshot', params: { format: 'png' } }));
  setTimeout(() => reject(new Error('capture timeout')), 10000);
});

writeFileSync(out, Buffer.from(result.data, 'base64'));
console.log(`saved ${out}`);
ws.close();

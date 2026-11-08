// Dev utility: capture the running Electron renderer via CDP.
// Usage: node scripts/capture-ui.mjs <output.png> [http://127.0.0.1:9222] [#/route]
import { writeFileSync } from 'node:fs';

const out = process.argv[2] ?? 'data/logs/dashboard.png';
const base = process.argv[3] ?? 'http://127.0.0.1:9222';
const hash = process.argv[4] ?? '';
const scrollY = Number(process.argv[5] ?? 0);
const clickText = process.argv[6] ?? '';
const waitMs = Number(process.argv[7] ?? 2500);

const targets = await (await fetch(`${base}/json`)).json();
const page = targets.find((t) => t.type === 'page');
if (!page) throw new Error('no page target');

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = rej;
});

let nextId = 1;
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    const timer = setTimeout(() => reject(new Error(`${method} timeout`)), 15000);
    const handler = (ev) => {
      const msg = JSON.parse(String(ev.data));
      if (msg.id === id) {
        clearTimeout(timer);
        ws.removeEventListener('message', handler);
        resolve(msg.result);
      }
    };
    ws.addEventListener('message', handler);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

if (hash) {
  await send('Runtime.evaluate', { expression: `location.hash = '${hash}'` });
  await new Promise((r) => setTimeout(r, 2000));
}

if (scrollY) {
  await send('Runtime.evaluate', { expression: `window.scrollTo(0, ${scrollY})` });
  await new Promise((r) => setTimeout(r, 800));
}

if (clickText) {
  const expr = `(() => { const b = [...document.querySelectorAll('button')].find(x => (x.textContent || '').includes(${JSON.stringify(clickText)})); if (b) { b.click(); return true; } return false; })()`;
  const clicked = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
  console.log('clicked:', clicked?.result?.value);
  await new Promise((r) => setTimeout(r, waitMs));
}

const result = await send('Page.captureScreenshot', { format: 'png' });
writeFileSync(out, Buffer.from(result.data, 'base64'));
console.log(`saved ${out}`);
ws.close();


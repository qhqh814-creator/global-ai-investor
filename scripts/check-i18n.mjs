// Dev utility: check i18n keys used in TSX against locale files.
// Usage: node scripts/check-i18n.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = 'app/src';
const locales = {
  'zh-CN': JSON.parse(readFileSync('app/src/i18n/locales/zh-CN.json', 'utf8')),
  'en-US': JSON.parse(readFileSync('app/src/i18n/locales/en-US.json', 'utf8'))
};

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (p.endsWith('.tsx') || p.endsWith('.ts')) out.push(p);
  }
  return out;
}

function flat(obj, prefix = '') {
  const map = new Set();
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const kk of flat(v, key)) map.add(kk);
    } else {
      map.add(key);
    }
  }
  return map;
}

const keys = new Set();
const re = /\bt\(\s*['"]([^'"]+)['"]/g;
for (const file of walk(root)) {
  const text = readFileSync(file, 'utf8');
  let m;
  while ((m = re.exec(text))) keys.add(m[1]);
}

const flatKeys = Object.fromEntries(Object.entries(locales).map(([lang, obj]) => [lang, flat(obj)]));
let failed = false;
for (const lang of Object.keys(locales)) {
  const missing = [...keys].filter((k) => !flatKeys[lang].has(k));
  if (missing.length) {
    failed = true;
    console.log(`[${lang}] missing ${missing.length}:`, missing.join(', '));
  } else {
    console.log(`[${lang}] OK — ${keys.size} literal keys`);
  }
}

// dynamic dashboard card keys must exist too
const dash = keys.has('dashboard.subtitle')
  ? ['sse_index','szse_index','chinext_index','star50','bse50','market_overview','breadth','limit_counts','turnover','good_news','risk_alerts','ai_opportunities','watchlist','signals','paper_account']
  : [];
for (const lang of Object.keys(locales)) {
  const missing = dash.filter((k) => !flatKeys[lang].has(`dashboard.cards.${k}`));
  if (missing.length) {
    failed = true;
    console.log(`[${lang}] missing dynamic card keys:`, missing.join(', '));
  }
}
process.exit(failed ? 1 : 0);

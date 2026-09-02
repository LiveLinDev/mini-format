// Decodes TOON documents with the official reference implementation (strict mode).
// stdin: JSON array of strings; stdout: JSON array of {ok, value|error}
import { decode } from './vendor/toon/src/index.ts';
import fs from 'node:fs';
const docs = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(docs.map((t) => {
  try { return { ok: true, value: decode(t, { strict: true }) }; }
  catch (e) { return { ok: false, error: String(e && e.message || e) }; }
})));

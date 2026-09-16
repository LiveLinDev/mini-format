// Official vendored TOON v4.1.1; no alternative encoder in this benchmark.
import { encode, decode } from '../toon_ref/vendor/toon/src/index.ts';
import fs from 'node:fs';
const documents = JSON.parse(fs.readFileSync(0, 'utf8'));
const output = documents.map(value => {
  const text = encode(value);
  return { text, decoded: decode(text, { strict: true }) };
});
process.stdout.write(JSON.stringify(output));

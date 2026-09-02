// Encodes JSON documents with the OFFICIAL TOON reference implementation
// (vendored from https://github.com/toon-format/toon, MIT, v4.1.1, spec 4.1).
// Usage: node --experimental-strip-types --experimental-transform-types toon_encode.mjs < docs.json > out.json
// stdin: JSON array of documents (or one document); stdout: JSON array of {toon, roundtrip}
import { encode, decode } from './vendor/toon/src/index.ts';
import fs from 'node:fs';
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const docs = Array.isArray(input) ? input : [input];
const out = docs.map((d) => {
  const toon = encode(d);
  let roundtrip = false;
  try { roundtrip = JSON.stringify(decode(toon)) === JSON.stringify(d); } catch (e) { roundtrip = false; }
  return { toon, roundtrip };
});
process.stdout.write(JSON.stringify(out));

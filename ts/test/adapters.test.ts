/* adapters.test.ts — HU17: proveedores intercambiables con fetch simulado y streams SSE sintéticos (MOCK: no hay llamadas reales).
 * Ninguna prueba usa la red ni claves reales: el fetch global se reemplaza por uno que falla.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  AdapterError, AnthropicAdapter, GroqAdapter, MissingKeyError, OpenAIAdapter, OpenAIResponsesAdapter, SimulatedAdapter,
  getAdapter, mergeRepair, parse, parseSSE, repairRequest, streamRecords,
} from '../src/index.ts';
import type { Contract, FetchLike, FetchResponseLike, GenerateRequest, MiniRecord, ModelAdapter } from '../src/index.ts';
import { LF, REG, chunk, lf, read, rng } from './helpers.ts';

const CLS = REG.get('cls');
const VALID = lf(read(path.join(REG.paths.get('cls') as string, 'fixtures', 'valid.mini'))).replace(/\n+$/, '');
const RECORDS = parse(VALID, CLS).records;
const KEY = 'sk-test-0123456789abcdef';
const REQUEST: GenerateRequest = { system: 'sistema', user: 'Clasifica los mensajes', maxTokens: 2048, temperature: 0 };

// ------------------------------------------------------------ sin red
const realFetch = globalThis.fetch;
before(() => {
  globalThis.fetch = (() => Promise.reject(new Error('network access is forbidden in tests'))) as typeof fetch;
});
after(() => {
  globalThis.fetch = realFetch;
});

// ------------------------------------------------------------ fetch simulado
interface Call { url: string; headers: Record<string, string>; body: Record<string, unknown> }

const enc = new TextEncoder();

/** Trocea bytes UTF-8 al azar (puede partir caracteres multibyte y CRLF). */
function byteChunks(text: string, seed: number): Uint8Array[] {
  const bytes = enc.encode(text);
  const r = rng(seed);
  const out: Uint8Array[] = [];
  for (let i = 0; i < bytes.length;) {
    const k = 1 + Math.floor(r() * 40);
    out.push(bytes.slice(i, i + k));
    i += k;
  }
  return out;
}

interface Delivery { delivered: number; total: number }

function sseBody(text: string, seed: number, delivery?: Delivery): ReadableStream<Uint8Array> {
  const parts = byteChunks(text, seed);
  if (delivery) delivery.total = parts.length;
  let i = 0;
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      await new Promise(r => setImmediate(r));
      if (i < parts.length) {
        controller.enqueue(parts[i++]);
        if (delivery) delivery.delivered = i;
      } else {
        controller.close();
      }
    },
  });
}

type Reply = { status?: number; json?: unknown; sse?: string; raw?: string; delivery?: Delivery };

function fakeFetch(replies: Reply[], calls: Call[]): FetchLike {
  let n = 0;
  return async (url, init) => {
    calls.push({ url, headers: init.headers, body: JSON.parse(init.body) as Record<string, unknown> });
    const rep = replies[Math.min(n++, replies.length - 1)];
    const status = rep.status ?? 200;
    const resp: FetchResponseLike = {
      status,
      text: async () => (rep.raw !== undefined ? rep.raw : rep.sse !== undefined ? rep.sse : JSON.stringify(rep.json)),
      body: rep.sse !== undefined ? sseBody(rep.sse, n, rep.delivery) : null,
    };
    return resp;
  };
}

/** Parte el documento en deltas pequeños (como tokens). */
function deltas(text: string, seed: number): string[] {
  return chunk(text, rng(seed), 1, 9);
}

const sse = (events: { event?: string; data: unknown }[], crlf = false): string => {
  const nl = crlf ? '\r\n' : '\n';
  return events.map(e => (e.event ? `event: ${e.event}${nl}` : '') + `data: ${typeof e.data === 'string' ? e.data : JSON.stringify(e.data)}${nl}${nl}`).join('');
};

// ------------------------------------------------------------ flujos por proveedor
function openaiChatSSE(text: string, seed = 1, usageKey: 'usage' | 'x_groq' = 'usage'): string {
  const ev: { data: unknown }[] = [{ data: { id: 'c1', model: 'gpt-test', choices: [{ index: 0, delta: { role: 'assistant', content: '' } }] } }];
  for (const d of deltas(text, seed)) ev.push({ data: { id: 'c1', model: 'gpt-test', choices: [{ index: 0, delta: { content: d } }] } });
  ev.push({ data: { id: 'c1', model: 'gpt-test', choices: [{ index: 0, delta: {}, finish_reason: 'stop' }] } });
  const usage = { prompt_tokens: 111, completion_tokens: 222 };
  ev.push({ data: usageKey === 'usage' ? { id: 'c1', choices: [], usage } : { id: 'c1', choices: [], x_groq: { usage } } });
  ev.push({ data: '[DONE]' });
  return ': keep-alive\n\n' + sse(ev);
}

function responsesSSE(text: string, seed = 2): string {
  const ev: { event: string; data: unknown }[] = [
    { event: 'response.created', data: { type: 'response.created', response: { model: 'gpt-test-r', status: 'in_progress' } } },
  ];
  for (const d of deltas(text, seed)) ev.push({ event: 'response.output_text.delta', data: { type: 'response.output_text.delta', delta: d } });
  ev.push({ event: 'response.output_text.done', data: { type: 'response.output_text.done', text } });
  ev.push({
    event: 'response.completed',
    data: { type: 'response.completed', response: { model: 'gpt-test-r', status: 'completed', usage: { input_tokens: 111, output_tokens: 222 } } },
  });
  return sse(ev, true);
}

function anthropicSSE(text: string, seed = 3, stop = 'end_turn'): string {
  const ev: { event: string; data: unknown }[] = [
    { event: 'message_start', data: { type: 'message_start', message: { model: 'claude-test', usage: { input_tokens: 100, cache_read_input_tokens: 11, output_tokens: 1 } } } },
    { event: 'content_block_start', data: { type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } } },
    { event: 'ping', data: { type: 'ping' } },
  ];
  for (const d of deltas(text, seed)) {
    ev.push({ event: 'content_block_delta', data: { type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text: d } } });
  }
  ev.push({ event: 'content_block_stop', data: { type: 'content_block_stop', index: 0 } });
  ev.push({ event: 'message_delta', data: { type: 'message_delta', delta: { stop_reason: stop }, usage: { output_tokens: 222 } } });
  ev.push({ event: 'message_stop', data: { type: 'message_stop' } });
  return sse(ev);
}

// ------------------------------------------------------------ código de aplicación (no cambia entre proveedores)
async function classifyMessages(adapter: ModelAdapter, contract: Contract): Promise<{ records: MiniRecord[]; seen: number; complete: boolean; outputTokens: number | null }> {
  const records: MiniRecord[] = [];
  const it = streamRecords(adapter, contract, REQUEST);
  for (;;) {
    const step = await it.next();
    if (step.done) {
      return { records, seen: step.value.reader.received, complete: step.value.reader.complete, outputTokens: step.value.generation.outputTokens };
    }
    records.push(step.value.record);
  }
}

describe('HU17 escenario 1: reemplazar el proveedor no cambia el código de la aplicación', () => {
  test('OpenAI -> Anthropic -> Groq -> Responses -> simulado: mismos registros', async () => {
    const calls: Call[] = [];
    const answer = 'Aquí tienes:\n```mini\n' + VALID + '\n```\nListo.';
    const adapters: ModelAdapter[] = [
      new OpenAIAdapter('gpt-test', { apiKey: KEY, fetch: fakeFetch([{ sse: openaiChatSSE(answer) }], calls) }),
      new AnthropicAdapter('claude-test', { apiKey: KEY, fetch: fakeFetch([{ sse: anthropicSSE(answer) }], calls) }),
      new GroqAdapter('llama-test', { apiKey: KEY, fetch: fakeFetch([{ sse: openaiChatSSE(answer, 4, 'x_groq') }], calls) }),
      new OpenAIResponsesAdapter('gpt-test-r', { apiKey: KEY, fetch: fakeFetch([{ sse: responsesSSE(answer) }], calls) }),
      getAdapter('simulated', 'sim', { responses: [answer], seed: 5 }),
    ];
    for (const adapter of adapters) {
      const out = await classifyMessages(adapter, CLS);
      assert.deepEqual(out.records, RECORDS, adapter.provider);
      assert.equal(out.complete, true, adapter.provider);
      assert.equal(out.seen, 12, adapter.provider);
      if (adapter.provider !== 'simulated') assert.equal(out.outputTokens, 222, adapter.provider);
    }
    assert.deepEqual(calls.map(c => c.url), [
      'https://api.openai.com/v1/chat/completions', 'https://api.anthropic.com/v1/messages',
      'https://api.groq.com/openai/v1/chat/completions', 'https://api.openai.com/v1/responses',
    ]);
  });

  test('cuerpos y cabeceras por proveedor', async () => {
    const calls: Call[] = [];
    const rf = { type: 'json_schema' as const, name: 'tickets', schema: { type: 'object' } };
    const req: GenerateRequest = { ...REQUEST, responseFormat: rf, seed: 7 };
    await new OpenAIAdapter('gpt-test', { apiKey: KEY, fetch: fakeFetch([{ sse: openaiChatSSE('x') }], calls) }).stream(req).result;
    await new AnthropicAdapter('claude-test', { apiKey: KEY, browser: true, fetch: fakeFetch([{ sse: anthropicSSE('x') }], calls) }).stream(req).result;
    await new OpenAIResponsesAdapter('gpt-r', { apiKey: KEY, sendTemperature: false, fetch: fakeFetch([{ sse: responsesSSE('x') }], calls) }).stream(req).result;
    await new GroqAdapter('llama', { apiKey: KEY, fetch: fakeFetch([{ sse: openaiChatSSE('x') }], calls) }).stream({ ...REQUEST, seed: 2 ** 31 + 5 }).result;
    const [oa, an, rs, gq] = calls;
    assert.equal(oa.headers.authorization, `Bearer ${KEY}`);
    assert.deepEqual(oa.body, {
      model: 'gpt-test', messages: [{ role: 'system', content: 'sistema' }, { role: 'user', content: 'Clasifica los mensajes' }],
      max_completion_tokens: 2048, temperature: 0, seed: 7,
      response_format: { type: 'json_schema', json_schema: { name: 'tickets', strict: true, schema: { type: 'object' } } },
      stream: true, stream_options: { include_usage: true },
    });
    assert.equal(an.headers['x-api-key'], KEY);
    assert.equal(an.headers['anthropic-version'], '2023-06-01');
    assert.equal(an.headers['anthropic-dangerous-direct-browser-access'], 'true');
    assert.deepEqual(an.body, {
      model: 'claude-test', max_tokens: 2048, system: 'sistema', messages: [{ role: 'user', content: 'Clasifica los mensajes' }],
      temperature: 0, output_config: { format: { type: 'json_schema', schema: { type: 'object' } } }, stream: true,
    });
    assert.deepEqual(rs.body, {
      model: 'gpt-r', instructions: 'sistema', input: 'Clasifica los mensajes', max_output_tokens: 2048,
      text: { format: { type: 'json_schema', name: 'tickets', strict: true, schema: { type: 'object' } } }, stream: true,
    });
    assert.equal(gq.body.seed, 5);
    assert.equal(gq.body.stream_options, undefined);
    await assert.rejects(new GroqAdapter('llama', { apiKey: KEY, fetch: fakeFetch([], calls) }).generate(req), /does not support structured output/);
  });
});

describe('HU17 escenario 2: adaptador simulado y fetch inyectado, sin internet', () => {
  test('el fetch global está bloqueado durante las pruebas', async () => {
    await assert.rejects(new OpenAIAdapter('gpt', { apiKey: KEY, retries: 0 }).generate(REQUEST), /network access is forbidden/);
  });

  test('simulado: determinista, trocea el flujo y trunca en maxTokens', async () => {
    const a = new SimulatedAdapter('sim', { respond: req => `eco:${req.user}`, seed: 3, maxChunk: 3 });
    const pieces: string[] = [];
    const s = a.stream(REQUEST);
    for await (const p of s) pieces.push(p);
    assert.ok(pieces.length > 3 && pieces.every(p => p.length <= 3));
    assert.equal(pieces.join(''), 'eco:Clasifica los mensajes');
    assert.equal((await s.result).text, 'eco:Clasifica los mensajes');
    assert.deepEqual((await a.generate(REQUEST)).text, 'eco:Clasifica los mensajes');
    assert.equal(a.calls.length, 2);
    const cut = await new SimulatedAdapter('sim', { responses: [VALID] }).generate({ ...REQUEST, maxTokens: 50 });
    assert.equal(cut.stopReason, 'max_tokens');
    assert.equal(cut.text, VALID.slice(0, 200));
  });

  test('los registros se emiten antes de que termine el flujo', async () => {
    const delivery: Delivery = { delivered: 0, total: 0 };
    const adapter = new AnthropicAdapter('claude-test', { apiKey: KEY, fetch: fakeFetch([{ sse: anthropicSSE(VALID), delivery }], []) });
    const seenAt: number[] = [];
    const it = streamRecords(adapter, CLS, REQUEST);
    for (;;) {
      const step = await it.next();
      if (step.done) break;
      seenAt.push(delivery.delivered);
    }
    assert.equal(seenAt.length, 12);
    assert.ok(seenAt[0] < delivery.total / 2, `primer registro tras ${seenAt[0]}/${delivery.total} fragmentos`);
  });

  test('respuesta truncada por max_tokens: el lector lo informa', async () => {
    const cutText = VALID.slice(0, Math.floor(VALID.length * 0.6));
    const adapter = new AnthropicAdapter('claude-test', { apiKey: KEY, fetch: fakeFetch([{ sse: anthropicSSE(cutText, 9, 'max_tokens') }], []) });
    const it = streamRecords(adapter, CLS, REQUEST);
    let step = await it.next();
    let n = 0;
    while (!step.done) {
      n++;
      step = await it.next();
    }
    assert.equal(step.value.generation.stopReason, 'max_tokens');
    assert.equal(step.value.reader.truncated, true);
    assert.equal(n, step.value.reader.valid);
    assert.ok(n > 0 && n < 12);
  });

  test('flujo completo con reparación selectiva usando cualquier adaptador', async () => {
    const lines = VALID.split(LF);
    const broken = [...lines];
    broken[3] = broken[3].replace('question,', 'question|');
    const req = repairRequest(broken.join(LF), CLS, 'es');
    const adapter: ModelAdapter = new OpenAIAdapter('gpt-test', {
      apiKey: KEY,
      fetch: fakeFetch([{ json: { model: 'gpt-test', choices: [{ message: { content: `cls|n=1\n${lines[3]}` }, finish_reason: 'stop' }], usage: { prompt_tokens: 5, completion_tokens: 6 } } }], []),
    });
    const answer = await adapter.generate({ system: req.system, user: req.user, maxTokens: req.maxTokensHint * 2, temperature: 0 });
    const merged = mergeRepair(broken.join(LF), answer.text, CLS, req);
    assert.equal(merged.ok, true);
    assert.equal(merged.text, VALID);
  });
});

describe('adaptadores HTTP: respuestas, errores y claves', () => {
  test('generate sin streaming por proveedor', async () => {
    const oa = await new OpenAIAdapter('m', {
      apiKey: KEY, fetch: fakeFetch([{ json: { model: 'gpt-x', choices: [{ message: { content: 'hola' }, finish_reason: 'stop' }], usage: { prompt_tokens: 3, completion_tokens: 4 } } }], []),
    }).generate(REQUEST);
    assert.deepEqual([oa.text, oa.inputTokens, oa.outputTokens, oa.stopReason, oa.model, oa.provider], ['hola', 3, 4, 'stop', 'gpt-x', 'openai']);
    const an = await new AnthropicAdapter('m', {
      apiKey: KEY,
      fetch: fakeFetch([{ json: { model: 'claude-x', content: [{ type: 'thinking', thinking: '...' }, { type: 'text', text: 'ho' }, { type: 'text', text: 'la' }], stop_reason: 'end_turn', usage: { input_tokens: 10, cache_creation_input_tokens: 2, cache_read_input_tokens: 3, output_tokens: 4 } } }], []),
    }).generate(REQUEST);
    assert.deepEqual([an.text, an.inputTokens, an.outputTokens, an.stopReason], ['hola', 15, 4, 'end_turn']);
    const rs = await new OpenAIResponsesAdapter('m', {
      apiKey: KEY,
      fetch: fakeFetch([{ json: { model: 'r', status: 'incomplete', incomplete_details: { reason: 'max_output_tokens' }, output: [{ type: 'reasoning' }, { type: 'message', content: [{ type: 'output_text', text: 'hola' }] }], usage: { input_tokens: 1, output_tokens: 2 } } }], []),
    }).generate(REQUEST);
    assert.deepEqual([rs.text, rs.inputTokens, rs.outputTokens, rs.stopReason], ['hola', 1, 2, 'max_output_tokens']);
  });

  test('reintenta estados reintentables y falla sin reintentar los demás', async () => {
    const calls: Call[] = [];
    const sleeps: number[] = [];
    const ok = { json: { choices: [{ message: { content: 'ok' } }] } };
    const a = new OpenAIAdapter('m', {
      apiKey: KEY, retries: 2, sleep: async ms => { sleeps.push(ms); }, fetch: fakeFetch([{ status: 429, raw: 'slow down' }, { status: 503, raw: '' }, ok], calls),
    });
    assert.equal((await a.generate(REQUEST)).text, 'ok');
    assert.equal(calls.length, 3);
    assert.equal(sleeps.length, 2);
    const b = new OpenAIAdapter('m', { apiKey: KEY, retries: 3, sleep: async () => {}, fetch: fakeFetch([{ status: 400, raw: `bad key ${KEY}` }], []) });
    await assert.rejects(b.generate(REQUEST), (e: unknown) => {
      assert.ok(e instanceof AdapterError);
      assert.equal(e.status, 400);
      assert.equal(e.retryable, false);
      assert.ok(!e.message.includes(KEY), 'la clave no aparece en el error');
      return true;
    });
    const c = new AnthropicAdapter('m', { apiKey: KEY, retries: 1, sleep: async () => {}, fetch: fakeFetch([{ status: 529, raw: 'overloaded' }], []) });
    await assert.rejects(c.stream(REQUEST).result, (e: unknown) => e instanceof AdapterError && e.status === 529 && e.retryable);
  });

  test('clave: opción, variable de entorno o MissingKeyError', async () => {
    const calls: Call[] = [];
    const saved = process.env.GROQ_API_KEY;
    try {
      delete process.env.GROQ_API_KEY;
      await assert.rejects(new GroqAdapter('m', { fetch: fakeFetch([], calls) }).generate(REQUEST), MissingKeyError);
      assert.equal(calls.length, 0);
      process.env.GROQ_API_KEY = 'gsk_fromenvironment123';
      await new GroqAdapter('m', { fetch: fakeFetch([{ json: { choices: [] } }], calls) }).generate(REQUEST);
      assert.equal(calls[0].headers.authorization, 'Bearer gsk_fromenvironment123');
      assert.ok(!String(new GroqAdapter('m', { apiKey: KEY })).includes(KEY));
    } finally {
      if (saved === undefined) delete process.env.GROQ_API_KEY;
      else process.env.GROQ_API_KEY = saved;
    }
  });

  test('eventos de error en el flujo', async () => {
    const errAnthropic = sse([{ event: 'message_start', data: { type: 'message_start', message: { usage: { input_tokens: 1 } } } },
      { event: 'error', data: { type: 'error', error: { type: 'overloaded_error', message: 'Overloaded' } } }]);
    const s = new AnthropicAdapter('m', { apiKey: KEY, fetch: fakeFetch([{ sse: errAnthropic }], []) }).stream(REQUEST);
    await assert.rejects((async () => { for await (const _ of s) { /* consumir */ } })(), /Overloaded/);
    await assert.rejects(s.result, /Overloaded/);
    const errOpenAI = sse([{ data: { error: { message: 'boom' } } }]);
    await assert.rejects(new OpenAIAdapter('m', { apiKey: KEY, fetch: fakeFetch([{ sse: errOpenAI }], []) }).stream(REQUEST).result, /boom/);
    await assert.rejects(new OpenAIAdapter('m', { apiKey: KEY, fetch: fakeFetch([{ sse: 'data: {no json\n\n' }], []) }).stream(REQUEST).result, /malformed SSE/);
    assert.throws(() => getAdapter('mistral', 'x'), /unknown provider/);
  });
});

describe('parseSSE', () => {
  test('CRLF partido entre fragmentos, datos multilínea, comentarios y eventos sin nombre', async () => {
    const text = ': comentario\r\nevent: uno\r\ndata: a\r\ndata: b\r\nid: 7\r\n\r\ndata: ñandú\n\ndata:sin-espacio\rdata: x\r\r';
    for (let seed = 1; seed < 20; seed++) {
      const events = [];
      for await (const ev of parseSSE(byteChunks(text, seed))) events.push(ev);
      assert.deepEqual(events, [
        { event: 'uno', data: 'a\nb', id: '7' },
        { event: 'message', data: 'ñandú', id: '7' },
        { event: 'message', data: 'sin-espacio\nx', id: '7' },
      ], `semilla ${seed}`);
    }
  });
});

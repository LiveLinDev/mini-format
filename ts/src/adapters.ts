/* adapters.ts — proveedores de modelos intercambiables detrás de una interfaz común.
 * Equivalente de minifmt.ai.adapters (referencia Python): OpenAI (Chat Completions y Responses),
 * Anthropic (Messages), Groq (compatible con OpenAI) y un adaptador simulado sin red.
 * Solo usa `fetch` (inyectable) y SSE para streaming; sin SDKs ni dependencias.
 * Las claves se leen de la opción `apiKey` o de la variable de entorno del proveedor (si existe
 * `process.env`); nunca se devuelven ni se incluyen en mensajes de error.
 * Módulo seguro para navegador (en el navegador, pase `apiKey` o use un proxy propio).
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */
import type { Contract, ContractJSON } from './contract.ts';
import { normalizeContract } from './contract.ts';
import { parseSSE } from './sse.ts';
import type { ByteSource, SSEEvent } from './sse.ts';
import { createReader } from './stream.ts';
import type { ReaderOptions, ReaderResult, StreamRecord } from './stream.ts';

// ------------------------------------------------------------------ tipos comunes
/** Formato de salida neutral: `{type: 'json_schema', name, schema}`. Cada adaptador lo traduce. */
export interface ResponseFormat {
  type: 'json_schema';
  name?: string;
  schema: Record<string, unknown>;
}

export interface GenerateRequest {
  system: string;
  user: string;
  maxTokens: number;
  /** null/undefined: no se envía. */
  temperature?: number | null;
  responseFormat?: ResponseFormat | null;
  seed?: number | null;
  signal?: AbortSignal;
}

/** Resultado común (mismas claves que el dict de la referencia, en camelCase). */
export interface GenerateResult {
  text: string;
  inputTokens: number | null;
  outputTokens: number | null;
  latencyMs: number;
  raw: unknown;
  stopReason: string | null;
  model: string;
  provider: string;
}

/** Flujo de texto de una generación: se itera una vez; `result` se resuelve al terminar. */
export interface ModelStream extends AsyncIterable<string> {
  /** Resultado final (texto completo, uso de tokens, motivo de parada). Consume el flujo si nadie lo itera. */
  readonly result: Promise<GenerateResult>;
}

/** Interfaz común de todos los proveedores: el código de la aplicación depende solo de ella. */
export interface ModelAdapter {
  readonly provider: string;
  readonly model: string;
  readonly supportsStructured: boolean;
  generate(request: GenerateRequest): Promise<GenerateResult>;
  stream(request: GenerateRequest): ModelStream;
}

/** Respuesta mínima de fetch que usan los adaptadores. */
export interface FetchResponseLike {
  status: number;
  text(): Promise<string>;
  body?: ByteSource | null;
}

/** Firma mínima de fetch (la global del navegador o de Node ≥ 18 la cumple). */
export type FetchLike = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: string; signal?: AbortSignal },
) => Promise<FetchResponseLike>;

// ------------------------------------------------------------------ errores y claves
const SENSITIVE_HEADERS = new Set(['authorization', 'x-api-key', 'api-key', 'proxy-authorization', 'cookie']);
const KEY_PATTERNS: [RegExp, string][] = [
  [/sk-[A-Za-z0-9_-]{8,}/g, '***'],
  [/gsk_[A-Za-z0-9]{8,}/g, '***'],
  [/(bearer\s+)[A-Za-z0-9_\-.=]{8,}/gi, '$1***'],
];
const RETRYABLE = new Set([408, 409, 429, 500, 502, 503, 504, 529]);

/** Oculta claves y cadenas con aspecto de credencial. `secrets`: valores exactos a ocultar. */
export function redact(text: unknown, secrets: readonly string[] = []): string {
  let s = String(text);
  for (const v of secrets) if (v && v.length >= 6) s = s.split(v).join('***');
  for (const [re, rep] of KEY_PATTERNS) s = s.replace(re, rep);
  return s;
}

/** Copia de cabeceras apta para registro (las de credenciales se reemplazan por ***). */
export function redactHeaders(headers: Record<string, string>, secrets: readonly string[] = []): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) out[k] = SENSITIVE_HEADERS.has(k.toLowerCase()) ? '***' : redact(v, secrets);
  return out;
}

/** La generación falló (red, estado HTTP, respuesta mal formada...). El mensaje está depurado de claves. */
export class AdapterError extends Error {
  readonly status: number | null;
  readonly retryable: boolean;
  constructor(message: string, opts: { status?: number | null; retryable?: boolean; secrets?: readonly string[] } = {}) {
    super(redact(message, opts.secrets));
    this.name = 'AdapterError';
    this.status = opts.status ?? null;
    this.retryable = !!opts.retryable;
  }
}

export class MissingKeyError extends AdapterError {
  constructor(message: string) {
    super(message);
    this.name = 'MissingKeyError';
  }
}

function envVar(name: string): string | undefined {
  const proc = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process;
  return proc && proc.env ? proc.env[name] : undefined;
}

function now(): number {
  const perf = (globalThis as { performance?: { now(): number } }).performance;
  return perf ? perf.now() : Date.now();
}

const round1 = (x: number): number => Math.round(x * 10) / 10;

// ------------------------------------------------------------------ flujo
type Settled = { ok: true; value: GenerateResult } | { ok: false; error: unknown };

class ModelStreamImpl implements ModelStream {
  private readonly source: () => AsyncGenerator<string, GenerateResult, void>;
  private started = false;
  private resolve!: (r: GenerateResult) => void;
  private reject!: (e: unknown) => void;
  private readonly settled: Promise<GenerateResult>;
  private done: Settled | null = null;

  constructor(source: () => AsyncGenerator<string, GenerateResult, void>) {
    this.source = source;
    this.settled = new Promise<GenerateResult>((res, rej) => {
      this.resolve = res;
      this.reject = rej;
    });
    this.settled.catch(() => undefined); // el error se entrega a quien itere o espere `result`
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<string, void, void> {
    if (this.started) throw new Error('model stream can only be iterated once');
    this.started = true;
    const gen = this.source();
    try {
      for (;;) {
        const step = await gen.next();
        if (step.done) {
          this.done = { ok: true, value: step.value };
          this.resolve(step.value);
          return;
        }
        yield step.value;
      }
    } catch (e) {
      this.done = { ok: false, error: e };
      this.reject(e);
      throw e;
    } finally {
      if (!this.done) {
        const e = new AdapterError('model stream was not consumed to the end');
        this.done = { ok: false, error: e };
        this.reject(e);
        await gen.return(undefined as never);
      }
    }
  }

  get result(): Promise<GenerateResult> {
    if (!this.started) {
      void (async () => {
        try {
          for await (const _ of this) { /* drenar */ }
        } catch { /* entregado por settled */ }
      })();
    }
    return this.settled;
  }
}

/** Crea un ModelStream a partir de un generador que produce deltas de texto y devuelve el resultado. */
export function createModelStream(source: () => AsyncGenerator<string, GenerateResult, void>): ModelStream {
  return new ModelStreamImpl(source);
}

// ------------------------------------------------------------------ base HTTP
export interface HttpAdapterOptions {
  apiKey?: string;
  /** URL completa del endpoint. */
  url?: string;
  fetch?: FetchLike;
  /** Reintentos ante estados reintentables o errores de red (por defecto 3). */
  retries?: number;
  /** Espera entre reintentos (inyectable en pruebas). */
  sleep?: (ms: number) => Promise<void>;
  /** Declara soporte de salida estructurada para este modelo. */
  structured?: boolean;
  /** false: no envía temperature (modelos que la rechazan). */
  sendTemperature?: boolean;
  /** Campos adicionales del cuerpo de la solicitud. */
  extraBody?: Record<string, unknown>;
  /** Cabeceras adicionales. */
  headers?: Record<string, string>;
}

interface StreamState {
  text: string;
  inputTokens: number | null;
  outputTokens: number | null;
  stopReason: string | null;
  model: string | null;
  events: number;
}

/** Base de los adaptadores HTTP: reintentos, depuración de errores y SSE. */
export abstract class HttpAdapter implements ModelAdapter {
  abstract readonly provider: string;
  readonly model: string;
  readonly supportsStructured: boolean;
  protected readonly options: HttpAdapterOptions;

  constructor(model: string, options: HttpAdapterOptions, structuredDefault: boolean) {
    this.model = model;
    this.options = options;
    this.supportsStructured = options.structured ?? structuredDefault;
  }

  protected abstract readonly envVar: string;
  protected abstract readonly defaultUrl: string;
  protected abstract authHeaders(key: string): Record<string, string>;
  protected abstract buildBody(req: GenerateRequest, stream: boolean): Record<string, unknown>;
  protected abstract parseResponse(raw: Record<string, unknown>): Omit<GenerateResult, 'latencyMs' | 'raw' | 'provider'>;
  /** Procesa un evento SSE; devuelve el texto nuevo (o ''). Lanza AdapterError ante eventos de error. */
  protected abstract onEvent(ev: SSEEvent, payload: Record<string, unknown> | null, state: StreamState): string;

  get url(): string {
    return this.options.url ?? this.defaultUrl;
  }

  toString(): string {
    return `<${this.constructor.name} ${this.provider}:${this.model}>`;
  }

  protected key(): string {
    const k = (this.options.apiKey ?? envVar(this.envVar) ?? '').trim();
    if (!k) throw new MissingKeyError(`API key missing: pass options.apiKey or set ${this.envVar}`);
    return k;
  }

  protected checkFormat(req: GenerateRequest): void {
    if (req.responseFormat && !this.supportsStructured) {
      throw new AdapterError(`${this.provider}:${this.model} does not support structured output`);
    }
    if (req.responseFormat && req.responseFormat.type !== 'json_schema') {
      throw new AdapterError(`unsupported response_format type ${String((req.responseFormat as { type?: unknown }).type)}`);
    }
  }

  protected temperature(req: GenerateRequest): number | undefined {
    return req.temperature !== null && req.temperature !== undefined && this.options.sendTemperature !== false
      ? req.temperature : undefined;
  }

  private fetchFn(): FetchLike {
    if (this.options.fetch) return this.options.fetch;
    const g = (globalThis as { fetch?: FetchLike }).fetch;
    if (!g) throw new AdapterError('fetch is not available: pass options.fetch');
    return g.bind(globalThis) as FetchLike;
  }

  /** POST con reintentos; devuelve la respuesta 2xx (sin leer el cuerpo). */
  protected async post(body: Record<string, unknown>, signal?: AbortSignal): Promise<FetchResponseLike> {
    const key = this.key();
    const secrets = [key];
    const headers = { 'content-type': 'application/json', ...this.authHeaders(key), ...(this.options.headers ?? {}) };
    const payload = JSON.stringify(body);
    const retries = this.options.retries ?? 3;
    const sleep = this.options.sleep ?? ((ms: number) => new Promise<void>(r => setTimeout(r, ms)));
    const fetchFn = this.fetchFn();
    let last: AdapterError | null = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
      let resp: FetchResponseLike | null = null;
      try {
        resp = await fetchFn(this.url, { method: 'POST', headers, body: payload, signal });
      } catch (e) {
        if (signal && signal.aborted) throw e;
        const err = e as { name?: string; message?: string };
        last = new AdapterError(`network error calling ${this.url}: ${err.name ?? 'Error'}: ${err.message ?? String(e)}`,
          { retryable: true, secrets });
      }
      if (resp) {
        if (resp.status >= 200 && resp.status < 300) return resp;
        let snippet = '';
        try {
          snippet = (await resp.text()).slice(0, 500);
        } catch { /* sin cuerpo */ }
        last = new AdapterError(`HTTP ${resp.status} from ${this.url}: ${snippet}`,
          { status: resp.status, retryable: RETRYABLE.has(resp.status), secrets });
        if (!last.retryable) throw last;
      }
      if (attempt < retries) await sleep(Math.min(30000, 1000 * 2 ** attempt + Math.random() * 1000));
    }
    throw last as AdapterError;
  }

  async generate(req: GenerateRequest): Promise<GenerateResult> {
    this.checkFormat(req);
    const body = this.buildBody(req, false);
    const t0 = now();
    const resp = await this.post(body, req.signal);
    const text = await resp.text();
    let raw: Record<string, unknown>;
    try {
      raw = JSON.parse(text) as Record<string, unknown>;
    } catch (e) {
      throw new AdapterError(`non-JSON answer from ${this.url}: ${(e as Error).message}`);
    }
    const parsed = this.parseResponse(raw);
    return { ...parsed, latencyMs: round1(now() - t0), raw, provider: this.provider };
  }

  stream(req: GenerateRequest): ModelStream {
    const self = this;
    return createModelStream(async function* () {
      self.checkFormat(req);
      const body = self.buildBody(req, true);
      const t0 = now();
      const resp = await self.post(body, req.signal);
      if (!resp.body) throw new AdapterError(`streaming answer from ${self.url} has no body`);
      const state: StreamState = { text: '', inputTokens: null, outputTokens: null, stopReason: null, model: null, events: 0 };
      for await (const ev of parseSSE(resp.body)) {
        state.events++;
        let payload: Record<string, unknown> | null = null;
        if (ev.data && ev.data !== '[DONE]') {
          try {
            payload = JSON.parse(ev.data) as Record<string, unknown>;
          } catch {
            throw new AdapterError(`malformed SSE data from ${self.url}: ${ev.data.slice(0, 200)}`);
          }
        }
        const delta = self.onEvent(ev, payload, state);
        if (delta) {
          state.text += delta;
          yield delta;
        }
      }
      return {
        text: state.text, inputTokens: state.inputTokens, outputTokens: state.outputTokens,
        latencyMs: round1(now() - t0), raw: { streamed: true, events: state.events }, stopReason: state.stopReason,
        model: state.model ?? self.model, provider: self.provider,
      };
    });
  }
}

const obj = (v: unknown): Record<string, unknown> =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, unknown> : {};
const numOrNull = (v: unknown): number | null => (typeof v === 'number' ? v : null);
const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null);

function streamError(provider: string, payload: Record<string, unknown> | null): AdapterError {
  const err = obj(payload && (payload.error ?? obj(payload.response).error));
  const msg = strOrNull(err.message) ?? JSON.stringify(payload);
  return new AdapterError(`${provider} stream error: ${msg}`, { retryable: false });
}

// ------------------------------------------------------------------ OpenAI Chat Completions
/** Formato neutral -> `response_format` de OpenAI (JSON Schema estricto). */
export function toOpenAIFormat(rf: ResponseFormat | null | undefined): Record<string, unknown> | undefined {
  if (!rf) return undefined;
  return { type: 'json_schema', json_schema: { name: rf.name ?? 'salida', strict: true, schema: rf.schema } };
}

export const OPENAI_CHAT_URL = 'https://api.openai.com/v1/chat/completions';
export const OPENAI_RESPONSES_URL = 'https://api.openai.com/v1/responses';
export const ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages';
export const ANTHROPIC_VERSION = '2023-06-01';
export const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';

/** Adaptador de Chat Completions (OpenAI y compatibles). */
export class OpenAIAdapter extends HttpAdapter {
  readonly provider: string = 'openai';
  protected readonly envVar: string = 'OPENAI_API_KEY';
  protected readonly defaultUrl: string = OPENAI_CHAT_URL;

  constructor(model: string, options: HttpAdapterOptions = {}) {
    super(model, options, true);
  }

  protected authHeaders(key: string): Record<string, string> {
    return { authorization: `Bearer ${key}` };
  }

  protected buildBody(req: GenerateRequest, stream: boolean): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: this.model,
      messages: [{ role: 'system', content: req.system }, { role: 'user', content: req.user }],
      max_completion_tokens: Math.trunc(req.maxTokens),
    };
    const t = this.temperature(req);
    if (t !== undefined) body.temperature = t;
    if (req.seed !== null && req.seed !== undefined) body.seed = Math.trunc(req.seed) % 2 ** 31;
    const rf = toOpenAIFormat(req.responseFormat);
    if (rf) body.response_format = rf;
    if (stream) {
      body.stream = true;
      body.stream_options = { include_usage: true };
    }
    return Object.assign(body, this.options.extraBody ?? {});
  }

  protected parseResponse(raw: Record<string, unknown>): Omit<GenerateResult, 'latencyMs' | 'raw' | 'provider'> {
    const choice = obj(Array.isArray(raw.choices) ? raw.choices[0] : undefined);
    const msg = obj(choice.message);
    const usage = obj(raw.usage);
    return {
      text: strOrNull(msg.content) ?? strOrNull(msg.refusal) ?? '',
      inputTokens: numOrNull(usage.prompt_tokens),
      outputTokens: numOrNull(usage.completion_tokens),
      stopReason: strOrNull(choice.finish_reason),
      model: strOrNull(raw.model) ?? this.model,
    };
  }

  protected onEvent(_ev: SSEEvent, payload: Record<string, unknown> | null, state: StreamState): string {
    if (!payload) return '';
    if (payload.error) throw streamError(this.provider, payload);
    if (typeof payload.model === 'string') state.model = payload.model;
    // OpenAI envía usage en el último fragmento; Groq lo envía en x_groq.usage
    const usage = obj(payload.usage ?? obj(payload.x_groq).usage);
    if (typeof usage.prompt_tokens === 'number') state.inputTokens = usage.prompt_tokens;
    if (typeof usage.completion_tokens === 'number') state.outputTokens = usage.completion_tokens;
    let out = '';
    for (const c of Array.isArray(payload.choices) ? payload.choices : []) {
      const choice = obj(c);
      const delta = obj(choice.delta);
      if (typeof delta.content === 'string') out += delta.content;
      else if (typeof delta.refusal === 'string') out += delta.refusal;
      if (typeof choice.finish_reason === 'string') state.stopReason = choice.finish_reason;
    }
    return out;
  }
}

/** Groq: endpoint compatible con Chat Completions de OpenAI. Salida estructurada solo en algunos modelos. */
export class GroqAdapter extends OpenAIAdapter {
  override readonly provider: string = 'groq';
  protected override readonly envVar: string = 'GROQ_API_KEY';
  protected override readonly defaultUrl: string = GROQ_URL;

  constructor(model: string, options: HttpAdapterOptions = {}) {
    super(model, { structured: false, ...options });
  }

  protected override buildBody(req: GenerateRequest, stream: boolean): Record<string, unknown> {
    const body = super.buildBody(req, stream);
    if (stream && !(this.options.extraBody && 'stream_options' in this.options.extraBody)) delete body.stream_options;
    return body;
  }
}

// ------------------------------------------------------------------ OpenAI Responses
/** Adaptador de la Responses API de OpenAI. */
export class OpenAIResponsesAdapter extends HttpAdapter {
  readonly provider: string = 'openai';
  protected readonly envVar: string = 'OPENAI_API_KEY';
  protected readonly defaultUrl: string = OPENAI_RESPONSES_URL;

  constructor(model: string, options: HttpAdapterOptions = {}) {
    super(model, options, true);
  }

  protected authHeaders(key: string): Record<string, string> {
    return { authorization: `Bearer ${key}` };
  }

  protected buildBody(req: GenerateRequest, stream: boolean): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: this.model,
      instructions: req.system,
      input: req.user,
      max_output_tokens: Math.trunc(req.maxTokens),
    };
    const t = this.temperature(req);
    if (t !== undefined) body.temperature = t;
    if (req.responseFormat) {
      body.text = { format: { type: 'json_schema', name: req.responseFormat.name ?? 'salida', strict: true, schema: req.responseFormat.schema } };
    }
    if (stream) body.stream = true;
    return Object.assign(body, this.options.extraBody ?? {});
  }

  private static stop(resp: Record<string, unknown>): string | null {
    const reason = strOrNull(obj(resp.incomplete_details).reason);
    return reason ?? strOrNull(resp.status);
  }

  protected parseResponse(raw: Record<string, unknown>): Omit<GenerateResult, 'latencyMs' | 'raw' | 'provider'> {
    let text = typeof raw.output_text === 'string' ? raw.output_text : '';
    if (!text) {
      for (const item of Array.isArray(raw.output) ? raw.output : []) {
        for (const part of Array.isArray(obj(item).content) ? obj(item).content as unknown[] : []) {
          const p = obj(part);
          if (p.type === 'output_text' && typeof p.text === 'string') text += p.text;
          else if (p.type === 'refusal' && typeof p.refusal === 'string') text += p.refusal;
        }
      }
    }
    const usage = obj(raw.usage);
    return {
      text,
      inputTokens: numOrNull(usage.input_tokens),
      outputTokens: numOrNull(usage.output_tokens),
      stopReason: OpenAIResponsesAdapter.stop(raw),
      model: strOrNull(raw.model) ?? this.model,
    };
  }

  protected onEvent(ev: SSEEvent, payload: Record<string, unknown> | null, state: StreamState): string {
    if (!payload) return '';
    const type = strOrNull(payload.type) ?? ev.event;
    if (type === 'error' || type === 'response.failed') throw streamError(this.provider, payload);
    if (type === 'response.output_text.delta' || type === 'response.refusal.delta') {
      return typeof payload.delta === 'string' ? payload.delta : '';
    }
    if (type === 'response.completed' || type === 'response.incomplete' || type === 'response.created') {
      const resp = obj(payload.response);
      if (typeof resp.model === 'string') state.model = resp.model;
      if (type !== 'response.created') {
        const usage = obj(resp.usage);
        state.inputTokens = numOrNull(usage.input_tokens);
        state.outputTokens = numOrNull(usage.output_tokens);
        state.stopReason = OpenAIResponsesAdapter.stop(resp);
      }
    }
    return '';
  }
}

// ------------------------------------------------------------------ Anthropic
export interface AnthropicAdapterOptions extends HttpAdapterOptions {
  /** Añade `anthropic-dangerous-direct-browser-access: true` (llamadas directas desde el navegador). */
  browser?: boolean;
}

/** Adaptador de la Messages API de Anthropic. */
export class AnthropicAdapter extends HttpAdapter {
  readonly provider: string = 'anthropic';
  protected readonly envVar: string = 'ANTHROPIC_API_KEY';
  protected readonly defaultUrl: string = ANTHROPIC_URL;
  private readonly browser: boolean;

  constructor(model: string, options: AnthropicAdapterOptions = {}) {
    super(model, options, true);
    this.browser = !!options.browser;
  }

  protected authHeaders(key: string): Record<string, string> {
    const h: Record<string, string> = { 'x-api-key': key, 'anthropic-version': ANTHROPIC_VERSION };
    if (this.browser) h['anthropic-dangerous-direct-browser-access'] = 'true';
    return h;
  }

  protected buildBody(req: GenerateRequest, stream: boolean): Record<string, unknown> {
    // la Messages API no tiene parámetro seed
    const body: Record<string, unknown> = {
      model: this.model,
      max_tokens: Math.trunc(req.maxTokens),
      system: req.system,
      messages: [{ role: 'user', content: req.user }],
    };
    const t = this.temperature(req);
    if (t !== undefined) body.temperature = t;
    if (req.responseFormat) body.output_config = { format: { type: 'json_schema', schema: req.responseFormat.schema } };
    if (stream) body.stream = true;
    for (const [k, v] of Object.entries(this.options.extraBody ?? {})) {
      body[k] = k === 'output_config' && body.output_config ? { ...obj(v), ...obj(body.output_config) } : v;
    }
    return body;
  }

  private static inputTokens(usage: Record<string, unknown>): number | null {
    const inp = numOrNull(usage.input_tokens);
    if (inp === null) return null;
    return inp + (numOrNull(usage.cache_creation_input_tokens) ?? 0) + (numOrNull(usage.cache_read_input_tokens) ?? 0);
  }

  protected parseResponse(raw: Record<string, unknown>): Omit<GenerateResult, 'latencyMs' | 'raw' | 'provider'> {
    let text = '';
    for (const b of Array.isArray(raw.content) ? raw.content : []) {
      const block = obj(b);
      if (block.type === 'text' && typeof block.text === 'string') text += block.text;
    }
    const usage = obj(raw.usage);
    return {
      text,
      inputTokens: AnthropicAdapter.inputTokens(usage),
      outputTokens: numOrNull(usage.output_tokens),
      stopReason: strOrNull(raw.stop_reason),
      model: strOrNull(raw.model) ?? this.model,
    };
  }

  protected onEvent(ev: SSEEvent, payload: Record<string, unknown> | null, state: StreamState): string {
    if (!payload) return '';
    const type = strOrNull(payload.type) ?? ev.event;
    switch (type) {
      case 'error':
        throw streamError(this.provider, payload);
      case 'message_start': {
        const msg = obj(payload.message);
        if (typeof msg.model === 'string') state.model = msg.model;
        const usage = obj(msg.usage);
        state.inputTokens = AnthropicAdapter.inputTokens(usage);
        if (typeof usage.output_tokens === 'number') state.outputTokens = usage.output_tokens;
        return '';
      }
      case 'content_block_delta': {
        const delta = obj(payload.delta);
        return delta.type === 'text_delta' && typeof delta.text === 'string' ? delta.text : '';
      }
      case 'message_delta': {
        const delta = obj(payload.delta);
        if (typeof delta.stop_reason === 'string') state.stopReason = delta.stop_reason;
        const usage = obj(payload.usage);
        if (typeof usage.output_tokens === 'number') state.outputTokens = usage.output_tokens;
        if (typeof usage.input_tokens === 'number') state.inputTokens = AnthropicAdapter.inputTokens(usage);
        return '';
      }
      default:
        return '';
    }
  }
}

// ------------------------------------------------------------------ simulado
export interface SimulatedAdapterOptions {
  /** Texto a responder para cada solicitud (por defecto 'OK'). */
  respond?: (request: GenerateRequest, call: number) => string;
  /** Respuestas fijas en orden (se repite la última). Alternativa a `respond`. */
  responses?: string[];
  /** Semilla del troceado determinista del flujo. */
  seed?: number;
  /** Tamaño máximo (caracteres) de cada fragmento del flujo. Por defecto 7. */
  maxChunk?: number;
  structured?: boolean;
  /** Tokens estimados por carácter (por defecto 1/4). */
  tokensPerChar?: number;
}

/** Adaptador determinista sin red: misma solicitud y semilla -> misma respuesta y mismos fragmentos. */
export class SimulatedAdapter implements ModelAdapter {
  readonly provider: string = 'simulated';
  readonly model: string;
  readonly supportsStructured: boolean;
  /** Solicitudes recibidas (para aserciones en pruebas). */
  readonly calls: GenerateRequest[] = [];
  private readonly opts: SimulatedAdapterOptions;

  constructor(model: string = 'sim', options: SimulatedAdapterOptions = {}) {
    this.model = model;
    this.opts = options;
    this.supportsStructured = options.structured ?? true;
  }

  private tokens(text: string): number {
    return text ? Math.max(1, Math.ceil(text.length * (this.opts.tokensPerChar ?? 0.25))) : 0;
  }

  private answer(req: GenerateRequest): Omit<GenerateResult, 'latencyMs'> {
    if (req.responseFormat && !this.supportsStructured) {
      throw new AdapterError(`${this.provider}:${this.model} does not support structured output`);
    }
    const call = this.calls.length;
    this.calls.push(req);
    let text = 'OK';
    if (this.opts.respond) text = this.opts.respond(req, call);
    else if (this.opts.responses && this.opts.responses.length) {
      text = this.opts.responses[Math.min(call, this.opts.responses.length - 1)];
    }
    let stop = 'end_turn';
    const perChar = this.opts.tokensPerChar ?? 0.25;
    if (this.tokens(text) > req.maxTokens) {
      text = text.slice(0, Math.max(0, Math.floor(req.maxTokens / perChar)));
      stop = 'max_tokens';
    }
    return {
      text, inputTokens: this.tokens(req.system) + this.tokens(req.user) + 8, outputTokens: this.tokens(text),
      raw: { simulated: true, call }, stopReason: stop, model: this.model, provider: this.provider,
    };
  }

  async generate(req: GenerateRequest): Promise<GenerateResult> {
    return { ...this.answer(req), latencyMs: 0 };
  }

  stream(req: GenerateRequest): ModelStream {
    const self = this;
    return createModelStream(async function* () {
      const res = self.answer(req);
      let a = (self.opts.seed ?? 0) >>> 0;
      const rnd = (): number => { // mulberry32
        a = (a + 0x6d2b79f5) >>> 0;
        let t = a;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
      };
      const max = Math.max(1, self.opts.maxChunk ?? 7);
      for (let i = 0; i < res.text.length;) {
        const k = 1 + Math.floor(rnd() * max);
        yield res.text.slice(i, i + k);
        i += k;
      }
      return { ...res, latencyMs: 0 };
    });
  }
}

// ------------------------------------------------------------------ registro de proveedores
export type ProviderName = 'openai' | 'openai-responses' | 'anthropic' | 'groq' | 'simulated' | 'simulado';

/** Crea un adaptador por nombre de proveedor (equivale a get_adapter de la referencia). */
export function getAdapter(provider: ProviderName | string, model: string, options: Record<string, unknown> = {}): ModelAdapter {
  switch (provider.toLowerCase()) {
    case 'openai': return new OpenAIAdapter(model, options as HttpAdapterOptions);
    case 'openai-responses': return new OpenAIResponsesAdapter(model, options as HttpAdapterOptions);
    case 'anthropic': return new AnthropicAdapter(model, options as AnthropicAdapterOptions);
    case 'groq': return new GroqAdapter(model, options as HttpAdapterOptions);
    case 'simulated':
    case 'simulado': return new SimulatedAdapter(model, options as SimulatedAdapterOptions);
    default:
      throw new AdapterError(`unknown provider '${provider}' (known: anthropic, groq, openai, openai-responses, simulated)`);
  }
}

// ------------------------------------------------------------------ registros en streaming
export interface StreamRecordsOptions extends ReaderOptions {
  /**
   * true (por defecto): descarta prosa previa y cercas de código como extractDocument, de modo
   * incremental (el documento empieza en la línea `<prefix>|...`).
   */
  extract?: boolean;
}

export interface StreamRecordsResult {
  /** Resultado del lector (documento, errores, truncamiento). */
  reader: ReaderResult;
  /** Resultado de la generación (texto crudo completo, tokens, motivo de parada). */
  generation: GenerateResult;
}

/** Filtro incremental por líneas equivalente a extractDocument. */
class DocumentGate {
  private readonly prefix: string;
  private readonly extract: boolean;
  private state: 'seek' | 'body' | 'done' = 'seek';
  private fenceBefore = false;
  private partial = '';
  private readonly held: string[] = [];

  constructor(prefix: string, extract: boolean) {
    this.prefix = prefix;
    this.extract = extract;
    if (!extract) this.state = 'body';
  }

  private static fence(line: string): boolean {
    return /^\s*(```|~~~)/.test(line);
  }

  private isHeader(line: string): boolean {
    const s = line.trim().replace(/^﻿+/, '');
    return s === this.prefix || s.startsWith(this.prefix + '|');
  }

  private line(line: string, out: string[]): void {
    if (!this.extract) {
      out.push(line);
      return;
    }
    if (this.state === 'done') return;
    if (this.state === 'seek') {
      if (this.isHeader(line)) {
        this.state = 'body';
        this.held.length = 0;
        out.push(line);
      } else {
        if (DocumentGate.fence(line)) this.fenceBefore = true;
        else this.held.push(line);
      }
      return;
    }
    if (DocumentGate.fence(line)) {
      if (this.fenceBefore) this.state = 'done';
      return;
    }
    out.push(line);
  }

  /** Devuelve texto listo para el lector (líneas completas terminadas en LF). */
  push(chunk: string): string {
    if (!this.extract) return chunk;
    const text = this.partial + chunk;
    const parts = text.split('\n');
    this.partial = parts.pop() as string;
    const out: string[] = [];
    for (const p of parts) this.line(p.replace(/\r$/, ''), out);
    return out.map(l => l + '\n').join('');
  }

  /** Cierra el flujo: la última línea sin LF, o todo lo retenido si nunca apareció la cabecera. */
  end(): string {
    if (!this.extract) return '';
    const out: string[] = [];
    if (this.partial) this.line(this.partial.replace(/\r$/, ''), out);
    this.partial = '';
    if (this.state === 'seek') return this.held.join('\n');
    return out.join('\n');
  }
}

/**
 * Genera con cualquier adaptador y lee los registros .mini a medida que llegan.
 * Emite cada registro válido en cuanto se completa su línea y devuelve el resultado final.
 */
export async function* streamRecords(
  adapter: ModelAdapter, contract: Contract | ContractJSON, request: GenerateRequest, opts: StreamRecordsOptions = {},
): AsyncGenerator<StreamRecord, StreamRecordsResult, void> {
  const c = normalizeContract(contract);
  const reader = createReader(c, opts);
  const gate = new DocumentGate(c.prefix, opts.extract !== false);
  const stream = adapter.stream(request);
  for await (const delta of stream) {
    const text = gate.push(delta);
    if (text) for (const rec of reader.push(text)) yield rec;
  }
  const generation = await stream.result;
  const tail = gate.end();
  const before = reader.records.length;
  const result = reader.end(tail || undefined);
  // registros completados por la última línea (sin LF final)
  for (let i = before; i < result.records.length; i++) {
    yield { record: result.records[i], line: result.document.recordLines[i], index: i };
  }
  return { reader: result, generation };
}

/* sse.ts — lector mínimo de Server-Sent Events (text/event-stream) sobre fetch.
 * Funciona con ReadableStream (navegador, Node ≥ 18) o con cualquier iterable asíncrono de bytes/texto.
 * MIT License — A. E. J. Palma Obispo, E. J. Palomino Santa Cruz (UPC, 2026)
 */

/** Un evento SSE ya ensamblado. `event` es 'message' si el servidor no lo nombra. */
export interface SSEEvent {
  event: string;
  data: string;
  id: string | null;
}

/** Cuerpo de respuesta aceptado: ReadableStream de la Fetch API o iterable (asíncrono) de fragmentos. */
export type ByteSource =
  | { getReader(): { read(): Promise<{ done: boolean; value?: Uint8Array | string }>; releaseLock(): void } }
  | AsyncIterable<Uint8Array | string>
  | Iterable<Uint8Array | string>;

/** Itera los fragmentos de un cuerpo como texto UTF-8 (decodificación incremental). */
export async function* textChunks(body: ByteSource): AsyncGenerator<string, void, void> {
  const decoder = new TextDecoder('utf-8');
  const decode = (v: Uint8Array | string | undefined): string =>
    v === undefined ? '' : typeof v === 'string' ? v : decoder.decode(v, { stream: true });
  if ('getReader' in body && typeof body.getReader === 'function') {
    const reader = body.getReader();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const t = decode(value);
        if (t) yield t;
      }
    } finally {
      reader.releaseLock();
    }
  } else {
    for await (const v of body as AsyncIterable<Uint8Array | string>) {
      const t = decode(v);
      if (t) yield t;
    }
  }
  const tail = decoder.decode();
  if (tail) yield tail;
}

/** Analiza un flujo text/event-stream según la especificación WHATWG (líneas CR, LF o CRLF). */
export async function* parseSSE(body: ByteSource): AsyncGenerator<SSEEvent, void, void> {
  let buffer = '';
  let data: string[] = [];
  let event = '';
  let id: string | null = null;
  let hasData = false;
  const dispatch = (): SSEEvent | null => {
    if (!hasData) {
      event = '';
      return null;
    }
    const out: SSEEvent = { event: event || 'message', data: data.join('\n'), id };
    data = [];
    event = '';
    hasData = false;
    return out;
  };
  const line = (raw: string): SSEEvent | null => {
    if (raw === '') return dispatch();
    if (raw.startsWith(':')) return null;
    const colon = raw.indexOf(':');
    const name = colon < 0 ? raw : raw.slice(0, colon);
    let value = colon < 0 ? '' : raw.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (name === 'data') {
      data.push(value);
      hasData = true;
    } else if (name === 'event') {
      event = value;
    } else if (name === 'id') {
      id = value;
    }
    return null;
  };
  for await (const chunk of textChunks(body)) {
    buffer += chunk;
    for (;;) {
      const m = /\r\n|\r|\n/.exec(buffer);
      // un CR final puede ser la primera mitad de un CRLF: se espera al siguiente fragmento
      if (!m || (m[0] === '\r' && m.index === buffer.length - 1)) break;
      const raw = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      const ev = line(raw);
      if (ev) yield ev;
    }
  }
  if (buffer) {
    const ev = line(buffer.replace(/\r$/, ''));
    if (ev) yield ev;
  }
  const last = dispatch();
  if (last) yield last;
}

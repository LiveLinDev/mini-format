"""Replay a complete saved AI run, or call an AI with a key kept in memory.

    python examples/flujo-soporte/run.py
    python examples/flujo-soporte/run.py --serve
    python examples/flujo-soporte/run.py --live [--formato mini|json] [--max-tokens N]

No model is called in replay mode. Live mode is an explicit local form action, or ``--live``, which reads the
provider from environment variables so the same application can switch provider or model without code changes:

    MINI_IA_URL       Chat Completions base URL of any OpenAI-compatible server (default https://api.openai.com/v1;
                      also vLLM, Ollama, DeepSeek, Groq...)
    MINI_IA_MODEL     model name (default gpt-4.1-mini)
    MINI_IA_KEY       key, kept in memory only (falls back to OPENAI_API_KEY; a local server may need none)
    MINI_IA_CABECERA  header that carries the key (default Authorization, sent as "Bearer <key>")
    MINI_IA_EXTRA     optional JSON merged into the request body, e.g. {"chat_template_kwargs": {"enable_thinking": false}}

``--formato`` selects the only component that changes: ``mini`` validates and repairs with mini-format,
``json`` asks for a JSON array and reads it with ``json.loads`` (the usual reader). Same messages, same model.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if (ROOT / "src").is_dir():
    sys.path.insert(0, str(ROOT / "src"))

OPENAI_URL = "https://api.openai.com/v1"
TASK = "Convierte estos 20 mensajes en tickets. Un ticket por mensaje, con su id original, titulo, categoria y prioridad.\n"
JSON_FORMAT = ("Responde solo con un arreglo JSON de 20 objetos con las claves id (entero), titulo (texto breve), "
               "categoria y prioridad (alta, media o baja), en el orden de los mensajes. Sin texto adicional.")


def chat(prompt, *, url=OPENAI_URL, model="gpt-4.1-mini", key=None, header="Authorization", extra=None,
         max_tokens=None, calls=None):
    """One Chat Completions call to an OpenAI-compatible server; returns (text, finish_reason).

    The key travels only in the request header. Each call appends tokens, latency and stop reason to ``calls``
    (never the key, the headers or the provider error body)."""
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    body.update(extra or {})
    headers = {"Content-Type": "application/json"}
    if key:
        headers[header] = "Bearer " + key if header.lower() == "authorization" else key
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    request = urllib.request.Request(endpoint, data=json.dumps(body).encode("utf-8"), headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as exc:
        # Never persist or return the provider body or request headers.
        raise ValueError(f"AI API returned HTTP {exc.code}") from None
    choice = answer["choices"][0]
    usage = answer.get("usage") or {}
    if calls is not None:
        calls.append({"input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
                      "latency_ms": round((time.perf_counter() - start) * 1000), "finish_reason": choice.get("finish_reason"),
                      "max_tokens": body.get("max_tokens"), "model": answer.get("model")})
    return (choice.get("message") or {}).get("content") or "", choice.get("finish_reason")


def read_json_tickets(text):
    """The usual reader: an optional Markdown fence is removed and the rest goes to ``json.loads``."""
    fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n?```\s*", text, re.S)
    data = json.loads(fenced.group(1) if fenced else text)
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), data)
    if not isinstance(data, list):
        raise ValueError("the JSON answer is not an array of tickets")
    return data


def execute(*, key=None, model="gpt-4.1-mini", out=None, url=OPENAI_URL, header="Authorization", extra=None,
            max_tokens=None, formato="mini", live=None):
    from minifmt.domain import build_bundle
    from minifmt.workflow import Workflow, WorkflowError
    sample = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    messages = json.loads((HERE / "messages.json").read_text(encoding="utf-8"))
    live = bool(key) if live is None else live
    with tempfile.TemporaryDirectory(prefix="mini_support_") as temporary:
        bundle = Path(temporary) / "toolkit"
        build_bundle([sample], "ticket", bundle)
        workflow = Workflow(bundle)
        task = TASK + json.dumps(messages, ensure_ascii=False)
        calls = []
        if not live:
            def generate(prompt):
                name = "raw.mini" if not calls else "correction.json"
                calls.append(name)
                return (HERE / name).read_bytes().decode("utf-8")

            data = workflow.run(generate, task, expected_records=20)
            if data != sample:
                raise ValueError("replay differs from the recorded JSON")
            history = {"mode": "replay", "author": "Muse", "recorded_date": "2026-10-03",
                       "note": "Recorded illustrative output; errors were deliberately inserted for the repair demonstration.",
                       **workflow.last_run}
            _save(out, history, data)
            return history

        options = dict(url=url, model=model, key=key, header=header, extra=extra, max_tokens=max_tokens, calls=calls)
        base = {"mode": "live", "author": model, "recorded_date": None, "note": "Live model output.",
                "format": formato, "endpoint": urllib.parse.urlsplit(url).netloc, "calls": calls}
        answers = []
        if formato == "json":
            text, _ = chat(TASK + json.dumps(messages, ensure_ascii=False) + "\n\n" + JSON_FORMAT, **options)
            answers.append(("respuesta_1.json", text))
            try:
                data, error = read_json_tickets(text), None
            except ValueError as exc:  # json.JSONDecodeError is a ValueError
                data, error = None, f"{type(exc).__name__}: {exc}"
            history = {**base, "ok": data is not None, "error": error, "data": data}
            _save(out, history, data, answers)
            return history

        def generate(prompt):
            text, _ = chat(prompt, **options)
            answers.append((f"respuesta_{len(answers) + 1}.mini", text))
            return text

        first, finish = chat(workflow.prompt(task, 20), **options)
        answers.append(("respuesta_1.mini", first))
        try:
            data = workflow.process(first, generate=generate, task=task, expected_records=20, truncated=finish == "length")
        except WorkflowError:
            data = None
        history = {**base, "summary": workflow.summary(), **workflow.last_run}
        history.setdefault("data", data)
        _save(out, history, data, answers)
        return history


def _save(out, history, data, answers=()):
    if not out:
        return
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in answers:
        (out / name).write_bytes(text.encode("utf-8"))
    for name, value in (("history.json", history), ("result.json", data)):
        (out / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def live_from_environment(out, formato="mini", max_tokens=None):
    """``--live``: provider, model and key come from MINI_IA_* variables (see the module docstring)."""
    url = os.environ.get("MINI_IA_URL", OPENAI_URL)
    key = os.environ.get("MINI_IA_KEY") or os.environ.get("OPENAI_API_KEY") or None
    extra = json.loads(os.environ["MINI_IA_EXTRA"]) if os.environ.get("MINI_IA_EXTRA") else None
    history = execute(key=key, live=True, model=os.environ.get("MINI_IA_MODEL", "gpt-4.1-mini"), out=out, url=url,
                      header=os.environ.get("MINI_IA_CABECERA", "Authorization"), extra=extra,
                      max_tokens=max_tokens, formato=formato)
    calls = history["calls"]
    records = len(history["data"]) if isinstance(history.get("data"), list) else 0
    salida = sum(c["output_tokens"] or 0 for c in calls)
    servido = next((c["model"] for c in calls if c.get("model")), None)
    informado = f" (el servidor informa: {servido})" if servido and servido != history["author"] else ""
    print(f"Proveedor: {history['endpoint']} · modelo: {history['author']}{informado} · formato: {formato}")
    for n, c in enumerate(calls, 1):
        print(f"  llamada {n}: {c['input_tokens']} tokens de entrada, {c['output_tokens']} de salida, "
              f"{c['latency_ms']} ms, fin={c['finish_reason']}" + (f", límite={c['max_tokens']}" if c["max_tokens"] else ""))
    if formato == "json":
        print(f"JSON: {'OK' if history['ok'] else 'NO SE PUDO LEER'} · {records} tickets" + (f" · {history['error']}" if history["error"] else ""))
    else:
        print(history.get("summary") or "")
    print(f"Tickets entregados a la aplicación: {records} de 20 · tokens de salida: {salida} · {out}/history.json")
    return history


def serve(port):
    # Keys are accepted only by the local server, never written to history.
    csrf = secrets.token_urlsafe(24)
    page = (HERE / "local.html").read_text(encoding="utf-8").replace("__CSRF__", csrf)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, kind="application/json"):
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            if self.path == "/":
                self.send(200, page, "text/html")
            else:
                self.send(404, '{"error":"Not found"}')

        def do_POST(self):
            if self.path != "/run" or self.headers.get("X-Mini-CSRF") != csrf:
                self.send(403, '{"error":"Invalid local request"}')
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 8192:
                self.send(400, '{"error":"Invalid request size"}')
                return
            try:
                body = json.loads(self.rfile.read(length))
                key = body.get("key", "").strip() if body.get("mode") == "live" else None
                if body.get("mode") == "live" and not key:
                    raise ValueError("Introduce tu API key para usar IA real.")
                history = execute(key=key, model=body.get("model") or "gpt-4.1-mini")
                self.send(200, json.dumps(history, ensure_ascii=False))
            except Exception as exc:
                report = getattr(exc, "report", None)
                self.send(422, json.dumps({"error": str(exc), "history": report}, ensure_ascii=False))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Abre http://127.0.0.1:{server.server_port} · Ctrl+C para salir", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="output/soporte")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--live", action="store_true", help="call the model configured in MINI_IA_URL / MINI_IA_MODEL / MINI_IA_KEY")
    ap.add_argument("--formato", choices=("mini", "json"), default="mini", help="component that reads the answer (live mode)")
    ap.add_argument("--max-tokens", type=int, help="output limit sent to the provider (live mode)")
    args = ap.parse_args()
    if args.serve:
        serve(args.port)
    elif args.live:
        live_from_environment(args.out, args.formato, args.max_tokens)
    else:
        history = execute(out=args.out)
        print(f"OK: 20 tickets - generate -> validate -> repair -> JSON - {args.out}/history.json")

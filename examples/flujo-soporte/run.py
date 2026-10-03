"""Replay a complete saved AI run, or call an AI with a key kept in memory.

    python examples/flujo-soporte/run.py
    python examples/flujo-soporte/run.py --serve

No model is called in replay mode. Live mode is an explicit local form action.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys
import tempfile
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if (ROOT / "src").is_dir():
    sys.path.insert(0, str(ROOT / "src"))


def execute(*, key=None, model="gpt-4.1-mini", out=None):
    from minifmt.domain import build_bundle
    from minifmt.workflow import Workflow
    sample = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    messages = json.loads((HERE / "messages.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="mini_support_") as temporary:
        bundle = Path(temporary) / "toolkit"
        build_bundle([sample], "ticket", bundle)
        workflow = Workflow(bundle)
        task = "Convierte estos 20 mensajes en tickets. Un ticket por mensaje, con su id original, titulo, categoria y prioridad.\n" + json.dumps(messages, ensure_ascii=False)
        calls = []

        def generate(prompt):
            if key:
                request = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                    data=json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(request, timeout=90) as response:
                        content = json.load(response)["choices"][0]["message"]["content"]
                except urllib.error.HTTPError as exc:
                    # Never persist or return the provider body or request headers.
                    raise ValueError(f"AI API returned HTTP {exc.code}") from None
                calls.append("live")
                return content
            name = "raw.mini" if not calls else "correction.json"
            calls.append(name)
            return (HERE / name).read_bytes().decode("utf-8")

        data = workflow.run(generate, task, expected_records=20)
        if not key and data != sample:
            raise ValueError("replay differs from the recorded JSON")
        history = {"mode": "live" if key else "replay", "author": model if key else "Muse", "recorded_date": "2026-10-03" if not key else None,
                   "note": "Recorded illustrative output; errors were deliberately inserted for the repair demonstration." if not key else "Live model output.",
                   **workflow.last_run}
        if out:
            out = Path(out)
            out.mkdir(parents=True, exist_ok=True)
            for name, value in (("history.json", history), ("result.json", data)):
                (out / name).write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
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
    args = ap.parse_args()
    if args.serve:
        serve(args.port)
    else:
        history = execute(out=args.out)
        print(f"OK: 20 tickets - generate -> validate -> repair -> JSON - {args.out}/history.json")

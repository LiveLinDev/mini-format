"""Genera las respuestas de V2 con Claude Code y Kimi Code (CLI con la cuenta del usuario, sin claves de API).

Lee las filas de ``run.py preparar`` / ``run.py preparar-reparacion`` (``system``, ``user``, ``celda_id``…), envía cada
una a la CLI indicada con el prompt de sistema EXACTO del arnés y sin herramientas, y escribe el JSONL que acepta
``run.py importar``, más el uso de tokens que informa cada CLI y el costo de salida (tokens de salida × tarifa de salida).

* Claude Code: ``claude -p --safe-mode`` (sin CLAUDE.md, skills, plugins, hooks ni MCP), ``--system-prompt`` del arnés,
  ``--tools ""``, ``--output-format json`` (trae ``usage.output_tokens``, que incluye el razonamiento).
* Kimi Code: ``kimi -p`` con un agente efímero (``tools: []``, cuerpo = prompt de sistema del arnés) y
  ``--output-format stream-json``; el uso se lee del registro local de la sesión (``wire.jsonl``: ``usage.output``).

Reanudable: una celda ya escrita no se vuelve a pedir. Uso:
  python experiments/generativo/cli/generar_cli.py PROMPTS.jsonl SALIDA.jsonl --herramienta claude --modelo claude-opus-5-5
  python experiments/generativo/cli/generar_cli.py PROMPTS.jsonl SALIDA.jsonl --herramienta kimi --modelo kimi-code/k3.1-pro
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from decimal import Decimal
from pathlib import Path

# Tarifas de SALIDA en USD por millón de tokens (fuentes en experiments/generativo/cli/tarifas_cli.json)
TARIFAS = json.loads((Path(__file__).with_name("tarifas_cli.json")).read_text(encoding="utf-8"))
_LOCK = threading.Lock()


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def version(cmd: str) -> str:
    try:
        return subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=60).stdout.strip().splitlines()[0]
    except Exception as e:  # noqa: BLE001
        return f"desconocida ({type(e).__name__})"


def entorno_claude() -> dict:
    """Entorno de la CLI como en una terminal del usuario: sin las variables de una sesión anfitriona de Claude
    (CLAUDE_CODE_SIMPLE, ANTHROPIC_BASE_URL…), con la carpeta de configuración donde inició sesión (MINI_CLAUDE_CONFIG_DIR)."""
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k.startswith("ANTHROPIC"))}
    if os.environ.get("MINI_CLAUDE_CONFIG_DIR"):
        env["CLAUDE_CONFIG_DIR"] = os.environ["MINI_CLAUDE_CONFIG_DIR"]
    return env


def llamar_claude(system: str, user: str, modelo: str, esfuerzo: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="mini_cli_") as cwd:
        cmd = [shutil.which("claude") or "claude", "-p", "--safe-mode", "--model", modelo, "--effort", esfuerzo,
               "--system-prompt", system, "--tools", "", "--output-format", "json", "--no-session-persistence"]
        t0 = time.time()
        r = subprocess.run(cmd, input=user, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd,
                           env=entorno_claude())
        lat = time.time() - t0
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return {"error": f"salida no JSON (código {r.returncode}): {(r.stderr or r.stdout)[:300]}", "latencia_s": lat}
    if d.get("is_error"):
        return {"error": str(d.get("result"))[:300], "latencia_s": lat}
    u = d.get("usage") or {}
    modelos = list((d.get("modelUsage") or {}).keys())
    return {"texto": d.get("result") or "", "salida": u.get("output_tokens"),
            "razonamiento": (u.get("output_tokens_details") or {}).get("thinking_tokens"),
            "entrada": u.get("input_tokens"), "entrada_cache": (u.get("cache_read_input_tokens") or 0)
            + (u.get("cache_creation_input_tokens") or 0), "modelo_informado": ",".join(modelos) or modelo,
            "latencia_s": lat, "turnos": d.get("num_turns")}


def _uso_kimi(session_id: str) -> dict:
    base = Path.home() / ".kimi-code" / "sessions"
    archivos = glob.glob(str(base / "*" / session_id / "agents" / "main" / "wire.jsonl"))
    salida = entrada = n = 0
    modelo = None
    for a in archivos:
        for linea in Path(a).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(linea)
            except ValueError:
                continue
            # el mismo uso se repite en context.append_loop_event y agent.message.appended: solo cuenta usage.record
            u = o.get("usage") if o.get("type") == "usage.record" else None
            if isinstance(u, dict) and "output" in u:
                salida += int(u.get("output") or 0)
                entrada += int(u.get("inputOther") or 0) + int(u.get("inputCacheRead") or 0)
                n += 1
            for m in _buscar(o, "model"):
                if isinstance(m, str) and "/" in m:
                    modelo = m
    return {"salida": salida if n else None, "entrada": entrada if n else None, "respuestas_modelo": n,
            "modelo_informado": modelo}


def _buscar(o, clave):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == clave:
                yield v
            yield from _buscar(v, clave)
    elif isinstance(o, list):
        for v in o:
            yield from _buscar(v, clave)


def llamar_kimi(system: str, user: str, modelo: str, esfuerzo: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="mini_cli_") as cwd:
        agente = Path(cwd) / "agente.md"
        cuerpo = system.replace("${", "$​{")  # el cuerpo del agente es plantilla: no se interpretan variables
        agente.write_text("---\nname: generador-mini\ndescription: Generador sin herramientas del arnés V2\n"
                          "tools: []\n---\n\n" + cuerpo + "\n", encoding="utf-8")
        env = {**os.environ, "KIMI_MODEL_THINKING_EFFORT": esfuerzo}
        cmd = [shutil.which("kimi") or "kimi", "-p", user, "-m", modelo, "--agent-file", str(agente),
               "--output-format", "stream-json"]
        t0 = time.time()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd, env=env)
        lat = time.time() - t0
    textos, sesion = [], None
    for linea in r.stdout.splitlines():
        try:
            o = json.loads(linea)
        except ValueError:
            continue
        if o.get("role") == "assistant" and isinstance(o.get("content"), str):
            textos.append(o["content"])
        if o.get("type") == "session.resume_hint":
            sesion = o.get("session_id")
    if r.returncode != 0 or not sesion:
        return {"error": f"kimi código {r.returncode}: {(r.stderr or '')[:300]}", "latencia_s": lat}
    uso = _uso_kimi(sesion)
    return {"texto": "\n".join(textos), "salida": uso["salida"], "razonamiento": None, "entrada": uso["entrada"],
            "entrada_cache": None, "modelo_informado": uso["modelo_informado"] or modelo, "latencia_s": lat,
            "turnos": uso["respuestas_modelo"], "sesion_kimi": sesion}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompts")
    ap.add_argument("salida")
    ap.add_argument("--herramienta", choices=["claude", "kimi"], required=True)
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--declarado", default=None,
                    help="nombre del modelo en celda_id/modelo_declarado (sin «/», que el importador usa como separador)")
    ap.add_argument("--esfuerzo", default="low")
    ap.add_argument("--paralelo", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--reintentos", type=int, default=2)
    a = ap.parse_args(argv)
    filas = [json.loads(x) for x in Path(a.prompts).read_text(encoding="utf-8").splitlines() if x.strip()]
    salida = Path(a.salida)
    hechas = set()
    if salida.exists():
        for x in salida.read_text(encoding="utf-8").splitlines():
            if x.strip():
                hechas.add(json.loads(x)["celda_id"])
    pendientes = [f for f in filas if f["celda_id"] not in hechas]
    precio = TARIFAS[a.modelo]
    ver = version(a.herramienta)
    llamar = llamar_claude if a.herramienta == "claude" else llamar_kimi
    print(f"{a.herramienta} {ver} | modelo {a.modelo} | esfuerzo {a.esfuerzo} | {len(pendientes)} de {len(filas)} pendientes",
          flush=True)

    def una(f):
        r = {}
        for intento in range(a.reintentos + 1):
            try:
                r = llamar(f["system"], f["user"], a.modelo, a.esfuerzo, a.timeout)
            except subprocess.TimeoutExpired:
                r = {"error": f"tiempo agotado ({a.timeout} s)"}
            if "error" not in r:
                break
            time.sleep(10 * (intento + 1))
        fila = {k: f[k] for k in ("celda_id", "dominio", "condicion", "repeticion", "prompt_id") if k in f}
        if "error" in r:
            fila.update({"respuesta_bruta": None, "error": r["error"]})
        else:
            costo = (Decimal(r["salida"]) * Decimal(str(precio["salida"])) / Decimal(10**6)) if r.get("salida") is not None else None
            fila.update({"respuesta_bruta": r["texto"], "uso_cli": {k: r.get(k) for k in (
                "salida", "razonamiento", "entrada", "entrada_cache", "turnos", "sesion_kimi")},
                "costo_salida_usd": None if costo is None else str(costo.quantize(Decimal("0.0000001")))})
        fila.update({"modelo_declarado": a.declarado or a.modelo.replace("/", "-"), "parametros": {
            "herramienta": a.herramienta, "version_cli": ver, "modelo_solicitado": a.modelo,
            "modelo_informado": r.get("modelo_informado"), "esfuerzo": a.esfuerzo,
            "tarifa_salida_usd_millon": precio["salida"], "latencia_s": round(r.get("latencia_s") or 0, 2)},
            "fecha_utc": ahora()})
        return fila

    ok = err = 0
    with cf.ThreadPoolExecutor(max_workers=a.paralelo) as ex:
        for fila in ex.map(una, pendientes):
            if fila.get("respuesta_bruta") is None:
                err += 1
                print("ERROR", fila["celda_id"], fila.get("error"), flush=True)
                continue  # las fallidas no se escriben: se reintentan en la siguiente ejecución
            ok += 1
            with _LOCK, open(salida, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
            if ok % 10 == 0:
                print(f"  {ok} respuestas", flush=True)
    print(f"listo: {ok} respuestas nuevas, {err} con error", flush=True)
    return 0 if err == 0 else 3


if __name__ == "__main__":
    sys.exit(main())

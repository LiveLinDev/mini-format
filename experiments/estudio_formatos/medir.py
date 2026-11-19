"""Estudio de formatos con modelos reales: la misma aplicación de soporte con JSON y con .mini.

Usa la aplicación de ``examples/flujo-soporte`` sin cambios: los mismos 20 mensajes, la misma tarea y el mismo
contrato ``ticket``. Solo cambia el componente que lee la respuesta:

* ``json``: la instrucción de claves y tipos de la aplicación y el lector habitual (``json.loads``); si la respuesta
  no se puede leer o algún registro no cumple el contrato, se pide UNA vez la respuesta completa de nuevo.
* ``mini``: el prompt del contrato .mini y ``Workflow.process`` de mini-format, con los ajustes locales deterministas
  y UNA ronda de corrección selectiva (solo las líneas inválidas).

Cada llamada guarda la respuesta tal como llegó, los tokens que informa el proveedor (salida y, si los hay,
razonamiento), la latencia de reloj y el diagnóstico de validación. ``ver.py`` y ``cortes.py`` trabajan sobre
estas corridas grabadas sin llamar a ningún modelo.

Corredores (``proveedores.json``):

* ``cli-claude``: Claude Code (``claude -p``) con la cuenta del usuario, sin herramientas y con un prompt de sistema
  fijo. ``MINI_CLAUDE_CONFIG_DIR`` indica la carpeta de configuración donde se inició sesión.
* ``cli-kimi``: Kimi Code (``kimi -p``) con un agente sin herramientas; los tokens se leen del registro de la sesión.
* ``openai-compatible``: cualquier servidor Chat Completions (OpenAI, DeepSeek, Groq, Ollama, vLLM…); la URL y el
  modelo están en ``proveedores.json`` y la clave, si hace falta, en la variable de entorno que indica ``clave_env``.

Uso:
    python experiments/estudio_formatos/medir.py --repeticiones 3
    python experiments/estudio_formatos/medir.py --ids claude-haiku-5-5 --formatos mini --repeticiones 1
    python experiments/estudio_formatos/medir.py --proveedores mis_proveedores.json --salida mis_corridas

Es reanudable: una corrida que ya tiene ``evaluacion.json`` no se vuelve a pedir. Al final se reescribe
``<salida>/resultados.json`` con todas las corridas de la carpeta.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
APP = RAIZ / "examples" / "flujo-soporte"
if (RAIZ / "src").is_dir():
    sys.path.insert(0, str(RAIZ / "src"))

ESQUEMA = "mini-format/estudio-formatos/1"
REGISTROS = 20
SISTEMA = ("Eres el componente de extracción de una aplicación de soporte. Responde exactamente en el formato que pide "
           "el mensaje del usuario, sin texto adicional.")
CAMPOS = {"id": int, "titulo": str, "categoria": str, "prioridad": str}


def cargar_app():
    """El módulo ``run.py`` de la aplicación de soporte (TASK, JSON_FORMAT, chat, read_json_tickets)."""
    spec = importlib.util.spec_from_file_location("flujo_soporte_run", APP / "run.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ corredores
def entorno_claude() -> dict:
    env = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE") or k.startswith("ANTHROPIC"))}
    if os.environ.get("MINI_CLAUDE_CONFIG_DIR"):
        env["CLAUDE_CONFIG_DIR"] = os.environ["MINI_CLAUDE_CONFIG_DIR"]
    return env


def llamar_cli_claude(prov: dict, prompt: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="estudio_formatos_") as cwd:
        cmd = [shutil.which("claude") or "claude", "-p", "--safe-mode", "--model", prov["modelo"],
               "--effort", prov.get("esfuerzo", "low"), "--system-prompt", SISTEMA, "--tools", "",
               "--output-format", "json", "--no-session-persistence"]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                           cwd=cwd, env=entorno_claude())
        lat = time.perf_counter() - t0
    try:
        d = json.loads(r.stdout)
    except ValueError:
        return {"error": f"salida no JSON (código {r.returncode}): {(r.stderr or r.stdout)[:300]}", "latencia_s": lat}
    if d.get("is_error"):
        return {"error": str(d.get("result"))[:300], "latencia_s": lat}
    u = d.get("usage") or {}
    return {"texto": d.get("result") or "", "salida": u.get("output_tokens"),
            "razonamiento": (u.get("output_tokens_details") or {}).get("thinking_tokens"),
            "entrada": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
            + (u.get("cache_creation_input_tokens") or 0),
            "modelo_informado": ",".join((d.get("modelUsage") or {}).keys()) or prov["modelo"],
            "fin": d.get("stop_reason"), "latencia_s": lat}


def _buscar(o, clave):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == clave:
                yield v
            yield from _buscar(v, clave)
    elif isinstance(o, list):
        for v in o:
            yield from _buscar(v, clave)


def _uso_kimi(sesion: str) -> dict:
    salida = entrada = n = 0
    modelo = None
    for a in glob.glob(str(Path.home() / ".kimi-code" / "sessions" / "*" / sesion / "agents" / "main" / "wire.jsonl")):
        for linea in Path(a).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                o = json.loads(linea)
            except ValueError:
                continue
            u = o.get("usage") if o.get("type") == "usage.record" else None   # el uso se repite en otros eventos
            if isinstance(u, dict) and "output" in u:
                salida += int(u.get("output") or 0)
                entrada += int(u.get("inputOther") or 0) + int(u.get("inputCacheRead") or 0)
                n += 1
            for m in _buscar(o, "model"):
                if isinstance(m, str) and "/" in m:
                    modelo = m
    return {"salida": salida if n else None, "entrada": entrada if n else None, "modelo": modelo}


def llamar_cli_kimi(prov: dict, prompt: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="estudio_formatos_") as cwd:
        agente = Path(cwd) / "agente.md"
        agente.write_text("---\nname: extractor-soporte\ndescription: Componente de extracción sin herramientas\n"
                          "tools: []\n---\n\n" + SISTEMA + "\n", encoding="utf-8")
        env = {**os.environ, "KIMI_MODEL_THINKING_EFFORT": prov.get("esfuerzo", "low")}
        cmd = [shutil.which("kimi") or "kimi", "-p", prompt, "-m", prov["modelo"], "--agent-file", str(agente),
               "--output-format", "stream-json"]
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=timeout, cwd=cwd, env=env)
        lat = time.perf_counter() - t0
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
        return {"error": f"kimi código {r.returncode}: {(r.stderr or r.stdout or '')[-300:]}", "latencia_s": lat}
    uso = _uso_kimi(sesion)
    return {"texto": "\n".join(textos), "salida": uso["salida"], "razonamiento": None, "entrada": uso["entrada"],
            "modelo_informado": uso["modelo"] or prov["modelo"], "fin": None, "latencia_s": lat}


def llamar_openai_compatible(prov: dict, prompt: str, timeout: int) -> dict:
    app = cargar_app()
    clave = os.environ.get(prov["clave_env"]) if prov.get("clave_env") else None
    llamadas = []
    t0 = time.perf_counter()
    try:
        texto, fin = app.chat(prompt, url=prov["url"], model=prov["modelo"], key=clave, extra=prov.get("extra"),
                              calls=llamadas)
    except (ValueError, OSError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"[:300], "latencia_s": time.perf_counter() - t0}
    c = llamadas[-1] if llamadas else {}
    return {"texto": texto, "salida": c.get("output_tokens"), "razonamiento": None, "entrada": c.get("input_tokens"),
            "modelo_informado": c.get("model") or prov["modelo"], "fin": fin, "latencia_s": time.perf_counter() - t0}


CORREDORES = {"cli-claude": llamar_cli_claude, "cli-kimi": llamar_cli_kimi, "openai-compatible": llamar_openai_compatible}


# ------------------------------------------------------------------ evaluación
def validar_json(texto: str, app) -> dict:
    """Lector habitual de la aplicación y comprobación del contrato registro por registro."""
    try:
        datos = app.read_json_tickets(texto)
    except ValueError as exc:
        return {"leido": False, "validos": 0, "recibidos": 0, "error": f"{type(exc).__name__}: {exc}"[:300]}
    validos, problemas = 0, []
    for i, r in enumerate(datos[:REGISTROS], 1):
        ok = (isinstance(r, dict) and set(r) == set(CAMPOS)
              and all(isinstance(r[k], t) and not isinstance(r[k], bool) for k, t in CAMPOS.items())
              and r["titulo"].strip() != "")
        validos += ok
        if not ok:
            problemas.append(i)
    error = None
    if problemas:
        error = f"registros que no cumplen el contrato: {problemas}"
    elif len(datos) != REGISTROS:
        error = f"se esperaban {REGISTROS} registros y llegaron {len(datos)}"
    return {"leido": True, "validos": validos, "recibidos": len(datos), "error": error}


def validos_mini(texto: str, workflow) -> dict:
    """Registros válidos de una respuesta .mini tras los ajustes locales (sin llamar al modelo)."""
    rt = workflow.runtime
    local = rt.repair(texto, workflow.contract)
    diag = rt.diagnose(local["text"], workflow.contract)
    validos = len(diag.get("valid_lines") or [])   # una cabecera inválida deja valid_lines vacío
    return {"validos": min(validos, REGISTROS), "ajustes_locales": local["changes"],
            "errores": [{k: e.get(k) for k in ("code", "line", "message")} for e in (diag.get("errors") or [])][:20]}


def nueva_toolkit(carpeta: Path):
    from minifmt.domain import build_bundle
    from minifmt.workflow import Workflow
    muestra = json.loads((APP / "expected.json").read_text(encoding="utf-8"))
    build_bundle([muestra], "ticket", carpeta)
    return Workflow(carpeta)


def una_corrida(prov: dict, formato: str, rep: int, destino: Path, timeout: int) -> dict:
    from minifmt.workflow import WorkflowError
    app = cargar_app()
    mensajes = json.loads((APP / "messages.json").read_text(encoding="utf-8"))
    tarea = app.TASK + json.dumps(mensajes, ensure_ascii=False)
    llamar = CORREDORES[prov["corredor"]]
    llamadas: list = []
    destino.mkdir(parents=True, exist_ok=True)
    ext = "mini" if formato == "mini" else "json"

    def pedir(prompt: str, etapa: str) -> str:
        try:
            r = llamar(prov, prompt, timeout)
        except subprocess.TimeoutExpired:
            r = {"error": f"tiempo agotado ({timeout} s)", "latencia_s": float(timeout)}
        n = len(llamadas) + 1
        nombre = f"respuesta_{n}_correccion.txt" if (formato == "mini" and etapa == "correccion") else f"respuesta_{n}.{ext}"
        if "error" not in r:
            (destino / nombre).write_bytes(r["texto"].encode("utf-8"))
        llamadas.append({"n": n, "etapa": etapa, "archivo": None if "error" in r else nombre,
                         "error": r.get("error"), "tokens_salida": r.get("salida"),
                         "tokens_razonamiento": r.get("razonamiento"), "tokens_entrada": r.get("entrada"),
                         "latencia_s": round(r.get("latencia_s") or 0.0, 3), "fin": r.get("fin"),
                         "modelo_informado": r.get("modelo_informado"), "fecha_utc": ahora()})
        if "error" in r:
            raise RuntimeError(r["error"])
        return r["texto"]

    ev = {"esquema": ESQUEMA, "proveedor": prov["id"], "corredor": prov["corredor"], "modelo": prov["modelo"],
          "esfuerzo": prov.get("esfuerzo"), "formato": formato, "repeticion": rep, "solicitados": REGISTROS}
    try:
        if formato == "json":
            prompt = tarea + "\n\n" + app.JSON_FORMAT
            texto = pedir(prompt, "generacion")
            inicial = validar_json(texto, app)
            final = inicial
            if inicial["error"] or not inicial["leido"]:
                correccion = (prompt + "\n\nRespuesta anterior:\n" + texto + "\n\nCORRECCIÓN: la respuesta anterior no "
                              "se pudo usar (" + (inicial["error"] or "") + "). Devuelve de nuevo el arreglo JSON completo "
                              f"de {REGISTROS} objetos, sin texto adicional.")
                final = validar_json(pedir(correccion, "correccion"), app)
            ev.update(validos_inicial=inicial["validos"], validos_final=final["validos"],
                      diagnostico_inicial=inicial, diagnostico_final=final)
        else:
            with tempfile.TemporaryDirectory(prefix="estudio_formatos_kit_") as kit:
                wf = nueva_toolkit(Path(kit) / "toolkit")
                texto = pedir(wf.prompt(tarea, REGISTROS), "generacion")
                inicial = validos_mini(texto, wf)
                try:
                    datos = wf.process(texto, generate=lambda p: pedir(p, "correccion"), task=tarea,
                                       expected_records=REGISTROS, max_repairs=1)
                    final = {"validos": min(len(datos), REGISTROS), "ok": True}
                except WorkflowError as exc:
                    diag = exc.report.get("diagnostics") or {}
                    final = {"validos": min(len(diag.get("valid_lines") or []), REGISTROS), "ok": False,
                             "errores": [{k: e.get(k) for k in ("code", "line", "message")}
                                         for e in (diag.get("errors") or [])][:20]}
                ev.update(validos_inicial=inicial["validos"], validos_final=final["validos"],
                          diagnostico_inicial=inicial, diagnostico_final=final, resumen=wf.summary())
        ev["estado"] = "completa"
    except RuntimeError as exc:
        ev.update(estado="fallida", error=str(exc))
    ev["llamadas"] = llamadas
    ev["fecha_utc"] = ahora()
    (destino / "evaluacion.json").write_bytes((json.dumps(ev, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return ev


def reunir(salida: Path) -> list:
    corridas = []
    for p in sorted(salida.glob("*/*/*/evaluacion.json")):
        ev = json.loads(p.read_text(encoding="utf-8"))
        ev["carpeta"] = p.parent.relative_to(salida).as_posix()
        corridas.append(ev)
    doc = {"esquema": ESQUEMA, "aplicacion": "examples/flujo-soporte (20 mensajes, contrato ticket)",
           "generado_utc": ahora(), "corridas": corridas}
    (salida / "resultados.json").write_bytes((json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return corridas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--proveedores", default=str(AQUI / "proveedores.json"))
    ap.add_argument("--ids", nargs="*", help="solo estos proveedores (por defecto, los activos)")
    ap.add_argument("--formatos", nargs="*", default=["json", "mini"], choices=["json", "mini"])
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--salida", default=str(AQUI / "corridas"))
    ap.add_argument("--paralelo", type=int, default=2)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--reunir", action="store_true", help="solo reescribe resultados.json con lo que hay en --salida")
    a = ap.parse_args(argv)
    salida = Path(a.salida)
    if a.reunir:
        print(f"{len(reunir(salida))} corridas en {salida / 'resultados.json'}")
        return 0
    provs = json.loads(Path(a.proveedores).read_text(encoding="utf-8"))["proveedores"]
    provs = [p for p in provs if (p["id"] in a.ids if a.ids else p.get("activo", True))]
    tareas = [(p, f, r) for p in provs for f in a.formatos for r in range(1, a.repeticiones + 1)
              if not (salida / p["id"] / f / str(r) / "evaluacion.json").exists()]
    print(f"{len(tareas)} corridas pendientes", flush=True)

    def correr(t):
        p, f, r = t
        ev = una_corrida(p, f, r, salida / p["id"] / f / str(r), a.timeout)
        print(f"{p['id']} {f} {r}: {ev['estado']} · válidos {ev.get('validos_inicial')} → {ev.get('validos_final')}"
              + (f" · {ev['error']}" if ev.get("error") else ""), flush=True)
        if ev["estado"] == "fallida":   # una corrida fallida no deja evaluacion.json: se reintenta en otra ejecución
            (salida / p["id"] / f / str(r) / "evaluacion.json").replace(
                salida / p["id"] / f / str(r) / f"fallida_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
        return ev

    with cf.ThreadPoolExecutor(max_workers=max(1, a.paralelo)) as ex:
        list(ex.map(correr, tareas))
    print(f"{len(reunir(salida))} corridas en {salida / 'resultados.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

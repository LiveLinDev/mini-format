"""Ejecuta los comandos reales de mini-format sobre los datos de la demo y guarda su salida en terminal.json.

La página /demo/ muestra esas salidas en su panel de terminal: no se escriben a mano. Se ejecuta la CLI del
repositorio (src/) en una carpeta temporal, con las respuestas grabadas de examples/mesa-de-ayuda, en español y en inglés.
Uso: python examples/demo/generar_terminal.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
MESA = RAIZ / "examples" / "mesa-de-ayuda"
VERSION = re.search(r'^version = "([^"]+)"', (RAIZ / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
ENTORNO = dict(os.environ, PYTHONPATH=str(RAIZ / "src"), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", NO_COLOR="1")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
ESCENARIOS = ("ok", "error", "cortada")

sys.path.insert(0, str(RAIZ / "src"))
from minifmt import Contract, parse  # noqa: E402


def correr(carpeta, args, entrada=None):
    """Ejecuta `mini ...` o `python ...` y devuelve la salida combinada, sin colores."""
    if args[0] == "mini":
        cmd = [sys.executable, "-m", "minifmt"] + args[1:]
    else:
        cmd = [sys.executable] + args[1:]
    r = subprocess.run(cmd, cwd=carpeta, env=ENTORNO, input=entrada, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    return ANSI.sub("", r.stdout or "").replace("\r", "").rstrip("\n")


def recortar(texto, lineas):
    """lineas: cuántas líneas iniciales se muestran, o (iniciales, finales) para conservar también el cierre."""
    cabeza, cola = lineas if isinstance(lineas, tuple) else (lineas, 0)
    partes = texto.split("\n")
    if len(partes) <= cabeza + cola:
        return texto
    return "\n".join(partes[:cabeza] + ["…"] + (partes[-cola:] if cola else []))


def paso(carpeta, comandos):
    """comandos: lista de (texto mostrado, argumentos reales, recorte de líneas o None, comentario)."""
    out = []
    for mostrado, args, lineas, comentario in comandos:
        salida = correr(carpeta, args)
        out.append({"cmd": mostrado, "out": recortar(salida, lineas) if lineas else salida, "nota": comentario})
    return out


def setup_transcripcion(carpeta, lang):
    """mini setup con las respuestas de la demo; como la entrada no se ve en un pipe, se intercala tras cada pregunta."""
    respuestas = [lang, "4", "tk", ".mini", "1"]
    salida = correr(carpeta, ["mini", "setup"], entrada="\n".join(respuestas) + "\n")
    partes = salida.split("›")
    texto = partes[0]
    for i, resto in enumerate(partes[1:]):
        r = respuestas[i] if i < len(respuestas) else ""
        resto = resto[1:] if resto.startswith(" ") else resto
        texto += "› " + r + ("" if resto.startswith("\n") else "\n") + resto
    return re.sub(r"\n{3,}", "\n\n", texto).strip("\n")


def generar(tmp, lang):
    t = (lambda es, en: es) if lang == "es" else (lambda es, en: en)
    rep = ["python", str(AQUI / "reparar.py")]
    sufijo = "" if lang == "es" else " --lang en"
    extra = [] if lang == "es" else ["--lang", "en"]
    datos = {"comunes": {}, "escenarios": {}}
    datos["comunes"]["instalar"] = [
        {"cmd": f"python -m pip install mini_format-{VERSION}-py3-none-any.whl",
         "out": f"Processing ./mini_format-{VERSION}-py3-none-any.whl\nInstalling collected packages: mini-format\nSuccessfully installed mini-format-{VERSION}",
         "nota": t("instalación del paquete publicado en mini-format.pmoluna.com", "install the package published at mini-format.pmoluna.com")},
    ] + paso(tmp, [("mini --help", ["mini", "--help"], 6, t("la herramienta queda disponible como «mini»", "the tool is now available as «mini»"))])
    datos["comunes"]["contrato"] = paso(tmp, [
        ("mini from-schema ticket.schema.json -p tk --out tk.contract.json", ["mini", "from-schema", "ticket.schema.json", "-p", "tk", "--out", "tk.contract.json"], None,
         t("el contrato se genera desde el esquema JSON que la aplicación ya tenía", "the contract is generated from the JSON Schema the application already had")),
        (f"mini prompt --contract tk.contract.json --lang {lang}", ["mini", "prompt", "--contract", "tk.contract.json", "--lang", lang], 12,
         t("la instrucción para la IA se escribe desde el contrato", "the instruction for the AI is written from the contract")),
    ])
    carpeta_setup = tmp / ("setup-" + lang)
    carpeta_setup.mkdir()
    datos["comunes"]["setup"] = [{"cmd": "mini setup", "out": setup_transcripcion(carpeta_setup, lang),
                                  "nota": t("asistente guiado: crea el contrato, la instrucción y el kit de integración en .mini/",
                                            "guided assistant: creates the contract, the instruction and the integration kit in .mini/")},
                                 {"cmd": "python .mini/workflow.py .mini/example.mini",
                                  "out": correr(carpeta_setup, ["python", ".mini/workflow.py", ".mini/example.mini"]),
                                  "nota": t("el kit valida el ejemplo del asistente, repara si hace falta y entrega JSON",
                                            "the kit validates the assistant's example, repairs if needed and hands over JSON")}]
    lineas_ok = {l.split("|")[0]: l for l in (MESA / "grabaciones" / "mini" / "ok.mini").read_text(encoding="utf-8").strip().split("\n")[1:]}
    contrato = Contract.from_dict(json.loads((tmp / "tk.contract.json").read_text(encoding="utf-8")))
    for esc in ESCENARIOS:
        shutil.copy(MESA / "grabaciones" / "mini" / f"{esc}.mini", tmp / "respuesta.mini")
        shutil.copy(MESA / "grabaciones" / "json" / f"{esc}.json", tmp / "respuesta.json")
        e = {}
        e["respuesta"] = paso(tmp, [
            ("mini tokens respuesta.mini", ["mini", "tokens", "respuesta.mini"], None, t("tamaño de la respuesta en .mini", "size of the .mini answer")),
            ("mini tokens respuesta.json", ["mini", "tokens", "respuesta.json"], None, t("tamaño de la misma respuesta pedida en JSON", "size of the same answer requested in JSON")),
        ])
        e["validar"] = paso(tmp, [
            ("mini validate respuesta.mini --contract tk.contract.json", ["mini", "validate", "respuesta.mini", "--contract", "tk.contract.json"], None,
             t("cada línea se revisa contra el contrato", "every line is checked against the contract")),
            ("python reparar.py respuesta.mini --contract tk.contract.json" + sufijo,
             rep + ["respuesta.mini", "--contract", "tk.contract.json", "--esperados", "10"] + extra, None,
             t("qué hay que volver a pedir", "what has to be requested again")),
        ])
        original = (tmp / "respuesta.mini").read_text(encoding="utf-8").strip().split("\n")
        presentes = [l.split("|")[0] for l in original[1:]]
        validos = {r["id"] for r in parse("\n".join(original), contrato, strict=False).records}
        pedidas = [lineas_ok[i] for i in presentes if i not in validos and i in lineas_ok] + [lineas_ok[i] for i in lineas_ok if i not in presentes]
        final = "respuesta.mini"
        if pedidas:
            (tmp / "correccion.mini").write_text("tk|n=" + str(len(pedidas)) + "\n" + "\n".join(pedidas) + "\n", encoding="utf-8")
            e["reparar"] = paso(tmp, [
                ("python reparar.py respuesta.mini --contract tk.contract.json --correccion correccion.mini --out reparada.mini" + sufijo,
                 rep + ["respuesta.mini", "--contract", "tk.contract.json", "--esperados", "10", "--correccion", "correccion.mini", "--out", "reparada.mini"] + extra, None,
                 t("correccion.mini es lo que respondió la IA al pedido de reparación", "correccion.mini is what the AI answered to the repair request")),
                ("mini validate reparada.mini --contract tk.contract.json", ["mini", "validate", "reparada.mini", "--contract", "tk.contract.json"], None,
                 t("se vuelve a comprobar el documento completo", "the whole document is checked again")),
            ])
            e["parcial"] = paso(tmp, [
                ("mini to-json respuesta.mini --contract tk.contract.json --lenient", ["mini", "to-json", "respuesta.mini", "--contract", "tk.contract.json", "--lenient"], (14, 4),
                 t("sin reparar: se entregan solo los registros válidos", "without repair: only the valid records are delivered")),
            ])
            final = "reparada.mini"
        e["resultado"] = paso(tmp, [
            (f"mini to-json {final} --contract tk.contract.json", ["mini", "to-json", final, "--contract", "tk.contract.json"], 16,
             t("la aplicación recibe JSON (con --out tickets.json se guarda en un archivo)", "the application receives JSON (--out tickets.json saves it to a file)")),
            (f"mini --forks familias bench {final} -p tk", ["mini", "--forks", "familias", "bench", final, "-p", "tk"], None,
             t("el mismo contenido medido en otros formatos", "the same content measured in other formats")),
        ])
        datos["escenarios"][esc] = e
    return datos


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mini-demo-"))
    try:
        shutil.copy(MESA / "ticket.schema.json", tmp / "ticket.schema.json")
        correr(tmp, ["mini", "from-schema", "ticket.schema.json", "-p", "tk", "--out", "tk.contract.json"])
        (tmp / "familias" / "tk").mkdir(parents=True)
        shutil.copy(tmp / "tk.contract.json", tmp / "familias" / "tk" / "contract.json")
        datos = {"version": VERSION, "contratoArchivo": (tmp / "tk.contract.json").read_text(encoding="utf-8"),
                 "es": generar(tmp, "es"), "en": generar(tmp, "en")}
        (AQUI / "terminal.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("escrito examples/demo/terminal.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

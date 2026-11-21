"""Recuperación ante respuestas cortadas: la misma respuesta real cortada en 20 puntos, en .mini y en JSON.

    python experiments/estudio_formatos/cortes.py corridas/claude-opus-5-5/mini/1/respuesta_1.mini \
        corridas/claude-opus-5-5/json/1/respuesta_1.json
    python experiments/estudio_formatos/cortes.py --todas corridas

Cada respuesta se corta en 20 posiciones repartidas por igual dentro del texto (sin incluir el final). En cada corte:

* registros completos: los registros cuyo texto entero queda antes del corte;
* recuperados (.mini): lo que entrega el lector de mini-format con la señal de corte del proveedor
  (``finish_reason == "length"``): conserva las líneas completas y descarta la última, que puede estar cortada;
* recuperados (JSON): lo que entrega ``json.loads`` (lector estricto), que no admite un documento incompleto.

Un registro recuperado solo cuenta si es idéntico al de la respuesta completa. No llama a ningún modelo.

Con ``--todas`` se mide una pareja por modelo y repetición (las 9 del estudio). La respuesta que se corta es la que la
aplicación aceptó en esa corrida:

* si la corrida no necesitó corrección, la primera respuesta (tras los ajustes locales deterministas);
* si la necesitó, la primera respuesta con las correcciones grabadas aplicadas por ``Workflow.process``, exactamente
  como en el estudio: las respuestas de corrección se leen de la carpeta de la corrida, no se pide nada al modelo.
  En JSON, la última respuesta de la corrida.

El informe declara la referencia de cada pareja y el denominador: parejas procesadas de las parejas encontradas,
cortes por formato y registros completos. Una pareja que no se pueda procesar aparece con su motivo; nunca se
descarta en silencio.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
APP = RAIZ / "examples" / "flujo-soporte"
if (RAIZ / "src").is_dir():
    sys.path.insert(0, str(RAIZ / "src"))
PUNTOS = 20
REGISTROS = 20


def posiciones(longitud: int, puntos: int = PUNTOS) -> list:
    return [longitud * i // (puntos + 1) for i in range(1, puntos + 1)]


class LectorMini:
    """Contrato ``ticket`` de la aplicación de soporte y lector con señal de corte."""

    def __init__(self):
        from minifmt.domain import build_bundle
        from minifmt.workflow import Workflow
        self._tmp = tempfile.TemporaryDirectory(prefix="cortes_")
        muestra = json.loads((APP / "expected.json").read_text(encoding="utf-8"))
        build_bundle([muestra], "ticket", Path(self._tmp.name) / "kit")
        self.wf = Workflow(Path(self._tmp.name) / "kit")

    def completo(self, texto: str) -> list:
        """Registros de la respuesta completa (tras los ajustes locales)."""
        rt = self.wf.runtime
        limpio = rt.repair(texto, self.wf.contract)["text"]
        return rt.decode(limpio, self.wf.contract)

    def recuperar(self, prefijo: str) -> list:
        rt = self.wf.runtime
        limpio = rt.repair(prefijo, self.wf.contract)["text"]
        corte = self.wf._cut(limpio, True, prefijo.rstrip(" \t").endswith("\n"))
        if corte is None:
            try:
                return rt.decode(limpio, self.wf.contract)
            except (ValueError, TypeError):
                return []
        try:
            return rt.decode(corte[0], self.wf.contract)
        except (ValueError, TypeError):
            return []

    def aplicar_correcciones(self, texto: str, correcciones: list) -> str:
        """Documento .mini que aceptó la aplicación: ``Workflow.process`` con las correcciones grabadas.

        Reproduce la corrida sin llamar al modelo: cada vez que el flujo pide una corrección, recibe la siguiente
        respuesta grabada. Si el flujo pide más correcciones de las que hay, la pareja no se puede procesar."""
        pendientes = iter(correcciones)

        def grabada(_prompt):
            try:
                return next(pendientes)
            except StopIteration:
                raise ValueError("la corrida no tiene más correcciones grabadas") from None

        self.wf.process(texto, generate=grabada, task="", expected_records=REGISTROS, max_repairs=len(correcciones))
        return self.wf.last_run["mini"]

    @staticmethod
    def fines(texto: str) -> list:
        """Posición final de cada línea de registro (sin el salto de línea)."""
        fines, pos = [], 0
        for i, linea in enumerate(texto.split("\n")):
            pos += len(linea)
            if i > 0 and linea.strip() and not linea.startswith("```"):
                fines.append(pos)
            pos += 1
        return fines


def fines_json(texto: str) -> list:
    """Posición final de cada objeto del arreglo JSON principal."""
    dec = json.JSONDecoder()
    i = texto.index("[") + 1
    fines = []
    while True:
        while i < len(texto) and texto[i] in " \t\r\n,":
            i += 1
        if i >= len(texto) or texto[i] == "]":
            return fines
        _, i = dec.raw_decode(texto, i)
        fines.append(i)


def leer_json_estricto(texto: str) -> list:
    try:
        datos = json.loads(texto)
    except ValueError:
        return []
    return datos if isinstance(datos, list) else []


def medir_par(texto_mini: str, texto_json: str, lector: LectorMini = None, puntos: int = PUNTOS) -> dict:
    lector = lector or LectorMini()
    texto_mini = texto_mini.replace("\r\n", "\n")
    orig_mini = lector.completo(texto_mini)
    fin_mini = lector.fines(texto_mini)[:len(orig_mini)]
    orig_json = json.loads(texto_json)
    fin_json = fines_json(texto_json)
    out = {}
    for fmt, texto, orig, fines, leer in (("mini", texto_mini, orig_mini, fin_mini, lector.recuperar),
                                          ("json", texto_json, orig_json, fin_json, leer_json_estricto)):
        completos = recuperados = 0
        for p in posiciones(len(texto), puntos):
            k = sum(1 for f in fines if f <= p)
            datos = leer(texto[:p])
            completos += k
            recuperados += sum(1 for a, b in zip(datos, orig) if a == b)
        out[fmt] = {"cortes": puntos, "registros_completos": completos, "recuperados": recuperados,
                    "recuperacion_pct": 100 * recuperados / completos if completos else None}
    return out


def _respuestas(carpeta: Path, etapa: str) -> list:
    """Archivos de respuesta de una corrida en el orden de sus llamadas (según evaluacion.json)."""
    ev = json.loads((carpeta / "evaluacion.json").read_text(encoding="utf-8"))
    return [carpeta / l["archivo"] for l in ev["llamadas"] if l["etapa"] == etapa and l.get("archivo")]


def referencia_mini(carpeta: Path, lector: LectorMini) -> tuple:
    """(texto que se corta, descripción de la referencia) de la corrida .mini de ``carpeta``."""
    primera = (carpeta / "respuesta_1.mini").read_text(encoding="utf-8").replace("\r\n", "\n")
    correcciones = _respuestas(carpeta, "correccion")
    if not correcciones:
        return primera, "primera respuesta"
    texto = lector.aplicar_correcciones(primera, [p.read_text(encoding="utf-8") for p in correcciones])
    return texto, "primera respuesta con la corrección grabada (" + ", ".join(p.name for p in correcciones) + ")"


def referencia_json(carpeta: Path) -> tuple:
    respuestas = _respuestas(carpeta, "generacion") + _respuestas(carpeta, "correccion")
    ultima = respuestas[-1] if respuestas else carpeta / "respuesta_1.json"
    descripcion = "primera respuesta" if ultima.name == "respuesta_1.json" else f"respuesta corregida ({ultima.name})"
    return ultima.read_text(encoding="utf-8"), descripcion


def pares(carpeta: Path):
    """(proveedor, repetición, carpeta .mini, carpeta JSON) de cada modelo y repetición con ambos formatos."""
    for m in sorted(Path(carpeta).glob("*/mini/*/evaluacion.json")):
        j = m.parents[2] / "json" / m.parent.name
        if (j / "evaluacion.json").is_file():
            yield m.parents[2].name, m.parent.name, m.parent, j


def medir_todas(carpeta: Path, lector: LectorMini, puntos: int = PUNTOS) -> dict:
    filas, total = [], {"mini": [0, 0], "json": [0, 0]}
    for prov, rep, cm, cj in pares(Path(carpeta)):
        fila = {"proveedor": prov, "repeticion": rep}
        try:
            texto_mini, ref_mini = referencia_mini(cm, lector)
            texto_json, ref_json = referencia_json(cj)
            fila.update({"referencia": {"mini": ref_mini, "json": ref_json},
                         **medir_par(texto_mini, texto_json, lector, puntos), "estado": "procesada"})
            for f in ("mini", "json"):
                total[f][0] += fila[f]["registros_completos"]
                total[f][1] += fila[f]["recuperados"]
        except (ValueError, TypeError, KeyError, OSError) as exc:
            fila.update({"estado": "no procesada", "motivo": f"{type(exc).__name__}: {exc}"[:200]})
        filas.append(fila)
    procesadas = sum(1 for f in filas if f["estado"] == "procesada")
    return {"parejas": len(filas), "procesadas": procesadas, "no_procesadas": len(filas) - procesadas,
            "cortes_por_formato": procesadas * puntos, "detalle": filas,
            "total": {f: {"registros_completos": c, "recuperados": rec,
                          "recuperacion_pct": 100 * rec / c if c else None} for f, (c, rec) in total.items()}}


def _linea_total(res: dict) -> list:
    out = []
    for f, nombre in (("mini", ".mini (lector con señal de corte)"), ("json", "JSON (json.loads)")):
        r = res[f]
        pct = "—" if r["recuperacion_pct"] is None else f"{r['recuperacion_pct']:.1f} %"
        out.append(f"{nombre}: {r['recuperados']} de {r['registros_completos']} registros completos recuperados ({pct})")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mini", nargs="?")
    ap.add_argument("json", nargs="?")
    ap.add_argument("--todas", metavar="CARPETA", help="una pareja por modelo y repetición de la carpeta de corridas")
    ap.add_argument("--puntos", type=int, default=PUNTOS)
    ap.add_argument("--json-salida", action="store_true", help="salida en JSON")
    a = ap.parse_args(argv)
    lector = LectorMini()
    if a.todas:
        res = medir_todas(Path(a.todas), lector, a.puntos)
    elif a.mini and a.json:
        res = medir_par(Path(a.mini).read_text(encoding="utf-8"), Path(a.json).read_text(encoding="utf-8"), lector, a.puntos)
    else:
        ap.error("indique una respuesta .mini y su par JSON, o --todas CARPETA")
    if a.json_salida:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not a.todas:
        print("\n".join(_linea_total(res)))
        return 0
    for f in res["detalle"]:
        if f["estado"] != "procesada":
            print(f"{f['proveedor']} {f['repeticion']}: NO PROCESADA ({f['motivo']})")
            continue
        nota = "" if f["referencia"]["mini"] == "primera respuesta" else f" · .mini: {f['referencia']['mini']}"
        print(f"{f['proveedor']} {f['repeticion']}: .mini {f['mini']['recuperados']}/{f['mini']['registros_completos']}"
              f" · JSON {f['json']['recuperados']}/{f['json']['registros_completos']}{nota}")
    print(f"Parejas procesadas: {res['procesadas']} de {res['parejas']} · {res['cortes_por_formato']} cortes por formato"
          + (f" · {res['no_procesadas']} no procesada(s), excluidas del total" if res["no_procesadas"] else ""))
    print("\n".join(_linea_total(res["total"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

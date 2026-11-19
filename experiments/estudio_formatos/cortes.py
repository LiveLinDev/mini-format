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


def pares(carpeta: Path):
    """(proveedor, repetición, ruta .mini, ruta .json) de las primeras respuestas grabadas."""
    for m in sorted(Path(carpeta).glob("*/mini/*/respuesta_1.mini")):
        j = m.parents[2] / "json" / m.parent.name / "respuesta_1.json"
        if j.is_file():
            yield m.parents[2].name, m.parent.name, m, j


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mini", nargs="?")
    ap.add_argument("json", nargs="?")
    ap.add_argument("--todas", metavar="CARPETA", help="todas las parejas de primeras respuestas de la carpeta de corridas")
    ap.add_argument("--puntos", type=int, default=PUNTOS)
    ap.add_argument("--json-salida", action="store_true", help="salida en JSON")
    a = ap.parse_args(argv)
    lector = LectorMini()
    if a.todas:
        filas, total = [], {"mini": [0, 0], "json": [0, 0]}
        for prov, rep, m, j in pares(Path(a.todas)):
            try:
                r = medir_par(m.read_text(encoding="utf-8"), j.read_text(encoding="utf-8"), lector, a.puntos)
            except (ValueError, TypeError) as exc:   # una respuesta que no se puede leer completa no tiene referencia
                filas.append({"proveedor": prov, "repeticion": rep, "omitida": f"{type(exc).__name__}: {exc}"[:120]})
                continue
            filas.append({"proveedor": prov, "repeticion": rep, **r})
            for f in ("mini", "json"):
                total[f][0] += r[f]["registros_completos"]
                total[f][1] += r[f]["recuperados"]
        res = {"pares": filas, "total": {f: {"registros_completos": c, "recuperados": rec,
                                             "recuperacion_pct": 100 * rec / c if c else None}
                                         for f, (c, rec) in total.items()}}
    elif a.mini and a.json:
        res = medir_par(Path(a.mini).read_text(encoding="utf-8"), Path(a.json).read_text(encoding="utf-8"), lector, a.puntos)
    else:
        ap.error("indique una respuesta .mini y su par JSON, o --todas CARPETA")
    if a.json_salida:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if a.todas:
        for f in res["pares"]:
            if "omitida" in f:
                print(f"{f['proveedor']} {f['repeticion']}: omitida ({f['omitida']})")
            else:
                print(f"{f['proveedor']} {f['repeticion']}: .mini {f['mini']['recuperados']}/{f['mini']['registros_completos']}"
                      f" · JSON {f['json']['recuperados']}/{f['json']['registros_completos']}")
        res = res["total"]
    for f, nombre in (("mini", ".mini (lector con señal de corte)"), ("json", "JSON (json.loads)")):
        r = res[f]
        pct = "—" if r["recuperacion_pct"] is None else f"{r['recuperacion_pct']:.1f} %"
        print(f"{nombre}: {r['recuperados']} de {r['registros_completos']} registros completos recuperados ({pct})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

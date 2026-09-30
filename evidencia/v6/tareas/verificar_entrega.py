"""Verificador OBJETIVO de las entregas de V6b (solo observador; no se entrega al participante).

    python evidencia/v6/tareas/verificar_entrega.py T1A entrega/      # T1A, T1B, T2, T3 o T4
    (con PYTHONPATH=src para importar minifmt)

Lee los archivos que cada tarea pide entregar, los compara con ``observador/*.referencia.json`` y
devuelve un informe JSON con un criterio por línea. Código de salida: 0 = cumple todos los
criterios, 1 = no cumple, 2 = uso incorrecto o entrega ausente.

Este verificador decide si la tarea está lograda; el tiempo lo mide el cronómetro de la herramienta
(``evidencia/v6/herramienta/sesion.html``). Un participante que agota el tope sin pasar este
verificador no ha tenido éxito aunque "casi" lo logre.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import Contract, canonical_equal, parse  # noqa: E402
from minifmt.errors import MiniError, MiniValidationError  # noqa: E402

TAREAS = ("T1A", "T1B", "T2", "T3", "T4")
ARCHIVOS = {
    "T1A": ["salida_T1.json"], "T1B": ["salida_T1.json"],
    "T2": ["T2_diagnostico.json", "T2_corregido.mini"],
    "T3": ["T3_recuperado.json"], "T4": ["contrato_cambios.json"],
}


def _ref(nombre: str) -> Dict[str, Any]:
    return json.loads((AQUI / "observador" / nombre).read_text(encoding="utf-8"))


def _contrato(ruta: str) -> Contract:
    return Contract.load(AQUI / "participante" / ruta)


def _errores(texto: str, contrato: Contract) -> Tuple[List[Dict[str, Any]], List[Tuple[str, int]]]:
    """(registros, [(código, línea)]) con el analizador tolerante; nunca lanza."""
    try:
        doc = parse(texto, contrato, strict=False)
        return list(doc.records), [(e.code, e.line) for e in doc.errors]
    except MiniValidationError as e:
        return [], [(x.code, x.line) for x in e.errors]
    except MiniError as e:
        return [], [(e.code, e.line)]


def _c(id_: str, cumple: bool, detalle: str) -> Dict[str, Any]:
    return {"id": id_, "cumple": bool(cumple), "detalle": detalle}


def _lee_json(ruta: Path) -> Tuple[Optional[Any], Optional[str]]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8-sig")), None
    except (OSError, ValueError) as e:
        return None, f"no se pudo leer {ruta.name}: {e}"


def _es_entero(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _t1(tarea: str, d: Path) -> List[Dict[str, Any]]:
    ref = _ref(f"{tarea}.referencia.json")
    obj, err = _lee_json(d / "salida_T1.json")
    if err:
        return [_c("entrega", False, err)]
    forma = (isinstance(obj, dict) and isinstance(obj.get("validos"), list) and isinstance(obj.get("rechazados"), list)
             and all(isinstance(r, dict) and _es_entero(r.get("posicion")) for r in obj["rechazados"]))
    crit = [_c("forma", forma, "objeto con 'validos' (lista) y 'rechazados' (lista de {posicion:int, motivo})")]
    if not forma:
        return crit
    crit.append(_c("validos_identicos", canonical_equal(obj["validos"], ref["validos"]),
                   f"esperados {len(ref['validos'])} registros válidos, en orden y sin cambiar valores; "
                   f"entregados {len(obj['validos'])}"))
    pos = [r["posicion"] for r in obj["rechazados"]]
    crit.append(_c("rechazados_correctos", sorted(pos) == sorted(ref["rechazados_posiciones"]) and len(set(pos)) == len(pos),
                   f"posiciones esperadas {ref['rechazados_posiciones']}; entregadas {pos}"))
    return crit


def _t2(d: Path) -> List[Dict[str, Any]]:
    ref = _ref("T2.referencia.json")
    contrato = _contrato("T2/contrato_tk.json")
    original = (AQUI / "participante" / "T2" / "respuesta.mini").read_text(encoding="utf-8")
    diag, err = _lee_json(d / "T2_diagnostico.json")
    crit: List[Dict[str, Any]] = []
    if err:
        crit.append(_c("diagnostico", False, err))
    else:
        ok = (isinstance(diag, dict) and diag.get("codigo_error") == ref["codigo_error"]
              and _es_entero(diag.get("linea")) and diag["linea"] == ref["linea_defecto"])
        crit.append(_c("diagnostico", ok, f"esperado {ref['codigo_error']} en la línea {ref['linea_defecto']}; "
                                          f"entregado {diag if isinstance(diag, dict) else diag!r}"))
    ruta = d / "T2_corregido.mini"
    try:
        corregido = ruta.read_text(encoding="utf-8-sig")
    except OSError as e:
        crit.append(_c("corregido", False, f"no se pudo leer {ruta.name}: {e}"))
        return crit
    recs, errs = _errores(corregido, contrato)
    crit.append(_c("corregido_valida", not errs, "el documento corregido valida sin errores" if not errs else f"errores: {errs}"))
    crit.append(_c("registros_esperados", canonical_equal(recs, ref["registros_esperados"]),
                   f"{len(ref['registros_esperados'])} registros con el valor correcto en el defectuoso"))
    a = original.replace("\r\n", "\n").rstrip("\n").split("\n")
    b = corregido.replace("\r\n", "\n").rstrip("\n").split("\n")
    otras = len(a) == len(b) and all(x.strip() == y.strip() for i, (x, y) in enumerate(zip(a, b), 1) if i != ref["linea_defecto"])
    crit.append(_c("otros_registros_intactos", otras, "todas las líneas salvo la defectuosa idénticas a la original"))
    return crit


def _t3(d: Path) -> List[Dict[str, Any]]:
    ref = _ref("T3.referencia.json")
    obj, err = _lee_json(d / "T3_recuperado.json")
    if err:
        return [_c("entrega", False, err)]
    forma = isinstance(obj, dict) and isinstance(obj.get("recuperados"), list)
    crit = [_c("forma", forma, "objeto con 'recuperados' (lista), 'sin_recuperar' y 'primer_no_recuperado'")]
    if not forma:
        return crit
    crit.append(_c("recuperados", canonical_equal(obj["recuperados"], ref["recuperados"]),
                   f"esperados {len(ref['recuperados'])} registros completos (el cortado no cuenta); "
                   f"entregados {len(obj['recuperados'])}"))
    crit.append(_c("sin_recuperar", _es_entero(obj.get("sin_recuperar")) and obj["sin_recuperar"] == ref["sin_recuperar"],
                   f"esperado {ref['sin_recuperar']}; entregado {obj.get('sin_recuperar')!r}"))
    crit.append(_c("primer_no_recuperado",
                   _es_entero(obj.get("primer_no_recuperado")) and obj["primer_no_recuperado"] == ref["primer_no_recuperado"],
                   f"esperado {ref['primer_no_recuperado']}; entregado {obj.get('primer_no_recuperado')!r}"))
    return crit


def _t4(d: Path) -> List[Dict[str, Any]]:
    ref = _ref("T4.referencia.json")
    datos, err = _lee_json(d / "contrato_cambios.json")
    if err:
        return [_c("entrega", False, err)]
    try:
        contrato = Contract.from_dict(datos)
    except (MiniError, KeyError, TypeError, AttributeError, ValueError) as e:
        return [_c("contrato_valido", False, f"el contrato no se puede cargar: {e}")]
    crit = [_c("contrato_valido", True, "el contrato se carga (perfil base)")]
    crit.append(_c("prefijo", contrato.prefix == ref["prefijo"], f"esperado {ref['prefijo']!r}; entregado {contrato.prefix!r}"))
    nombres = [f.name for f in contrato.fields]
    crit.append(_c("campos", nombres == ref["campos"], f"esperados {ref['campos']}; entregados {nombres}"))
    base = AQUI / "participante" / "T4"
    recs, errs = _errores((base / "caso_positivo.mini").read_text(encoding="utf-8"), contrato)
    crit.append(_c("positivo_acepta", not errs, "caso_positivo.mini valida sin errores" if not errs else f"errores: {errs}"))
    crit.append(_c("positivo_canonico", canonical_equal(recs, ref["registros_positivo"]),
                   "los registros del positivo salen con los nombres y valores esperados"))
    _, errs_n = _errores((base / "caso_negativo.mini").read_text(encoding="utf-8"), contrato)
    esperado = (ref["negativo"]["codigo_error"], ref["negativo"]["linea"])
    crit.append(_c("negativo_rechaza", esperado in errs_n,
                   f"caso_negativo.mini debe dar {esperado[0]} en la línea {esperado[1]}; errores: {errs_n}"))
    return crit


def verificar(tarea: str, carpeta: Path) -> Dict[str, Any]:
    if tarea not in TAREAS:
        raise ValueError(f"tarea desconocida: {tarea} (válidas: {', '.join(TAREAS)})")
    faltan = [a for a in ARCHIVOS[tarea] if not (carpeta / a).is_file()]
    if faltan:
        crit = [_c("entrega", False, f"falta(n) en {carpeta}: {', '.join(faltan)}")]
    elif tarea in ("T1A", "T1B"):
        crit = _t1(tarea, carpeta)
    else:
        crit = {"T2": _t2, "T3": _t3, "T4": _t4}[tarea](carpeta)
    return {"tarea": tarea, "cumple": all(c["cumple"] for c in crit), "criterios": crit,
            "nota": "Decide el logro de la tarea; el tiempo lo registra el cronómetro de la sesión."}


def main(argv: Optional[List[str]] = None) -> int:
    for flujo in (sys.stdout, sys.stderr):                     # UTF-8 también en consolas de Windows
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        informe = verificar(argv[0], Path(argv[1]))
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    faltaba = informe["criterios"] and informe["criterios"][0]["id"] == "entrega" and not informe["cumple"]
    if faltaba and "falta" in informe["criterios"][0]["detalle"]:
        return 2
    return 0 if informe["cumple"] else 1


if __name__ == "__main__":
    sys.exit(main())

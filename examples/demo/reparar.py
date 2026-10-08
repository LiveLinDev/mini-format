"""Reparación selectiva de una respuesta .mini, desde la línea de comandos.

Sin --correccion muestra qué hay que volver a pedir al modelo: las líneas inválidas (con su error) y los
registros que faltan. Con --correccion combina la respuesta del modelo con el documento original: acepta
solo las líneas que ahora cumplen el contrato, añade los registros faltantes y escribe el documento reparado.

Uso:
  python reparar.py respuesta.mini --contract tk.contract.json
  python reparar.py respuesta.mini --contract tk.contract.json --correccion correccion.mini --out reparada.mini
"""
import argparse
import json
import sys
from pathlib import Path

from minifmt import Contract, dumps, parse
from minifmt.ai import extract_document, merge_repair, repair_request


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("respuesta")
    ap.add_argument("--contract", required=True)
    ap.add_argument("--esperados", type=int, help="registros pedidos (por defecto, el n de la cabecera)")
    ap.add_argument("--correccion", help="respuesta del modelo con las líneas corregidas y los registros faltantes")
    ap.add_argument("--out")
    ap.add_argument("--lang", default="es", choices=["es", "en"], help="idioma de los mensajes y del pedido de reparación")
    a = ap.parse_args(argv)
    t = (lambda es, en: es) if a.lang == "es" else (lambda es, en: en)

    contrato = Contract.from_dict(json.loads(Path(a.contract).read_text(encoding="utf-8")))
    original = extract_document(Path(a.respuesta).read_text(encoding="utf-8"), contrato)
    doc = parse(original, contrato, strict=False)
    solicitud = repair_request(original, contrato, a.lang)
    lineas = original.split("\n")
    invalidas = [n for n in solicitud.lines if n > 1]
    esperados = a.esperados or doc.header.get("n") or len(doc.records)
    con_error = len(invalidas)
    faltan = max(0, esperados - len(doc.records) - con_error)

    if not a.correccion:
        print(t(f"Registros válidos: {len(doc.records)} de {esperados}", f"Valid records: {len(doc.records)} of {esperados}"))
        for n in invalidas:
            errores = [e for e in doc.errors if e.line == n]
            motivo = "; ".join(f"{e.code} {e.message}" for e in errores) or t("línea inválida", "invalid line")
            print(t("  línea", "  line") + f" {n}: {lineas[n - 1][:60]}  →  {motivo}")
        print(t(f"Registros que faltan: {faltan}", f"Missing records: {faltan}"))
        if not invalidas and not faltan:
            print(t("No hay nada que reparar.", "Nothing to repair."))
            return 0
        print(t(f"Se vuelve a pedir al modelo solo: {con_error} línea(s) inválida(s) y {faltan} registro(s) faltante(s).",
                f"Only this is requested from the model again: {con_error} invalid line(s) and {faltan} missing record(s)."))
        print(t("Los registros válidos se conservan y no se vuelven a pagar.", "Valid records are kept and not paid for again."))
        return 1

    respuesta = extract_document(Path(a.correccion).read_text(encoding="utf-8"), contrato)
    cuerpo = respuesta.split("\n")[1:]
    corregidas = cuerpo[:con_error]
    nuevas = cuerpo[con_error:]
    texto = original
    if invalidas:
        fusion = merge_repair(original, contrato.prefix + "|n=" + str(len(corregidas)) + "\n" + "\n".join(corregidas), contrato, solicitud)
        texto = fusion.text
        print(t("Líneas corregidas y aceptadas: ", "Corrected lines accepted: ") + (", ".join(map(str, fusion.replaced)) or t("ninguna", "none")))
    registros = parse(texto, contrato, strict=False).records
    vistos = {r.get("id") for r in registros}
    extra = [r for r in parse(contrato.prefix + "|n=" + str(len(nuevas)) + "\n" + "\n".join(nuevas), contrato, strict=False).records
             if r.get("id") not in vistos]
    if extra:
        print(t("Registros faltantes añadidos: ", "Missing records added: ") + ", ".join(str(r.get("id")) for r in extra))
    final = dumps({"header": {}, contrato.records_key: registros + extra}, contrato)
    comprobado = parse(final, contrato, strict=True)
    if a.out:
        Path(a.out).write_text(final, encoding="utf-8")
    print(t(f"Documento reparado: {len(comprobado.records)} de {esperados} registros válidos",
            f"Repaired document: {len(comprobado.records)} of {esperados} valid records") + (f" → {a.out}" if a.out else ""))
    if not a.out:
        sys.stdout.write(final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

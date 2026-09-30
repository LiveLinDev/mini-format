"""Escribe examples/optimizacion/<dominio>/: contratos, instrucciones reales, respuestas, mapa y datos de referencia.

Todo se genera con las herramientas reales (``from_json_schema``, ``spec_block``, ``make_prompt``, ``dumps``) y es
reproducible: ``tools/ejecutar_opt.py`` lo regenera y una prueba comprueba que lo versionado coincide.

Las «respuestas» son la SERIALIZACIÓN determinista de los datos de referencia, no salida de un modelo.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import datos, ejemplo, medir, perfiles
from .dominios import dominios

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "examples" / "optimizacion"
REGISTROS_EJEMPLO = {"tickets": 10, "eventos": 10, "comentarios": 5}


def _escribir(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto if texto.endswith("\n") else texto + "\n", encoding="utf-8", newline="\n")


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def archivos_dominio(dom_id: str) -> Dict[str, str]:
    """{nombre de archivo: contenido} de la carpeta de un dominio."""
    prep = medir.preparar(dom_id)
    dom, esp = prep.dom, prep.esp
    if dom_id == "tickets":
        regs = ejemplo.registros_canonicos()                    # los 10 tickets del hilo de la mesa de ayuda
        origen = "los 10 tickets del hilo de «Cómo funciona» (examples/mesa-de-ayuda/grabaciones/mini/ok.mini; procedencia asistido_ia, no verificable)"
    else:
        regs = dom.generar(datos.SEMILLA_PRUEBA, 0, REGISTROS_EJEMPLO[dom_id])
        origen = (f"sintético determinista (semilla {datos.SEMILLA_PRUEBA}, lote 0)" if dom.sintetico
                  else "benchmark/public/data/comments.json, tramo de prueba (JSONPlaceholder, MIT)")
    i = prep.instr
    f: Dict[str, str] = {
        "esquema.json": _json(dom.esquema),
        "contrato_general.json": _json(perfiles.contrato_general(dom).to_dict()),
        "contrato_dominio.json": _json(prep.contrato_dom),
        "contrato_especializado.json": _json(esp.contrato().to_dict()),
        "mapa.json": _json(esp.mapa_explicito()),
        "instruccion_json.txt": i["json"]["sin_ejemplo"],
        "instruccion_json_con_ejemplo.txt": i["json"]["con_ejemplo"],
        "instruccion_general.es.txt": i["general_fromschema"]["sin_ejemplo"],
        "instruccion_general_con_ejemplo.es.txt": i["general_fromschema"]["con_ejemplo"],
        "instruccion_dominio.es.txt": i["general_dominio"]["sin_ejemplo"],
        "instruccion_dominio_con_ejemplo.es.txt": i["general_dominio"]["con_ejemplo"],
        "instruccion_especializada_compacta.es.txt": i["especializado"]["compacta_sin_ejemplo"],
        "instruccion_especializada_compacta_con_ejemplo.es.txt": i["especializado"]["compacta_con_ejemplo"],
        "instruccion_especializada_spec_block.es.txt": i["especializado"]["spec_block_sin_ejemplo"],
        "instruccion_especializada_spec_block_con_ejemplo.es.txt": i["especializado"]["spec_block_con_ejemplo"],
        "respuesta_json_compacto.json": perfiles.json_compacto(dom, regs),
        "respuesta_json_legible.json": perfiles.json_legible(dom, regs),
        "respuesta_general.mini": perfiles.salida_general(dom, regs),
        "respuesta_dominio.mini": perfiles.salida_dominio(dom, prep.contrato_dom, regs),
        "respuesta_especializada.mini": perfiles.salida_especializada(esp, regs),
        "datos_originales.json": json.dumps(regs, ensure_ascii=False, separators=(",", ":")),
    }
    f["LEEME.md"] = leeme(dom, regs, origen)
    return f


def leeme(dom, regs, origen: str) -> str:
    etiqueta = {"representativo": "REPRESENTATIVO", "favorable": "FAVORABLE (diseñado con esa forma; no es promesa general)",
                "ahorro_pequeno": "AHORRO PEQUEÑO (texto libre largo; sin ahorro en el total con lotes pequeños)"}[dom.etiqueta]
    return (f"# {dom.titulo}\n\n"
            f"* Caso: **{etiqueta}**.\n"
            f"* Datos de referencia ({len(regs)} registros): {origen}. {'Sintético.' if dom.sintetico else 'No sintético: datos públicos de prueba.'}\n"
            f"* Las «respuestas» son la serialización determinista de esos datos, no salida de un modelo.\n"
            f"* Las instrucciones las producen las herramientas reales: `mini from-schema` + `spec_block` (general), `mini build` (`make_prompt`, "
            f"perfil mini-domain/1) y, para el especializado, `spec_block` sobre el contrato diseñado a mano y una plantilla compacta propia "
            f"(`instruccion_compacta`, sin validar con un modelo real).\n"
            f"* El mapa (`mapa.json`) vive en la aplicación: el núcleo de .mini no lo conoce. También se imprime en la instrucción, así que sus tokens se cuentan.\n\n"
            f"```bash\npython examples/optimizacion/reconstruir.py {dom.id}\n```\n")


def escribir(destino: Path = DESTINO, dominios_ids=("tickets", "eventos", "comentarios")) -> List[Path]:
    hechos = []
    for d in dominios_ids:
        for nombre, contenido in archivos_dominio(d).items():
            ruta = destino / d / nombre
            _escribir(ruta, contenido)
            hechos.append(ruta)
    return hechos

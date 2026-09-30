"""El ejemplo concreto que usará «Cómo funciona»: diez tickets, de punta a punta.

Parte de los diez tickets de ``examples/mesa-de-ayuda`` (el hilo que ya muestra el sitio) y produce, con la
herramienta real, todo lo que hace falta para contarlo: los registros canónicos, el JSON legible y compacto,
el .mini general y el especializado, las instrucciones que se enviarían (general y especializada, con mapas),
los conteos medidos por tokenizador y por componente, un registro cortado y uno erróneo con los diagnósticos
reales de ``minifmt`` y la conversión a JSON canónico de la aplicación.

PROCEDENCIA de los diez registros: ``examples/mesa-de-ayuda/grabaciones/mini/ok.mini`` (incorporado en el
commit c5e6605, 2026-09-17, sesión asistida por IA). No existe ningún registro (modelo, fecha de llamada,
``usage``) de que sea la salida literal de una llamada a un proveedor, aunque el README de esa carpeta lo
llama «respuesta grabada de un modelo». Aquí se etiqueta ``asistido_ia`` con procedencia no verificable y se
usa solo como CONTENIDO de ejemplo; todas las cifras se recalculan localmente sobre ese texto.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import dumps, from_json_schema, parse  # noqa: E402
from minifmt.ai.repair import invalid_items, merge_repair, repair_request  # noqa: E402
from minifmt.errors import MiniValidationError  # noqa: E402

from . import datos, diseno, perfiles, tokenizadores  # noqa: E402
from .dominios import dominios  # noqa: E402
from .especializacion import comprobar_equivalencia, serializar_objeto  # noqa: E402

MESA = RAIZ / "examples" / "mesa-de-ayuda"
ORIGEN = MESA / "grabaciones" / "mini" / "ok.mini"
ORIGEN_JSON = MESA / "grabaciones" / "json" / "ok.json"
MENSAJES = MESA / "mensajes.json"
CORTE = 0.75           # la grabación «cortada» del sitio se trunca al 75 %; se usa la misma proporción


def registros_canonicos() -> List[Dict[str, Any]]:
    dom = dominios()["tickets"]
    c = perfiles.contrato_general(dom)
    doc = parse(ORIGEN.read_text(encoding="utf-8"), c, strict=True)
    regs = doc.to_canonical()["records"]
    en_json = json.loads(ORIGEN_JSON.read_text(encoding="utf-8"))["tickets"]
    if serializar_objeto(regs) != serializar_objeto(en_json):
        raise RuntimeError("ok.mini y ok.json de mesa-de-ayuda ya no contienen los mismos tickets")
    return regs


def _conteos(textos: Dict[str, str]) -> Dict[str, Dict[str, int]]:
    """{tokenizador: {etiqueta: tokens del texto COMPLETO}}."""
    return {n: {k: t.contar(v) for k, v in textos.items()} for n, t in tokenizadores.todos().items()}


def _texto_json_cortado(texto: str) -> Dict[str, Any]:
    corte = texto[: int(len(texto) * CORTE)]
    try:
        json.loads(corte)
        err = None
    except ValueError as e:
        err = f"{type(e).__name__}: {e}"
    # objetos cerrados dentro del arreglo (aunque el texto no sea JSON válido)
    prof = cerrados = 0
    en_txt = esc = False
    for ch in corte:
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            en_txt = not en_txt
        elif not en_txt:
            if ch == "{":
                prof += 1
            elif ch == "}":
                prof -= 1
                if prof == 1:
                    cerrados += 1
    return {"texto": corte, "json_loads": err, "objetos_completos_en_el_texto": cerrados,
            "registros_utilizables_sin_reparar": 0 if err else None}


def _diagnostico(texto: str, contrato) -> Dict[str, Any]:
    doc = parse(texto, contrato, strict=False)
    d = doc.diagnostics()
    return d


def construir(comparacion: Optional[List[Dict[str, Any]]] = None,
              equilibrio: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    dom = dominios()["tickets"]
    esp = diseno.especializacion_de("tickets")
    regs = registros_canonicos()
    mensajes = json.loads(MENSAJES.read_text(encoding="utf-8"))
    dev = dom.generar(datos.SEMILLA_DESARROLLO, 0, perfiles.MUESTRAS_DOMINIO)
    cd = perfiles.contrato_dominio(dom, dev)
    ins = perfiles.instrucciones(dom, esp, cd, dev)
    cg, ce = perfiles.contrato_general(dom), esp.contrato()

    # ---- salidas
    j_comp, j_leg = perfiles.json_compacto(dom, regs), perfiles.json_legible(dom, regs)
    j_abr = perfiles.json_abreviado(esp, regs)
    m_gen = perfiles.salida_general(dom, regs)
    m_dom = perfiles.salida_dominio(dom, cd, regs)
    m_esp = perfiles.salida_especializada(esp, regs)
    perfiles.verificar_general(dom, regs)
    perfiles.verificar_dominio(dom, cd, regs)
    perfiles.verificar_json_abreviado(esp, regs)
    comprobar_equivalencia(esp, regs)

    # ---- conversión a JSON canónico de la aplicación
    objeto_parse = parse(m_esp, ce, strict=True).to_canonical()
    reconstruido = esp.reconstruir(objeto_parse)
    conversion = {
        "paso_1_parse_del_mini_especializado": objeto_parse,
        "paso_2_reconstruir_con_el_mapa": {dom.clave_json: reconstruido},
        "json_canonico_de_la_aplicacion": json.dumps({dom.clave_json: reconstruido}, ensure_ascii=False, separators=(",", ":")),
        "identico_al_original": serializar_objeto(reconstruido) == serializar_objeto(regs),
        "nota": "El objeto del paso 1 lleva los códigos cortos tal cual: el núcleo de .mini no conoce el mapa. "
                "Solo el paso 2, que es de la aplicación, devuelve las etiquetas, el identificador T-… y el tipo original.",
    }

    # ---- registro erróneo (código fuera de la enumeración) y cortado
    lineas_e = m_esp.split("\n")
    lineas_g = m_gen.split("\n")
    idx_err = 4                                              # 5.º registro = línea física 6 (como en error.mini)
    cols = lineas_e[idx_err + 1].split("|")
    cols[2] = "f"                                            # categoria: 'f' no está en {a|p|e|c}
    mal_e = "\n".join(lineas_e[: idx_err + 1] + ["|".join(cols)] + lineas_e[idx_err + 2:])
    colg = lineas_g[idx_err + 1].split("|")
    colg[2] = "facturacion"                                  # como en grabaciones/mini/error.mini
    mal_g = "\n".join(lineas_g[: idx_err + 1] + ["|".join(colg)] + lineas_g[idx_err + 2:])
    regs_mal = [dict(r) for r in regs]
    regs_mal[idx_err]["categoria"] = "facturacion"
    mal_j = perfiles.json_compacto(dom, regs_mal)
    # corrección selectiva de la línea inválida: la línea original (no es salida de un modelo)
    req = repair_request(mal_e, ce, "es", include_spec=False)
    corregida = f"{esp.prefijo}|n=1\n{lineas_e[idx_err + 1]}"
    fusion = merge_repair(mal_e, corregida, ce)
    erroneo = {
        "descripcion": "Una línea trae un código de categoría que no existe (en el general, una etiqueta que no existe), "
                       "como la grabación «error» del sitio.",
        "mini_especializado": mal_e,
        "diagnostico_especializado": _diagnostico(mal_e, ce),
        "mini_general": mal_g,
        "diagnostico_general": _diagnostico(mal_g, cg),
        "json_compacto": mal_j,
        "json_loads": "sin error: es JSON válido; el valor fuera de la enumeración solo lo detecta una validación de esquema (no incluida)",
        "lineas_a_regenerar": [it.line for it in invalid_items(mal_e, ce)],
        "peticion_de_reparacion_usuario": req.user,
        "reparacion": {"respuesta_de_reparacion": corregida,
                       "nota_de_procedencia": "la línea corregida es la original del documento: demuestra el mecanismo, no es salida de un modelo",
                       "documento_reparado_identico_al_original": fusion.text == m_esp,
                       "ok": bool(fusion.ok)},
    }
    corte_e = m_esp[: int(len(m_esp) * CORTE)]
    corte_g = m_gen[: int(len(m_gen) * CORTE)]
    cortado = {
        "descripcion": f"La respuesta se interrumpe al {int(CORTE * 100)} % de su longitud (como la grabación «cortada» del sitio).",
        "mini_especializado": corte_e,
        "diagnostico_especializado": _diagnostico(corte_e, ce),
        "mini_general": corte_g,
        "diagnostico_general": _diagnostico(corte_g, cg),
        "json_compacto": _texto_json_cortado(j_comp),
    }
    # registros recuperables del mini cortado (los válidos), reconstruidos
    dd = parse(corte_e, ce, strict=False)
    cortado["registros_recuperados_y_reconstruidos"] = esp.reconstruir({"header": dd.header, "records": dd.records})
    cortado["mini_con_n_declarado"] = 10

    # ---- conteos (texto COMPLETO de cada cosa, por tokenizador)
    textos: Dict[str, str] = {
        "salida.json_compacto": j_comp, "salida.json_legible": j_leg, "salida.json_abreviado": j_abr,
        "salida.mini_general": m_gen, "salida.mini_dominio": m_dom, "salida.mini_especializado": m_esp,
        "instruccion.json.schema_sin_ejemplo": ins["json"]["sin_ejemplo"],
        "instruccion.json.schema_con_ejemplo": ins["json"]["con_ejemplo"],
        "instruccion.general_fromschema.sin_ejemplo": ins["general_fromschema"]["sin_ejemplo"],
        "instruccion.general_fromschema.con_ejemplo": ins["general_fromschema"]["con_ejemplo"],
        "instruccion.general_dominio.sin_ejemplo": ins["general_dominio"]["sin_ejemplo"],
        "instruccion.general_dominio.con_ejemplo": ins["general_dominio"]["con_ejemplo"],
    }
    for k, v in ins["especializado"].items():
        textos[f"instruccion.especializado.{k}"] = v
    conteos = _conteos(textos)
    totales = {}
    sep = "\n\n"
    combos = [
        ("json_compacto", "ninguna", "", j_comp),
        ("json_compacto", "schema_sin_ejemplo", ins["json"]["sin_ejemplo"], j_comp),
        ("json_compacto", "schema_con_ejemplo", ins["json"]["con_ejemplo"], j_comp),
        ("general_fromschema", "sin_ejemplo", ins["general_fromschema"]["sin_ejemplo"], m_gen),
        ("general_fromschema", "con_ejemplo", ins["general_fromschema"]["con_ejemplo"], m_gen),
        ("general_dominio", "sin_ejemplo", ins["general_dominio"]["sin_ejemplo"], m_dom),
        ("general_dominio", "con_ejemplo", ins["general_dominio"]["con_ejemplo"], m_dom),
    ] + [("especializado", k, v, m_esp) for k, v in ins["especializado"].items()]
    toks = tokenizadores.todos()
    for nombre, t in toks.items():
        totales[nombre] = {f"{p}.{v}": (t.contar(i + sep + s) if i else t.contar(s)) for p, v, i, s in combos}
    componentes_mini = {}
    for nombre, t in toks.items():
        l = m_esp.split("\n")
        g = m_gen.split("\n")
        componentes_mini[nombre] = {
            "especializado.cabecera": t.contar(l[0]), "especializado.registros_juntos": t.contar("\n".join(l[1:])),
            "general.cabecera": t.contar(g[0]), "general.registros_juntos": t.contar("\n".join(g[1:])),
            "nota": "cada componente es un texto completo tokenizado aparte; no suman exactamente el conteo del documento"}

    lineas_instr = ins["especializado"]["compacta_sin_ejemplo"].split("\n")
    componentes_instr = {nombre: [{"linea": i + 1, "texto": l, "tokens": t.contar(l)} for i, l in enumerate(lineas_instr)]
                         for nombre, t in toks.items()}

    def ahorro(a, b):
        return None if not b else round(100 * (1 - a / b), 2)

    lectura = {}
    for nombre in toks:
        c, tt = conteos[nombre], totales[nombre]
        lectura[nombre] = {
            "ahorro_salida_general_vs_json_compacto_pct": ahorro(c["salida.mini_general"], c["salida.json_compacto"]),
            "ahorro_salida_especializado_vs_json_compacto_pct": ahorro(c["salida.mini_especializado"], c["salida.json_compacto"]),
            "ahorro_salida_especializado_vs_json_abreviado_pct": ahorro(c["salida.mini_especializado"], c["salida.json_abreviado"]),
            "ahorro_total_general_con_ejemplo_vs_json_sin_instruccion_pct": ahorro(tt["general_fromschema.con_ejemplo"], tt["json_compacto.ninguna"]),
            "ahorro_total_especializado_compacta_con_ejemplo_vs_json_sin_instruccion_pct": ahorro(tt["especializado.compacta_con_ejemplo"], tt["json_compacto.ninguna"]),
            "ahorro_total_especializado_compacta_con_ejemplo_vs_json_con_esquema_y_ejemplo_pct": ahorro(tt["especializado.compacta_con_ejemplo"], tt["json_compacto.schema_con_ejemplo"]),
            "instruccion_especializado_menos_general_con_ejemplo_tokens": conteos[nombre]["instruccion.especializado.compacta_con_ejemplo"] - conteos[nombre]["instruccion.general_fromschema.con_ejemplo"],
        }
    out: Dict[str, Any] = {
        "esquema": "mini-format/ejemplo-tickets/1",
        "estudio": "OPT",
        "uso": "Ejemplo concreto de «Cómo funciona»: 10 tickets. Las cifras de este archivo las produce experiments/optimizacion/ejemplo.py; "
               "no se editan a mano.",
        "procedencia": "reproducido_local",
        "origen_de_los_registros": {
            "ruta": ORIGEN.relative_to(RAIZ).as_posix(),
            "comentario": "Los 10 tickets del hilo de la mesa de ayuda del sitio (T-1041 a T-1050).",
            "procedencia_del_origen": "asistido_ia",
            "nota_de_procedencia": "Incorporado en el commit c5e6605 (2026-09-17, sesión asistida por IA). No hay registro de modelo, fecha de llamada ni usage; "
                                   "el README de la carpeta lo llama «respuesta grabada de un modelo» y eso no se puede verificar. "
                                   "No es una medición de un modelo: solo contenido de ejemplo.",
        },
        "mensajes": mensajes,
        "registros_canonicos": regs,
        "json": {"legible": j_leg, "compacto": j_comp, "abreviado_control": j_abr},
        "mini": {"general": m_gen, "dominio_mini_build": m_dom, "especializado": m_esp},
        "instrucciones": {
            "json": ins["json"],
            "general_fromschema": ins["general_fromschema"],
            "general_dominio": ins["general_dominio"],
            "especializado": ins["especializado"],
        },
        "mapa_explicito": esp.mapa_explicito(),
        "contratos": {"general": cg.to_dict(), "especializado": esp.contrato_dict()},
        "conteos": {"tokens_por_texto_completo": conteos, "tokens_total_instruccion_mas_salida": totales,
                    "componentes_del_mini": componentes_mini,
                    "componentes_de_la_instruccion_especializada_compacta": componentes_instr,
                    "separador_del_total": "salto de línea doble"},
        "lectura": lectura,
        "conversion_a_json_canonico": conversion,
        "registro_erroneo": erroneo,
        "registro_cortado": cortado,
        "advertencias": [
            "Los conteos son locales (tiktoken con vocabulario archivado): aproximan, no son usage ni conteo de solicitud de ningún proveedor.",
            "Con 10 tickets el total con instrucción puede no compensar; el punto de equilibrio está en la serie por lote.",
            "La instrucción compacta es una plantilla propia del estudio y no se validó con un modelo real (sin llamadas de API).",
        ],
    }
    if comparacion is not None:
        out["serie_tickets_por_lote"] = [
            {k: c[k] for k in ("tokenizador", "n", "perfil", "instruccion", "ahorro_salida_pct", "ahorro_total_pct",
                               "ahorro_total_con_esquema_pct", "mini_instruccion", "mini_total")}
            for c in comparacion
            if c["dominio"] == "tickets" and (c["perfil"], c["instruccion"]) in (
                ("especializado", "compacta_con_ejemplo"), ("general_fromschema", "con_ejemplo"))]
    if equilibrio is not None:
        out["equilibrio_tickets"] = [e for e in equilibrio if e["dominio"] == "tickets"
                                     and ((e["perfil"], e["instruccion"]) in (("especializado", "compacta_con_ejemplo"), ("general_fromschema", "con_ejemplo"))
                                          or e["comparador"] == "salida")]
    return out

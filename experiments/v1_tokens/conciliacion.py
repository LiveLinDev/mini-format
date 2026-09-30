"""Conciliación de las cifras de ahorro de V1 y desglose payload / estructura / prompt / total.

Las cuatro cifras que circulan (33,8 %, 34,8 %, 34,99 %, 35,64 %) miden cosas distintas.
Este módulo las DERIVA de los archivos de resultados (nada se escribe a mano) y registra,
para cada una, unidad, estadístico, denominador, conjunto, tokenizador y archivo de origen.

Vocabulario fijado (la palabra «payload» tenía dos significados):

* ``contenido_hojas``        cota inferior de contenido: cada valor hoja se tokeniza POR SEPARADO y
                             se suma (``formats.payload_tokens``; la columna ``payload`` de
                             ``benchmark/results/summary_12.csv``). No es un texto que se envíe.
* ``documento``              el texto completo del documento transmitido (antes «payload» en los
                             documentos del equipo: 35,64 % = «solo documento, sin contrato»).
* ``estructura_compartida``  contrato (.mini) o mapa de aplanado (CSV/TOON plano) que el receptor
                             necesita para decodificar; 0 para JSON/YAML/XML tipado/TOON nativo.
* ``prompt_reutilizable``    bloque de instrucción que se antepone en cada solicitud (``spec_block``
                             de .mini; instrucción + JSON Schema para JSON).
* ``total``                  conteo del texto COMPLETO enviado (estructura o prompt + "\\n" + documento),
                             nunca la suma de fragmentos tokenizados por separado.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

import comun as C
import formats
import instruccion as INS

DEFINICIONES = {
    "contenido_hojas": "Cota inferior de contenido: cada valor hoja del objeto se tokeniza por separado y se suman los conteos (benchmark/formats.py::payload_tokens; columna `payload` de benchmark/results/summary_12.csv). No es un texto que se envíe a un modelo.",
    "documento": "Texto completo del documento transmitido (encabezado, metadatos, sintaxis y contenido), sin contrato, mapa ni prompt. Es lo que los documentos del equipo llamaban 'solo payload' (35,64 %).",
    "estructura_compartida": "Contrato (.mini: JSON compacto del contrato) o mapa de aplanado (CSV reversible, TOON plano) que el receptor necesita para decodificar. 0 para JSON, YAML, XML tipado y TOON nativo, que son autodescriptivos.",
    "prompt_reutilizable": "Bloque de instrucción que acompaña a cada solicitud: spec_block del contrato para .mini; instrucción + JSON Schema (json_schema) para JSON compacto. Se solapa con la estructura compartida (describe el mismo contrato en lenguaje natural): no se suman.",
    "total": "Conteo del texto completo enviado: tokenizer.count(estructura_o_prompt + '\\n' + documento). No es la suma de conteos de fragmentos.",
}


def _n(x: Any) -> Any:
    return None if x is None else int(x)


def desglose(toks: Dict[str, Any], dominios: Optional[Sequence[str]] = None,
             casos: Sequence[tuple] = (("ciclo", 12), ("muestreo", 100))) -> List[Dict[str, Any]]:
    """Por dominio y tokenizador: contenido, documento, estructura, prompt y totales de JSON compacto y .mini."""
    reg = C.registro()
    filas: List[Dict[str, Any]] = []
    for variante, n in casos:
        for p in (dominios or reg.contracts):
            c = reg.get(p)
            doc = C.generar(p, n, variante)
            texto = {"json_compact": formats.json_compact(doc, c), "mini": formats.mini_ser(doc, c)}
            estructura = {"json_compact": "", "mini": json.dumps(c.to_dict(), ensure_ascii=False, separators=(",", ":"))}
            prompts = {lang: {"json_compact": INS.bloques(c, lang)["json_schema"], "mini": INS.bloques(c, lang)["mini_spec"]} for lang in ("es", "en")}
            for tname, tk in toks.items():
                for f in ("json_compact", "mini"):
                    t = texto[f]
                    e = estructura[f]
                    fila: Dict[str, Any] = {
                        "variante": variante, "n": n, "dominio": p, "tokenizador": tname, "formato": f,
                        "replicacion_de_base": n > 12,
                        "contenido_hojas": formats.payload_tokens(doc, tk.count),
                        "documento": tk.count(t),
                        "estructura_compartida": tk.count(e) if e else 0,
                        "total_documento_mas_estructura": tk.count(e + "\n" + t) if e else tk.count(t),
                    }
                    for lang in ("es", "en"):
                        pr = prompts[lang][f]
                        fila[f"prompt_reutilizable_{lang}"] = tk.count(pr)
                        fila[f"total_documento_mas_prompt_{lang}"] = tk.count(pr + "\n" + t)
                    filas.append(fila)
    return filas


def ahorros_desglose(filas: Sequence[Dict[str, Any]], variante: str, n: int, tokenizador: str) -> Dict[str, Any]:
    """Ahorro de .mini frente a JSON compacto por unidad: media por dominio y agregado por suma."""
    sel = [f for f in filas if f["variante"] == variante and f["n"] == n and f["tokenizador"] == tokenizador]
    doms = sorted({f["dominio"] for f in sel})
    out: Dict[str, Any] = {}
    # «contenido_hojas» no entra: es el mismo contenido para ambos formatos (ahorro 0 por construcción) y no es un texto enviado.
    for col in ("documento", "total_documento_mas_estructura", "total_documento_mas_prompt_es", "total_documento_mas_prompt_en"):
        m = {f["dominio"]: f[col] for f in sel if f["formato"] == "mini"}
        j = {f["dominio"]: f[col] for f in sel if f["formato"] == "json_compact"}
        a = [100 * (1 - m[d] / j[d]) for d in doms]
        out[col] = {"media_por_dominio_pct": float(np.mean(a)), "agregado_suma_pct": 100 * (1 - sum(m.values()) / sum(j.values())),
                    "suma_mini": int(sum(m.values())), "suma_json_compacto": int(sum(j.values()))}
    return out


# ------------------------------------------------------------------ las cuatro cifras
def _leer_csv(p: Path) -> List[Dict[str, str]]:
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def cifras(summary_12_csv: Path, tokens_benchmark_csv: Path, ahorro_resumen_csv: Path, tokens_serie_csv: Path,
           publico_json: Path, rutas: Dict[str, str]) -> List[Dict[str, Any]]:
    """Recalcula desde archivos las cuatro cifras. ``rutas`` = ruta a citar de cada archivo."""
    out: List[Dict[str, Any]] = []

    # 33,8 %: media por dominio del ahorro redondeado a 1 decimal, n=12 ciclo, o200k, solo documento.
    s12 = _leer_csv(summary_12_csv)
    pct = [float(r["mini_vs_json_compact_pct"]) for r in s12]
    tb = [r for r in _leer_csv(tokens_benchmark_csv) if r["n"] == "12" and r["tokenizer"] == "o200k_base" and r["format"] in ("mini", "json_compact")]
    m = {r["prefix"]: int(r["tokens"]) for r in tb if r["format"] == "mini"}
    j = {r["prefix"]: int(r["tokens"]) for r in tb if r["format"] == "json_compact"}
    sin_redondeo = [100 * (1 - m[d] / j[d]) for d in sorted(m)]
    out.append({
        "cifra_id": "linea_base_n12.media_por_dominio",
        "cifra_citada": "33,8 %",
        "valor_recalculado_pct": float(np.mean(pct)),
        "valor_sin_redondear_pct": float(np.mean(sin_redondeo)),
        "unidad": "ahorro de tokens de .mini frente a JSON compacto, %",
        "estadistico": "media aritmética de 14 ahorros por dominio (cada dominio pesa igual)",
        "denominador": {"descripcion": "tokens de JSON compacto de cada dominio (n=12); la media no tiene un denominador único",
                        "suma_tokens_json_compacto": int(sum(j.values())), "suma_tokens_mini": int(sum(m.values()))},
        "conjunto": "14 dominios x 12 registros base (168 registros escritos a mano; q extiende a a), protocolo 'ciclo'",
        "replicacion_de_base": False,
        "tokenizador": "o200k_base",
        "que_cuenta": "documento (sin contrato, sin mapa, sin prompt)",
        "generador_mini": "minifmt.dumps (contrato de forks/<dominio>)",
        "archivos": [f"{rutas['summary_12']} (columna mini_vs_json_compact_pct, redondeada a 1 decimal)",
                     f"{rutas['tokens_benchmark']} (tokens sin redondear)"],
        "lectura_alternativa_misma_serie": {"agregado_por_suma_pct": 100 * (1 - sum(m.values()) / sum(j.values()))},
        "comando": "python benchmark/run_benchmark.py",
    })

    # 34,8 %: media por dominio, n=100 muestreo, o200k.
    ar = [r for r in _leer_csv(ahorro_resumen_csv) if r["tokenizador"] == "o200k_base" and r["variante"] == "muestreo" and r["n"] == "100" and r["referencia"] == "json_compact"]
    assert len(ar) == 1, "ahorro_resumen.csv no tiene la fila o200k/muestreo/100/json_compact"
    ts = [r for r in _leer_csv(tokens_serie_csv) if r["tokenizador"] == "o200k_base" and r["variante"] == "muestreo" and r["n"] == "100" and r["formato"] in ("mini", "json_compact")]
    m2 = {r["dominio"]: int(r["tokens"]) for r in ts if r["formato"] == "mini"}
    j2 = {r["dominio"]: int(r["tokens"]) for r in ts if r["formato"] == "json_compact"}
    out.append({
        "cifra_id": "serie_n100_muestreo.media_por_dominio",
        "cifra_citada": "34,8 %",
        "valor_recalculado_pct": float(ar[0]["media"]),
        "valor_sin_redondear_pct": float(np.mean([100 * (1 - m2[d] / j2[d]) for d in sorted(m2)])),
        "ic95_bootstrap_dominios": [float(ar[0]["ic95_inf"]), float(ar[0]["ic95_sup"])],
        "unidad": "ahorro de tokens de .mini frente a JSON compacto, %",
        "estadistico": "media aritmética de 14 ahorros por dominio",
        "denominador": {"descripcion": "tokens de JSON compacto de cada dominio (n=100)",
                        "suma_tokens_json_compacto": int(sum(j2.values())), "suma_tokens_mini": int(sum(m2.values()))},
        "conjunto": "14 dominios x 100 registros por dominio, variante 'muestreo'; los 12 registros base se REPITEN (8 pasadas + 4) con identificadores nuevos",
        "replicacion_de_base": True,
        "tokenizador": "o200k_base",
        "que_cuenta": "documento (sin contrato, sin mapa, sin prompt)",
        "generador_mini": "minifmt.dumps (contrato de forks/<dominio>)",
        "archivos": [f"{rutas['ahorro_resumen']} (fila o200k_base / muestreo / n=100 / json_compact, columna media)",
                     f"{rutas['tokens_serie']} (tokens por dominio)"],
        "lectura_alternativa_misma_serie": {"agregado_por_suma_pct": 100 * (1 - sum(m2.values()) / sum(j2.values()))},
        "comando": "python experiments/v1_tokens/run.py",
    })

    # 34,99 % y 35,64 %: benchmark público, agregado por suma, o200k.
    pub = json.loads(Path(publico_json).read_text(encoding="utf-8"))
    ds = pub["datasets"]
    den = sum(d["formats"]["json_compact"]["tokens"] for d in ds)
    num_doc = sum(d["formats"]["mini"]["tokens"] for d in ds)
    num_est = sum(d["formats"]["mini"]["payload_plus_schema_tokens"] for d in ds)
    num_est_sueltos = sum(d["formats"]["mini"]["tokens"] + d["formats"]["mini"]["shared_schema_tokens"] for d in ds)
    num_prompt = sum(d["formats"]["mini"]["payload_plus_prompt_tokens"] for d in ds)
    comun_pub = {
        "unidad": "ahorro de tokens de .mini frente a JSON compacto, %",
        "estadistico": "agregado por suma (1 - Σ tokens .mini / Σ tokens JSON compacto) sobre los 4 snapshots",
        "conjunto": "4 snapshots públicos con SHA-256 (DummyJSON products y users, JSONPlaceholder comments, USGS earthquakes): "
                    + f"{pub['summary']['records']:,}".replace(",", ".") + " objetos únicos, sin repetición",
        "replicacion_de_base": False,
        "tokenizador": pub["tokenizer"],
        "generador_mini": "minifmt.domain (mini-domain/1), contrato inferido del snapshot completo",
        "comando": "python benchmark/public/run.py",
    }
    out.append({
        "cifra_id": "publico.suma.documento_mas_contrato",
        "cifra_citada": "34,99 %",
        "valor_recalculado_pct": 100 * (1 - num_est / den),
        "unidad": comun_pub["unidad"], "estadistico": comun_pub["estadistico"],
        "denominador": {"descripcion": "Σ tokens de JSON compacto (documento; su esquema no se cuenta: JSON es autodescriptivo)", "suma_tokens_json_compacto": int(den)},
        "numerador": {"descripcion": "Σ payload_plus_schema_tokens de .mini: conteo conjunto de contrato compartido + documento", "suma_tokens_mini": int(num_est),
                      "suma_si_se_contaran_por_separado": int(num_est_sueltos)},
        "conjunto": comun_pub["conjunto"], "replicacion_de_base": False, "tokenizador": comun_pub["tokenizador"],
        "que_cuenta": "documento + contrato compartido (estructura) de .mini frente al documento de JSON compacto",
        "generador_mini": comun_pub["generador_mini"],
        "archivos": [f"{rutas['publico']} (campos formats.mini.payload_plus_schema_tokens y formats.json_compact.tokens; no se guarda como campo: se calcula)"],
        "comando": comun_pub["comando"],
    })
    out.append({
        "cifra_id": "publico.suma.documento_sin_contrato",
        "cifra_citada": "35,64 %",
        "valor_recalculado_pct": 100 * (1 - num_doc / den),
        "valor_archivado_pct": float(pub["summary"]["weighted_savings_pct"]["json_compact"]),
        "unidad": comun_pub["unidad"], "estadistico": comun_pub["estadistico"],
        "denominador": {"descripcion": "Σ tokens de JSON compacto (documento)", "suma_tokens_json_compacto": int(den)},
        "numerador": {"descripcion": "Σ tokens del documento .mini, sin contrato", "suma_tokens_mini": int(num_doc)},
        "conjunto": comun_pub["conjunto"], "replicacion_de_base": False, "tokenizador": comun_pub["tokenizador"],
        "que_cuenta": "documento (sin contrato, sin mapa, sin prompt)",
        "generador_mini": comun_pub["generador_mini"],
        "archivos": [f"{rutas['publico']} (campo summary.weighted_savings_pct.json_compact)"],
        "comando": comun_pub["comando"],
        "lectura_alternativa_mismo_conjunto": {
            "con_contrato_y_prompt_de_mini_pct": 100 * (1 - num_prompt / den),
            "nota": "con el prompt de generación de .mini (en inglés) frente al documento JSON sin instrucción: la asimetría perjudica a .mini",
        },
    })
    return out


def informe_md(cifras_: Sequence[Dict[str, Any]], desg: Dict[str, Any]) -> str:
    def f2(x):
        return "—" if x is None else f"{x:.2f}".replace(".", ",")
    L = ["# Conciliación de cifras de ahorro de V1", "",
         "Cada cifra se deriva de un archivo de resultados; las cuatro miden cosas distintas y no son intercambiables.", "",
         "| Cifra citada | Recalculada | Estadístico | Conjunto | Tokenizador | Qué cuenta | Denominador |",
         "|---|---:|---|---|---|---|---|"]
    for c in cifras_:
        den = c["denominador"]
        d = den.get("suma_tokens_json_compacto")
        miles = f"{d:,}".replace(",", ".")
        L.append(f"| {c['cifra_citada']} | {f2(c['valor_recalculado_pct'])} % | {c['estadistico']} | {c['conjunto']} | {c['tokenizador']} | "
                 f"{c['que_cuenta']} | {den['descripcion']}; Σ = {miles} |")
    L += ["", "## Lecturas de las mismas series con otra estadística", ""]
    for c in cifras_:
        alt = c.get("lectura_alternativa_misma_serie")
        if alt:
            L.append(f"* {c['cifra_citada']}: agregado por suma de la misma serie = {f2(alt['agregado_por_suma_pct'])} %.")
        alt = c.get("lectura_alternativa_mismo_conjunto")
        if alt:
            L.append(f"* {c['cifra_citada']}: con el prompt de .mini frente al documento JSON = {f2(alt['con_contrato_y_prompt_de_mini_pct'])} % (nota: {alt['nota']}).")
    L += ["", "## Archivos de origen", ""]
    for c in cifras_:
        L.append(f"* **{c['cifra_citada']}** ({c['cifra_id']}): " + "; ".join(c["archivos"]) + f". Comando: `{c['comando']}`.")
    L += ["", "## Vocabulario (la palabra «payload» tenía dos significados)", ""]
    for k, v in DEFINICIONES.items():
        L.append(f"* **{k}**: {v}")
    L += ["", "## Ahorro de .mini frente a JSON compacto según la unidad contada", "",
          "| Serie | Tokenizador | Unidad | Media por dominio | Agregado por suma |", "|---|---|---|---:|---:|"]
    nombres = {"documento": "documento", "total_documento_mas_estructura": "documento + estructura compartida",
               "total_documento_mas_prompt_es": "documento + prompt (es)", "total_documento_mas_prompt_en": "documento + prompt (en)"}
    for clave, por_tok in desg.items():
        for t, unidades in por_tok.items():
            for u, etq in nombres.items():
                v = unidades[u]
                L.append(f"| {clave} | {t} | {etq} | {f2(v['media_por_dominio_pct'])} % | {f2(v['agregado_suma_pct'])} % |")
    L += ["", "Para JSON compacto la estructura compartida es 0 (es autodescriptivo), pero su instrucción equivalente (JSON Schema) no lo es: "
          "por eso se publican las tres unidades y ninguna se elige por su resultado. "
          "El desglose por dominio y tokenizador está en `desglose_dominio_tokenizador.csv`.", ""]
    return "\n".join(L)

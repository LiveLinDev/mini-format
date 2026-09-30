"""Tablas y texto derivados de los resultados de una corrida (nunca se escriben cifras a mano).

``bloque_readme`` produce el bloque de cifras de ``experiments/optimizacion/README.md`` y ``adr`` el texto del
ADR de PROPUESTA. Ambos leen los CSV de ``evidencia/corridas/<run_id>/``; una prueba comprueba que lo versionado
coincide con lo que estas funciones generan desde esos archivos.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

TOKENIZADORES = ("o200k_base", "cl100k_base", "r50k_base")
DOMINIOS = ("tickets", "eventos", "comentarios")
ETIQUETAS = {"tickets": "tickets (representativo)", "eventos": "eventos de planta (FAVORABLE)",
             "comentarios": "comentarios (texto libre; ahorro pequeño)"}
PERFIL = {"json_compacto": "JSON compacto (base)", "general_fromschema": "general: mini from-schema",
          "general_dominio": "general: mini build", "especializado": "especializado (instrucción compacta)"}
MARCA_INI = "<!-- cifras:inicio (generado por tools/ejecutar_opt.py; no editar a mano) -->"
MARCA_FIN = "<!-- cifras:fin -->"


def leer(dir_corrida: Path, nombre: str) -> List[Dict[str, str]]:
    with open(Path(dir_corrida) / nombre, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(x: str, nd: int = 1) -> str:
    return "—" if x in ("", None) else f"{float(x):.{nd}f}"


def _pct(x: str) -> str:
    return "—" if x in ("", None) else f"{float(x):+.1f} %"


def _fila(rows, dom, tk, n, perfil, instr):
    return next((r for r in rows if r["dominio"] == dom and r["tokenizador"] == tk and r["n"] == str(n)
                 and r["perfil"] == perfil and r["instruccion"] == instr), None)


def tabla_n100(dir_corrida: Path, tk: str = "o200k_base", n: int = 100) -> str:
    agr = leer(dir_corrida, "resultados_resumen.csv")
    comp = leer(dir_corrida, "comparacion.csv")
    L = [f"| Dominio | Perfil | Instrucción (tokens) | Salida | Total | Ahorro de salida | Ahorro del total vs JSON sin instrucción | Ahorro del total vs JSON con esquema |",
         "|---|---|--:|--:|--:|--:|--:|--:|"]
    for d in DOMINIOS:
        b = _fila(agr, d, tk, n, "json_compacto", "ninguna")
        L.append(f"| {ETIQUETAS[d]} | {PERFIL['json_compacto']} | 0 | {_f(b['salida'])} | {_f(b['total'])} | — | — | — |")
        for perfil, instr in (("general_fromschema", "con_ejemplo"), ("general_dominio", "con_ejemplo"), ("especializado", "compacta_con_ejemplo")):
            c = _fila(comp, d, tk, n, perfil, instr)
            L.append(f"| | {PERFIL[perfil]} | {_f(c['mini_instruccion'], 0)} | {_f(c['mini_salida'])} | {_f(c['mini_total'])} | "
                     f"{_pct(c['ahorro_salida_pct'])} | {_pct(c['ahorro_total_pct'])} | {_pct(c['ahorro_total_con_esquema_pct'])} |")
    return "\n".join(L)


def tabla_por_tokenizador(dir_corrida: Path, n: int = 100) -> str:
    comp = leer(dir_corrida, "comparacion.csv")
    L = ["| Dominio | Tokenizador | Ahorro de salida general | Ahorro de salida especializado | Ahorro del total general | Ahorro del total especializado | Instrucción general → especializada (tokens) |",
         "|---|---|--:|--:|--:|--:|--:|"]
    for d in DOMINIOS:
        for tk in TOKENIZADORES:
            g = _fila(comp, d, tk, n, "general_fromschema", "con_ejemplo")
            e = _fila(comp, d, tk, n, "especializado", "compacta_con_ejemplo")
            L.append(f"| {ETIQUETAS[d] if tk == TOKENIZADORES[0] else ''} | {tk} | {_pct(g['ahorro_salida_pct'])} | {_pct(e['ahorro_salida_pct'])} | "
                     f"{_pct(g['ahorro_total_pct'])} | {_pct(e['ahorro_total_pct'])} | {_f(g['mini_instruccion'], 0)} → {_f(e['mini_instruccion'], 0)} |")
    return "\n".join(L)


def tabla_serie(dir_corrida: Path, tk: str = "o200k_base") -> str:
    comp = leer(dir_corrida, "comparacion.csv")
    ns = sorted({int(r["n"]) for r in comp})
    L = ["| Dominio · perfil | " + " | ".join(f"n={n}" for n in ns) + " |", "|---|" + "--:|" * len(ns)]
    for d in DOMINIOS:
        for perfil, instr in (("general_fromschema", "con_ejemplo"), ("especializado", "compacta_con_ejemplo")):
            cs = [_fila(comp, d, tk, n, perfil, instr) for n in ns]
            L.append(f"| {d} · {'general' if perfil.startswith('general') else 'especializado'} | " + " | ".join(_pct(c["ahorro_total_pct"]) for c in cs) + " |")
    return "\n".join(L)


def tabla_equilibrio(dir_corrida: Path) -> str:
    eq = leer(dir_corrida, "equilibrio.csv")

    def n_est(d, tk, perfil, instr, comp):
        r = next((x for x in eq if x["dominio"] == d and x["tokenizador"] == tk and x["perfil"] == perfil
                  and x["instruccion"] == instr and x["comparador"] == comp), None)
        if r is None:
            return "—"
        return r["n_estrella"] if r["n_estrella"] else f"no existe en n ≤ {r['nmax_medido']}"

    L = ["| Dominio | Tokenizador | Salida (n*) | Total general con ejemplo | Total especializado con ejemplo | Total especializado sin ejemplo |", "|---|---|--:|--:|--:|--:|"]
    for d in DOMINIOS:
        for tk in TOKENIZADORES:
            L.append(f"| {ETIQUETAS[d] if tk == TOKENIZADORES[0] else ''} | {tk} | {n_est(d, tk, 'especializado', 'no_aplica', 'salida')} | "
                     f"{n_est(d, tk, 'general_fromschema', 'con_ejemplo', 'total')} | {n_est(d, tk, 'especializado', 'compacta_con_ejemplo', 'total')} | "
                     f"{n_est(d, tk, 'especializado', 'compacta_sin_ejemplo', 'total')} |")
    return "\n".join(L)


def tabla_control(dir_corrida: Path, tk: str = "o200k_base", n: int = 100) -> str:
    comp = leer(dir_corrida, "comparacion.csv")
    L = ["| Dominio | JSON compacto | JSON con las mismas abreviaturas | .mini especializado | Ahorro frente a JSON compacto | Ahorro frente a JSON abreviado (efecto del formato) |",
         "|---|--:|--:|--:|--:|--:|"]
    for d in DOMINIOS:
        c = _fila(comp, d, tk, n, "especializado", "compacta_con_ejemplo")
        L.append(f"| {ETIQUETAS[d]} | {_f(c['json_compacto_salida'])} | {_f(c['json_abreviado_salida'])} | {_f(c['mini_salida'])} | "
                 f"{_pct(c['ahorro_salida_pct'])} | {_pct(c['ahorro_salida_vs_json_abreviado_pct'])} |")
    return "\n".join(L)


def tabla_simulacion(dir_corrida: Path, tk: str = "o200k_base", n: int = 100) -> str:
    prop = leer(dir_corrida, "propuesta_simulacion.csv")
    L = ["| Dominio | Salida general (tokens) | General con diccionario simulado | Ahorro potencial | Especializado a mano | Columnas del diccionario |", "|---|--:|--:|--:|--:|---|"]
    for d in DOMINIOS:
        r = next(x for x in prop if x["dominio"] == d and x["n"] == str(n) and x["tokenizador"] == tk)
        L.append(f"| {ETIQUETAS[d]} | {r['tokens_salida_general']} | {_f(r['tokens_salida_general_con_diccionario_simulado'], 0)} | "
                 f"{_pct(r['ahorro_potencial_vs_general_pct'])} | {r['tokens_salida_especializado_a_mano']} | "
                 f"{r['columnas'].strip('[]').replace(chr(39), '') or ('ninguna: ' + r['motivo'])} |")
    return "\n".join(L)


def bloque_readme(dir_corrida: Path) -> str:
    dir_corrida = Path(dir_corrida)
    m = json.loads((dir_corrida / "manifiesto.json").read_text(encoding="utf-8"))
    crit = m["criterio"]
    partes = [
        MARCA_INI, "",
        f"Corrida `{m['run_id']}` (procedencia `{m['procedencia']}`, commit `{m['codigo']['commit'][:7]}`, árbol limpio: {str(m['codigo']['arbol_limpio']).lower()}). "
        f"Resultado del criterio fijado de antemano: **{crit['resultado']}** "
        f"(C1 salida ≥ 30 % en los tres tokenizadores: {str(crit['C1_ahorro_salida_ge_30_en_los_tres_tokenizadores']).lower()}; "
        f"C2 total menor que JSON: {str(crit['C2_total_menor_que_json_en_los_tres_tokenizadores']).lower()}; "
        f"C3 equivalencia exacta sin fallos: {str(crit['C3_equivalencia_exacta_sin_fallos']).lower()}).", "",
        "### n = 100, tokenizador o200k_base (lectura primaria)", "",
        "Media de los lotes medidos. «Salida» es el texto que devuelve el modelo; «Total» es instrucción + salida tokenizados como un solo texto. "
        "Positivo = .mini usa menos tokens que JSON compacto.", "", tabla_n100(dir_corrida), "",
        "### n = 100, por tokenizador", "", tabla_por_tokenizador(dir_corrida), "",
        "### Ahorro del total (instrucción con ejemplo + salida) según el tamaño de lote, o200k_base", "",
        "Negativo = el .mini gasta MÁS que JSON compacto sin instrucción. Frente a un JSON que también lleva su esquema como instrucción el equilibrio llega antes (columna correspondiente de la tabla de n = 100).", "",
        tabla_serie(dir_corrida), "",
        "### Punto de equilibrio n* (menor n desde el cual el .mini gasta menos hasta n = 250)", "",
        "«Salida»: payload frente a JSON compacto. «Total»: instrucción + salida frente a JSON compacto con instrucción 0 (lectura más dura para .mini).", "",
        tabla_equilibrio(dir_corrida), "",
        "### Control: cuánto es del formato y cuánto de las abreviaturas (n = 100, o200k_base)", "",
        "JSON con las mismas abreviaturas (códigos, enteros escalados y constantes una sola vez) usa menos tokens que JSON compacto sin ellas: parte del ahorro del perfil especializado NO es del formato.", "",
        tabla_control(dir_corrida), "",
        "### Simulación de una ampliación NO implementada: diccionario por documento (n = 100, o200k_base)", "",
        tabla_simulacion(dir_corrida), "",
        MARCA_FIN, ""]
    return "\n".join(partes)


def insertar_bloque(ruta_readme: Path, bloque: str) -> None:
    s = Path(ruta_readme).read_text(encoding="utf-8")
    a, b = s.index(MARCA_INI), s.index(MARCA_FIN) + len(MARCA_FIN)
    Path(ruta_readme).write_text(s[:a] + bloque.rstrip("\n") + s[b:], encoding="utf-8", newline="\n")


def bloque_en_readme(ruta_readme: Path) -> str:
    s = Path(ruta_readme).read_text(encoding="utf-8")
    a, b = s.index(MARCA_INI), s.index(MARCA_FIN) + len(MARCA_FIN)
    return s[a:b]


def adr(dir_corrida: Path) -> str:
    """Texto del ADR 0030 (PROPUESTA, no vigente). Las cifras salen de ``propuesta_simulacion.csv``."""
    m = json.loads((Path(dir_corrida) / "manifiesto.json").read_text(encoding="utf-8"))
    return f"""# ADR 0030. Alias de enumeración y diccionarios por documento (propuesta, no implementada)

* Estado: **Propuesta (no vigente)**. No hay decisión tomada, ni SPEC 1.2, ni implementación.
* Fecha: 2026-09-30
* Especificación: [SPEC.md](../../SPEC.md) §5, §6 y §8 (cambio propuesto para una futura SPEC 1.2)
* Evidencia: corrida `{m['run_id']}` del estudio OPT ([manifiesto](../../evidencia/corridas/{m['run_id']}/manifiesto.json),
  [simulación](../../evidencia/corridas/{m['run_id']}/propuesta_simulacion.csv)); diseño en
  [experiments/optimizacion](../../experiments/optimizacion/README.md)

## Contexto y problema

El estudio OPT diseñó, dentro de SPEC 1.1 y sin ampliar el formato, una configuración especializada: códigos cortos de
enumeración, identificador numérico con prefijo constante, enteros escalados y hora en minutos. La equivalencia
código↔etiqueta vive en la **aplicación** como un mapa explícito (`mapa.json`), que además se imprime en la instrucción
(así sus tokens se cuentan) y se verifica con una ida y vuelta exacta de todos los registros. Dos límites motivan este registro:

1. Cada aplicación reimplementa el mapa y su decodificador. El objeto canónico que entrega `parse` lleva el código, no la
   etiqueta, y `spec_block` no imprime la `desc` de los campos `enum` (`src/minifmt/prompt.py`, rama de las enumeraciones): el
   mapa viaja como texto libre en la `description` del contrato.
2. El único diccionario que existe hoy es la cabecera `e=` del perfil `mini-domain/1` (solo Python, sin `js/mini.js`, sin
   casos de conformidad, errores `D_*`).

## Alternativas consideradas

1. **No ampliar** (estado actual): el mapa sigue en la aplicación.
2. **Alias de enumeración en el contrato**: cada valor de un `enum` puede declarar un `code` único dentro del campo; el
   documento escribe el código, el objeto canónico contiene la etiqueta y `spec_block` imprime `código=etiqueta`.
3. **Diccionario por documento en la cabecera**: una clave reservada declara, para columnas de texto repetido, la lista de
   valores del documento; las filas llevan el índice entero. Sin contrato adicional.
4. **Portar `mini-domain/1` a TypeScript** y a `js/mini.js` con sus casos de conformidad.

## Decisión

Ninguna. Este registro es una propuesta para discusión: no cambia SPEC.md ni SPEC.es.md, ni el código. Se sugiere evaluar la
alternativa 2 por separado de la 3, porque resuelven problemas distintos.

## Ganancia potencial medida por simulación (NO implementada)

* **Alternativa 2.** Por construcción el texto del documento sería el mismo que el de la configuración especializada ya
  medida (el alias es el código del mapa): los tokens de **salida** serían idénticos a los de la columna «Especializado a mano»
  de la tabla siguiente. La propuesta **no añade ahorro de tokens**: añade portabilidad (mapa dentro del contrato, validación E10
  sobre alias, instrucción generada con los alias y decodificación en ambas implementaciones).
* **Alternativa 3.** Simulación sobre el perfil general (contrato de `mini from-schema`) con la regla de `mini build` (columna
  `str` o `enum`, 2 a 64 valores distintos, al menos 3 filas por valor, al menos 6 filas, ahorro neto en bytes). El diccionario
  viaja completo en cada documento y su coste está contado; no incluye el coste de instruir al modelo sobre la sintaxis.
  Es un techo para estos datos, no una predicción.

{tabla_simulacion(dir_corrida)}

Lectura: un diccionario automático por documento recupera una parte del ahorro que hoy exige diseñar a mano los códigos,
solo donde las columnas repiten mucho; donde el texto es libre o casi no se repite (tickets, comentarios) no aplica o
aporta poco. Las cifras son del perfil general frente a sí mismo con diccionario; no mezclan el ahorro frente a JSON.

## Consecuencias si se aceptara

* **Versión:** SPEC 1.2 (regla nueva de §5 o §6). Un documento 1.1 no cambia. Un contrato con alias requiere una
  implementación 1.2; una implementación 1.1 que lea ese contrato debería fallar de forma visible (E10 al validar un código),
  no degradar en silencio: debe comprobarse, porque hoy `Field.from_dict` ignora claves desconocidas.
* **Casos de conformidad necesarios** (`conformance/generate.py`): alias válido y canónico con etiqueta; código desconocido
  (E10); alias repetido dentro del campo (E20); alias igual a la etiqueta de otro valor (E20); alias con separador o
  escape (E20); ida y vuelta `dumps`/`parse`; estabilidad de texto para un documento emitido por el serializador; alias en
  elementos de lista y en claves de cabecera; y, para la alternativa 3, índice fuera de rango, diccionario duplicado y
  escape dentro del diccionario.
* **Implementaciones:** Python (`contract.py`, `parser.py`, `serializer.py`, `prompt.py`) y TypeScript (`ts/src/*`),
  regenerar `js/mini.js` y las copias del motor del sitio; actualizar `mini to-schema`/`from-schema` (`x-mini`).
* **Pruebas:** paridad Python/TypeScript sobre los casos nuevos, fuzz de ida y vuelta con alias y mapeo inverso, y una prueba
  de que `spec_block` imprime código y etiqueta (hoy omite los valores de enumeraciones dentro de tuplas).
* **Riesgo:** un alias corto mnemotécnico puede confundirse entre campos (p. ej. `a` en dos enumeraciones); la adherencia
  de un modelo a códigos cortos NO está medida (este estudio no hizo llamadas a modelos) y debe validarse con V2/V3.

## Evidencia

* Corrida [`{m['run_id']}`](../../evidencia/corridas/{m['run_id']}/manifiesto.json), archivo `propuesta_simulacion.csv`.
* [experiments/optimizacion/README.md](../../experiments/optimizacion/README.md): diseño, lo que no funcionó y límites.
* [src/minifmt/prompt.py](../../src/minifmt/prompt.py): qué imprime hoy `spec_block` (no imprime la `desc` de los campos `enum` ni los valores de
  enumeraciones dentro de tuplas).
"""

"""OPT: lo publicado (corrida, ejemplo de «Cómo funciona», carpetas de ejemplos, README y ADR) coincide con lo que se recalcula.

Los oráculos son independientes de ``optimizacion.medir`` y ``optimizacion.ejemplo``: los textos se reconstruyen con
``minifmt`` y ``json`` a partir de los archivos publicados, y los tokens se cuentan con ``Tokenizador.ids``.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "src", ROOT / "experiments", ROOT / "tools"):
    sys.path.insert(0, str(p))

import evidencia_lib as ev  # noqa: E402
from minifmt import dumps, parse  # noqa: E402
from minifmt.contract import Contract  # noqa: E402
from optimizacion import carpeta_ejemplos, documentos, ejemplo, tokenizadores  # noqa: E402

CORRIDAS = sorted((ROOT / "evidencia" / "corridas").glob("opt-*/manifiesto.json"))
pytestmark = pytest.mark.skipif(not CORRIDAS, reason="no hay corrida OPT archivada")
DIR = CORRIDAS[-1].parent if CORRIDAS else None
TOK = ("o200k_base", "cl100k_base", "r50k_base")


def _csv(nombre):
    with open(DIR / nombre, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _compacto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _n_tokens(nombre: str, texto: str) -> int:
    return len(tokenizadores.obtener(nombre).ids(texto))


# ------------------------------------------------------------------------- manifiesto
def test_el_manifiesto_es_valido_y_declara_la_procedencia_real():
    m = json.loads((DIR / "manifiesto.json").read_text(encoding="utf-8"))
    assert ev.validar_corrida(m, DIR) == []
    assert m["estudio"] == "OPT" and m["procedencia"] == "reproducido_local"
    assert m["gasto_usd"] == 0 and m["modelo"] is None
    assert m["estado_ejecucion"] == "ejecutado" and m["resultado"] in ("cumple", "no_cumple")
    assert m["codigo"]["arbol_limpio"] is True and m["codigo"]["commit"]
    assert [t["nombre"] for t in m["tokenizadores"]] == list(TOK)
    assert all(t["vocabulario_sha256"] and t["tipo"] == "exacto_local" for t in m["tokenizadores"])
    assert any("Sin llamadas a modelos" in x for x in m["limitaciones"])
    crit = ROOT / "experiments" / "optimizacion" / "criterio.json"
    assert m["criterio"]["sha256"] == ev.sha256_archivo(crit)        # el criterio no cambió después de la corrida
    assert m["criterio"]["fijado_en_los_commits"] == ["c196ec9", "42b3c91"]


def test_los_conjuntos_sinteticos_estan_etiquetados_y_el_publico_lleva_licencia():
    m = json.loads((DIR / "manifiesto.json").read_text(encoding="utf-8"))
    por = {c["nombre"].split()[0]: c for c in m["conjuntos"]}
    assert por["tickets"]["sintetico"] is True and por["eventos"]["sintetico"] is True and por["tickets"]["semilla"] == 20261001
    assert por["comentarios"]["sintetico"] is False and por["comentarios"]["licencia"].startswith("MIT")


def test_el_resultado_del_criterio_se_recalcula_desde_los_csv():
    m = json.loads((DIR / "manifiesto.json").read_text(encoding="utf-8"))
    comp = _csv("comparacion.csv")
    ok1 = ok2 = True
    for tk in TOK:
        f = next(r for r in comp if (r["dominio"], r["tokenizador"], r["n"], r["perfil"], r["instruccion"]) ==
                 ("tickets", tk, "100", "especializado", "compacta_con_ejemplo"))
        ok1 &= 100 * (1 - float(f["mini_salida"]) / float(f["json_compacto_salida"])) >= 30
        ok2 &= float(f["mini_total"]) < float(f["json_compacto_total_sin_instruccion"])
    fallos = json.loads((DIR / "fallos_de_equivalencia.json").read_text(encoding="utf-8"))
    ok3 = not [x for x in fallos if x["perfil"] != "general_dominio"]
    assert m["criterio"]["C1_ahorro_salida_ge_30_en_los_tres_tokenizadores"] is bool(ok1)
    assert m["criterio"]["C2_total_menor_que_json_en_los_tres_tokenizadores"] is bool(ok2)
    assert m["criterio"]["C3_equivalencia_exacta_sin_fallos"] is bool(ok3)
    assert m["resultado"] == ("cumple" if (ok1 and ok2 and ok3) else "no_cumple")


# ------------------------------------------------------------------------- conteos de la tabla
def test_conteos_de_un_lote_de_la_tabla_coinciden_con_un_recalculo_independiente():
    """Lote 0 de n=10 de tickets: texto reconstruido con minifmt/json y contado con ``ids``; instrucciones leídas de los archivos publicados."""
    from optimizacion import datos
    regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 10)
    base = ROOT / "examples" / "optimizacion" / "tickets"
    cg = Contract.load(base / "contrato_general.json")
    ce = Contract.load(base / "contrato_especializado.json")
    mapa = json.loads((base / "mapa.json").read_text(encoding="utf-8"))
    cod = {c["campo"]: c["codigos"] for c in mapa["campos"] if c["tratamiento"] == "codigos"}
    recs = [{"id": int(r["id"][2:]), "prioridad": cod["prioridad"][r["prioridad"]], "categoria": cod["categoria"][r["categoria"]],
             "resumen": r["resumen"], "horas": r["horas"]} for r in regs]
    salidas = {"json_compacto": _compacto({"tickets": regs}),
               "general_fromschema": dumps({"header": {}, "records": regs}, cg),
               "especializado": dumps({"prefix": "tke", "header": {}, "records": recs}, ce)}
    instr = {"general_fromschema": (base / "instruccion_general_con_ejemplo.es.txt").read_text(encoding="utf-8").rstrip("\n"),
             "especializado": (base / "instruccion_especializada_compacta_con_ejemplo.es.txt").read_text(encoding="utf-8").rstrip("\n")}
    filas = [r for r in _csv("resultados_por_lote.csv") if r["dominio"] == "tickets" and r["n"] == "10" and r["lote"] == "0"]
    assert filas, "falta el lote 0 de n=10 de tickets"
    for tk in TOK:
        for perfil, texto in salidas.items():
            esperado_salida = _n_tokens(tk, texto)
            if perfil == "json_compacto":
                f = next(r for r in filas if r["tokenizador"] == tk and (r["perfil"], r["instruccion"]) == ("json_compacto", "ninguna"))
                assert int(f["tokens_salida"]) == esperado_salida == int(f["tokens_total"])
                continue
            var = "con_ejemplo" if perfil == "general_fromschema" else "compacta_con_ejemplo"
            f = next(r for r in filas if r["tokenizador"] == tk and (r["perfil"], r["instruccion"]) == (perfil, var))
            assert int(f["tokens_salida"]) == esperado_salida
            assert int(f["tokens_instruccion"]) == _n_tokens(tk, instr[perfil])
            assert int(f["tokens_total"]) == _n_tokens(tk, instr[perfil] + "\n\n" + texto)      # texto completo, no suma


def test_el_punto_de_equilibrio_se_recalcula_desde_la_curva():
    curva = {(r["tokenizador"], int(r["n"])): r for r in _csv("curva_equilibrio.csv") if r["dominio"] == "tickets"}
    eq = {(r["tokenizador"], r["perfil"], r["instruccion"], r["comparador"]): r for r in _csv("equilibrio.csv") if r["dominio"] == "tickets"}
    for tk in TOK:
        ns = sorted(n for (t, n) in curva if t == tk)
        diffs = [int(curva[(tk, n)]["json_compacto.ninguna.total"]) - int(curva[(tk, n)]["especializado.compacta_con_ejemplo.total"]) for n in ns]
        n_est = None
        for i in range(len(diffs) - 1, -1, -1):
            if diffs[i] > 0:
                n_est = ns[i]
            else:
                break
        fila = eq[(tk, "especializado", "compacta_con_ejemplo", "total")]
        assert (int(fila["n_estrella"]) if fila["n_estrella"] else None) == n_est


# ------------------------------------------------------------------------- ejemplo de «Cómo funciona»
def test_el_ejemplo_trae_entre_6_y_10_tickets_y_la_conversion_a_json_es_identica():
    e = json.loads((DIR / "ejemplo_tickets.json").read_text(encoding="utf-8"))
    assert 6 <= len(e["registros_canonicos"]) <= 10
    assert e["procedencia"] == "reproducido_local" and e["origen_de_los_registros"]["procedencia_del_origen"] == "asistido_ia"
    assert e["conversion_a_json_canonico"]["identico_al_original"] is True
    assert e["conversion_a_json_canonico"]["json_canonico_de_la_aplicacion"] == _compacto({"tickets": e["registros_canonicos"]})


def test_los_textos_y_conteos_del_ejemplo_se_recalculan_sin_usar_el_codigo_del_ejemplo():
    e = json.loads((DIR / "ejemplo_tickets.json").read_text(encoding="utf-8"))
    regs = e["registros_canonicos"]
    assert e["json"]["compacto"] == _compacto({"tickets": regs})
    assert e["json"]["legible"] == json.dumps({"tickets": regs}, ensure_ascii=False, indent=2)
    cg = Contract.from_dict(e["contratos"]["general"])
    ce = Contract.from_dict(e["contratos"]["especializado"])
    assert e["mini"]["general"] == dumps({"header": {}, "records": regs}, cg)
    cod = {c["campo"]: c["codigos"] for c in e["mapa_explicito"]["campos"] if c["tratamiento"] == "codigos"}
    recs = [{"id": int(r["id"][2:]), "prioridad": cod["prioridad"][r["prioridad"]], "categoria": cod["categoria"][r["categoria"]],
             "resumen": r["resumen"], "horas": r["horas"]} for r in regs]
    assert e["mini"]["especializado"] == dumps({"prefix": "tke", "header": {}, "records": recs}, ce)
    textos = {"salida.json_compacto": e["json"]["compacto"], "salida.json_legible": e["json"]["legible"],
              "salida.json_abreviado": e["json"]["abreviado_control"], "salida.mini_general": e["mini"]["general"],
              "salida.mini_dominio": e["mini"]["dominio_mini_build"], "salida.mini_especializado": e["mini"]["especializado"],
              "instruccion.json.schema_sin_ejemplo": e["instrucciones"]["json"]["sin_ejemplo"],
              "instruccion.json.schema_con_ejemplo": e["instrucciones"]["json"]["con_ejemplo"],
              "instruccion.general_fromschema.sin_ejemplo": e["instrucciones"]["general_fromschema"]["sin_ejemplo"],
              "instruccion.general_fromschema.con_ejemplo": e["instrucciones"]["general_fromschema"]["con_ejemplo"],
              "instruccion.general_dominio.sin_ejemplo": e["instrucciones"]["general_dominio"]["sin_ejemplo"],
              "instruccion.general_dominio.con_ejemplo": e["instrucciones"]["general_dominio"]["con_ejemplo"]}
    for k, v in e["instrucciones"]["especializado"].items():
        textos[f"instruccion.especializado.{k}"] = v
    for tk in TOK:
        assert e["conteos"]["tokens_por_texto_completo"][tk] == {k: _n_tokens(tk, v) for k, v in textos.items()}
        t = e["conteos"]["tokens_total_instruccion_mas_salida"][tk]
        instr = e["instrucciones"]["especializado"]["compacta_con_ejemplo"]
        assert t["especializado.compacta_con_ejemplo"] == _n_tokens(tk, instr + "\n\n" + e["mini"]["especializado"])
        assert t["json_compacto.ninguna"] == _n_tokens(tk, e["json"]["compacto"])
        assert t["general_fromschema.con_ejemplo"] == _n_tokens(
            tk, e["instrucciones"]["general_fromschema"]["con_ejemplo"] + "\n\n" + e["mini"]["general"])
        lect = e["lectura"][tk]
        sj, sm = e["conteos"]["tokens_por_texto_completo"][tk]["salida.json_compacto"], e["conteos"]["tokens_por_texto_completo"][tk]["salida.mini_especializado"]
        assert lect["ahorro_salida_especializado_vs_json_compacto_pct"] == round(100 * (1 - sm / sj), 2)


def test_los_diagnosticos_del_ejemplo_son_los_reales_de_minifmt():
    e = json.loads((DIR / "ejemplo_tickets.json").read_text(encoding="utf-8"))
    ce = Contract.from_dict(e["contratos"]["especializado"])
    cg = Contract.from_dict(e["contratos"]["general"])
    err = e["registro_erroneo"]
    assert err["diagnostico_especializado"] == parse(err["mini_especializado"], ce, strict=False).diagnostics()
    assert err["diagnostico_general"] == parse(err["mini_general"], cg, strict=False).diagnostics()
    assert [x["code"] for x in err["diagnostico_especializado"]["errors"]] == ["E10"] and err["lineas_a_regenerar"] == [6]
    assert err["reparacion"]["documento_reparado_identico_al_original"] is True
    cor = e["registro_cortado"]
    d = parse(cor["mini_especializado"], ce, strict=False).diagnostics()
    assert cor["diagnostico_especializado"] == d and d["truncated"] is True and d["missing_records"] >= 1
    with pytest.raises(ValueError):
        json.loads(cor["json_compacto"]["texto"])
    assert cor["json_compacto"]["json_loads"].startswith("JSONDecodeError")


def test_el_ejemplo_versionado_coincide_con_el_que_produce_el_codigo():
    archivado = json.loads((DIR / "ejemplo_tickets.json").read_text(encoding="utf-8"))
    nuevo = json.loads(json.dumps(ejemplo.construir(), ensure_ascii=False))
    for k in ("serie_tickets_por_lote", "equilibrio_tickets"):
        archivado.pop(k, None)
    assert nuevo == archivado


# ------------------------------------------------------------------------- carpetas, README y ADR
@pytest.mark.parametrize("dom", ["tickets", "eventos", "comentarios"])
def test_las_carpetas_de_ejemplos_coinciden_con_lo_que_genera_el_codigo(dom):
    for nombre, contenido in carpeta_ejemplos.archivos_dominio(dom).items():
        esperado = contenido if contenido.endswith("\n") else contenido + "\n"
        real = (carpeta_ejemplos.DESTINO / dom / nombre).read_text(encoding="utf-8")
        assert real == esperado, f"{dom}/{nombre} no coincide"


@pytest.mark.parametrize("dom", ["tickets", "eventos", "comentarios"])
def test_reconstruir_py_funciona_como_programa_sobre_cada_carpeta(dom):
    r = subprocess.run([sys.executable, str(ROOT / "examples" / "optimizacion" / "reconstruir.py"), dom],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "idénticos a datos_originales.json" in r.stdout


def test_el_bloque_de_cifras_del_readme_se_regenera_desde_los_csv():
    readme = ROOT / "experiments" / "optimizacion" / "README.md"
    assert documentos.bloque_en_readme(readme) == documentos.bloque_readme(DIR).rstrip("\n")


def test_el_adr_de_propuesta_no_es_vigente_y_se_regenera_desde_los_csv():
    adr = ROOT / "docs" / "adr" / "0030-propuesta-alias-de-enumeracion-y-diccionarios-por-documento.md"
    texto = adr.read_text(encoding="utf-8")
    assert texto == documentos.adr(DIR)
    assert "Propuesta (no vigente)" in texto and "NO implementada" in texto and "SPEC 1.2" in texto


# ------------------------------------------------------------------------- el ejecutor
def test_el_ejecutor_en_modo_rapido_registra_una_corrida_valida_y_no_evaluable(tmp_path):
    import ejecutar_opt
    destino = ejecutar_opt.correr(tmp_path / "opt-prueba", "opt-prueba-rapida", (1, 5), 12, False, False)
    m = json.loads(destino.read_text(encoding="utf-8"))
    assert ev.validar_corrida(m, tmp_path / "opt-prueba") == []
    assert m["resultado"] == "no_evaluable" and m["estado_ejecucion"] == "parcial"
    assert {"comparacion.csv", "equilibrio.csv", "ejemplo_tickets.json", "fallos_de_equivalencia.json"} <= {p.name for p in (tmp_path / "opt-prueba").iterdir()}

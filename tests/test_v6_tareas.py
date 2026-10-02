"""Pruebas del repositorio de tareas T1-T4 de V6b (evidencia/v6/tareas/).

Comprueban, con minifmt y con jsonschema como oráculos independientes de quien escribió los datos, que las
respuestas congeladas "correctas" validan y las defectuosas fallan exactamente donde deben, que las
variantes A y B de T1 son equivalentes, que el verificador de entregas acepta soluciones correctas y
rechaza las defectuosas, y que lo que recibe el participante no trae la solución.

Los datasets de B, T2, T3 y T4 son sintéticos (redactados por el equipo); no hay datos de participantes.
"""
import hashlib
import importlib.util
import json
import py_compile
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
TAREAS = RAIZ / "evidencia" / "v6" / "tareas"
PART = TAREAS / "participante"
OBS = TAREAS / "observador"

from minifmt import Contract, canonical_equal, parse  # noqa: E402
from minifmt.ai import merge_repair, repair_request  # noqa: E402
from minifmt.errors import MiniValidationError  # noqa: E402


def cargar(nombre, ruta):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nombre] = m
    spec.loader.exec_module(m)
    return m


CT = cargar("construir_tareas", TAREAS / "construir_tareas.py")
VE = cargar("verificar_entrega", TAREAS / "verificar_entrega.py")


def txt(p):
    return Path(p).read_text(encoding="utf-8")


def js(p):
    return json.loads(txt(p))


def errores(texto, contrato):
    """[(código, línea)] con el analizador tolerante; y los registros válidos."""
    try:
        doc = parse(texto, contrato, strict=False)
    except MiniValidationError as e:
        return [(x.code, x.line) for x in e.errors], []
    return [(e.code, e.line) for e in doc.errors], list(doc.records)


# ------------------------------------------------------------------------------------------
# Construcción y manifiesto
# ------------------------------------------------------------------------------------------
def test_el_disco_coincide_con_lo_que_genera_el_constructor():
    generado = CT.construir()
    for ruta, datos in generado.items():
        p = TAREAS / ruta
        assert p.exists(), ruta
        assert p.read_bytes() == datos, f"{ruta} difiere del constructor: ejecuta construir_tareas.py"
    # y no sobran archivos generados a mano dentro de participante/ u observador/
    en_disco = {p.relative_to(TAREAS).as_posix() for d in (PART, OBS) for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    assert en_disco == {r for r in generado if r.startswith(("participante/", "observador/"))}


def test_manifiesto_hashes_y_origen_real():
    man = js(TAREAS / "respuestas_congeladas.json")
    for ruta, sha in man["archivos"].items():
        if ruta == "respuestas_congeladas.json":
            continue
        assert hashlib.sha256((TAREAS / ruta).read_bytes()).hexdigest() == sha, ruta
    # Las respuestas y los contratos de origen siguen siendo los mismos bytes.
    for ruta, sha in man["origen_real"].items():
        assert hashlib.sha256((RAIZ / ruta).read_bytes()).hexdigest() == sha, ruta
    # copias literales
    assert (PART / "T1A_json" / "respuesta.json").read_bytes() == (RAIZ / "examples/mesa-de-ayuda/grabaciones/json/error.json").read_bytes()
    assert (PART / "T1A_mini" / "respuesta.mini").read_bytes() == (RAIZ / "examples/mesa-de-ayuda/grabaciones/mini/error.mini").read_bytes()
    assert (PART / "T1A_json" / "ticket.schema.json").read_bytes() == (RAIZ / "examples/mesa-de-ayuda/ticket.schema.json").read_bytes()
    assert (PART / "T4" / "contrato_origen_cat.json").read_bytes() == (RAIZ / "forks/cat/contract.json").read_bytes()
    # La guía se compara con su fuente congelada, no con la documentación pública mutable.
    guia = man["guia_congelada"]
    assert guia == CT.GUIA_ORIGEN
    fuente = (TAREAS / guia["copia"]).read_bytes()
    assert hashlib.sha256(fuente).hexdigest() == guia["sha256"]
    assert (PART / "guia_mini.md").read_bytes() == fuente
    assert man["suma_topes_min"] == 100 and man["sesion_max_min"] == 120


def test_el_constructor_rechaza_una_guia_congelada_alterada(tmp_path, monkeypatch):
    fuente = tmp_path / CT.GUIA_ORIGEN["copia"]
    fuente.parent.mkdir()
    fuente.write_bytes((PART / "guia_mini.md").read_bytes() + b"\nCambio no autorizado\n")
    monkeypatch.setattr(CT, "AQUI", tmp_path)
    with pytest.raises(ValueError, match="SHA-256 de origen"):
        CT.construir()


def test_topes_del_plan_coinciden_en_todos_los_materiales():
    assert CT.TOPES_MIN == {"T1_json": 30, "T1_mini": 30, "T2": 15, "T3": 10, "T4": 15}
    assert sum(CT.TOPES_MIN.values()) == 100
    assert CT.INTRO_MIN + sum(CT.TOPES_MIN.values()) + CT.CIERRE_MIN == 120 == CT.SESION_MAX_MIN     # no 80
    analizador = cargar("analizar_v6_t", RAIZ / "tools" / "analizar_v6.py")
    assert analizador.TOPES_MIN == CT.TOPES_MIN
    est = {"T1A_json": "30 minutos", "T1A_mini": "30 minutos", "T1B_json": "30 minutos", "T1B_mini": "30 minutos",
           "T2": "15 minutos", "T3": "10 minutos", "T4": "15 minutos"}
    for carpeta, tope in est.items():
        assert tope in txt(PART / carpeta / "enunciado.md").splitlines()[0], carpeta


# ------------------------------------------------------------------------------------------
# T1: variantes A y B, respuestas correctas y defectuosas
# ------------------------------------------------------------------------------------------
def _contrato_de_esquema(esquema_json, prefijo):
    from minifmt.schema import from_json_schema
    return from_json_schema(esquema_json, prefijo)


def test_t1_contratos_son_los_que_genera_from_schema():
    tk = Contract.load(PART / "T1A_mini" / "contrato_tk.json")
    assert tk.to_dict() == _contrato_de_esquema(js(RAIZ / "examples/mesa-de-ayuda/ticket.schema.json"), "tk").to_dict()
    inc = Contract.load(PART / "T1B_mini" / "contrato_inc.json")
    assert inc.to_dict() == _contrato_de_esquema(js(PART / "T1B_json" / "esquema_inc.json"), "inc").to_dict()


@pytest.mark.parametrize("variante,clave,contrato,prefijo,pos", [("A", "tickets", "T1A_mini/contrato_tk.json", "tk", 5),
                                                                 ("B", "incidencias", "T1B_mini/contrato_inc.json", "inc", 7)])
def test_t1_json_y_mini_dicen_lo_mismo_y_fallan_donde_deben(variante, clave, contrato, prefijo, pos):
    jsonschema = pytest.importorskip("jsonschema")
    esquema = js(PART / f"T1{variante}_json" / ("ticket.schema.json" if variante == "A" else "esquema_inc.json"))
    respuesta = js(PART / f"T1{variante}_json" / "respuesta.json")[clave]
    # oráculo 1 (jsonschema, independiente de minifmt): exactamente un registro inválido, en la posición esperada
    val = jsonschema.Draft7Validator(esquema)
    malos = [i for i, r in enumerate(respuesta, 1) if list(val.iter_errors(r))]
    assert malos == [pos]
    # oráculo 2 (minifmt): un solo error E10 en la línea pos+1
    c = Contract.load(PART / f"T1{variante}_mini" / Path(contrato).name)
    errs, validos = errores(txt(PART / f"T1{variante}_mini" / "respuesta.mini"), c)
    assert errs == [("E10", pos + 1)]
    # ambos formatos llevan los mismos registros
    resto = [r for i, r in enumerate(respuesta, 1) if i != pos]
    assert canonical_equal(validos, resto)
    # y coinciden con la referencia del observador
    ref = js(OBS / f"T1{variante}.referencia.json")
    assert canonical_equal(ref["validos"], resto) and ref["rechazados_posiciones"] == [pos]
    # el registro defectuoso es el mismo dato en ambos formatos
    assert len(respuesta) == 10


def test_t1_variantes_a_y_b_son_equivalentes_en_forma_y_dificultad():
    ca = Contract.load(PART / "T1A_mini" / "contrato_tk.json")
    cb = Contract.load(PART / "T1B_mini" / "contrato_inc.json")
    tipos = lambda c: [(f.type, len(f.values or []), f.min, f.max) for f in c.fields]      # noqa: E731
    assert [t[:2] for t in tipos(ca)] == [t[:2] for t in tipos(cb)]              # misma forma: str, enum3, enum4, str, int
    assert [t[0] for t in tipos(cb)] == ["str", "enum", "enum", "str", "int"]
    # mismos nombres de campo distintos: no se puede reutilizar el código de una condición tal cual
    assert {f.name for f in ca.fields}.isdisjoint({f.name for f in cb.fields})
    # misma cantidad de registros, un defecto del mismo código, en posiciones distintas
    assert len(js(PART / "T1A_json" / "respuesta.json")["tickets"]) == len(js(PART / "T1B_json" / "respuesta.json")["incidencias"]) == 10
    ra, rb = js(OBS / "T1A.referencia.json"), js(OBS / "T1B.referencia.json")
    assert ra["codigo_error"] == rb["codigo_error"] == "E10"
    assert ra["rechazados_posiciones"] != rb["rechazados_posiciones"]
    # mismo tamaño aproximado del texto (±15 %) en cada formato
    for fmt, nombre in (("json", "respuesta.json"), ("mini", "respuesta.mini")):
        a = len(txt(PART / f"T1A_{fmt}" / nombre))
        b = len(txt(PART / f"T1B_{fmt}" / nombre))
        assert abs(a - b) / a < 0.15, (fmt, a, b)


def test_t1_enunciados_equivalentes_entre_condiciones():
    """Los enunciados de JSON y .mini solo difieren en lo propio del formato."""
    for v in ("A", "B"):
        j = txt(PART / f"T1{v}_json" / "enunciado.md")
        m = txt(PART / f"T1{v}_mini" / "enunciado.md")
        for frag in ("Qué debe hacer `procesar`", "`validos`", "`rechazados`", "entrega/salida_T1.json", "empezando en 1"):
            assert frag in j and frag in m, (v, frag)
        # mismo número de líneas de instrucciones numeradas
        assert re.findall(r"^\d\. ", j, re.M) == re.findall(r"^\d\. ", m, re.M)


# ------------------------------------------------------------------------------------------
# T2, T3, T4: respuestas congeladas
# ------------------------------------------------------------------------------------------
def test_t2_defectuosa_falla_solo_en_la_linea_8_y_la_corregida_valida():
    c = Contract.load(PART / "T2" / "contrato_tk.json")
    errs, validos = errores(txt(PART / "T2" / "respuesta.mini"), c)
    assert errs == [("E05", 8)]
    assert len(validos) == 11
    ref = js(OBS / "T2.referencia.json")
    assert (ref["codigo_error"], ref["linea_defecto"]) == ("E05", 8)
    ok_errs, ok_recs = errores(txt(OBS / "T2.corregido_esperado.mini"), c)
    assert ok_errs == [] and canonical_equal(ok_recs, ref["registros_esperados"]) and len(ok_recs) == 12
    # los 11 válidos de la respuesta son los mismos de la referencia (salvo el defectuoso)
    sin = [r for i, r in enumerate(ref["registros_esperados"], 1) if i != 7]
    assert canonical_equal(validos, sin)
    # la corrección congelada repara el documento por el camino de la biblioteca
    respuesta = txt(PART / "T2" / "respuesta.mini")
    req = repair_request(respuesta, c, "es")
    assert req.lines == [8]
    fus = merge_repair(respuesta, txt(PART / "T2" / "correccion_modelo.mini"), c, req)
    assert fus.ok and fus.replaced == [8] and fus.notes == []
    assert fus.text.rstrip("\n") == txt(OBS / "T2.corregido_esperado.mini").rstrip("\n")


def test_t3_cortada_recupera_11_y_faltan_4():
    c = Contract.load(PART / "T3" / "contrato_tk.json")
    cortada = txt(PART / "T3" / "respuesta_cortada.mini")
    assert not cortada.endswith("\n")                                   # se corta a mitad de línea
    errs, validos = errores(cortada, c)
    assert errs == [("E05", 13), ("E04", 0)]                            # registro 12 incompleto y recuento distinto
    ref = js(OBS / "T3.referencia.json")
    assert canonical_equal(validos, ref["recuperados"]) and len(validos) == 11
    assert (ref["declarados"], ref["sin_recuperar"], ref["primer_no_recuperado"]) == (15, 4, 12)
    ok_errs, ok_recs = errores(txt(OBS / "T3.completo_esperado.mini"), c)
    assert ok_errs == [] and len(ok_recs) == 15
    assert canonical_equal(ok_recs[:11], ref["recuperados"])
    # trampa deliberada: el analizador cuenta 12 líneas de registro (la cortada incluida), no 11 recuperables
    doc = parse(cortada, c, strict=False)
    assert len(doc.records) == 11 and ref["sin_recuperar"] == 15 - len(doc.records)


def test_t4_solucion_acepta_el_positivo_y_rechaza_el_negativo_en_e13():
    sol = Contract.load(OBS / "T4.contrato_solucion.json")
    errs, recs = errores(txt(PART / "T4" / "caso_positivo.mini"), sol)
    ref = js(OBS / "T4.referencia.json")
    assert errs == [] and canonical_equal(recs, ref["registros_positivo"])
    errs, _ = errores(txt(PART / "T4" / "caso_negativo.mini"), sol)
    assert errs == [("E13", 3)] and (ref["negativo"]["codigo_error"], ref["negativo"]["linea"]) == ("E13", 3)
    assert sol.prefix == "chg" and [f.name for f in sol.fields] == ref["campos"]
    # el punto de partida es de otro dominio y no acepta el caso positivo tal cual
    cat = Contract.load(PART / "T4" / "contrato_origen_cat.json")
    assert cat.prefix == "cat"
    errs_cat, _ = errores(txt(PART / "T4" / "caso_positivo.mini"), cat)
    assert errs_cat                                                     # el contrato de origen no sirve sin adaptarlo
    # la tabla del enunciado menciona cada campo del contrato solución
    enun = txt(PART / "T4" / "enunciado.md")
    for nombre in ref["campos"]:
        assert f"`{nombre}`" in enun


# ------------------------------------------------------------------------------------------
# Verificador de entregas: soluciones correctas pasan, defectuosas fallan
# ------------------------------------------------------------------------------------------
def escribe(d, nombre, obj):
    (d / nombre).parent.mkdir(parents=True, exist_ok=True)
    (d / nombre).write_text(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def veredicto(tarea, carpeta):
    r = VE.verificar(tarea, carpeta)
    return r["cumple"], {c["id"]: c["cumple"] for c in r["criterios"]}


@pytest.fixture
def soluciones():
    return {"json": cargar("sol_t1_json", OBS / "soluciones" / "T1_json.py"), "mini": cargar("sol_t1_mini", OBS / "soluciones" / "T1_mini.py")}


@pytest.mark.parametrize("variante,clave", [("A", "tickets"), ("B", "incidencias")])
def test_verificador_acepta_las_soluciones_de_referencia_de_t1(tmp_path, soluciones, variante, clave):
    pytest.importorskip("jsonschema")
    # condición JSON
    esquema = js(PART / f"T1{variante}_json" / ("ticket.schema.json" if variante == "A" else "esquema_inc.json"))
    sal = soluciones["json"].procesar(txt(PART / f"T1{variante}_json" / "respuesta.json"), esquema, clave)
    escribe(tmp_path / "j", "salida_T1.json", sal)
    assert veredicto(f"T1{variante}", tmp_path / "j") == (True, {"forma": True, "validos_identicos": True, "rechazados_correctos": True})
    # condición .mini
    c = Contract.load(PART / f"T1{variante}_mini" / ("contrato_tk.json" if variante == "A" else "contrato_inc.json"))
    sal = soluciones["mini"].procesar(txt(PART / f"T1{variante}_mini" / "respuesta.mini"), c)
    escribe(tmp_path / "m", "salida_T1.json", sal)
    assert veredicto(f"T1{variante}", tmp_path / "m")[0] is True


def _ref_t1(v):
    return js(OBS / f"T1{v}.referencia.json")


@pytest.mark.parametrize("v", ["A", "B"])
def test_verificador_rechaza_entregas_t1_defectuosas(tmp_path, v):
    ref = _ref_t1(v)
    bien = {"validos": ref["validos"], "rechazados": [{"posicion": ref["rechazados_posiciones"][0], "motivo": "x"}]}
    ok = lambda s: (escribe(tmp_path / s[0], "salida_T1.json", s[1]), veredicto(f"T1{v}", tmp_path / s[0]))[1]      # noqa: E731
    assert ok(("ok", bien))[0] is True
    # 1) incluye el registro inválido como si fuera bueno (no detecta el fallo)
    todos = [dict(r) for r in ref["validos"]]
    assert ok(("c1", {"validos": todos, "rechazados": []}))[1]["rechazados_correctos"] is False
    # 2) rechaza en la posición equivocada
    assert ok(("c2", {**bien, "rechazados": [{"posicion": 1, "motivo": "x"}]}))[1]["rechazados_correctos"] is False
    # 3) tumba a los válidos (devuelve solo una parte)
    assert ok(("c3", {**bien, "validos": ref["validos"][:-1]}))[1]["validos_identicos"] is False
    # 4) altera un valor válido (coerción de un entero a cadena)
    alt = json.loads(json.dumps(ref["validos"]))
    clave_int = next(k for k, val in alt[0].items() if isinstance(val, int))
    alt[0][clave_int] = str(alt[0][clave_int])
    assert ok(("c4", {**bien, "validos": alt}))[1]["validos_identicos"] is False
    # 5) cambia el orden
    assert ok(("c5", {**bien, "validos": list(reversed(ref["validos"]))}))[1]["validos_identicos"] is False
    # 6) rechaza de más
    assert ok(("c6", {**bien, "rechazados": bien["rechazados"] + [{"posicion": 3, "motivo": "y"}]}))[1]["rechazados_correctos"] is False
    # 7) posiciones duplicadas
    assert ok(("c7", {**bien, "rechazados": bien["rechazados"] * 2}))[1]["rechazados_correctos"] is False
    # 8) forma incorrecta y archivo ausente
    assert ok(("c8", {"validos": ref["validos"]}))[1]["forma"] is False
    assert ok(("c9", {"validos": ref["validos"], "rechazados": [{"posicion": "5", "motivo": "x"}]}))[1]["forma"] is False
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert veredicto(f"T1{v}", vacio)[0] is False
    escribe(tmp_path / "roto", "salida_T1.json", "{no es json")
    assert veredicto(f"T1{v}", tmp_path / "roto")[0] is False


def test_verificador_t2(tmp_path):
    ok_txt = txt(OBS / "T2.corregido_esperado.mini")
    bien = tmp_path / "bien"
    escribe(bien, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    escribe(bien, "T2_corregido.mini", ok_txt)
    assert veredicto("T2", bien) == (True, {"diagnostico": True, "corregido_valida": True, "registros_esperados": True, "otros_registros_intactos": True})
    # diagnóstico con código o línea equivocados
    for i, diag in enumerate([{"codigo_error": "E10", "linea": 8}, {"codigo_error": "E05", "linea": 7}, {"codigo_error": "E05", "linea": "8"}]):
        d = tmp_path / f"d{i}"
        escribe(d, "T2_diagnostico.json", diag)
        escribe(d, "T2_corregido.mini", ok_txt)
        assert veredicto("T2", d)[1]["diagnostico"] is False
    # sin reparar: el defecto sigue
    d = tmp_path / "sin"
    escribe(d, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    escribe(d, "T2_corregido.mini", txt(PART / "T2" / "respuesta.mini"))
    assert veredicto("T2", d)[1]["corregido_valida"] is False
    # "reparación" que borra el registro defectuoso: valida pero pierde datos
    lineas = ok_txt.rstrip("\n").split("\n")
    d = tmp_path / "borra"
    escribe(d, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    escribe(d, "T2_corregido.mini", "\n".join([lineas[0].replace("n=12", "n=11")] + lineas[1:7] + lineas[8:]) + "\n")
    v = veredicto("T2", d)
    assert v[0] is False and v[1]["corregido_valida"] is True and v[1]["registros_esperados"] is False
    # repara pero toca otro registro válido
    d = tmp_path / "toca"
    escribe(d, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    escribe(d, "T2_corregido.mini", ok_txt.replace("Doble cargo", "Cobro doble"))
    v = veredicto("T2", d)
    assert v[0] is False and v[1]["otros_registros_intactos"] is False
    # repara inventando otro valor en el defectuoso
    d = tmp_path / "inventa"
    escribe(d, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    escribe(d, "T2_corregido.mini", ok_txt.replace("A\\|B", "A y B"))
    v = veredicto("T2", d)
    assert v[0] is False and v[1]["registros_esperados"] is False
    # falta un archivo
    d = tmp_path / "falta"
    escribe(d, "T2_diagnostico.json", {"codigo_error": "E05", "linea": 8})
    assert veredicto("T2", d)[0] is False


def test_verificador_t3(tmp_path):
    ref = js(OBS / "T3.referencia.json")
    bien = {"recuperados": ref["recuperados"], "sin_recuperar": 4, "primer_no_recuperado": 12}
    d = tmp_path / "b"
    escribe(d, "T3_recuperado.json", bien)
    assert veredicto("T3", d) == (True, {"forma": True, "recuperados": True, "sin_recuperar": True, "primer_no_recuperado": True})
    casos = {
        "cortado_cuenta": ({**bien, "recuperados": ref["recuperados"] + [{"id": "T-3312", "prioridad": "media", "categoria": "error", "resumen": "El corrector ortográfico subraya palab", "horas": 2}]}, "recuperados"),
        "faltan_menos": ({**bien, "recuperados": ref["recuperados"][:10]}, "recuperados"),
        "cuenta_3": ({**bien, "sin_recuperar": 3}, "sin_recuperar"),          # error típico: usar missing_records del diagnóstico
        "cuenta_4_cadena": ({**bien, "sin_recuperar": "4"}, "sin_recuperar"),
        "primero_13": ({**bien, "primer_no_recuperado": 13}, "primer_no_recuperado"),
    }
    for nombre, (obj, criterio) in casos.items():
        d = tmp_path / nombre
        escribe(d, "T3_recuperado.json", obj)
        v = veredicto("T3", d)
        assert v[0] is False and v[1][criterio] is False, nombre
    d = tmp_path / "forma"
    escribe(d, "T3_recuperado.json", [1, 2])
    assert veredicto("T3", d)[1]["forma"] is False


def test_verificador_t4(tmp_path):
    sol = js(OBS / "T4.contrato_solucion.json")
    d = tmp_path / "ok"
    escribe(d, "contrato_cambios.json", sol)
    assert veredicto("T4", d) == (True, {"contrato_valido": True, "prefijo": True, "campos": True, "positivo_acepta": True,
                                          "positivo_canonico": True, "negativo_rechaza": True})

    def variante(nombre, mut):
        c = json.loads(json.dumps(sol))
        mut(c)
        dd = tmp_path / nombre
        escribe(dd, "contrato_cambios.json", c)
        return veredicto("T4", dd)

    def sin_rango(c):
        for f in c["core"]:
            if f["name"] == "ventana_min":
                f.pop("max")
    v = variante("sin_max", sin_rango)
    assert v[0] is False and v[1]["negativo_rechaza"] is False and v[1]["positivo_acepta"] is True       # el contrato "laxo" no rechaza
    v = variante("prefijo", lambda c: c.update(prefix="cat"))
    assert v[0] is False and v[1]["prefijo"] is False
    v = variante("campo_nombre", lambda c: c["core"][0].update(name="id"))
    assert v[1]["campos"] is False and v[1]["positivo_canonico"] is False
    v = variante("enum_corto", lambda c: c["core"][2].update(values=["estandar", "normal"]))
    assert v[0] is False and v[1]["positivo_acepta"] is False                                               # rechaza lo que debía aceptar
    def todo_str(c):
        for f in c["core"]:
            if f["name"] in ("ventana_min", "tipo", "riesgo"):
                f["type"] = "str"
                for k in ("values", "min", "max"):
                    f.pop(k, None)
    v = variante("todo_str", todo_str)
    assert v[0] is False and v[1]["negativo_rechaza"] is False
    v = variante("cat_sin_adaptar", lambda c: (c.clear(), c.update(js(PART / "T4" / "contrato_origen_cat.json"))))
    assert v[0] is False
    # contrato roto
    d = tmp_path / "roto"
    escribe(d, "contrato_cambios.json", {"prefix": "chg", "core": [{"name": "x", "type": "enum"}]})
    assert veredicto("T4", d)[0] is False
    d = tmp_path / "no_json"
    escribe(d, "contrato_cambios.json", "no es json")
    assert veredicto("T4", d)[0] is False


def test_verificador_cli_codigos_de_salida(tmp_path):
    import subprocess
    ref = _ref_t1("A")
    d = tmp_path / "e"
    escribe(d, "salida_T1.json", {"validos": ref["validos"], "rechazados": [{"posicion": 5, "motivo": "x"}]})
    env = {"PYTHONPATH": str(RAIZ / "src"), "PATH": __import__("os").environ.get("PATH", ""), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")}
    def corre(*a):
        return subprocess.run([sys.executable, str(TAREAS / "verificar_entrega.py"), *map(str, a)], capture_output=True, text=True, encoding="utf-8", env=env)
    r = corre("T1A", d)
    assert r.returncode == 0 and json.loads(r.stdout)["cumple"] is True
    escribe(d, "salida_T1.json", {"validos": [], "rechazados": []})
    assert corre("T1A", d).returncode == 1
    assert corre("T1A", tmp_path / "no_hay").returncode == 2
    assert corre("T9", d).returncode == 2
    assert corre().returncode == 2


# ------------------------------------------------------------------------------------------
# Lo que recibe el participante
# ------------------------------------------------------------------------------------------
def test_el_paquete_del_participante_no_trae_la_solucion():
    nombres = [p.name.lower() for p in PART.rglob("*") if p.is_file()]
    assert not any(("referencia" in n or "solucion" in n or "esperado" in n or "corregido" in n) for n in nombres)
    todo = "\n".join(txt(p) for p in PART.rglob("*") if p.is_file() and p.suffix in (".md", ".py") and p.name != "guia_mini.md")
    assert "observador/" not in todo and "verificar_entrega" not in todo
    # el contrato solución de T4 (prefijo chg, rango 15-480) no viaja dentro del paquete
    for p in PART.rglob("*.json"):
        d = js(p)
        assert not (isinstance(d, dict) and d.get("prefix") == "chg"), p
    # T2: la corrección congelada trae solo la línea del modelo, no el documento completo
    assert len(txt(PART / "T2" / "correccion_modelo.mini").strip().splitlines()) == 2


def test_enunciados_piden_el_archivo_de_entrega_que_el_verificador_lee():
    assert "entrega/salida_T1.json" in txt(PART / "T1A_json" / "enunciado.md")
    for nombre in VE.ARCHIVOS["T2"]:
        assert nombre in txt(PART / "T2" / "enunciado.md")
    for nombre in VE.ARCHIVOS["T3"] + VE.ARCHIVOS["T4"]:
        assert nombre in txt(PART / ("T3" if nombre.startswith("T3") else "T4") / "enunciado.md")
    # el verificador y los enunciados hablan de las mismas claves
    for clave in ("codigo_error", "linea"):
        assert clave in txt(PART / "T2" / "enunciado.md")
    for clave in ("recuperados", "sin_recuperar", "primer_no_recuperado"):
        assert clave in txt(PART / "T3" / "enunciado.md")


def test_stubs_compilan_y_fallan_hasta_que_se_completan(tmp_path):
    for carpeta in ("T1A_json", "T1A_mini", "T1B_json", "T1B_mini"):
        ruta = PART / carpeta / "cliente.py"
        py_compile.compile(str(ruta), cfile=str(tmp_path / f"{carpeta}.pyc"), doraise=True)
        m = cargar(f"stub_{carpeta}", ruta)
        with pytest.raises(NotImplementedError):
            m.procesar("")


def test_materiales_de_tareas_sin_emojis_ni_dingbats():
    malos = []
    for p in TAREAS.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".py", ".json", ".mini") and "__pycache__" not in p.parts and p.name != "guia_mini.md":
            m = re.findall("[←-⇿☀-➿⬀-⯿\U0001f000-\U0001faff]", txt(p))
            if m:
                malos.append((p.name, m))
    assert malos == []


# ------------------------------------------------------------------------------------------
# Verificación cruzada con el motor JavaScript (js/mini.js): mismas respuestas, mismos errores
# ------------------------------------------------------------------------------------------
def test_respuestas_congeladas_dan_los_mismos_errores_en_python_y_en_javascript():
    import shutil
    import subprocess
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node no está instalado")
    casos = [
        ("T1A_mini/contrato_tk.json", "T1A_mini/respuesta.mini"), ("T1B_mini/contrato_inc.json", "T1B_mini/respuesta.mini"),
        ("T2/contrato_tk.json", "T2/respuesta.mini"), ("T3/contrato_tk.json", "T3/respuesta_cortada.mini"),
    ]
    extra = [(PART / "T2" / "contrato_tk.json", OBS / "T2.corregido_esperado.mini"),
             (PART / "T3" / "contrato_tk.json", OBS / "T3.completo_esperado.mini"),
             (OBS / "T4.contrato_solucion.json", PART / "T4" / "caso_positivo.mini"),
             (OBS / "T4.contrato_solucion.json", PART / "T4" / "caso_negativo.mini")]
    pares = [(PART / c, PART / r) for c, r in casos] + extra
    js_code = """
    const M = require(process.argv[1]); const fs = require('fs');
    const pares = JSON.parse(fs.readFileSync(0, 'utf8'));
    const out = pares.map(([c, r]) => {
      const con = M.normalizeContract(JSON.parse(fs.readFileSync(c, 'utf8')));
      const d = M.parse(fs.readFileSync(r, 'utf8'), con, {strict: false});
      return [d.errors.map(e => [e.code, e.line]), d.records.length];
    });
    process.stdout.write(JSON.stringify(out));
    """
    r = subprocess.run([node, "-e", js_code, str(RAIZ / "js" / "mini.js")], input=json.dumps([[str(a), str(b)] for a, b in pares]),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    desde_js = json.loads(r.stdout)
    for (c, m), (errs_js, n_js) in zip(pares, desde_js):
        errs_py, recs_py = errores(txt(m), Contract.load(c))
        assert [list(e) for e in errs_py] == errs_js, (m.name, errs_py, errs_js)
        assert len(recs_py) == n_js, m.name

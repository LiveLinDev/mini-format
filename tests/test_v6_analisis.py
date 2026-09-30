"""Pruebas de tools/analizar_v6.py (análisis de V6b y contrabalanceo).

Los datos son FIXTURES de prueba (evidencia/v6/fixtures_de_prueba/): no son datos de participantes.
Los valores de referencia de SUS, medianas, cuantiles y tasas están calculados a mano (ver los
comentarios) o con ``statistics``/``scipy`` como oráculo independiente; ninguno sale del código bajo prueba.
"""
import csv
import importlib.util
import json
import math
import random
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIX = RAIZ / "evidencia" / "v6" / "fixtures_de_prueba"
SCRIPT = RAIZ / "tools" / "analizar_v6.py"


def _mod():
    spec = importlib.util.spec_from_file_location("analizar_v6", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules["analizar_v6"] = m
    spec.loader.exec_module(m)
    return m


A = _mod()


def cli(*args, cwd=None):
    r = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8", cwd=cwd or RAIZ)
    return r.returncode, r.stdout, r.stderr


def sesion(codigo, tareas=None, sus=None, tipo="estudio", valido=True, tipo_datos="participantes"):
    """Sesión mínima en la forma JSON de la herramienta; ``tareas`` = {tarea: (resultado, segundos, ayudas)}."""
    ts = {}
    for t, v in (tareas or {}).items():
        res, seg = v[0], v[1]
        ay = v[2] if len(v) > 2 else (1 if res == "completa_con_ayuda" else 0)
        ts[t] = {"tope_s": A.TOPES_S.get(t, 60), "resultado": res, "segundos_activos": seg, "ayudas": [{"t_s": 1, "nota": ""}] * ay}
    return {"tipo_datos": tipo_datos, "participante": {"codigo": codigo, "tipo": tipo, "valido": valido},
            "tareas": ts, "sus": {"respuestas": sus}}


def norm(*ss):
    return [A.normalizar_sesion(s) for s in ss]


S, C, TA, NC, AB = "completa_sin_ayuda", "completa_con_ayuda", "tiempo_agotado", "no_completa", "abandono"


# ------------------------------------------------------------------------------------------
# SUS
# ------------------------------------------------------------------------------------------
# Cada vector se calculó a mano: impares (r-1), pares (5-r), suma x 2,5.
SUS_A_MANO = [
    ([3] * 10, 50.0),                                             # 5x2 + 5x2 = 20 -> 50
    ([5, 1] * 5, 100.0),                                          # 5x4 + 5x4 = 40 -> 100
    ([1, 5] * 5, 0.0),
    ([4, 2] * 5, 75.0),                                           # 5x3 + 5x3 = 30 -> 75
    ([5, 1, 4, 2, 5, 1, 4, 2, 5, 2], 87.5),                       # impares 4+3+4+3+4=18; pares 4+3+4+3+3=17 -> 35 -> 87,5
    ([4, 3, 4, 2, 3, 2, 4, 1, 5, 3], 72.5),                       # impares 3+3+2+3+4=15; pares 2+3+3+4+2=14 -> 29 -> 72,5
    ([2, 4, 3, 3, 2, 4, 3, 3, 2, 4], 35.0),                       # impares 1+2+1+2+1=7; pares 1+2+1+2+1=7 -> 14 -> 35
    ([5, 3, 3, 3, 3, 3, 3, 3, 3, 3], 55.0),                       # solo el ítem 1 sube: 4+8=12 impares; 10 pares -> 22 -> 55
    ([3, 5, 3, 3, 3, 3, 3, 3, 3, 3], 45.0),                       # solo el ítem 2 (par) en 5: impares 10; pares 0+8=8 -> 18 -> 45
]


@pytest.mark.parametrize("resp,esperado", SUS_A_MANO)
def test_sus_referencia_a_mano(resp, esperado):
    assert A.puntuar_sus(resp) == (esperado, None)


@pytest.mark.parametrize("resp", [
    [3] * 9, [3] * 11, [None] + [3] * 9, [""] + [3] * 9, [6] + [3] * 9, [0] + [3] * 9, [3.5] + [3] * 9,
    [True] + [3] * 9, ["a"] + [3] * 9, None,
])
def test_sus_incompleto_o_invalido_no_se_puntua(resp):
    v, motivo = A.puntuar_sus(resp)
    assert v is None and motivo


def test_sus_paridad_de_items_es_la_que_dice_brooke():
    # si se invirtiera la paridad, este vector daría otra cosa: 5 en impares y 1 en pares da el máximo
    assert A.puntuar_sus([5, 1, 5, 1, 5, 1, 5, 1, 5, 1])[0] == 100.0
    assert A.puntuar_sus([1, 5, 1, 5, 1, 5, 1, 5, 1, 5])[0] == 0.0


def test_sus_resumen_media_ic_y_decision():
    est = norm(*[sesion(f"EST-{i:02d}", sus=v) for i, (v, _) in enumerate(SUS_A_MANO[:8], 1)])
    r = A.analizar_sus(est)
    puntos = [p for _, p in SUS_A_MANO[:8]]
    assert r["n_puntuados"] == 8
    assert r["media"] == pytest.approx(statistics.mean(puntos))
    assert r["desv_muestral"] == pytest.approx(statistics.stdev(puntos))
    scipy_stats = pytest.importorskip("scipy.stats")
    lo, hi = scipy_stats.t.interval(0.95, 7, loc=statistics.mean(puntos), scale=statistics.stdev(puntos) / math.sqrt(8))
    assert r["ic95"] == pytest.approx([lo, hi], abs=0.02)        # la tabla t tiene 3 decimales
    assert r["media"] == pytest.approx(59.375)                   # (50+100+0+75+87,5+72,5+35+55)/8 = 475/8
    assert r["decision"] == "meta_no_observada"                  # por debajo de 70


def test_sus_decision_segun_n_y_media():
    alto = [4, 2] * 5                                            # 75
    assert A.analizar_sus(norm(*[sesion(f"EST-{i:02d}", sus=alto) for i in range(1, 8)]))["decision"] == "muestra_insuficiente"
    assert A.analizar_sus(norm(*[sesion(f"EST-{i:02d}", sus=alto) for i in range(1, 9)]))["decision"] == "meta_observada"
    # una media de exactamente 70 cuenta como meta (>= 70)
    casi = [4, 2, 4, 2, 4, 2, 4, 2, 3, 2]                        # impares 3+3+3+3+2=14; pares 3x5=15 -> 29 -> 72,5
    assert A.puntuar_sus(casi)[0] == 72.5
    setenta = [4, 2, 4, 2, 4, 2, 4, 2, 3, 3]                     # impares 14; pares 3+3+3+3+2=14 -> 28 -> 70
    assert A.puntuar_sus(setenta)[0] == 70.0
    r = A.analizar_sus(norm(*[sesion(f"EST-{i:02d}", sus=setenta) for i in range(1, 9)]))
    assert r["media"] == 70.0 and r["decision"] == "meta_observada"
    assert A.analizar_sus([])["decision"] == "sin_datos"


def test_sus_formulario_incompleto_no_entra_en_la_media():
    ss = [sesion(f"EST-{i:02d}", sus=[4, 2] * 5) for i in range(1, 9)]
    ss.append(sesion("EST-09", sus=[5, 1, 5, 1, 5, 1, 5, 1, 5, None]))
    r = A.analizar_sus(norm(*ss))
    assert r["n_estudio"] == 9 and r["n_puntuados"] == 8 and r["media"] == 75.0
    fila = [f for f in r["participantes"] if f["codigo"] == "EST-09"][0]
    assert fila["sus"] is None and "ítem 10" in fila["motivo_no_puntuado"]


def test_t_critico_tabla_coincide_con_scipy():
    st = pytest.importorskip("scipy.stats")
    for gl in range(1, 31):
        assert A.t_critico(gl) == pytest.approx(st.t.ppf(0.975, gl), abs=0.002)
    assert A.t_critico(35) == pytest.approx(st.t.ppf(0.975, 35), abs=0.02)


# ------------------------------------------------------------------------------------------
# Cuantiles y censura
# ------------------------------------------------------------------------------------------
def test_cuantil_sin_censura_coincide_con_statistics_tipo_7():
    rnd = random.Random(11)
    for _ in range(300):
        n = rnd.randint(2, 15)
        xs = [round(rnd.uniform(1, 30), 1) for _ in range(n)]
        q = statistics.quantiles(xs, n=4, method="inclusive")      # tipo 7 (lineal, inclusivo)
        for p, ref in zip((0.25, 0.5, 0.75), q):
            v, det = A.cuantil_censurado(xs, p)
            assert det and v == pytest.approx(ref)


def test_cuantil_censurado_casos_a_mano():
    # [1,2,3,None]: mediana = (2+3)/2 = 2,5, determinada
    assert A.cuantil_censurado([1, 2, 3, None], 0.5) == (2.5, True)
    # [1,2,None,None]: los dos centrales son 2 y censurado -> indeterminada
    assert A.cuantil_censurado([1, 2, None, None], 0.5) == (None, False)
    # [1,None,None]: mediana = la censurada
    assert A.cuantil_censurado([1, None, None], 0.5) == (None, False)
    # n impar con mediana observada aunque haya censuradas por encima
    assert A.cuantil_censurado([5, 6, 7, None, None], 0.5) == (7, True)
    # Q3 de [1,2,3,4,None]: posición 3 -> 4, determinado; Q3 de [1,2,3,None,None]: posición 3 -> censurada
    assert A.cuantil_censurado([1, 2, 3, 4, None], 0.75) == (4, True)
    assert A.cuantil_censurado([1, 2, 3, None, None], 0.75) == (None, False)
    # el orden de entrada no importa
    assert A.cuantil_censurado([None, 3, 1, None, 2], 0.25) == (2, True)
    assert A.cuantil_censurado([], 0.5) == (None, False)


def _t1_mini(tiempos_min):
    """Sesiones con T1 .mini dado en minutos; ``None`` = tiempo agotado."""
    return norm(*[sesion(f"EST-{i:02d}", tareas={"T1_mini": (TA, None) if m is None else (S, m * 60)})
                  for i, m in enumerate(tiempos_min, 1)])


def test_censura_no_se_trunca_ni_se_descarta():
    # 8 participantes: 4 terminan (10,12,14,16 min) y 4 agotan el tiempo.
    est = _t1_mini([10, 12, 14, 16, None, None, None, None])
    r = A.analizar_t1(est)["T1_mini"]
    assert r["n"] == 8 and r["n_logradas"] == 4 and r["n_censuradas"] == 4
    assert r["mediana_min"] is None and r["mediana_determinada"] is False
    # cota inferior: lo no logrado vale al menos el tope (30): (16+30)/2 = 23
    assert r["mediana_cota_inferior_min"] == 23.0
    assert A.analizar_t1(est)["meta_mediana_mini"]["estado"] == "no_demostrada_por_censura"
    # lo que NO se hace: truncar a 30 (mediana 23, parecería que cumple) ni descartar (mediana 13)
    truncado = statistics.median([10, 12, 14, 16, 30, 30, 30, 30])
    descartado = statistics.median([10, 12, 14, 16])
    assert truncado == 23 and descartado == 13
    assert r["mediana_min"] not in (truncado, descartado)


def test_mediana_determinada_con_minoria_censurada_y_meta():
    est = _t1_mini([10, 12, 14, 16, 18, None, None, None])      # mediana = (16+18)/2 = 17
    t = A.analizar_t1(est)
    assert t["T1_mini"]["mediana_min"] == 17.0 and t["T1_mini"]["mediana_determinada"]
    assert t["meta_mediana_mini"]["estado"] == "meta_observada"
    # mediana observada pero por encima de 30 no puede darse (el tope es 30); con 30,0 exactos cuenta como <= 30
    est2 = _t1_mini([30, 30, 30, 30, 30, 30, 30, 30])
    assert A.analizar_t1(est2)["meta_mediana_mini"]["estado"] == "meta_observada"
    # muestra insuficiente y sin datos
    assert A.analizar_t1(_t1_mini([10, 12, 14]))["meta_mediana_mini"]["estado"] == "muestra_insuficiente"
    assert A.analizar_t1([])["meta_mediana_mini"]["estado"] == "sin_datos"


def test_no_logradas_cuentan_como_censuradas_sea_cual_sea_el_motivo():
    ss = [sesion(f"EST-{i:02d}", tareas={"T1_mini": v}) for i, v in
          enumerate([(S, 600), (S, 700), (S, 800), (TA, None), (NC, None), (AB, None), (C, 900), (S, 1000)], 1)]
    r = A.analizar_t1(norm(*ss))["T1_mini"]
    assert r["n_logradas"] == 5 and r["n_censuradas"] == 3                 # no completa y abandono no son éxito
    assert r["mediana_min"] == pytest.approx((900 + 1000) / 2 / 60)        # 8 valores: centrales 4.º y 5.º, ambos observados
    assert r["q3_min"] is None and r["q3_determinado"] is False            # Q3 (posición 5,25) cae entre censuradas


def test_sensibilidad_ayuda_cuenta_como_fallo():
    ss = [sesion(f"EST-{i:02d}", tareas={"T1_mini": v}) for i, v in
          enumerate([(S, 600), (C, 700), (C, 800), (S, 900), (S, 1000)], 1)]
    r = A.analizar_t1(norm(*ss))["T1_mini"]
    assert r["n_censuradas"] == 0 and r["mediana_min"] == 800 / 60
    assert r["sensibilidad_ayuda_cuenta_como_fallo"]["n_censuradas"] == 2


def test_diferencias_pareadas_solo_entre_logradas():
    ss = [sesion("EST-01", tareas={"T1_json": (S, 1200), "T1_mini": (S, 720)}),      # -8
          sesion("EST-02", tareas={"T1_json": (S, 1800), "T1_mini": (S, 1110)}),     # -11,5
          sesion("EST-03", tareas={"T1_json": (TA, None), "T1_mini": (S, 600)}),     # no se imputa
          sesion("EST-04", tareas={"T1_json": (S, 1620), "T1_mini": (S, 1770)})]     # +2,5
    d = A.analizar_t1(norm(*ss))["diferencias_pareadas"]
    assert d["n_pares"] == 3 and d["n_pares_con_censura_excluidos_de_este_calculo"] == 1
    assert d["mediana_diferencia_min"] == -8.0 and d["minimo"] == -11.5 and d["maximo"] == 2.5


# ------------------------------------------------------------------------------------------
# Tasa de éxito
# ------------------------------------------------------------------------------------------
def test_wilson_referencias_conocidas():
    lo, hi = A.wilson(5, 10)
    assert (lo, hi) == pytest.approx((0.2366, 0.7634), abs=1e-3)
    lo, hi = A.wilson(0, 10)
    assert (lo, hi) == pytest.approx((0.0, 0.2775), abs=1e-3)
    lo, hi = A.wilson(10, 10)
    assert (lo, hi) == pytest.approx((0.7225, 1.0), abs=1e-3)
    assert A.wilson(0, 0) is None


def test_exito_por_tarea_y_denominadores_explicitos():
    ss = [sesion("EST-01", tareas={"T2": (S, 500), "T3": (S, 300)}),
          sesion("EST-02", tareas={"T2": (C, 700), "T3": (TA, None)}),
          sesion("EST-03", tareas={"T2": (NC, None)}),                        # T3 sin registrar
          sesion("EST-04", tareas={"T2": (AB, None), "T3": (S, 200)})]
    r = A.analizar_exito(norm(*ss))
    t2, t3 = r["por_tarea"]["T2"], r["por_tarea"]["T3"]
    assert (t2["n_intentos"], t2["logradas"], t2["sin_ayuda"], t2["sin_registro"]) == (4, 2, 1, 0)
    assert (t3["n_intentos"], t3["logradas"], t3["sin_ayuda"], t3["sin_registro"]) == (3, 2, 2, 1)
    assert t2["tasa_exito"] == 0.5 and t3["tasa_sin_ayuda"] == pytest.approx(2 / 3)
    assert r["por_tarea"]["T4"]["n_intentos"] == 0 and r["por_tarea"]["T4"]["tasa_exito"] is None
    g = r["global"]
    assert (g["n_intentos"], g["logradas"], g["sin_ayuda"]) == (7, 4, 3)       # un intento sin registro NO cuenta como éxito ni fallo
    assert g["tasa_sin_ayuda"] == pytest.approx(3 / 7) and g["meta_estado"] == "meta_no_observada"


def test_exito_meta_80_por_ciento():
    ss = [sesion(f"EST-{i:02d}", tareas={"T2": (S, 500)}) for i in range(1, 5)] + [sesion("EST-05", tareas={"T2": (C, 500)})]
    g = A.analizar_exito(norm(*ss))["global"]
    assert g["tasa_sin_ayuda"] == 0.8 and g["meta_estado"] == "meta_observada"      # 4/5 = 80 %: >= 80 %


# ------------------------------------------------------------------------------------------
# Pilotos, exclusiones y fixtures completos
# ------------------------------------------------------------------------------------------
def test_pilotos_e_invalidos_no_entran_en_las_cifras():
    sesiones = A.cargar_sesiones([FIX / "sesiones_fixture.json"])
    r = A.resumen(sesiones)
    assert r["exclusiones"]["pilotos_excluidos"] == ["PIL-01", "PIL-02"] and r["exclusiones"]["n_pilotos_excluidos"] == 2
    assert [x["codigo"] for x in r["exclusiones"]["invalidos_excluidos"]] == ["EST-10"]
    assert r["n_validos_estudio"] == 9
    # los pilotos y el inválido traen T1 de 1 min y SUS 100: si entraran, la media de SUS sería otra
    assert r["sus"]["maximo"] == 100.0 and r["sus"]["media"] == 61.875
    assert r["t1"]["T1_mini"]["minimo_logrado_min"] == 8.0           # no 1,0 (los pilotos)


def test_solo_pilotos_no_da_estudio():
    ss = norm(sesion("PIL-01", tareas={"T1_mini": (S, 60)}, sus=[5, 1] * 5, tipo="piloto"),
              sesion("PIL-02", tareas={"T1_mini": (S, 60)}, sus=[5, 1] * 5, tipo="piloto"))
    r = A.resumen(ss)
    assert r["n_validos_estudio"] == 0 and r["muestra_suficiente"] is False
    assert r["sus"]["decision"] == "sin_datos" and r["t1"]["meta_mediana_mini"]["estado"] == "sin_datos"
    assert r["todas_las_metas_observadas"] is False


def test_fixture_hecho_a_mano_resumen_completo():
    """Valores calculados a mano sobre evidencia/v6/fixtures_de_prueba (9 sesiones de estudio)."""
    r = A.resumen(A.cargar_sesiones([FIX / "sesiones_fixture.json"]))
    assert r["es_fixture"] is True and any("FIXTURE" in a for a in r["avisos"])
    # SUS: 75, 50, 100, 0, 87,5, 72,5, 35, (incompleto), 75 -> 8 puntuados, suma 495 -> 61,875
    assert r["sus"]["n_puntuados"] == 8 and r["sus"]["media"] == pytest.approx(61.875)
    assert r["sus"]["decision"] == "meta_no_observada"
    # T1 .mini (min): 12, 18,5, 25 (con ayuda), 29,5, censurada, 8, 21, censurada (abandono), 15
    #   ordenado: 8 12 15 18,5 21 25 29,5 inf inf -> mediana 21; Q1 15; Q3 29,5
    m = r["t1"]["T1_mini"]
    assert (m["n"], m["n_logradas"], m["n_censuradas"]) == (9, 7, 2)
    assert (m["mediana_min"], m["q1_min"], m["q3_min"]) == (21.0, 15.0, 29.5)
    assert r["t1"]["meta_mediana_mini"]["estado"] == "meta_observada"
    # T1 JSON (min): 20, 30, censurada, 27, censurada, 14, 26, censurada, 22 -> 14 20 22 26 27 30 inf inf inf
    j = r["t1"]["T1_json"]
    assert (j["mediana_min"], j["q1_min"], j["q3_min"], j["q3_determinado"]) == (27.0, 22.0, None, False)
    # pareadas: E01 -8, E02 -11,5, E04 +2,5, E06 -6, E07 -5, E09 -7 -> mediana de (-7, -6) = -6,5
    d = r["t1"]["diferencias_pareadas"]
    assert (d["n_pares"], d["n_pares_con_censura_excluidos_de_este_calculo"], d["mediana_diferencia_min"]) == (6, 3, -6.5)
    # éxito por tarea: intentos / logradas / sin ayuda
    esperado = {"T1_json": (9, 6, 6), "T1_mini": (9, 7, 6), "T2": (9, 7, 5), "T3": (8, 7, 7), "T4": (9, 7, 5)}
    for t, (n, lg, sa) in esperado.items():
        x = r["exito"]["por_tarea"][t]
        assert (x["n_intentos"], x["logradas"], x["sin_ayuda"]) == (n, lg, sa), t
    g = r["exito"]["global"]
    assert (g["n_intentos"], g["sin_ayuda"]) == (44, 29) and g["tasa_sin_ayuda"] == pytest.approx(29 / 44)
    assert r["metas"] == {"sus": "meta_no_observada", "mediana_t1_mini": "meta_observada", "sin_ayuda": "meta_no_observada"}
    assert r["todas_las_metas_observadas"] is False


def test_csv_y_json_del_fixture_dan_el_mismo_resumen():
    a = A.resumen(A.cargar_sesiones([FIX / "sesiones_fixture.json"]))
    b = A.resumen(A.cargar_sesiones([FIX / "sesiones_fixture.csv"]))
    assert a == b


def test_directorio_con_ambos_formatos_repite_codigos():
    with pytest.raises(A.ErrorDatos, match="repetidos"):
        A.cargar_sesiones([FIX])


# ------------------------------------------------------------------------------------------
# Validación de datos de entrada
# ------------------------------------------------------------------------------------------
def test_tiempo_de_tarea_lograda_no_puede_superar_el_tope():
    with pytest.raises(A.ErrorDatos, match="tope"):
        A.normalizar_sesion(sesion("EST-01", tareas={"T2": (S, 1000)}))
    with pytest.raises(A.ErrorDatos, match="tope"):
        A.normalizar_sesion(sesion("EST-01", tareas={"T2": (S, 902)}))
    for seg in (900, 900.5, 901):                     # en el tope, y 1 s de tolerancia por redondeo
        A.normalizar_sesion(sesion("EST-01", tareas={"T2": (S, seg)}))


def test_tope_distinto_del_plan_se_rechaza():
    s = sesion("EST-01", tareas={"T2": (S, 500)})
    s["tareas"]["T2"]["tope_s"] = 1200
    with pytest.raises(A.ErrorDatos, match="tope_s"):
        A.normalizar_sesion(s)


def test_sin_ayuda_con_ayudas_registradas_es_inconsistente():
    s = sesion("EST-01", tareas={"T2": (S, 500, 2)})
    with pytest.raises(A.ErrorDatos, match="sin ayuda"):
        A.normalizar_sesion(s)


@pytest.mark.parametrize("codigo", ["", "a", "Ana Perez", "ana@ejemplo.org", "x" * 30])
def test_codigos_que_parecen_datos_personales_se_rechazan(codigo):
    with pytest.raises(A.ErrorDatos, match="codigo"):
        A.normalizar_sesion(sesion(codigo))


def test_resultado_y_tarea_desconocidos_y_tipos():
    with pytest.raises(A.ErrorDatos, match="resultado"):
        A.normalizar_sesion(sesion("EST-01", tareas={"T2": ("exito", 100)}))
    with pytest.raises(A.ErrorDatos, match="tarea desconocida"):
        A.normalizar_sesion(sesion("EST-01", tareas={"T9": (S, 100)}))
    with pytest.raises(A.ErrorDatos, match="tipo debe"):
        A.normalizar_sesion(sesion("EST-01", tipo="experto"))
    s = sesion("EST-01")
    del s["tipo_datos"]
    with pytest.raises(A.ErrorDatos, match="tipo_datos"):
        A.normalizar_sesion(s)


def test_no_se_mezclan_fixtures_y_participantes(tmp_path):
    a = sesion("EST-01", tipo_datos="participantes")
    b = sesion("EST-02", tipo_datos="fixture_de_prueba")
    (tmp_path / "x.json").write_text(json.dumps([a, b]), encoding="utf-8")
    with pytest.raises(A.ErrorDatos, match="mezclar"):
        A.cargar_sesiones([tmp_path / "x.json"])


def test_codigos_repetidos(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps([sesion("EST-01"), sesion("EST-01")]), encoding="utf-8")
    with pytest.raises(A.ErrorDatos, match="repetidos"):
        A.cargar_sesiones([tmp_path / "x.json"])


def test_lectura_de_formas_json(tmp_path):
    s1, s2 = sesion("EST-01"), sesion("EST-02")
    (tmp_path / "uno.json").write_text(json.dumps(s1), encoding="utf-8")
    (tmp_path / "lista.json").write_text(json.dumps([s2]), encoding="utf-8")
    assert [s["codigo"] for s in A.cargar_sesiones([tmp_path / "uno.json", tmp_path / "lista.json"])] == ["EST-01", "EST-02"]
    (tmp_path / "obj.json").write_text(json.dumps({"sesiones": [s1, s2]}), encoding="utf-8")
    assert len(A.cargar_sesiones([tmp_path / "obj.json"])) == 2
    with pytest.raises(A.ErrorDatos):
        A.cargar_sesiones([tmp_path / "no_existe.json"])


# ------------------------------------------------------------------------------------------
# Contrabalanceo
# ------------------------------------------------------------------------------------------
def test_contrabalanceo_determinista_y_sensible_a_la_semilla():
    assert A.contrabalanceo(12, 7) == A.contrabalanceo(12, 7)
    planes = {json.dumps(A.contrabalanceo(12, s), sort_keys=True) for s in range(10)}
    assert len(planes) >= 6                        # semillas distintas dan asignaciones distintas


@pytest.mark.parametrize("semilla", [0, 1, 42, 99999])
def test_contrabalanceo_equilibrio_en_todo_n(semilla):
    for n in range(1, 41):
        filas = A.contrabalanceo(n, semilla, 2)
        est = [f for f in filas if f["tipo"] == "estudio"]
        assert [f["codigo"] for f in est] == [f"EST-{i:02d}" for i in range(1, n + 1)]
        # orden JSON primero / .mini primero: diferencia <= 1 sobre todo el estudio y sobre cada prefijo
        for k in range(1, n + 1):
            j = sum(1 for f in est[:k] if f["orden_t1"] == "json_mini")
            assert abs(j - (k - (j))) <= 1, (n, k)
        # cada una de las cuatro secuencias aparece n//4 o n//4 + 1 veces
        cuentas = [sum(1 for f in est if f["secuencia"] == s) for s in A.SECUENCIAS]
        assert max(cuentas) - min(cuentas) <= 1, (n, cuentas)
        if n % 4 == 0:
            assert cuentas == [n // 4] * 4
        # cada formato se resuelve con la variante A y con la B un número equilibrado de veces
        a_json = sum(1 for f in est if f["variante_json"] == "A")
        assert abs(a_json - (n - a_json)) <= 1, n


def test_contrabalanceo_variante_en_cada_orden():
    est = [f for f in A.contrabalanceo(40, 5, 2) if f["tipo"] == "estudio"]
    for orden in ("json_mini", "mini_json"):
        sub = [f for f in est if f["orden_t1"] == orden]
        a = sum(1 for f in sub if f["variante_json"] == "A")
        assert abs(a - (len(sub) - a)) <= 1


def test_contrabalanceo_pilotos_aparte_y_ambos_ordenes():
    filas = A.contrabalanceo(8, 3, 2)
    pil = [f for f in filas if f["tipo"] == "piloto"]
    assert [f["codigo"] for f in pil] == ["PIL-01", "PIL-02"]
    assert {f["orden_t1"] for f in pil} == {"json_mini", "mini_json"}          # un piloto de cada orden
    assert sum(1 for f in filas if f["tipo"] == "estudio") == 8                # los pilotos no ocupan plazas del estudio
    assert len(A.contrabalanceo(8, 3, 0)) == 8


@pytest.mark.parametrize("n,s,p", [(0, 1, 2), (201, 1, 2), (8, -1, 2), (8, 2 ** 32, 2), (8, 1, 11)])
def test_contrabalanceo_argumentos_invalidos(n, s, p):
    with pytest.raises(A.ErrorDatos):
        A.contrabalanceo(n, s, p)


def test_contrabalanceo_cli_formatos(tmp_path):
    rc, out, err = cli("contrabalanceo", "--participantes", "8", "--semilla", "42", "--formato", "json")
    assert rc == 0, err
    doc = json.loads(out)
    assert doc["semilla"] == 42 and len(doc["asignaciones"]) == 10
    rc, out, _ = cli("contrabalanceo", "--participantes", "8", "--semilla", "42", "--formato", "csv")
    filas = list(csv.DictReader(out.splitlines()))
    assert [f["codigo"] for f in filas] == [a["codigo"] for a in doc["asignaciones"]]
    rc, out, _ = cli("contrabalanceo", "--participantes", "8", "--semilla", "42")          # tabla
    assert out.splitlines()[0].split()[0] == "codigo" and "EST-08" in out
    destino = tmp_path / "plan.json"
    rc, out, _ = cli("contrabalanceo", "--participantes", "4", "--semilla", "1", "--formato", "json", "--salida", destino)
    assert rc == 0 and json.loads(destino.read_text(encoding="utf-8"))["participantes"] == 4
    rc, _, err = cli("contrabalanceo", "--participantes", "0", "--semilla", "1")
    assert rc == 2 and "participantes" in err


# ------------------------------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------------------------------
def test_cli_resumen_json_y_csv_iguales_y_aviso_de_fixture():
    rc, out_j, err = cli("resumen", FIX / "sesiones_fixture.json")
    assert rc == 0, err
    rc2, out_c, _ = cli("resumen", FIX / "sesiones_fixture.csv")
    assert rc2 == 0 and json.loads(out_j) == json.loads(out_c)
    r = json.loads(out_j)
    assert r["es_fixture"] is True and r["tipo_datos"] == "fixture_de_prueba"


def test_cli_subcomandos_individuales():
    for sub in ("t1", "exito"):
        rc, out, err = cli(sub, FIX / "sesiones_fixture.json")
        assert rc == 0, err
        json.loads(out)
    rc, out, _ = cli("puntuar-sus", FIX / "sesiones_fixture.json", "--formato", "csv")
    filas = list(csv.DictReader(out.splitlines()))
    assert len(filas) == 9                                                   # solo el estudio válido
    por = {f["codigo"]: f["sus"] for f in filas}
    assert float(por["EST-01"]) == 75.0 and por["EST-08"] == "" and float(por["EST-03"]) == 100.0
    rc, out, _ = cli("puntuar-sus", FIX / "sesiones_fixture.json")
    assert json.loads(out)["media"] == pytest.approx(61.875)


def test_cli_datos_invalidos_salen_con_codigo_2(tmp_path):
    mal = sesion("EST-01", tareas={"T2": (S, 5000)})
    (tmp_path / "m.json").write_text(json.dumps(mal), encoding="utf-8")
    rc, _, err = cli("resumen", tmp_path / "m.json")
    assert rc == 2 and "tope" in err
    rc, _, err = cli("resumen", tmp_path / "no_existe.json")
    assert rc == 2


def test_manifiesto_se_niega_con_fixtures():
    rc, _, err = cli("manifiesto", FIX / "sesiones_fixture.json")
    assert rc == 2 and "fixture" in err


def test_manifiesto_con_datos_no_fixture_valida_contra_evidencia_lib(tmp_path):
    sys.path.insert(0, str(RAIZ / "tools"))
    import evidencia_lib as ev
    # Sesiones sintéticas declaradas como 'participantes' SOLO dentro de este directorio temporal, para probar el
    # tubo de datos. No se escriben en el repositorio ni en evidencia/corridas.
    def hechas(n):
        return [sesion(f"EST-{i:02d}", tareas={"T1_mini": (S, 600), "T1_json": (S, 900), "T2": (S, 300), "T3": (S, 200), "T4": (S, 400)},
                       sus=[4, 2] * 5) for i in range(1, n + 1)]
    (tmp_path / "corto.json").write_text(json.dumps(hechas(5)), encoding="utf-8")
    m = A.construir_manifiesto(A.cargar_sesiones([tmp_path / "corto.json"]), A._archivos([tmp_path / "corto.json"]), "cmd")
    assert ev.validar_corrida(m) == []
    assert m["procedencia"] == "participantes" and m["estudio"] == "V6b"
    assert m["estado_ejecucion"] == "parcial" and m["resultado"] == "no_evaluable"          # n < 8: no se declara nada
    (tmp_path / "largo.json").write_text(json.dumps(hechas(8)), encoding="utf-8")
    m = A.construir_manifiesto(A.cargar_sesiones([tmp_path / "largo.json"]), A._archivos([tmp_path / "largo.json"]), "cmd")
    assert ev.validar_corrida(m) == []
    assert m["estado_ejecucion"] == "ejecutado" and m["resultado"] == "cumple" and m["criterio"]
    # no contiene datos individuales
    assert "EST-01" not in json.dumps(m["resumen"])
    # un fallo de meta da no_cumple
    malas = hechas(8)
    for s in malas:
        s["sus"]["respuestas"] = [3] * 10
    (tmp_path / "mal.json").write_text(json.dumps(malas), encoding="utf-8")
    m = A.construir_manifiesto(A.cargar_sesiones([tmp_path / "mal.json"]), A._archivos([tmp_path / "mal.json"]), "cmd")
    assert m["resultado"] == "no_cumple" and ev.validar_corrida(m) == []


def test_plan_de_n_menor_es_prefijo_del_plan_de_n_mayor():
    """El plan se puede generar una vez con N = 12 y usar en orden: cualquier prefijo coincide con el plan de menos N."""
    grande = A.contrabalanceo(12, 2026, 2)
    for n in range(1, 12):
        chico = A.contrabalanceo(n, 2026, 2)
        assert chico == grande[:len(chico)]

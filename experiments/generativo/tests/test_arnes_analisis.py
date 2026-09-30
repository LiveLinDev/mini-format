"""Estadística por conglomerados, latencia (mediana y p95), costo por 1 000 válidos y meta V2; todo con datos hechos a mano."""
from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path

import pytest

import analyze
from arnes.estadistica import bootstrap_diferencia, bootstrap_razon, mediana, percentil, wilson
from arnes.tarifas import Tarifas

TARIFAS = Path(__file__).resolve().parent / "fixtures" / "tarifas_prueba.json"


def muestra(i, *, brazo="D", tarea="ext-cls", modelo="gpt-4.1-mini", prov="openai", valid=8, solic=10, flujo=1.0, costo="0.001",
            desenlace="ok", exactos=None, procedencia="api_real", rep=1, usage=True, **extra):
    m = {"id": f"v2/{tarea}/{brazo}/{prov}:{modelo}/r{rep:03d}-{i}", "experimento": "v2", "tarea": tarea, "tipo_tarea": "extraccion",
         "brazo": brazo, "proveedor": prov, "modelo": modelo, "repeticion": rep, "procedencia": procedencia, "desenlace": desenlace,
         "metricas": {"esperados": solic, "solicitados": solic, "validos_finales": valid, "validos_contrato": valid, "aceptados": valid,
                      "espurios": 0, "correctos": valid if exactos is None else exactos,
                      "exactos_contenido": valid if exactos is None else exactos, "incorrectos_sin_aviso": solic - valid,
                      "perdidos_sin_aviso": 0, "perdidos_detectados": 0, "parseable": True, "sintaxis_ok": True, "exacto": valid == solic,
                      "detectado": False, "tokens_entrada": 100, "tokens_salida": 50, "latencia_ms": flujo * 1000, "llamadas": 1,
                      "llamadas_reparacion": 0, "tokens_reparacion_entrada": 0, "tokens_reparacion_salida": 0, "truncado": False},
         "latencia": {"flujo_s": flujo, "origen_api": "medida"} if flujo is not None else None,
         "costo_usd": costo,
         "solicitud": {"id": f"s{i}", "grupo": f"g{i}", "registros_solicitados": solic, "registros_validos_finales": valid,
                       "intentos": [{"fase": "generacion", "proveedor": prov, "modelo": modelo, "estado": "ok", "latencia_s": flujo,
                                     "usage": ({"entrada_sin_cache": 1_000_000, "entrada_cache_lectura": 0, "entrada_cache_escritura": 0,
                                                "salida": 500_000, "razonamiento": None, "razonamiento_incluido_en_salida": True,
                                                "otros_usd": {}} if usage else None), "costo_usd": costo}]}}
    m.update(extra)
    return m


# ------------------------------------------------------------------ bootstrap por conglomerados
def test_bootstrap_razon_basico_y_denominador_cero():
    est, lo, hi = bootstrap_razon([(9, 10)] * 20 + [(5, 10)] * 5, n_boot=400, semilla=1)
    assert math.isclose(est, (9 * 20 + 5 * 5) / 250)
    assert 0 < lo < est < hi < 1
    assert bootstrap_razon([], n_boot=10) == (None, None, None)
    assert bootstrap_razon([(0, 0), (0, 0)], n_boot=10) == (None, None, None)      # NUNCA 0 ni NaN
    assert bootstrap_razon([(3, 4)], n_boot=10) == (0.75, 0.75, 0.75)
    a = bootstrap_razon([(1, 2), (2, 2), (0, 2)], n_boot=300, semilla=9)
    assert a == bootstrap_razon([(1, 2), (2, 2), (0, 2)], n_boot=300, semilla=9)    # reproducible con semilla


def test_el_ic_por_conglomerado_es_mas_ancho_que_tratar_cada_registro_como_independiente():
    # 12 solicitudes de 11 registros, cada una o totalmente buena o totalmente mala: fuerte correlación interna
    clusters = [(11, 11)] * 6 + [(0, 11)] * 6
    _, lo, hi = bootstrap_razon(clusters, n_boot=800, semilla=3)
    _, wlo, whi = wilson(66, 132)                       # 132 registros como si fueran independientes
    assert (hi - lo) > 1.5 * (whi - wlo)


def test_bootstrap_diferencia_pareada():
    pares = [((5, 10), (8, 10))] * 10 + [((6, 10), (6, 10))] * 10
    est, lo, hi = bootstrap_diferencia(pares, n_boot=400, semilla=2)
    assert math.isclose(est, (80 + 60) / 200 - (50 + 60) / 200) and lo > 0
    assert bootstrap_diferencia([((1, 0), (1, 1))], n_boot=5) == (None, None, None)      # par con denominador 0: excluido


def test_mediana_y_percentil_por_rango_mas_cercano():
    v = list(range(1, 21))                                   # 1..20
    assert mediana(v) == 10.5 and percentil(v, 0.95) == 19 and percentil(v, 1.0) == 20 and percentil(v, 0.5) == 10
    assert percentil([7], 0.95) == 7 and percentil([], 0.95) is None and mediana([None, None]) is None
    assert percentil([1, 2, 3, None, 4], 0.95) == 4 and mediana([3, 1, 2]) == 2


# ------------------------------------------------------------------ agregado
def test_validez_es_validos_sobre_solicitados_con_ic_por_solicitud_y_documento():
    g = [muestra(i, valid=10 if i % 2 else 6, tarea="ext-cls" if i < 6 else "ext-log") for i in range(12)]
    f = analyze.agregar(g, n_boot=300)
    assert f["validez_final_pct"] == pytest_approx(80.0) and f["registros_solicitados"] == 120
    assert f["validez_final_ic_solicitud_inf"] < 80 < f["validez_final_ic_solicitud_sup"]
    assert f["validez_final_ic_documento_inf"] is not None            # segundo nivel de conglomerado (tarea)
    assert f["exactitud_contenido_pct"] == pytest_approx(80.0)


def pytest_approx(x):
    return pytest.approx(x, abs=1e-6)


def test_denominador_cero_da_none_no_cero():
    f = analyze.agregar([muestra(0, valid=0, solic=0)], n_boot=50)
    assert f["validez_final_pct"] is None and f["cumplimiento_contrato_pct"] is None
    assert f["exactitud_contenido_pct"] is None and f["costo_por_1000_validos_usd"] is None
    assert analyze.agregar([], n_boot=10)["muestras"] == 0


def test_latencia_mediana_p95_y_exclusion_de_errores_tecnicos():
    g = [muestra(i, flujo=float(i + 1)) for i in range(20)] + [muestra(99, flujo=500.0, desenlace="error_tecnico")]
    f = analyze.agregar(g, ic=False)
    assert f["latencia_flujo_mediana_s"] == 10.5 and f["latencia_flujo_p95_s"] == 19.0 and f["latencia_n"] == 20
    assert f["latencia_excluidas_error_tecnico"] == 1 and f["latencia_origen"] == "medida"
    sim = analyze.agregar([muestra(0, flujo=2.0, latencia={"flujo_s": 2.0, "origen_api": "simulada"})], ic=False)
    assert sim["latencia_origen"] == "simulada"


def test_costo_por_1000_validos_y_denominador_cero_informa_el_costo_incurrido():
    tar = Tarifas.cargar(TARIFAS)
    g = [muestra(i, valid=5, solic=10) for i in range(4)]                   # 4 solicitudes × (1M entrada + 0,5M salida) = 4·(1+1) USD
    f = analyze.agregar(g, tarifas=tar, ic=False)
    assert f["costo_usd_total"] == 8.0 and f["validos_finales"] == 20 and f["costo_por_1000_validos_usd"] == 400.0
    assert f["costo_solicitud_mediana_usd"] == 2.0
    cero = analyze.agregar([muestra(i, valid=0, solic=10) for i in range(2)], tarifas=tar, ic=False)
    assert cero["costo_por_1000_validos_usd"] is None and "sin registros válidos" in cero["costo_nota"] and "4.000000" in cero["costo_nota"]


def test_sin_tarifa_verificada_el_costo_es_tarifa_no_verificada():
    tar = Tarifas.cargar(TARIFAS)
    g = [muestra(i, modelo="llama-3.3-70b-versatile", prov="groq") for i in range(3)]
    f = analyze.agregar(g, tarifas=tar, ic=False)
    assert f["costo_usd_total"] is None and f["costo_nota"] == "tarifa no verificada"
    sin_usage = analyze.agregar([muestra(0, usage=False)], tarifas=tar, ic=False)
    assert sin_usage["costo_usd_total"] is None
    asistido = analyze.agregar([muestra(0, procedencia="asistido_ia")], tarifas=tar, ic=False)
    assert asistido["costo_usd_total"] is None and "asistido_ia" in asistido["costo_nota"]


def test_el_costo_se_recalcula_con_las_tarifas_dadas():
    tar = Tarifas.cargar(TARIFAS)
    s = muestra(0, costo="999")                                              # costo guardado distinto
    assert analyze.costo_de(s, tar) == Decimal("2.0") and analyze.costo_de(s, None) == Decimal("999")


def test_desenlaces_se_cuentan_sin_perder_ninguno():
    g = [muestra(0, desenlace="ok"), muestra(1, desenlace="truncada"), muestra(2, desenlace="negativa"),
         muestra(3, desenlace="error_tecnico"), muestra(4, desenlace="vacia"), muestra(5, desenlace="formato_invalido")]
    f = analyze.agregar(g, ic=False)
    assert [f[f"desenlace_{d}"] for d in analyze.DESENLACES] == [1, 1, 1, 1, 1, 1] and sum(f[f"desenlace_{d}"] for d in analyze.DESENLACES) == f["muestras"]


# ------------------------------------------------------------------ comparaciones y meta
def test_comparaciones_pareadas_misma_celda():
    ms = []
    for r in range(1, 9):
        ms.append(muestra(r, brazo="B", rep=r, valid=6))
        ms.append(muestra(r, brazo="D", rep=r, valid=9))
        ms.append(muestra(r, brazo="D+1", rep=r, valid=10, generacion_de="x"))
    filas = {f["comparacion"]: f for f in analyze.comparaciones_pareadas(ms, n_boot=200)}
    f = filas["D − B"]
    assert f["pares"] == 8 and f["diferencia_pp"] == pytest_approx(30.0) and f["ic_solicitud_inf"] > 0 and f["exploratoria"] is True
    assert filas["D+1 − D"]["misma_respuesta"] is True and filas["D+1 − D"]["diferencia_pp"] == pytest_approx(10.0)
    assert "D − B" in filas and all(x["exploratoria"] for x in filas.values())


def test_meta_v2_solo_se_evalua_con_api_real():
    filas = [{"experimento": "v2", "brazo": "D", "modelo_completo": f"{p}:{m}", "validez_final_pct": v}
             for p, m, v in (("openai", "a", 97.0), ("anthropic", "b", 96.0), ("groq", "c", 95.5), ("groq", "d", 80.0))]
    sim = analyze.evaluar_meta_v2(filas, ["simulado"])
    assert sim["resultado"] == "no_evaluable" and sim["por_brazo"]["D"]["cumple"] is None and "api_real" in sim["motivo"]
    assert analyze.evaluar_meta_v2(filas, ["api_real", "simulado"])["resultado"] == "no_evaluable"      # mezcla: tampoco
    real = analyze.evaluar_meta_v2(filas, ["api_real"])
    d = real["por_brazo"]["D"]
    assert real["resultado"] == "evaluado" and d["modelos_que_cumplen"] == 3 and d["proveedores_que_cumplen"] == 3 and d["cumple"] is True
    pocos = analyze.evaluar_meta_v2(filas[:2] + filas[3:], ["api_real"])
    assert pocos["por_brazo"]["D"]["cumple"] is False
    assert analyze.CRITERIO_V2["umbral"] == 0.95 and analyze.CRITERIO_V2["min_modelos"] == 3 and analyze.CRITERIO_V2["min_proveedores"] == 2


def test_reparacion_informa_ganados_adversos_y_auditoria():
    def par(i, vb, vr, aud):
        b = muestra(i, brazo="D", rep=i, valid=vb)
        r = muestra(i, brazo="D+1", rep=i, valid=vr, generacion_de=b["id"],
                    reparacion={"rondas": [{"sin_resolver": [1] if vr < 10 else []}], "auditoria": aud})
        r["metricas"]["llamadas_reparacion"] = 1
        r["costo_incremental_usd"] = "0.5"
        return b, r
    aud = {"validos_sobrescritos": 0, "identidades_duplicadas_finales": 1, "identidades_inventadas": 0,
           "correcciones_rechazadas_identidad": None}
    ms = [x for p in (par(1, 7, 10, dict(aud, identidades_duplicadas_finales=0)), par(2, 9, 8, aud)) for x in p]
    (f,) = analyze.reparacion(ms)
    assert f["pares"] == 2 and f["registros_validos_ganados"] == 3 - 1 and f["muestras_con_cambio_adverso"] == 1
    assert f["registros_adversos"] == 1 and f["lineas_no_recuperadas"] == 1
    assert f["identidades_duplicadas_finales"] == 1 and f["reparaciones_auditadas"] == 2 and f["costo_reparacion_usd"] == 1.0
    assert f["identidades_inventadas"] == 0 and f["correcciones_rechazadas_identidad"] is None     # n/a no es 0


def test_v3a_heredada_denominador_cero_es_none():
    filas = [{"id": "m1", "brazo": "B", "proveedor": "p", "modelo": "m", "recuperados": 0, "ideal": 0, "eficiencia": None,
              "cero": True, "incorrectos_sin_aviso": 0} for _ in range(4)]
    (f,) = analyze.resumen_v3a(filas)
    assert f["eficiencia_media_pct"] is None and f["recuperados_sobre_ideal_pct"] is None and f["cortes_sin_ideal"] == 4
    from arnes.truncamiento import cortes_muestra
    import arnes.brazos as B
    from arnes import tareas as T
    t = T.construir("ext-cls")
    import json
    regs = [B._registro_json(r, t.contrato) for r in t.registros[:3]]      # 3 registros completos: por debajo del 33 % no hay nada recuperable
    texto = json.dumps({"messages": regs}, ensure_ascii=False, indent=1)
    cortes = cortes_muestra({"id": "v2/x", "tarea": "ext-cls", "brazo": "B", "proveedor": "p", "modelo": "m",
                             "respuesta": {"text": texto}}, t, 20, 7)
    assert any(c["ideal"] == 0 and c["eficiencia"] is None for c in cortes)      # corte corto: nada recuperable, no es fracaso

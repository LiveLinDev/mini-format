"""Piloto simulado versionado: reproducibilidad (golden), consistencia de conteos y estados y evidencia emitida.

El lector .mini es parte del tratamiento del brazo D: si el núcleo cambia su comportamiento, el piloto versionado deja de
reproducirse (así pasó entre 0cfa477 y d10eb6e).  Esta prueba lo detecta.  Para no bloquear los arreglos legítimos del
núcleo (p. ej. la garantía de identidad de merge_repair), las filas del brazo D y D+1 solo avisan; los demás brazos
(JSON y su reparación, que son del arnés) deben coincidir exactamente.
Para regenerar el piloto:
    python experiments/generativo/run.py ejecutar --config configs/piloto.yaml --adapter simulado --emitir-evidencia
"""
from __future__ import annotations

import csv
import json
import sys
import warnings
from pathlib import Path

import pytest

import analyze
import run
from arnes import brazos as B

ROOT = Path(__file__).resolve().parents[3]
PILOTO = ROOT / "experiments" / "generativo" / "resultados" / "simulado" / "piloto"
sys.path.insert(0, str(ROOT / "tools"))
import evidencia_lib as EV  # noqa: E402

COLUMNAS_ESTABLES = ("muestras", "registros_solicitados", "registros_aceptados", "validos_finales", "correctos",
                     "incorrectos_sin_aviso", "perdidos_sin_aviso", "perdidos_detectados", "identidades_duplicadas",
                     "desenlace_ok", "desenlace_formato_invalido", "desenlace_vacia", "desenlace_truncada",
                     "desenlace_negativa", "desenlace_error_tecnico", "tokens_entrada_media", "tokens_salida_media",
                     "sintaxis_ok_pct", "exacto_pct", "latencia_flujo_mediana_s", "latencia_flujo_p95_s", "intentos_totales")


def _filas(ruta: Path):
    with open(ruta, newline="", encoding="utf-8") as fh:
        return {(f["experimento"], f["tipo_tarea"], f["brazo"]): f for f in csv.DictReader(fh)}


@pytest.fixture(scope="module")
def regenerado(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("golden")
    assert run.main(["ejecutar", "--config", "configs/piloto.yaml", "--adapter", "simulado", "--salida", str(tmp / "res")]) == 0
    assert analyze.main(["--resultados", str(tmp / "res"), "--sin-figuras", "--bootstrap", "0"]) == 0
    return tmp / "res"


def test_el_piloto_versionado_existe_y_esta_marcado_simulado():
    man = json.loads((PILOTO / "manifiesto.json").read_text(encoding="utf-8"))
    assert man["simulado"] is True and man["procedencia"] == "simulado" and "SIMULADOS" in man["advertencia"]
    assert (PILOTO / "analisis" / "resumen.md").read_text(encoding="utf-8").count("RESULTADOS SIMULADOS") >= 1
    assert (PILOTO.parent / "piloto_historico_0cfa477" / "LEEME.md").exists()         # el anterior quedó marcado como histórico


def test_el_piloto_se_reproduce_a_head(regenerado):
    viejo = _filas(PILOTO / "analisis" / "resumen_brazos.csv")
    nuevo = _filas(regenerado / "analisis" / "resumen_brazos.csv")
    assert set(viejo) == set(nuevo)
    diferencias = []
    for clave, fv in viejo.items():
        fn = nuevo[clave]
        assert fv["muestras"] == fn["muestras"], clave
        dif = [c for c in COLUMNAS_ESTABLES if (fv.get(c) or "") != (fn.get(c) or "")]
        if not dif:
            continue
        if clave[2] in ("D", "D+1"):
            diferencias.append((clave, dif))
            continue
        pytest.fail(f"{clave}: el piloto versionado ya no se reproduce en {dif}; regéneralo (ver docstring)")
    if diferencias:
        warnings.warn("el lector o la reparación .mini del núcleo cambiaron y el piloto versionado ya no reproduce los brazos D/D+1 "
                      f"({diferencias[:2]}...): regenere el piloto", stacklevel=1)


def test_determinismo_bit_a_bit_de_las_muestras(regenerado, tmp_path):
    assert run.main(["ejecutar", "--config", "configs/piloto.yaml", "--adapter", "simulado", "--salida", str(tmp_path / "otra"),
                     "--limite", "40"]) == 0
    a = [json.loads(l) for l in (regenerado / "muestras.jsonl").read_text(encoding="utf-8").splitlines()][:40]
    b = [json.loads(l) for l in (tmp_path / "otra" / "muestras.jsonl").read_text(encoding="utf-8").splitlines()]
    for x, y in zip(a, b):
        x.pop("fecha"), y.pop("fecha")
        assert x == y


def test_conteos_y_estados_son_consistentes(regenerado):
    est = json.loads((regenerado / "estado_estudio.json").read_text(encoding="utf-8"))
    c = est["celdas"]
    plan = [json.loads(l) for l in (regenerado / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    ms = [json.loads(l) for l in (regenerado / "muestras.jsonl").read_text(encoding="utf-8").splitlines()]
    assert est["estado"] == "completo"
    assert sum(c.values()) == len(plan)                                                   # suma por estado = total de celdas del plan
    assert c["hecha"] == sum(1 for p in plan if p["estado"] == "pendiente") == len(ms)    # toda celda ejecutable tiene su muestra
    assert c["no_aplicable"] == sum(1 for p in plan if p["estado"] == "no_aplicable")
    assert c["pendiente"] == c["bloqueado"] == c["error_tecnico"] == 0
    assert len({m["id"] for m in ms}) == len(ms) and {m["id"] for m in ms} == {p["id"] for p in plan if p["estado"] == "pendiente"}
    man = json.loads((regenerado / "manifiesto.json").read_text(encoding="utf-8"))
    assert man["unidades"] == len(ms) and man["no_aplicables"] == c["no_aplicable"]
    # cada X+1 tiene su X y cada C/C+1 faltante es de un modelo sin modo estructurado
    ids = {m["id"] for m in ms}
    assert all(m["generacion_de"] in ids for m in ms if B.es_reparacion(m["brazo"]))
    assert all("llama-3.3" in p["id"] and p["brazo"] in ("C", "C+1") for p in plan if p["estado"] == "no_aplicable")
    # desenlaces: ninguna muestra se pierde en el recuento
    filas = analyze.agrupar(ms, ("experimento", "brazo"), ic=False)
    assert sum(f["muestras"] for f in filas) == len(ms)
    assert all(sum(f[f"desenlace_{d}"] for d in analyze.DESENLACES) == f["muestras"] for f in filas)


def test_las_corridas_emitidas_del_piloto_validan():
    base = ROOT / "evidencia" / "corridas"
    ids = ["v2-simulado-piloto", "v3b-simulado-piloto", "v4-simulado-piloto"]
    for rid in ids:
        d = base / rid
        assert (d / "manifiesto.json").exists(), rid
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        assert EV.validar_corrida(m, d) == [], rid                # incluye los SHA-256 de los resultados
        assert m["procedencia"] == "simulado" and m["resultado"] == "no_evaluable" and m["gasto_usd"] == 0.0
        assert m["comando"].startswith("python experiments/generativo/run.py ejecutar --config configs/piloto.yaml")
    # las cifras de la corrida V2 salen del CSV del piloto versionado, no de otra parte
    m = json.loads((base / ids[0] / "manifiesto.json").read_text(encoding="utf-8"))
    viejo = _filas(PILOTO / "analisis" / "resumen_brazos.csv")
    for k, v in m["resumen"]["validez_final_pct_por_brazo_y_tipo"].items():
        tipo, brazo = k.split("/")
        assert v == float(viejo[("v2", tipo, brazo)]["validez_final_pct"])

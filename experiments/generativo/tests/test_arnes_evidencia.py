"""Emisión de las corridas V2, V3b y V4 con tools/evidencia_lib: validan, son simulado/no_evaluable y derivan de archivos."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
import yaml

import run
from arnes import evidencia as EVI

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import evidencia_lib as EV  # noqa: E402

TARIFAS = Path(__file__).resolve().parent / "fixtures" / "tarifas_prueba.json"
CONFIG = {"nombre": "mini", "semilla": 11, "idioma": "es", "temperatura": 0.7, "max_tokens": 4096, "repeticiones": 2,
          "tareas": ["ext-cls", "gen-card"], "brazos": ["A", "B", "C", "D", "B+1", "D+1"],
          "modelos": [{"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True, "perfil_simulado": "debil"},
                      {"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False, "perfil_simulado": "medio"}],
          "experimentos": {"v2": {"activo": True}, "v3b": {"activo": True, "repeticiones": 1, "brazos": ["A", "D", "D+1"]}},
          "reparacion": {"max_rondas": 1}}


@pytest.fixture(scope="module")
def corridas(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ev")
    cfg = tmp / "mini.yaml"
    cfg.write_text(yaml.safe_dump(CONFIG, allow_unicode=True), encoding="utf-8")
    destino = tmp / "corridas"
    original = EVI.emitir_corridas
    EVI.emitir_corridas = lambda *a, **k: original(*a, **dict(k, directorio_corridas=destino))
    try:
        # --tarifas apunta a un archivo que no existe: la prueba no depende de que el repositorio traiga evidencia/tarifas/
        assert run.main(["ejecutar", "--config", str(cfg), "--adapter", "simulado", "--salida", str(tmp / "res"),
                         "--tarifas", str(tmp / "sin_tarifas.json"), "--emitir-evidencia", "prueba-mini"]) == 0
    finally:
        EVI.emitir_corridas = original
    return tmp, destino


def test_se_emiten_v2_v3b_y_v4(corridas):
    _, destino = corridas
    assert sorted(p.name for p in destino.iterdir()) == ["v2-prueba-mini", "v3b-prueba-mini", "v4-prueba-mini"]


def test_todos_los_manifiestos_validan_y_son_simulado_no_evaluable(corridas):
    _, destino = corridas
    for d in destino.iterdir():
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        assert EV.validar_corrida(m, d) == [], d.name
        assert m["procedencia"] == "simulado" and m["resultado"] == "no_evaluable" and m["estado_ejecucion"] == "ejecutado"
        assert m["gasto_usd"] == 0.0 and m["modelo"] is None
        assert m["esquema"] == EV.ESQUEMA_CORRIDA and m["comando"].startswith("python experiments/generativo/run.py ejecutar")
        assert m["limitaciones"] and any("simulador" in x for x in m["limitaciones"])
        assert m["tarifas"] is None and all(len(r["sha256"]) == 64 for r in m["resultados"])
        assert all(c["sintetico"] is True for c in m["conjuntos"]) and m["contratos"] and m["prompts"]
        assert m["tokenizadores"][0]["tipo"] == "aproximacion"
        assert all(b"\r" not in (ROOT / r["ruta"]).read_bytes() if (ROOT / r["ruta"]).exists() else b"\r" not in (d / Path(r["ruta"]).name).read_bytes()
                   for r in m["resultados"])
        assert "commit" in m["codigo"] and "arbol_limpio" in m["codigo"]          # null si se ejecuta fuera de un repositorio git


def test_una_corrida_simulada_no_puede_declararse_cumple(corridas):
    _, destino = corridas
    m = json.loads((destino / "v2-prueba-mini" / "manifiesto.json").read_text(encoding="utf-8"))
    m["resultado"] = "cumple"
    m["criterio"] = {"x": 1}
    assert any("simulado no puede declararse" in e for e in EV.validar_corrida(m))


def test_las_cifras_del_manifiesto_salen_de_los_archivos(corridas):
    _, destino = corridas
    d = destino / "v2-prueba-mini"
    m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
    with open(d / "resumen_brazos.csv", newline="", encoding="utf-8") as fh:
        filas = {f"{f['tipo_tarea']}/{f['brazo']}": f for f in csv.DictReader(fh)}
    for k, v in m["resumen"]["validez_final_pct_por_brazo_y_tipo"].items():
        esperado = filas[k]["validez_final_pct"]
        assert (v is None and esperado == "") or v == float(esperado)
    assert m["conteos"]["registros_validos_finales"] is None and "validos_finales" in m["notas"]    # null con explicación, no 0
    assert m["criterio"]["resultado_del_criterio"] == "no_evaluable"
    sols = [json.loads(l) for l in (d / "solicitudes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert sols and set(sols[0]) >= {"id", "grupo", "registros_solicitados", "registros_validos_finales", "intentos"}
    assert all(s["procedencia"] == "simulado" for s in sols)


def test_v3b_y_v4_conservan_su_identidad(corridas):
    _, destino = corridas
    v3b = json.loads((destino / "v3b-prueba-mini" / "manifiesto.json").read_text(encoding="utf-8"))
    assert v3b["estudio"] == "V3b" and v3b["parametros"]["v3b"]["brazos"] and any("experiments/truncamiento" in x for x in v3b["limitaciones"])
    lineas = [json.loads(l) for l in (destino / "v3b-prueba-mini" / "v3b_muestras.jsonl").read_text(encoding="utf-8").splitlines()]
    assert lineas and all(x["limite_salida"] and "stop_reason" in x for x in lineas)
    v4 = json.loads((destino / "v4-prueba-mini" / "manifiesto.json").read_text(encoding="utf-8"))
    assert v4["estudio"] == "V4" and v4["resumen"]["origen_latencia"] == "simulada"
    assert any("sintética" in x for x in v4["limitaciones"])
    with open(destino / "v4-prueba-mini" / "latencia_costo.csv", newline="", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    assert filas and all(f["latencia_origen"] == "simulada" for f in filas)
    # sin tarifa verificada el costo está vacío y dice por qué; nunca un 0
    assert all(f["costo_por_1000_validos_usd"] == "" and f["costo_nota"] for f in filas)


def test_codigo_de_la_corrida_ignora_las_salidas_pero_no_el_codigo(monkeypatch):
    base = {"commit": "abc", "rama": "x", "arbol_limpio": False, "snapshot_sha256": "h",
            "archivos_modificados": ["experiments/generativo/resultados/simulado/piloto/manifiesto.json", "evidencia/corridas/v2-x/a.csv"]}
    monkeypatch.setattr(EVI.EV, "info_codigo", lambda: dict(base))
    c = EVI.codigo_de_la_corrida()
    assert c["arbol_limpio"] is True and c["snapshot_sha256"] is None and c["ignorados_por_ser_salidas"] == 2 and c["archivos_modificados"] == []
    sucio = dict(base, archivos_modificados=base["archivos_modificados"] + ["experiments/generativo/arnes/brazos.py"])
    monkeypatch.setattr(EVI.EV, "info_codigo", lambda: dict(sucio))
    c2 = EVI.codigo_de_la_corrida()                                   # hay código modificado: se conserva tal cual
    assert c2["arbol_limpio"] is False and c2["snapshot_sha256"] == "h" and len(c2["archivos_modificados"]) == 3
    monkeypatch.setattr(EVI.EV, "info_codigo", lambda: dict(base, arbol_limpio=True, archivos_modificados=[], snapshot_sha256=None))
    assert EVI.codigo_de_la_corrida()["arbol_limpio"] is True

"""Runner completo con el adaptador simulado: matriz, reanudación, presupuesto, dry-run y análisis."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import analyze
import run
from arnes import ejecucion as X
from arnes.costos import Precios, estimar

CONFIG = {
    "nombre": "prueba",
    "semilla": 123,
    "idioma": "es",
    "temperatura": 0.7,
    "max_tokens": 4096,
    "repeticiones": 2,
    "tareas": ["ext-cls", "gen-card"],
    "brazos": ["A", "B", "C", "D", "D+R"],
    "modelos": [
        {"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True, "perfil_simulado": "debil"},
        {"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False, "perfil_simulado": "debil"},
    ],
    "experimentos": {"v2": {"activo": True},
                     "v3b": {"activo": True, "repeticiones": 1, "brazos": ["A", "D", "D+R"], "fraccion_max_tokens": 0.5},
                     "v3a": {"cortes_por_muestra": 5, "semilla": 7}},
    "reparacion": {"max_rondas": 2, "incluir_entrada": False},
}


@pytest.fixture
def cfg_path(tmp_path):
    p = tmp_path / "prueba.yaml"
    p.write_text(yaml.safe_dump(CONFIG, allow_unicode=True), encoding="utf-8")
    return p


def _esperadas():
    # v2: 2 tareas × 2 reps × (openai: 5 brazos + groq: 4 brazos sin C) ; v3b: 2 tareas × 1 rep × 2 modelos × 3 brazos
    return 2 * 2 * (5 + 4) + 2 * 1 * 2 * 3


def test_matriz_y_omisiones(cfg_path):
    cfg = X.cargar_config(cfg_path)
    unidades, omitidas = X.enumerar(cfg, X.Contexto(cfg))
    assert len(unidades) == _esperadas()
    assert len({u.id for u in unidades}) == len(unidades)
    assert any("groq:llama-3.3-70b-versatile" in o and "brazo C omitido" in o for o in omitidas)
    v3b = [u for u in unidades if u.experimento == "v3b"]
    assert all(u.max_tokens < 4096 for u in v3b)
    ids = [u.id for u in unidades]
    for u in unidades:                      # D+R siempre después de su D
        if u.brazo == "D+R":
            assert ids.index(u.id_brazo("D")) < ids.index(u.id)


def test_config_invalida(tmp_path):
    malo = dict(CONFIG, brazos=["A", "Z"])
    p = tmp_path / "malo.yaml"
    p.write_text(yaml.safe_dump(malo), encoding="utf-8")
    assert run.main(["--config", str(p), "--adapter", "simulado", "--dry-run"]) == 2
    sin_d = dict(CONFIG, brazos=["A", "D+R"])
    p.write_text(yaml.safe_dump(sin_d), encoding="utf-8")
    assert run.main(["--config", str(p), "--adapter", "simulado", "--dry-run"]) == 2


def test_dry_run_no_escribe_nada(cfg_path, tmp_path, capsys):
    salida = tmp_path / "res"
    assert run.main(["--config", str(cfg_path), "--adapter", "simulado", "--dry-run", "--salida", str(salida)]) == 0
    out = capsys.readouterr().out
    assert "costo esperado" in out and "TOTAL" in out and "provisional" in out
    assert not salida.exists()


def test_estimacion_cuenta_llamadas(cfg_path):
    cfg = X.cargar_config(cfg_path)
    ctx = X.Contexto(cfg)
    unidades, _ = X.enumerar(cfg, ctx)
    est = estimar(unidades, ctx, Precios.cargar(), cfg)
    gen = sum(1 for u in unidades if u.brazo != "D+R")
    assert est.llamadas == gen
    assert est.costo_esperado is not None and 0 < est.costo_esperado < est.costo_maximo


def test_runner_completo_reanudable_y_analisis(cfg_path, tmp_path):
    salida = tmp_path / "res"
    args = ["--config", str(cfg_path), "--adapter", "simulado", "--salida", str(salida)]
    assert run.main(args) == 0
    muestras = X.leer_muestras(salida / "muestras.jsonl")
    assert len(muestras) == _esperadas()
    s = muestras[0]
    for clave in ("prompt", "respuesta", "metricas", "costo_usd", "semilla", "simulado"):
        assert clave in s
    assert all(m["simulado"] and m["adaptador"] == "simulado" for m in muestras)
    assert all(m["metricas"]["tokens_entrada"] and m["metricas"]["latencia_ms"] > 0 for m in muestras)
    dr = [m for m in muestras if m["brazo"] == "D+R"]
    assert dr and all(m["generacion_de"].replace("/D/", "/D+R/") == m["id"] for m in dr)
    assert any(m["metricas"]["llamadas_reparacion"] > 0 for m in dr)     # el perfil 'debil' produce reparaciones
    v3b = [m for m in muestras if m["experimento"] == "v3b" and m["brazo"] == "A"]
    assert all(m["metricas"]["truncado"] for m in v3b)
    man = json.loads((salida / "manifiesto.json").read_text(encoding="utf-8"))
    assert man["simulado"] and "SIMULADOS" in man["advertencia"]

    # reanudación: no repite nada
    tam = (salida / "muestras.jsonl").stat().st_size
    assert run.main(args) == 0
    assert (salida / "muestras.jsonl").stat().st_size == tam

    # una línea final corrupta (escritura interrumpida) se repite sin duplicar las demás
    lineas = (salida / "muestras.jsonl").read_text(encoding="utf-8").splitlines()
    ultima = json.loads(lineas[-1])
    (salida / "muestras.jsonl").write_text("\n".join(lineas[:-1]) + "\n" + lineas[-1][: len(lineas[-1]) // 2],
                                           encoding="utf-8")
    assert run.main(args) == 0
    ids = [m["id"] for m in X.leer_muestras(salida / "muestras.jsonl")]
    assert ids.count(ultima["id"]) == 1 and len(ids) == _esperadas()

    # análisis
    assert analyze.main(["--resultados", str(salida)]) == 0
    an = salida / "analisis"
    for nombre in ("resumen_brazos.csv", "resumen_brazo_modelo.csv", "resumen_brazo_tarea.csv", "reparacion.csv",
                   "v3a_truncamiento.csv", "resumen.md", "fig_v2_desenlaces_registros.png",
                   "fig_v2_incorrectos_sin_aviso.png", "fig_v2_tokens.png", "fig_v3_recuperacion.png"):
        assert (an / nombre).exists(), nombre
    md = (an / "resumen.md").read_text(encoding="utf-8")
    assert "RESULTADOS SIMULADOS" in md and "[" in md


def test_determinismo_entre_ejecuciones(cfg_path, tmp_path):
    textos = []
    for d in ("r1", "r2"):
        assert run.main(["--config", str(cfg_path), "--adapter", "simulado", "--salida", str(tmp_path / d),
                         "--limite", "12"]) == 0
        textos.append([(m["id"], m["respuesta"]["text"]) for m in X.leer_muestras(tmp_path / d / "muestras.jsonl")])
    assert textos[0] == textos[1] and len(textos[0]) == 12


def test_presupuesto_previo_y_durante(cfg_path, tmp_path):
    salida = tmp_path / "res"
    assert run.main(["--config", str(cfg_path), "--adapter", "simulado", "--salida", str(salida),
                     "--max-costo-usd", "0.0001"]) == 2
    assert not (salida / "muestras.jsonl").exists()
    cfg = X.cargar_config(cfg_path)
    ctx = X.Contexto(cfg)
    unidades, _ = X.enumerar(cfg, ctx)
    ej = X.Ejecutor(cfg, ctx, "simulado", salida, Precios.cargar(), max_costo=0.0005)
    res = ej.correr(unidades)
    assert res["abortado"] and "supera" in res["abortado"]
    assert 0 < len(X.leer_muestras(salida / "muestras.jsonl")) < len(unidades)


def test_real_exige_confirmacion_y_claves(cfg_path, tmp_path, sin_claves, capsys):
    salida = tmp_path / "real"
    assert run.main(["--config", str(cfg_path), "--adapter", "real", "--salida", str(salida)]) == 2
    assert "--confirmar-real" in capsys.readouterr().err
    assert run.main(["--config", str(cfg_path), "--adapter", "real", "--confirmar-real", "--salida", str(salida)]) == 2
    err = capsys.readouterr().err
    assert "OPENAI_API_KEY" in err and "GROQ_API_KEY" in err
    assert not (salida / "muestras.jsonl").exists()


def test_fallo_de_adaptador_se_registra_y_reintenta(cfg_path, tmp_path):
    from minifmt.ai.adapters import Adapter, AdapterError

    class Roto(Adapter):
        provider = "roto"
        supports_structured = True

        def generate(self, system, user, **kw):
            raise AdapterError("HTTP 500 simulado", status=500, retryable=True)

    cfg = X.cargar_config(cfg_path)
    cfg["max_fallos_seguidos"] = 3
    ctx = X.Contexto(cfg)
    unidades, _ = X.enumerar(cfg, ctx)
    adapt = {(m["proveedor"], m["modelo"]): Roto(m["modelo"]) for m in cfg["modelos"]}
    ej = X.Ejecutor(cfg, ctx, "real", tmp_path / "f", Precios.cargar(), adaptadores=adapt)
    res = ej.correr(unidades)
    assert res["fallos"] == 3 and "fallos seguidos" in res["abortado"]
    assert len((tmp_path / "f" / "fallos.jsonl").read_text(encoding="utf-8").splitlines()) == 3
    assert not (tmp_path / "f" / "muestras.jsonl").exists()

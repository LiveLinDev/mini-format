"""Runner completo con el adaptador simulado: matriz, reanudación, presupuesto, dry-run y análisis."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

import analyze
import run
from arnes import ejecucion as X
from arnes.costos import estimar
from arnes.tarifas import Tarifas

TARIFAS = Path(__file__).resolve().parent / "fixtures" / "tarifas_prueba.json"

CONFIG = {
    "nombre": "prueba",
    "semilla": 123,
    "idioma": "es",
    "temperatura": 0.7,
    "max_tokens": 4096,
    "repeticiones": 2,
    "tareas": ["ext-cls", "gen-card"],
    "brazos": ["A", "B", "C", "D", "B+1", "D+1"],
    "modelos": [
        {"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True, "perfil_simulado": "debil"},
        {"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False, "perfil_simulado": "debil"},
    ],
    "experimentos": {"v2": {"activo": True},
                     "v3b": {"activo": True, "repeticiones": 1, "brazos": ["A", "D", "D+1"], "fraccion_max_tokens": 0.5},
                     "v3a": {"cortes_por_muestra": 5, "semilla": 7}},
    "reparacion": {"max_rondas": 2, "incluir_entrada": False},
}


@pytest.fixture
def cfg_path(tmp_path):
    p = tmp_path / "prueba.yaml"
    p.write_text(yaml.safe_dump(CONFIG, allow_unicode=True), encoding="utf-8")
    return p


def _esperadas():
    # v2: 2 tareas × 2 reps × (openai: 6 brazos + groq: 5 brazos sin C) ; v3b: 2 tareas × 1 rep × 2 modelos × 3 brazos
    return 2 * 2 * (6 + 5) + 2 * 1 * 2 * 3


def test_matriz_y_omisiones(cfg_path):
    cfg = X.cargar_config(cfg_path)
    unidades, omitidas = X.enumerar(cfg, X.Contexto(cfg))
    assert len(unidades) == _esperadas()
    assert len({u.id for u in unidades}) == len(unidades)
    assert any("groq:llama-3.3-70b-versatile" in o and "brazo C omitido" in o for o in omitidas)
    v3b = [u for u in unidades if u.experimento == "v3b"]
    assert all(u.max_tokens < 4096 for u in v3b)
    ids = [u.id for u in unidades]
    for u in unidades:                      # cada X+1 va DESPUÉS de su X
        if u.brazo.endswith("+1"):
            assert ids.index(u.id_brazo(u.brazo[:-2])) < ids.index(u.id)


def test_config_invalida(tmp_path):
    p = tmp_path / "malo.yaml"
    p.write_text(yaml.safe_dump(dict(CONFIG, brazos=["A", "Z"])), encoding="utf-8")
    assert run.main(["--config", str(p), "--adapter", "simulado", "--dry-run"]) == 2
    p.write_text(yaml.safe_dump(dict(CONFIG, brazos=["A", "D+1"])), encoding="utf-8")   # D+1 sin D
    assert run.main(["--config", str(p), "--adapter", "simulado", "--dry-run"]) == 2
    p.write_text(yaml.safe_dump(dict(CONFIG, brazos=["D", "D+R"])), encoding="utf-8")   # nombre antiguo
    assert run.main(["--config", str(p), "--adapter", "simulado", "--dry-run"]) == 2


def test_dry_run_no_escribe_nada(cfg_path, tmp_path, capsys):
    salida = tmp_path / "res"
    assert run.main(["--config", str(cfg_path), "--adapter", "simulado", "--dry-run", "--salida", str(salida)]) == 0
    out = capsys.readouterr().out
    assert "TOTAL" in out and "tarifa no verificada" in out and "Recuento de llamadas" in out
    assert not salida.exists()
    assert run.main(["dry-run", "--config", str(cfg_path), "--tarifas", str(TARIFAS)]) == 0
    assert "verificada" in capsys.readouterr().out


def test_estimacion_cuenta_llamadas(cfg_path):
    cfg = X.cargar_config(cfg_path)
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    est = estimar(en, ctx, Tarifas.cargar(TARIFAS), cfg)
    gen = sum(1 for u in en.unidades if not u.brazo.endswith("+1"))
    assert est.llamadas == gen
    # groq:llama-3.3 no tiene tarifa verificada: su costo es None y el total también (nunca un precio supuesto)
    assert est.costo_esperado is None and est.costo_maximo is None
    por_modelo = {f.modelo: f for f in est.filas}
    assert por_modelo["llama-3.3-70b-versatile"].costo_esperado is None
    f = por_modelo["gpt-4.1-mini"]
    assert f.costo_esperado is not None and 0 < f.costo_esperado < f.costo_maximo


def test_runner_completo_reanudable_y_analisis(cfg_path, tmp_path):
    salida = tmp_path / "res"
    args = ["--config", str(cfg_path), "--adapter", "simulado", "--salida", str(salida)]
    assert run.main(args) == 0
    muestras = X.leer_muestras(salida / "muestras.jsonl")
    assert len(muestras) == _esperadas()
    s = muestras[0]
    for clave in ("prompt", "respuesta", "metricas", "solicitud", "latencia", "desenlace", "semilla", "simulado"):
        assert clave in s
    assert all(m["simulado"] and m["adaptador"] == "simulado" and m["procedencia"] == "simulado" for m in muestras)
    assert all(m["metricas"]["tokens_entrada"] and m["metricas"]["latencia_ms"] > 0 for m in muestras)
    dr = [m for m in muestras if m["brazo"] == "D+1"]
    assert dr and all(m["generacion_de"].replace("/D/", "/D+1/") == m["id"] for m in dr)
    assert any(m["metricas"]["llamadas_reparacion"] > 0 for m in dr)     # el perfil 'debil' produce reparaciones
    v3b = [m for m in muestras if m["experimento"] == "v3b" and m["brazo"] == "A"]
    assert v3b and all(m["v3b"]["limite_salida"] == m["max_tokens"] and "respuesta_bruta" in m["v3b"] for m in v3b)
    man = json.loads((salida / "manifiesto.json").read_text(encoding="utf-8"))
    assert man["simulado"] and "SIMULADOS" in man["advertencia"]
    assert man["hashes"]["diseno_sha256"] and man["orden"]["semilla"] is not None

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
    assert analyze.main(["--resultados", str(salida), "--bootstrap", "100"]) == 0
    an = salida / "analisis"
    for nombre in ("resumen_brazos.csv", "resumen_brazo_modelo.csv", "resumen_brazo_tarea.csv", "reparacion.csv",
                   "comparaciones_pareadas.csv", "desenlaces.csv", "latencia_costo.csv", "solicitudes.jsonl", "meta_v2.json",
                   "v3a_truncamiento.csv", "resumen.md", "fig_v2_desenlaces_registros.png", "fig_v2_validez_final.png",
                   "fig_v2_tokens.png", "fig_v3_recuperacion.png", "fig_v4_latencia.png"):
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


def test_presupuesto_previo_y_proyeccion_antes_de_llamar(cfg_path, tmp_path):
    # solo modelos con tarifa verificada en el fixture
    cfg_dict = dict(CONFIG, modelos=[CONFIG["modelos"][0]], repeticiones=1)
    p = tmp_path / "solo_openai.yaml"
    p.write_text(yaml.safe_dump(cfg_dict, allow_unicode=True), encoding="utf-8")
    salida = tmp_path / "res"
    # tope menor que el costo esperado: se rechaza antes de empezar y sin escribir nada
    assert run.main(["--config", str(p), "--adapter", "simulado", "--salida", str(salida), "--tarifas", str(TARIFAS),
                     "--max-costo-usd", "0.000001"]) == 2
    assert not (salida / "muestras.jsonl").exists()
    # sin tarifas no se puede proyectar
    assert run.main(["--config", str(p), "--adapter", "simulado", "--salida", str(salida), "--max-costo-usd", "5"]) == 2
    # durante la ejecución: nunca se gasta más que el tope (la llamada que lo superaría NO se hace)
    cfg = X.cargar_config(p)
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    tarifas = Tarifas.cargar(TARIFAS)
    tope = 0.0105                         # cabe el peor caso de una llamada pero no el de dos seguidas
    ej = X.Ejecutor(cfg, ctx, "simulado", salida, tarifas, max_costo=tope)
    res = ej.ejecutar_estudio(en)
    assert res["abortado"] and res["abortado"].startswith("presupuesto") and res["estado"] == "abortado"
    assert 0 < len(X.leer_muestras(salida / "muestras.jsonl")) < len(en.unidades)
    assert ej.libro.gastado + ej.libro.incierto <= Decimal(str(tope))
    assert res["celdas"]["bloqueado"] > 0


def test_real_exige_confirmacion_autorizacion_y_claves(cfg_path, tmp_path, sin_claves, capsys):
    salida = tmp_path / "real"
    assert run.main(["--config", str(cfg_path), "--adapter", "real", "--salida", str(salida)]) == 2
    assert "--confirmar-real" in capsys.readouterr().err
    assert run.main(["--config", str(cfg_path), "--adapter", "real", "--confirmar-real", "--salida", str(salida),
                     "--max-costo-usd", "5", "--tarifas", str(TARIFAS)]) == 2
    err = capsys.readouterr().err
    assert "autorizado_usd" in err and "OPENAI_API_KEY" in err and "GROQ_API_KEY" in err
    assert "tarifa no verificada" in err                   # llama-3.3 no tiene tarifa verificada
    assert not (salida / "muestras.jsonl").exists() and not salida.exists()


def test_fallo_de_adaptador_se_conserva_y_se_reintenta(cfg_path, tmp_path):
    from minifmt.ai.adapters import Adapter, AdapterError
    from arnes.presupuesto import autorizacion_de_prueba

    class Roto(Adapter):
        provider = "roto"
        supports_structured = True

        def generate(self, system, user, **kw):
            raise AdapterError("HTTP 500 simulado", status=500, retryable=True)

    cfg = X.cargar_config(cfg_path)
    cfg["modelos"] = cfg["modelos"][:1]                      # solo el modelo con tarifa verificada en el fixture
    cfg["max_fallos_seguidos"] = 3
    cfg["controles"] = {"reintentos_por_llamada": 1}
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    adapt = {(m["proveedor"], m["modelo"]): Roto(m["modelo"]) for m in cfg["modelos"]}
    ej = X.Ejecutor(cfg, ctx, "real", tmp_path / "f", Tarifas.cargar(TARIFAS), adaptadores=adapt,
                    autorizacion=autorizacion_de_prueba(), dormir=lambda s: None)
    res = ej.correr(en.unidades)
    assert res["fallos"] == 3 and "fallos seguidos" in res["abortado"]
    assert len((tmp_path / "f" / "fallos.jsonl").read_text(encoding="utf-8").splitlines()) == 6   # 3 celdas × 2 intentos
    muestras = X.leer_muestras(tmp_path / "f" / "muestras.jsonl")
    # el error NO se elimina: queda como muestra clasificada, con sus dos intentos
    assert len(muestras) == 3 and all(m["desenlace"] == "error_tecnico" and m["reintentable"] for m in muestras)
    assert all(len(m["solicitud"]["intentos"]) == 2 for m in muestras)
    assert all(m["metricas"]["perdidos"] == m["metricas"]["solicitados"] for m in muestras)

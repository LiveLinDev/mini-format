"""Dry-run del estudio completo: recuento de llamadas (6 720 nominales, 6 300 a ejecutar, 8 400 primarias), costo con
tarifas disponibles y «tarifa no verificada» donde faltan.  No ejecuta ni escribe nada."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

import run
from arnes import ejecucion as X
from arnes.costos import estimar, recuento
from arnes.tarifas import Tarifas

ROOT = Path(__file__).resolve().parents[3]
ESTUDIO = ROOT / "experiments" / "generativo" / "configs" / "estudio.yaml"
PILOTO = ROOT / "experiments" / "generativo" / "configs" / "piloto.yaml"
TARIFAS = Path(__file__).resolve().parent / "fixtures" / "tarifas_prueba.json"


@pytest.fixture(scope="module")
def estudio():
    cfg = X.cargar_config(ESTUDIO)
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    return cfg, ctx, en


def test_recuento_del_estudio_completo_y_por_que(estudio):
    cfg, ctx, en = estudio
    r = recuento(cfg, en)
    v2, v3b, tot = r["experimentos"]["v2"], r["experimentos"]["v3b"], r["totales"]
    assert v2["primarias_nominales"] == 14 * 4 * 30 * 4 == 6720               # el número del Plan
    assert v2["no_aplicables_primarias"] == 14 * 30 == 420                       # C no aplica a llama-3.3 (estructurado: false)
    assert v2["primarias_a_ejecutar"] == 6300
    assert v3b["primarias_nominales"] == 14 * 4 * 10 * 4 == 2240 and v3b["primarias_a_ejecutar"] == 2100
    assert tot["primarias_a_ejecutar"] == 8400 and tot["primarias_nominales"] == 8960        # 6 300 + 2 100
    assert tot["reparaciones_maximas"] == 6300 + 2100                                           # una ronda por celda X+1
    assert tot["llamadas_maximas"] == 8400 + 8400
    texto = " ".join(r["explicacion"])
    assert "6720" in texto and "menos 420" in texto and "groq:llama-3.3-70b-versatile" in texto and "= 6300" in texto
    assert "= 8400" in texto


def test_no_aplicables_estan_en_el_plan_no_en_las_celdas(estudio):
    cfg, ctx, en = estudio
    assert len(en.no_aplicables) == 420 * 2 + 140 * 2                              # C y C+1, V2 y V3b
    assert all("llama-3.3-70b-versatile" in x["id"] and x["motivo"] for x in en.no_aplicables)
    assert not any(u.modelo == "llama-3.3-70b-versatile" and u.brazo.startswith("C") for u in en.unidades)
    assert len(en.unidades) == 6300 * 2 + 2100 * 2                                   # primarias + celdas de reparación


def test_costo_con_tarifas_disponibles_y_no_verificada_donde_faltan(estudio):
    cfg, ctx, en = estudio
    est = estimar(en, ctx, Tarifas.cargar(TARIFAS), cfg)
    por = {(f.proveedor, f.modelo): f for f in est.filas}
    assert por[("groq", "llama-3.3-70b-versatile")].costo_esperado is None            # no_verificada en el fixture
    assert por[("groq", "llama-3.3-70b-versatile")].tarifa_estado == "no_verificada"
    ok = por[("openai", "gpt-4.1-mini")]
    assert ok.costo_esperado is not None and ok.costo_esperado < ok.costo_maximo and ok.tarifa_estado == "verificada"
    assert est.costo_esperado is None and est.costo_maximo is None                    # el total NO se inventa
    tabla = est.tabla()
    assert "tarifa no verificada" in tabla and "8400" in tabla
    # sin archivo de tarifas todo es «tarifa no verificada»
    vacio = estimar(en, ctx, Tarifas(), cfg)
    assert all(f.costo_esperado is None for f in vacio.filas)


def test_el_costo_maximo_es_la_cota_de_agotar_max_tokens(estudio):
    cfg, ctx, en = estudio
    est = estimar(en, ctx, Tarifas.cargar(TARIFAS), cfg)
    f = {(x.proveedor, x.modelo): x for x in est.filas}[("openai", "gpt-4.1-mini")]
    t = Tarifas.cargar(TARIFAS).obtener("openai", "gpt-4.1-mini")
    manual = (Decimal(str(f.tokens_entrada_max)) * t.entrada_sin_cache + Decimal(str(f.tokens_salida_max)) * t.salida) / 1_000_000
    assert f.costo_maximo == manual


def test_dry_run_no_ejecuta_ni_escribe_ni_crea_adaptadores(tmp_path, monkeypatch, capsys):
    def prohibido(*a, **k):
        raise AssertionError("el dry-run no debe crear adaptadores ni ejecutores")
    monkeypatch.setattr(X, "crear_adaptador", prohibido)
    monkeypatch.setattr(X, "get_adapter", prohibido)
    monkeypatch.setattr(X.Ejecutor, "__init__", prohibido)
    salida = tmp_path / "res"
    salida_json = tmp_path / "dry.json"
    assert run.main(["dry-run", "--config", str(ESTUDIO), "--tarifas", str(TARIFAS), "--json", str(salida_json)]) == 0
    out = capsys.readouterr().out
    assert "TOTAL: 8400 llamadas primarias (nominal 8960, 1120 celdas no aplicables)" in out
    assert "«tarifa no verificada» para: groq:llama-3.3-70b-versatile" in out
    d = json.loads(salida_json.read_text(encoding="utf-8"))
    assert d["recuento"]["totales"]["primarias_a_ejecutar"] == 8400 and d["costo_esperado_usd"] is None
    assert any(m["tarifa"] == "no_verificada" and m["costo_esperado_usd"] is None for m in d["por_modelo"])
    # el flag heredado hace lo mismo y tampoco escribe
    assert run.main(["--config", str(ESTUDIO), "--adapter", "real", "--dry-run", "--salida", str(salida)]) == 0
    assert not salida.exists()


def test_sin_autorizacion_el_diseno_completo_no_se_ejecuta(tmp_path, sin_claves, capsys, monkeypatch):
    monkeypatch.setattr(X, "get_adapter", lambda *a, **k: (_ for _ in ()).throw(AssertionError("llamada real")))
    salida = tmp_path / "res"
    assert run.main(["ejecutar", "--config", str(ESTUDIO), "--adapter", "real", "--confirmar-real", "--max-costo-usd", "40",
                     "--tarifas", str(TARIFAS), "--salida", str(salida)]) == 2
    err = capsys.readouterr().err
    assert "NO autorizada" in err and "autorizado_usd es 0" in err and "tarifa no verificada para groq:llama-3.3-70b-versatile" in err
    assert not salida.exists()


def test_el_piloto_tambien_se_cuenta(capsys):
    cfg = X.cargar_config(PILOTO)
    en = X.enumerar_completo(cfg, X.Contexto(cfg))
    r = recuento(cfg, en)["totales"]
    assert r["primarias_nominales"] == 4 * 3 * 6 * 4 + 4 * 3 * 3 * 4 and r["no_aplicables"] == 2 * (4 * 6 + 4 * 3)

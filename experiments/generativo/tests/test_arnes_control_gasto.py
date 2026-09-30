"""Controles de gasto: autorización, proyección antes de cada llamada, libro, reintentos, usage por categorías,
detención segura, reanudación y estado del estudio.  Ninguna prueba toca la red (adaptadores inyectados)."""
from __future__ import annotations

import json
import signal
from decimal import Decimal
from pathlib import Path

import pytest

import run
from arnes import brazos as B
from arnes import ejecucion as X
from arnes import plan as PL
from arnes import tareas as T
from arnes.presupuesto import (Autorizacion, ErrorAutorizacion, Libro, Presupuesto, autorizacion_de_prueba,
                               validar_autorizacion)
from arnes.tarifas import Tarifas, costo_peor_caso, costo_usage
from arnes.usage import es_negativa, usage_de_respuesta
from minifmt.ai.adapters import Adapter, AdapterError
from minifmt.ai.adapters.base import result

TARIFAS = Path(__file__).resolve().parent / "fixtures" / "tarifas_prueba.json"
MODELOS = [{"proveedor": "openai", "modelo": "gpt-4.1-mini", "estructurado": True}]


def cfg_base(**extra):
    cfg = {"nombre": "gasto", "semilla": 5, "idioma": "es", "temperatura": 0.0, "max_tokens": 4096, "repeticiones": 3,
           "tareas": ["ext-cls"], "brazos": ["A", "D", "D+1"], "modelos": MODELOS, "experimentos": {"v2": {"activo": True}},
           "reparacion": {"max_rondas": 1}, "controles": {"reintentos_por_llamada": 2}, "presupuesto": {}}
    cfg.update(extra)
    return cfg


class Falso(Adapter):
    """Adaptador de prueba: devuelve texto fijo con un usage de estilo OpenAI; cuenta las llamadas."""
    provider = "falso"
    supports_structured = True

    def __init__(self, textos=None, errores=None, usage=None, stop="stop", alllamar=None):
        super().__init__("falso")
        self.llamadas = 0
        self.textos = textos or {}
        self.errores = list(errores or [])
        self.usage = usage or {"prompt_tokens": 1000, "completion_tokens": 500}
        self.stop = stop
        self.alllamar = alllamar

    def generate(self, system, user, *, max_tokens, temperature, response_format=None, seed=None):
        self.llamadas += 1
        if self.alllamar:
            self.alllamar(self)
        if self.errores:
            e = self.errores.pop(0)
            if e is not None:
                raise e
        texto = self.textos.get(system, "{}")
        raw = {"usage": dict(self.usage), "choices": [{"message": {"content": texto}, "finish_reason": self.stop}]}
        return result(texto, self.usage["prompt_tokens"], self.usage["completion_tokens"], 250.0, raw,
                      stop_reason=self.stop, model="gpt-4.1-mini-2025", provider="openai")


def montar(tmp_path, cfg=None, adaptador=None, **kw):
    cfg = cfg or cfg_base()
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    ad = adaptador or Falso()
    ej = X.Ejecutor(cfg, ctx, "real", tmp_path / "res", Tarifas.cargar(TARIFAS), adaptadores={("openai", "gpt-4.1-mini"): ad},
                    autorizacion=kw.pop("autorizacion", autorizacion_de_prueba()), dormir=kw.pop("dormir", lambda s: None), **kw)
    return cfg, ctx, en, ej, ad


# ------------------------------------------------------------------ autorización
def _modelos_ok():
    return [{"proveedor": "openai", "modelo": "gpt-4.1-mini"}]


def test_por_defecto_nada_esta_autorizado():
    assert Presupuesto.desde_config({}).autorizado_usd == 0
    with pytest.raises(ErrorAutorizacion) as e:
        validar_autorizacion(Presupuesto.desde_config({}), 5.0, Tarifas.cargar(TARIFAS), _modelos_ok(),
                             costo_esperado=Decimal(1), costo_maximo=Decimal(2))
    assert "autorizado_usd es 0" in str(e.value)


def test_cada_condicion_de_rechazo_se_informa():
    tar = Tarifas.cargar(TARIFAS)
    firmado = Presupuesto(Decimal(10), None, "Responsable", "2026-10-01")
    ok = validar_autorizacion(firmado, 5.0, tar, _modelos_ok(), costo_esperado=Decimal(1), costo_maximo=Decimal(3))
    assert isinstance(ok, Autorizacion) and ok.tope_usd == Decimal(5)
    def motivos(**kw):
        a = dict(presupuesto=firmado, max_costo_usd=5.0, tarifas=tar, modelos=_modelos_ok(),
                 costo_esperado=Decimal(1), costo_maximo=Decimal(3), claves_faltantes=())
        a.update(kw)
        with pytest.raises(ErrorAutorizacion) as e:
            validar_autorizacion(a.pop("presupuesto"), a.pop("max_costo_usd"), a.pop("tarifas"), a.pop("modelos"), **a)
        return " | ".join(e.value.errores)
    assert "falta --max-costo-usd" in motivos(max_costo_usd=None)
    assert "supera lo autorizado" in motivos(max_costo_usd=11.0)
    assert "firmado_por" in motivos(presupuesto=Presupuesto(Decimal(10), None, "", "2026-10-01"))
    assert "fecha" in motivos(presupuesto=Presupuesto(Decimal(10), None, "Responsable", ""))
    assert "tarifa no verificada para groq:llama-3.3-70b-versatile" in motivos(modelos=[{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile"}])
    assert "tarifa no verificada para openai:no-existe (ausente)" in motivos(modelos=[{"proveedor": "openai", "modelo": "no-existe"}])
    assert "no cabe" in motivos(costo_esperado=Decimal(6))
    assert "costo esperado/máximo" in motivos(costo_esperado=None)
    assert "OPENAI_API_KEY" in motivos(claves_faltantes=["OPENAI_API_KEY"])


def test_la_autorizacion_no_se_puede_fabricar():
    with pytest.raises(ErrorAutorizacion):
        Autorizacion(tope_usd=Decimal(100), presupuesto=Presupuesto())


def test_ejecutor_real_sin_autorizacion_no_llama_a_nadie(tmp_path):
    cfg = cfg_base()
    ad = Falso()
    with pytest.raises(ErrorAutorizacion):
        X.Ejecutor(cfg, X.Contexto(cfg), "real", tmp_path / "x", Tarifas.cargar(TARIFAS), adaptadores={("openai", "gpt-4.1-mini"): ad})
    assert ad.llamadas == 0 and not (tmp_path / "x" / "muestras.jsonl").exists()


def test_modelo_sin_tarifa_verificada_no_se_llama_ni_siquiera_con_autorizacion(tmp_path):
    cfg = cfg_base(modelos=[{"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False}], brazos=["A"])
    ctx = X.Contexto(cfg)
    en = X.enumerar_completo(cfg, ctx)
    ad = Falso()
    ej = X.Ejecutor(cfg, ctx, "real", tmp_path / "r", Tarifas.cargar(TARIFAS), adaptadores={("groq", "llama-3.3-70b-versatile"): ad},
                    autorizacion=autorizacion_de_prueba())
    res = ej.correr(en.unidades)
    assert ad.llamadas == 0 and "tarifa no verificada" in res["abortado"]


def test_run_real_rechaza_sin_llamar_y_sin_escribir(tmp_path, sin_claves, monkeypatch, capsys):
    import yaml
    cfg = cfg_base()
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    llamadas = []
    monkeypatch.setattr(X, "get_adapter", lambda *a, **k: llamadas.append(a))
    salida = tmp_path / "res"
    # falta --max-costo-usd, falta la autorización y faltan claves: nada de eso llama a un adaptador
    assert run.main(["--config", str(p), "--adapter", "real", "--confirmar-real", "--salida", str(salida), "--tarifas", str(TARIFAS)]) == 2
    err = capsys.readouterr().err
    assert "falta --max-costo-usd" in err and "autorizado_usd" in err and "OPENAI_API_KEY" in err
    assert llamadas == [] and not salida.exists()


# ------------------------------------------------------------------ usage por categorías (sin doble conteo) y costo
def test_usage_openai_con_cache_y_razonamiento_sin_doble_conteo():
    r = {"raw": {"usage": {"prompt_tokens": 1000, "completion_tokens": 500,
                           "prompt_tokens_details": {"cached_tokens": 400},
                           "completion_tokens_details": {"reasoning_tokens": 200}}}}
    u = usage_de_respuesta("openai", r)
    assert u["entrada_sin_cache"] == 600 and u["entrada_cache_lectura"] == 400 and u["entrada_cache_escritura"] == 0
    assert u["salida"] == 500 and u["razonamiento"] == 200 and u["razonamiento_incluido_en_salida"] is True
    # 600·1 + 400·0,10 + 500·2 = 1640 millonésimas de USD (el razonamiento ya está en la salida: no se suma otra vez)
    tar = Tarifas.cargar(TARIFAS).obtener("openai", "gpt-4.1-mini")
    assert costo_usage(tar, u) == Decimal("0.001640")


def test_usage_anthropic_separa_las_categorias_de_cache():
    r = {"raw": {"usage": {"input_tokens": 100, "cache_read_input_tokens": 300, "cache_creation_input_tokens": 50,
                           "output_tokens": 70}}, "input_tokens": 450, "output_tokens": 70}     # el adaptador suma la entrada
    u = usage_de_respuesta("anthropic", r)
    assert (u["entrada_sin_cache"], u["entrada_cache_lectura"], u["entrada_cache_escritura"], u["salida"]) == (100, 300, 50, 70)
    assert u["razonamiento"] is None
    tar = Tarifas.cargar(TARIFAS).obtener("anthropic", "claude-haiku-4-5")
    assert costo_usage(tar, u) == (Decimal(100) * 1 + Decimal(300) * Decimal("0.10") + Decimal(50) * Decimal("1.25") + Decimal(70) * 5) / 1_000_000


def test_razonamiento_fuera_de_la_salida_se_suma_aparte_y_otros_usd():
    tar = Tarifas.cargar(TARIFAS).obtener("openai", "gpt-4.1-mini")
    u = {"entrada_sin_cache": 0, "entrada_cache_lectura": 0, "entrada_cache_escritura": 0, "salida": 100, "razonamiento": 50,
         "razonamiento_incluido_en_salida": False, "otros_usd": {"busqueda": "0.01"}}
    assert costo_usage(tar, u) == Decimal(150) * 2 / 1_000_000 + Decimal("0.01")


def test_sin_usage_o_sin_tarifa_el_costo_es_none_nunca_cero():
    tar = Tarifas.cargar(TARIFAS)
    assert usage_de_respuesta("openai", {"raw": {"choices": []}}) is None
    assert costo_usage(tar.obtener("openai", "gpt-4.1-mini"), None) is None
    assert costo_usage(tar.obtener("groq", "llama-3.3-70b-versatile"), {"salida": 5}) is None     # no_verificada
    assert costo_usage(None, {"salida": 5}) is None                                                # ausente
    assert costo_peor_caso(tar.obtener("groq", "llama-3.3-70b-versatile"), 100, 100) is None
    assert tar.estado("groq", "llama-3.3-70b-versatile") == "no_verificada" and tar.estado("x", "y") == "ausente"


def test_negativa_se_detecta():
    assert es_negativa("openai", {"stop_reason": "stop", "raw": {"choices": [{"message": {"refusal": "no puedo"}}]}})
    assert es_negativa("anthropic", {"stop_reason": "refusal", "raw": {}})
    assert not es_negativa("openai", {"stop_reason": "stop", "raw": {"choices": [{"message": {"content": "hola"}}]}})


def test_la_solicitud_lleva_intentos_con_usage_y_costo(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1)
    ad = Falso(usage={"prompt_tokens": 1000, "completion_tokens": 500, "prompt_tokens_details": {"cached_tokens": 200}})
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    t = ctx.tareas["ext-cls"]
    ad.textos[ctx.prompt(t, "A").system] = B.salida_referencia(t, "A")
    res = ej.ejecutar_estudio(en)
    assert res["estado"] == "completo"
    s = X.leer_muestras(tmp_path / "res" / "muestras.jsonl")[0]
    sol = s["solicitud"]
    assert set(sol) >= {"id", "grupo", "registros_solicitados", "registros_validos_finales", "intentos"}
    assert sol["registros_solicitados"] == len(t.registros) and sol["registros_validos_finales"] == len(t.registros)
    (i,) = sol["intentos"]
    assert i["fase"] == "generacion" and i["proveedor"] == "openai" and i["modelo"] == "gpt-4.1-mini"
    assert i["usage"]["entrada_sin_cache"] == 800 and i["usage"]["entrada_cache_lectura"] == 200 and i["usage"]["salida"] == 500
    assert i["latencia_s"] == 0.25 and Decimal(i["costo_usd"]) == Decimal("0.001820")
    assert s["costo_usd"] == "0.00182" and s["procedencia"] == "api_real" and s["desenlace"] == "ok"
    assert ej.libro.gastado == Decimal("0.001820")


# ------------------------------------------------------------------ proyección ANTES de llamar
def test_la_proyeccion_bloquea_antes_de_la_llamada(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=2)
    ad = Falso()
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad, autorizacion=autorizacion_de_prueba(0.0001))
    res = ej.ejecutar_estudio(en)
    assert ad.llamadas == 0 and res["abortado"].startswith("presupuesto") and "supera el tope" in res["abortado"]
    assert res["celdas"]["bloqueado"] == len(en.unidades) and res["estado"] == "abortado"


def test_el_gasto_nunca_supera_el_tope(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=6)
    ad = Falso()
    # peor caso de una llamada ≈ 4096·2e-6 + entrada ≈ 0,0097: con tope 0,02 caben 1 o 2 llamadas (gasto real ≈ 0,002)
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad, autorizacion=autorizacion_de_prueba(0.0115))
    res = ej.ejecutar_estudio(en)
    assert res["abortado"] and ad.llamadas >= 1
    assert ej.libro.gastado + ej.libro.incierto <= Decimal("0.0115")
    # un tope que deja pasar la primera llamada pero no una segunda proyectada antes de gastar
    assert ad.llamadas == len(X.leer_muestras(tmp_path / "res" / "muestras.jsonl"))


def test_por_celda_max_usd(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1, presupuesto={"por_celda_max_usd": 0.0001})
    cfg, ctx, en, ej, ad = montar(tmp_path, cfg)
    res = ej.ejecutar_estudio(en)
    assert ad.llamadas == 0 and "por_celda_max_usd" in res["abortado"]


def test_libro_orfanas_y_reanudacion(tmp_path):
    ruta = tmp_path / "libro.jsonl"
    lib = Libro(ruta, Decimal("1.0"))
    a = lib.iniciar("c1", "generacion", Decimal("0.3"))
    lib.terminar(a, ok=True, costo=Decimal("0.1"))
    lib.iniciar("c2", "generacion", Decimal("0.2"))                   # el proceso murió: sin fin
    lib2 = Libro(ruta, Decimal("1.0"))
    assert lib2.gastado == Decimal("0.1") and lib2.incierto == Decimal("0.2") and lib2.huerfanas == 1
    assert lib2.proyectar(Decimal("0.7")) is None and lib2.proyectar(Decimal("0.71")) is not None   # 0,1 + 0,2 + 0,7 = 1,0
    assert "tarifa no verificada" in lib2.proyectar(None)


# ------------------------------------------------------------------ reintentos y errores
def test_reintentos_se_registran_uno_a_uno(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1)
    esperas = []
    ad = Falso(errores=[AdapterError("HTTP 503", status=503, retryable=True), AdapterError("HTTP 429", status=429, retryable=True), None])
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad, dormir=esperas.append)
    t = ctx.tareas["ext-cls"]
    ad.textos[ctx.prompt(t, "A").system] = B.salida_referencia(t, "A")
    ej.ejecutar_estudio(en)
    s = X.leer_muestras(tmp_path / "res" / "muestras.jsonl")[0]
    est = [i["estado"] for i in s["solicitud"]["intentos"]]
    assert est == ["error", "error", "ok"] and [i["status"] for i in s["solicitud"]["intentos"][:2]] == [503, 429]
    assert esperas == [1.0, 2.0] and ad.llamadas == 3
    assert s["desenlace"] == "ok" and s["reintentable"] is False
    # los intentos fallidos con status no se cobran; el libro anota las tres llamadas
    assert ej.libro.llamadas == 3 and ej.libro.incierto == 0


def test_error_sin_status_cuenta_como_gasto_incierto(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1, controles={"reintentos_por_llamada": 0})
    ad = Falso(errores=[AdapterError("timeout", retryable=True)])
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    ej.ejecutar_estudio(en)
    assert ej.libro.incierto > 0          # pudo facturarse: se cuenta el peor caso
    s = X.leer_muestras(tmp_path / "res" / "muestras.jsonl")[0]
    assert s["desenlace"] == "error_tecnico" and s["solicitud"]["intentos"][0]["costo_incierto"] is True


def test_error_no_reintentable_y_posible_no_aplicable_en_C(tmp_path):
    cfg = cfg_base(brazos=["C"], repeticiones=1)
    ad = Falso(errores=[AdapterError("HTTP 400 schema no soportado", status=400, retryable=False)])
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    ej.ejecutar_estudio(en)
    s = X.leer_muestras(tmp_path / "res" / "muestras.jsonl")[0]
    assert ad.llamadas == 1 and s["reintentable"] is False and s["posible_no_aplicable"] is True
    assert s["desenlace"] == "error_tecnico" and s["solicitud"]["registros_validos_finales"] == 0


def test_error_reintentable_arrastra_los_intentos_fallidos_al_reanudar(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1, controles={"reintentos_por_llamada": 0})
    ad = Falso(errores=[AdapterError("HTTP 500", status=500, retryable=True), None])
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    t = ctx.tareas["ext-cls"]
    ad.textos[ctx.prompt(t, "A").system] = B.salida_referencia(t, "A")
    r1 = ej.ejecutar_estudio(en)
    assert r1["celdas"]["pendiente"] == 1 and r1["estado"] == "parcial"            # no está «hecha»: se reintenta
    _, _, _, ej2, _ = montar(tmp_path, cfg, ad)
    r2 = ej2.ejecutar_estudio(en)
    assert r2["estado"] == "completo"
    ms = X.leer_muestras(tmp_path / "res" / "muestras.jsonl")
    assert len(ms) == 1 and [i["estado"] for i in ms[0]["solicitud"]["intentos"]] == ["error", "ok"]      # nada se ocultó
    lineas = (tmp_path / "res" / "muestras.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2                                                          # el error sigue en el archivo (append-only)


def test_negativa_y_respuesta_vacia_y_corte_se_clasifican(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1)
    for stop, texto, esperado in (("length", "{\"messages\": [{\"id\"", "truncada"), ("stop", "   ", "vacia"),
                                  ("stop", "no puedo ayudar con eso", "formato_invalido")):
        ad = Falso(stop=stop)
        cfg2, ctx, en, ej, _ = montar(tmp_path / stop / esperado, cfg, ad)
        ad.textos[ctx.prompt(ctx.tareas["ext-cls"], "A").system] = texto
        ej.ejecutar_estudio(en)
        s = X.leer_muestras(tmp_path / stop / esperado / "res" / "muestras.jsonl")[0]
        assert s["desenlace"] == esperado and s["respuesta"]["text"] == texto       # la respuesta bruta se conserva
        assert s["metricas"]["solicitados"] == len(ctx.tareas["ext-cls"].registros) and s["metricas"]["validos_finales"] == 0
    # negativa del proveedor
    ad = Falso(stop="stop")
    cfg2, ctx, en, ej, _ = montar(tmp_path / "neg", cfg, ad)

    def generate(system, user, **kw):
        raw = {"usage": {"prompt_tokens": 10, "completion_tokens": 3}, "choices": [{"message": {"refusal": "no puedo"}, "finish_reason": "stop"}]}
        return result("no puedo", 10, 3, 100.0, raw, stop_reason="stop", model="m", provider="openai")
    ad.generate = generate
    ej.ejecutar_estudio(en)
    assert X.leer_muestras(tmp_path / "neg" / "res" / "muestras.jsonl")[0]["desenlace"] == "negativa"


# ------------------------------------------------------------------ detención segura y reanudación
def test_detencion_segura_deja_estado_y_celdas_faltantes_con_motivo(tmp_path):
    cfg = cfg_base(brazos=["A", "D", "D+1"], repeticiones=3)
    disparo = {"n": 0}

    def cuando(ad):
        disparo["n"] += 1
        if disparo["n"] == 3:
            ej.solicitar_detencion("SIGINT")
    ad = Falso(alllamar=cuando)
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    res = ej.ejecutar_estudio(en)
    assert res["interrumpido"] == "SIGINT" and res["estado"] == "interrumpido"
    est = json.loads((tmp_path / "res" / "estado_estudio.json").read_text(encoding="utf-8"))
    assert est["estado"] == "interrumpido" and est["interrupcion"]["senal"] == "SIGINT"
    c = est["celdas"]
    assert c["hecha"] + c["error_tecnico"] == 3                      # la llamada en curso terminó y se guardó
    assert sum(c.values()) == len(en.unidades) + len(en.no_aplicables)     # todas las celdas contabilizadas
    falt = [json.loads(l) for l in (tmp_path / "res" / "celdas_faltantes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(falt) == c["pendiente"] + c["bloqueado"] + c["no_aplicable"]
    assert all(f["motivo"] for f in falt) and {f["estado"] for f in falt} == {"pendiente"}
    assert "interrupción" in falt[0]["motivo"]


def test_senal_real_sigint_es_capturada_y_restaura_el_manejador(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=3)
    previo = signal.getsignal(signal.SIGINT)
    n = {"k": 0}

    def cuando(ad):
        n["k"] += 1
        if n["k"] == 2:
            signal.raise_signal(signal.SIGINT)
    ad = Falso(alllamar=cuando)
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad)
    res = ej.ejecutar_estudio(en)                                     # no debe propagar KeyboardInterrupt
    assert res["interrumpido"] == "SIGINT" and ad.llamadas == 2
    assert signal.getsignal(signal.SIGINT) is previo


def test_segunda_senal_interrumpe_la_llamada_y_cuenta_el_peor_caso_como_incierto(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=2)

    def cuando(ad):
        ej.solicitar_detencion("SIGINT")
        ej.solicitar_detencion("SIGINT")                            # segunda señal: KeyboardInterrupt dentro de la llamada
    cfg, ctx, en, ej, ad = montar(tmp_path, cfg, Falso(alllamar=cuando))
    res = ej.ejecutar_estudio(en)
    assert res["interrumpido"] and res["estado"] == "interrumpido"
    assert ej.libro.incierto > 0 and ej.libro.huerfanas == 0
    assert not (tmp_path / "res" / "muestras.jsonl").exists() or not X.leer_muestras(tmp_path / "res" / "muestras.jsonl")


def test_reanudacion_exacta_sin_duplicar_y_conteos_por_estado_suman_el_total(tmp_path):
    cfg = cfg_base(brazos=["A", "D", "D+1"], repeticiones=4)
    cfg, ctx, en, ej, ad = montar(tmp_path, cfg)
    r1 = ej.ejecutar_estudio(en, limite=5)
    assert r1["estado"] == "parcial" and r1["ejecutadas"] == 5
    c = r1["celdas"]
    assert sum(c.values()) == len(en.unidades) + len(en.no_aplicables) and c["hecha"] == 5
    ids1 = {m["id"] for m in X.leer_muestras(tmp_path / "res" / "muestras.jsonl")}
    _, _, _, ej2, ad2 = montar(tmp_path, cfg)
    r2 = ej2.ejecutar_estudio(en)
    assert r2["estado"] == "completo" and r2["saltadas"] == 5 and r2["ejecutadas"] == len(en.unidades) - 5
    lineas = (tmp_path / "res" / "muestras.jsonl").read_text(encoding="utf-8").splitlines()
    ids = [json.loads(l)["id"] for l in lineas]
    assert len(ids) == len(set(ids)) == len(en.unidades) and ids1 <= set(ids)
    assert sum(r2["celdas"].values()) == len(en.unidades)
    assert json.loads((tmp_path / "res" / "estado_estudio.json").read_text(encoding="utf-8"))["reanudaciones"] == 1
    # el estado persistido coincide con el recuento calculado
    falt = (tmp_path / "res" / "celdas_faltantes.jsonl").read_text(encoding="utf-8").strip()
    assert falt == ""


def test_la_reparacion_espera_a_su_base(tmp_path):
    cfg = cfg_base(brazos=["D", "D+1"], repeticiones=1)
    ad = Falso(errores=[AdapterError("HTTP 500", status=500, retryable=True)] * 3, )
    cfg, ctx, en, ej, _ = montar(tmp_path, cfg, ad, dormir=lambda s: None)
    res = ej.ejecutar_estudio(en)
    # D falla tras sus 3 intentos: la celda D+1 queda BLOQUEADA con su motivo (no se inventa una respuesta base)
    assert res["celdas"]["bloqueado"] + res["celdas"]["pendiente"] >= 1
    falt = [json.loads(l) for l in (tmp_path / "res" / "celdas_faltantes.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any("D+1" in f["id"] and f["estado"] == "bloqueado" and "base" in f["motivo"] for f in falt)


# ------------------------------------------------------------------ manifiesto y candado
def _yaml(tmp_path, cfg, nombre="c.yaml"):
    import yaml
    p = tmp_path / nombre
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    return str(p)


def test_reanudar_con_otro_diseno_se_rechaza_salvo_nueva_version(tmp_path, capsys):
    cfg = cfg_base(modelos=[dict(MODELOS[0], perfil_simulado="medio")], brazos=["A", "D"], repeticiones=2)
    salida = str(tmp_path / "res")
    args = ["--adapter", "simulado", "--salida", salida]
    assert run.main(["--config", _yaml(tmp_path, cfg)] + args) == 0
    man1 = (tmp_path / "res" / "manifiesto.json").read_text(encoding="utf-8")
    cambiado = dict(cfg, temperatura=0.9)
    assert run.main(["--config", _yaml(tmp_path, cambiado, "c2.yaml")] + args) == 2
    assert "el diseño cambió" in capsys.readouterr().err
    assert (tmp_path / "res" / "manifiesto.json").read_text(encoding="utf-8") == man1          # inmutable
    assert run.main(["--config", _yaml(tmp_path, cambiado, "c2.yaml")] + args + ["--nueva-version", "cambio de temperatura"]) == 0
    v = [json.loads(l) for l in (tmp_path / "res" / "versiones.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(v) == 1 and v[0]["motivo"] == "cambio de temperatura" and (tmp_path / "res" / "manifiesto.v1.json").exists()
    # el presupuesto NO forma parte del diseño: firmarlo después no invalida nada
    firmado = dict(cambiado, presupuesto={"autorizado_usd": 5, "firmado_por": "X", "fecha": "2026-10-01"})
    assert run.main(["--config", _yaml(tmp_path, firmado, "c3.yaml")] + args) == 0


def test_no_se_mezclan_simulado_y_real_en_el_mismo_directorio(tmp_path, capsys, sin_claves):
    cfg = cfg_base(modelos=[dict(MODELOS[0], perfil_simulado="medio")], brazos=["A"], repeticiones=1)
    salida = str(tmp_path / "res")
    assert run.main(["--config", _yaml(tmp_path, cfg), "--adapter", "simulado", "--salida", salida]) == 0
    hashes = json.loads((tmp_path / "res" / "manifiesto.json").read_text(encoding="utf-8"))["hashes"]
    with pytest.raises(PL.ErrorReanudacion, match="otro adaptador"):
        PL.verificar_reanudacion(tmp_path / "res", "real", hashes, None)


def test_candado_de_directorio(tmp_path):
    with PL.Candado(tmp_path):
        with pytest.raises(PL.ErrorCandado):
            PL.Candado(tmp_path).__enter__()
    assert not (tmp_path / "ejecucion.lock").exists()
    (tmp_path / "ejecucion.lock").write_text("pid=1", encoding="utf-8")            # huérfano
    with pytest.raises(PL.ErrorCandado):
        PL.Candado(tmp_path).__enter__()
    with PL.Candado(tmp_path, forzar=True):
        pass


def test_plan_y_manifiesto_quedan_escritos(tmp_path):
    cfg = cfg_base(modelos=[dict(MODELOS[0], perfil_simulado="medio")], brazos=["A", "C", "C+1"], repeticiones=1,
                   modelos_extra=None)
    cfg["modelos"] = [dict(MODELOS[0], perfil_simulado="medio"),
                      {"proveedor": "groq", "modelo": "llama-3.3-70b-versatile", "estructurado": False, "perfil_simulado": "medio"}]
    assert run.main(["--config", _yaml(tmp_path, cfg), "--adapter", "simulado", "--salida", str(tmp_path / "res")]) == 0
    plan = [json.loads(l) for l in (tmp_path / "res" / "plan.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [p["estado"] for p in plan].count("no_aplicable") == 2 and sum(1 for p in plan if p["estado"] == "pendiente") == 4
    assert all(p["motivo"] for p in plan if p["estado"] == "no_aplicable")
    man = json.loads((tmp_path / "res" / "manifiesto.json").read_text(encoding="utf-8"))
    h = man["hashes"]
    assert set(h) >= {"config_sha256", "prompts_sha256", "contratos", "conjuntos", "orden_sha256", "diseno_sha256", "codigo_arnes_sha256"}
    assert all(len(c["sha256"]) == 64 for c in h["contratos"] + h["conjuntos"]) and h["conjuntos"][0]["sintetico"] is True
    assert man["condiciones_ejecucion"]["red"] == "simulada" and man["orden"]["semilla"] == man["orden"]["semilla"]


def test_adaptadores_reales_se_crean_sin_reintentos_propios_y_sin_red():
    """Los reintentos los hace el arnés (cada uno se proyecta y se registra): los de los adaptadores quedan en 0."""
    for prov in ("openai", "anthropic", "groq", "deepseek"):
        ad = X.crear_adaptador({"proveedor": prov, "modelo": "m", "estructurado": True}, "real", None, 1)
        assert getattr(ad, "_max_retries", getattr(ad, "retries", None)) == 0, prov


def test_usage_deepseek_y_groq_compatibles():
    r = {"raw": {"usage": {"prompt_tokens": 900, "completion_tokens": 100, "prompt_cache_hit_tokens": 600,
                           "prompt_cache_miss_tokens": 300}}}
    u = usage_de_respuesta("deepseek", r)
    assert (u["entrada_sin_cache"], u["entrada_cache_lectura"], u["salida"]) == (300, 600, 100)
    g = usage_de_respuesta("groq", {"raw": {"usage": {"prompt_tokens": 50, "completion_tokens": 10, "queue_time": 0.1}}})
    assert (g["entrada_sin_cache"], g["entrada_cache_lectura"], g["razonamiento"]) == (50, 0, None)


def test_estado_inicial_no_dice_error_reintentable(tmp_path):
    cfg = cfg_base(brazos=["A"], repeticiones=1)
    cfg, ctx, en, ej, ad = montar(tmp_path, cfg)
    c, falt = ej._contadores(en, {"inicial": True}, None)
    assert c["pendiente"] == len(en.unidades) and all(f["motivo"] == "aún no ejecutada" for f in falt)

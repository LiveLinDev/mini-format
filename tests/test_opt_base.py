"""OPT: tokenizadores locales, conjuntos de datos deterministas y reglas de la medición.

Los oráculos son independientes del código bajo prueba: valores publicados de GPT-2 para r50k_base, hashes
oficiales de los vocabularios, propiedades de los generadores y casos construidos a mano para el punto de equilibrio.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "src", ROOT / "experiments", ROOT / "tools"):
    sys.path.insert(0, str(p))

from optimizacion import datos, medir, tokenizadores  # noqa: E402

# sha256 oficiales de los vocabularios (los mismos expected_hash de tiktoken_ext.openai_public)
HASHES = {
    "o200k_base": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
    "cl100k_base": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    "r50k_base": "306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930",
}


# ------------------------------------------------------------------------- tokenizadores
@pytest.mark.parametrize("nombre", sorted(HASHES))
def test_vocabulario_archivado_tiene_el_hash_oficial(nombre):
    ruta = ROOT / "benchmark" / "vocab" / f"{nombre}.tiktoken"
    assert hashlib.sha256(ruta.read_bytes()).hexdigest() == HASHES[nombre]


def test_r50k_reproduce_los_ids_publicados_de_gpt2():
    t = tokenizadores.obtener("r50k_base")
    assert t.ids("Hello world") == [15496, 995]
    assert t.ids("hello world") == [31373, 995]


@pytest.mark.parametrize("nombre", sorted(HASHES))
def test_el_respaldo_en_python_puro_cuenta_igual_que_tiktoken(nombre):
    rapido, puro = tokenizadores.obtener(nombre), tokenizadores.Tokenizador(nombre, forzar_puro=True)
    textos = ["tke|n=2\n1041|a|a|No puede iniciar sesión tras cambiar la contraseña|2",
              '{"tickets":[{"id":"T-1041","prioridad":"alta"}]}', "Capacitación sobre el módulo de reportes",
              "línea 1\\nlínea 2 | con barra \\\\ y comillas \"x\"", ""]
    for t in textos:
        assert rapido.contar(t) == puro.contar(t), (nombre, t)


def test_el_total_se_cuenta_sobre_el_texto_concatenado_no_sumando_fragmentos():
    t = tokenizadores.obtener("o200k_base")
    a, b = "hel", "lo"
    assert t.contar(a + b) != t.contar(a) + t.contar(b)      # «hello» es un solo token; por partes son dos


def test_tokenizador_desconocido_se_rechaza():
    with pytest.raises(ValueError):
        tokenizadores.Tokenizador("p50k_base")


# ------------------------------------------------------------------------- datos
GENERADORES = {"tickets": datos.generar_tickets, "eventos": datos.generar_eventos}


@pytest.mark.parametrize("dom", sorted(GENERADORES))
def test_generadores_son_deterministas_y_anidados(dom):
    g = GENERADORES[dom]
    a, b = g(datos.SEMILLA_PRUEBA, 0, 40), g(datos.SEMILLA_PRUEBA, 0, 40)
    assert a == b
    assert g(datos.SEMILLA_PRUEBA, 0, 7) == a[:7]            # el lote de n es prefijo del de m > n
    assert g(datos.SEMILLA_DESARROLLO, 0, 40) != a           # desarrollo y prueba no se mezclan
    assert g(datos.SEMILLA_PRUEBA, 1, 40) != a               # los lotes son distintos


def test_eventos_tienen_fecha_constante_por_lote_y_distinta_entre_lotes():
    l0, l1 = datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 60), datos.generar_eventos(datos.SEMILLA_PRUEBA, 1, 60)
    assert len({r["fecha"] for r in l0}) == 1 and len({r["fecha"] for r in l1}) == 1
    assert l0[0]["fecha"] != l1[0]["fecha"]
    horas = [r["hora"] for r in l0]
    assert horas == sorted(horas)                            # cronológico


def test_tickets_respetan_el_esquema_de_la_aplicacion():
    regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 300)
    assert {r["prioridad"] for r in regs} <= set(datos.TICKETS_ENUM_PRIORIDAD)
    assert {r["categoria"] for r in regs} <= set(datos.TICKETS_ENUM_CATEGORIA)
    assert all(0 <= r["horas"] <= 40 and isinstance(r["horas"], int) for r in regs)
    ids = [r["id"] for r in regs]
    assert len(set(ids)) == len(ids) and all(i.startswith("T-") and i[2:].isdigit() and i[2] != "0" for i in ids)


@pytest.mark.parametrize("dom", sorted(GENERADORES) + ["comentarios"])
def test_los_datos_no_traen_espacios_en_los_extremos_ni_cadenas_vacias(dom):
    """Límite conocido del serializador (espacio exterior y «» se alteran en silencio): los datos medidos no los usan."""
    g = GENERADORES.get(dom) or datos.generar_comentarios
    for lote in range(2):
        for r in g(datos.SEMILLA_PRUEBA, lote, 50):
            for v in r.values():
                if isinstance(v, str):
                    assert v == v.strip() and v != "" and "\r" not in v


def test_comentarios_particion_de_desarrollo_y_prueba_es_disjunta_y_completa():
    todos = datos.cargar_comentarios()
    dev, prueba = todos[datos.COM_DESARROLLO], todos[datos.COM_PRUEBA]
    assert len(dev) + len(prueba) == len(todos) == 500
    assert not ({c["id"] for c in dev} & {c["id"] for c in prueba})
    assert datos.generar_comentarios(datos.SEMILLA_PRUEBA, 0, 5) == prueba[:5]
    assert datos.generar_comentarios(datos.SEMILLA_DESARROLLO, 0, 5) == dev[:5]


def test_snapshot_de_comentarios_tiene_el_sha256_registrado():
    esperado = "400a33270b7ae5f080e5eb48afdfae1fd7426fd50e385e5197bab811c20e611d"      # benchmark/public/sources.json
    assert hashlib.sha256(datos.COMENTARIOS.read_bytes()).hexdigest() == esperado


# ------------------------------------------------------------------------- equilibrio
def _curva(diffs, dom="d", tk="t", perfil="especializado", instr="compacta_con_ejemplo"):
    """Filas de curva cuyo 'JSON menos .mini' vale exactamente ``diffs[n-1]`` tokens de total y de salida."""
    filas = []
    for i, d in enumerate(diffs, start=1):
        base = {"dominio": dom, "tokenizador": tk, "n": i, "lote": 0}
        filas.append({**base, "perfil": "json_compacto", "instruccion": "ninguna", "tokens_salida": 1000 + d, "tokens_instruccion": 0, "tokens_total": 1000 + d})
        for v in ("schema_sin_ejemplo", "schema_con_ejemplo"):
            filas.append({**base, "perfil": "json_compacto", "instruccion": v, "tokens_salida": 1000 + d, "tokens_instruccion": 50, "tokens_total": 1050 + d})
        filas.append({**base, "perfil": perfil, "instruccion": instr, "tokens_salida": 1000, "tokens_instruccion": 10, "tokens_total": 1000})
    return filas


def _n_estrella(diffs, comparador="total"):
    eq = medir.equilibrios(_curva(diffs))
    fila = next(e for e in eq if e["perfil"] == "especializado" and e["comparador"] == comparador and e["instruccion"] in ("compacta_con_ejemplo", "no_aplica"))
    return fila


def test_equilibrio_es_el_cruce_persistente_no_el_primero():
    diffs = [-9, -5, 1, -2, 3, 4, 6, 8] + [9] * 110 + [10] * 132          # 250 puntos; cruza en 3, vuelve a perder en 4, gana desde 5
    f = _n_estrella(diffs)
    assert f["primer_n_con_ahorro"] == 3 and f["n_estrella"] == 5 and f["existe"] is True


def test_equilibrio_no_existe_si_siempre_pierde_y_extrapola_solo_si_la_pendiente_es_positiva():
    # JSON menos .mini crece 1 token por registro pero empieza en -400: a n=250 todavía pierde
    diffs = [-400 + i for i in range(250)]
    f = _n_estrella(diffs)
    assert f["n_estrella"] is None and f["existe"] is False
    assert f["pendiente_ahorro_por_registro"] == 1.0 and f["n_extrapolado_no_medido"] == 250 + 151.0
    plano = _n_estrella([-5] * 250)
    assert plano["n_estrella"] is None and plano["n_extrapolado_no_medido"] is None      # sin pendiente no se extrapola


def test_equilibrio_respecto_al_json_con_esquema_es_mas_temprano_que_respecto_al_json_sin_instruccion():
    diffs = [-30 + i for i in range(250)]                                   # 1050 + d frente a 1000: el esquema suma 50
    sin = _n_estrella(diffs, "total")["n_estrella"]
    con = _n_estrella(diffs, "total_con_esquema")["n_estrella"]
    assert con is not None and (sin is None or con < sin)


def test_agregar_promedia_lotes_y_comparar_signo_positivo_es_ahorro():
    filas = []
    for lote, (js, mi) in enumerate([(100, 60), (120, 70)]):
        base = {"dominio": "d", "tokenizador": "t", "n": 5, "lote": lote}
        filas.append({**base, "perfil": "json_compacto", "instruccion": "ninguna", "tokens_salida": js, "tokens_instruccion": 0, "tokens_total": js,
                      "caracteres_salida": 1})
        filas.append({**base, "perfil": "especializado", "instruccion": "compacta_con_ejemplo", "tokens_salida": mi, "tokens_instruccion": 20,
                      "tokens_total": mi + 20, "caracteres_salida": 1})
    agr = medir.agregar(filas)
    assert {(a["perfil"], a["salida"], a["lotes"]) for a in agr} == {("json_compacto", 110, 2), ("especializado", 65, 2)}
    c = medir.comparar(agr)[0]
    assert round(c["ahorro_salida_pct"], 6) == round(100 * (1 - 65 / 110), 6)
    assert round(c["ahorro_total_pct"], 6) == round(100 * (1 - 85 / 110), 6)

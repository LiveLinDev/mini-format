"""V3a: corte por tokens en frontera de token y de carácter (experiments/truncamiento/corte.py)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT / "experiments", ROOT / "src"):
    sys.path.insert(0, str(_p))

pytest.importorskip("tiktoken")
pytest.importorskip("regex")

from truncamiento import corte as K  # noqa: E402


@pytest.fixture(scope="module")
def enc():
    return K.cargar_o200k()


# ------------------------------------------------------------------ L_k calculado a mano
@pytest.mark.parametrize("k,t_ref,esperado", [
    (1, 100, 5), (10, 100, 50), (20, 100, 100), (7, 100, 35),
    (1, 10, 1),     # 0,5 -> mitad hacia arriba
    (1, 30, 2),     # 1,5 -> 2
    (3, 50, 8),     # 7,5 -> 8
    (1, 1, 0),      # 0,05 -> 0
    (20, 5216, 5216),
    (13, 5216, 3390),  # 13/20*5216 = 3390,4
])
def test_limite_k_a_mano(k, t_ref, esperado):
    assert K.limite_k(k, t_ref) == esperado


def test_limite_k_es_monotono_y_termina_en_t_ref():
    for t in (1, 7, 100, 2455, 21512):
        ls = [K.limite_k(k, t) for k in range(1, 21)]
        assert ls == sorted(ls)
        assert ls[-1] == t


# ------------------------------------------------------------------ vocabulario local
def test_vocabulario_local_es_el_oficial(enc):
    import hashlib
    assert hashlib.sha256(K.VOCAB_O200K.read_bytes()).hexdigest() == K.O200K_SHA256
    # Conteo conocido de o200k_base: "hello world" son dos tokens.
    assert len(enc.encode("hello world")) == 2


# ------------------------------------------------------------------ prefijos
def test_prefijo_ascii_coincide_con_la_decodificacion_de_los_tokens(enc):
    texto = '{"id":"a1","v":12.5,"s":"hola mundo"}'
    seg = K.segmentar(enc, texto)
    ids = enc.encode(texto)
    for limite in range(1, len(ids)):
        p = K.prefijo_por_tokens(seg, limite)
        assert p.texto == enc.decode(ids[:limite])
        assert p.truncado and p.bytes_descartados == 0
        assert p.n_bytes == len(p.texto.encode("utf-8"))
        assert texto.startswith(p.texto)


def test_limite_mayor_o_igual_que_los_tokens_devuelve_el_texto_completo(enc):
    texto = "abc def ghi"
    seg = K.segmentar(enc, texto)
    for limite in (seg.n_tokens, seg.n_tokens + 1, 10_000):
        p = K.prefijo_por_tokens(seg, limite)
        assert p.texto == texto and not p.truncado and p.bytes_descartados == 0


def test_limite_cero_es_el_prefijo_vacio_truncado(enc):
    p = K.prefijo_por_tokens(K.segmentar(enc, "hola"), 0)
    assert p.texto == "" and p.truncado and p.n_bytes == 0


def test_limite_negativo_se_rechaza(enc):
    with pytest.raises(ValueError):
        K.prefijo_por_tokens(K.segmentar(enc, "hola"), -1)


def test_los_bytes_de_los_tokens_suman_el_texto_utf8(enc):
    texto = "año 2026 — ¿qué tal? 日本語 🙂 adiós"
    seg = K.segmentar(enc, texto)
    assert seg.fin_bytes[-1] == len(texto.encode("utf-8"))
    assert seg.fin_bytes == sorted(seg.fin_bytes)


def test_corte_dentro_de_un_caracter_multibyte_descarta_la_cola_incompleta(enc):
    """Un token BPE puede partir un carácter UTF-8: el prefijo no debe traer U+FFFD ni un carácter a medias."""
    texto = "x " + "🙂🙂🙂🤔" * 6 + " fin"   # o200k parte estos emoji en tokens de bytes sueltos
    seg = K.segmentar(enc, texto)
    partidos = []
    for limite in range(1, seg.n_tokens):
        p = K.prefijo_por_tokens(seg, limite)
        assert "�" not in p.texto
        assert texto.startswith(p.texto)                       # siempre un prefijo exacto del original
        assert p.n_bytes == len(p.texto.encode("utf-8"))
        if p.bytes_descartados:
            partidos.append((limite, p))
            corte = seg.fin_bytes[limite - 1]
            assert corte - p.bytes_descartados == p.n_bytes     # se descartó justo la cola incompleta
            assert 1 <= p.bytes_descartados <= 3                # un carácter UTF-8 tiene como máximo 4 bytes
            # el primer byte descartado es el inicio de un carácter (no un byte de continuación)
            assert seg.datos[p.n_bytes] & 0xC0 != 0x80
    # la prueba solo vale si el caso ocurrió de verdad en este texto
    assert partidos, "ningún límite cayó dentro de un carácter multibyte; elige otro texto de prueba"


def test_prefijos_anidados_y_monotonos(enc):
    texto = "El módulo añadió ñandúes — 日本語, 🙂. " * 20
    seg = K.segmentar(enc, texto)
    previo = ""
    for limite in range(0, seg.n_tokens + 1):
        p = K.prefijo_por_tokens(seg, limite)
        assert p.texto.startswith(previo)
        previo = p.texto
    assert previo == texto

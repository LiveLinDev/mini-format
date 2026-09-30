"""OPT: la ida y vuelta es EXACTA antes de comparar tokens, y la comprobación puede fallar.

* Ida y vuelta de todos los perfiles sobre los tres dominios.
* Decodificador independiente (examples/optimizacion/reconstruir.py: solo minifmt + mapa.json).
* Casos que deben ser descartados (ceros a la izquierda, precisión perdida, constante que no lo es, valor sin código).
* Una reconstrucción defectuosa tiene que hacer fallar la comprobación.
* Fuzz con semilla fija sobre textos con los caracteres que el formato escapa.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "src", ROOT / "experiments", ROOT / "tools"):
    sys.path.insert(0, str(p))

from minifmt import parse  # noqa: E402
from minifmt.errors import MiniValidationError  # noqa: E402
from optimizacion import datos, diseno, especializacion, medir, perfiles  # noqa: E402
from optimizacion.dominios import dominios  # noqa: E402
from optimizacion.especializacion import Campo, Especializacion, NoEquivalente, comprobar_equivalencia  # noqa: E402

_spec = importlib.util.spec_from_file_location("opt_reconstruir", ROOT / "examples" / "optimizacion" / "reconstruir.py")
reconstruir = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reconstruir)

DOMS = ("tickets", "eventos", "comentarios")


def _compacto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


@pytest.mark.parametrize("dom_id", DOMS)
@pytest.mark.parametrize("n", [1, 2, 17, 60])
def test_todos_los_perfiles_reconstruyen_el_lote(dom_id, n):
    prep = medir.preparar(dom_id)
    regs = prep.dom.generar(datos.SEMILLA_PRUEBA, 0, n)
    for perfil in perfiles.PERFILES:
        prep.verificar(perfil, regs)                          # lanza NoEquivalente si algo no vuelve idéntico


@pytest.mark.parametrize("dom_id", DOMS)
def test_decodificador_independiente_reconstruye_con_el_mapa_del_archivo(dom_id, tmp_path):
    prep = medir.preparar(dom_id)
    regs = prep.dom.generar(datos.SEMILLA_PRUEBA, 1, 40)
    (tmp_path / "contrato_especializado.json").write_text(json.dumps(prep.esp.contrato().to_dict()), encoding="utf-8")
    (tmp_path / "mapa.json").write_text(json.dumps(prep.esp.mapa_explicito()), encoding="utf-8")
    texto = perfiles.salida_especializada(prep.esp, regs)
    assert _compacto(reconstruir.reconstruir(tmp_path, texto)) == _compacto(regs)


def test_un_mapa_con_dos_codigos_cambiados_no_reconstruye_lo_original(tmp_path):
    prep = medir.preparar("tickets")
    regs = prep.dom.generar(datos.SEMILLA_PRUEBA, 0, 30)
    mapa = prep.esp.mapa_explicito()
    cat = next(c for c in mapa["campos"] if c["campo"] == "categoria")
    k = list(cat["codigos"])
    cat["codigos"][k[0]], cat["codigos"][k[1]] = cat["codigos"][k[1]], cat["codigos"][k[0]]
    (tmp_path / "contrato_especializado.json").write_text(json.dumps(prep.esp.contrato().to_dict()), encoding="utf-8")
    (tmp_path / "mapa.json").write_text(json.dumps(mapa), encoding="utf-8")
    vuelta = reconstruir.reconstruir(tmp_path, perfiles.salida_especializada(prep.esp, regs))
    assert _compacto(vuelta) != _compacto(regs)


def test_un_codigo_fuera_de_la_enumeracion_se_rechaza_con_e10():
    prep = medir.preparar("tickets")
    texto = perfiles.salida_especializada(prep.esp, prep.dom.generar(datos.SEMILLA_PRUEBA, 0, 3))
    lineas = texto.split("\n")
    cols = lineas[2].split("|")
    cols[2] = "zz"
    lineas[2] = "|".join(cols)
    with pytest.raises(MiniValidationError) as e:
        parse("\n".join(lineas), prep.esp.contrato(), strict=True)
    assert [x.code for x in e.value.errors] == ["E10"] and e.value.errors[0].line == 3


# ----------------------------------------------------------------- configuraciones que se descartan
def _tickets_esp(**cambios):
    base = diseno.especializacion_de("tickets")
    campos = [replace(c, **cambios.get(c.orig, {})) for c in base.campos]
    return replace(base, campos=campos)


def test_id_con_ceros_a_la_izquierda_se_descarta():
    esp = _tickets_esp()
    regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 3)
    regs[1]["id"] = "T-0042"
    with pytest.raises(NoEquivalente):
        comprobar_equivalencia(esp, regs)


def test_id_con_otro_prefijo_o_sin_digitos_se_descarta():
    esp = _tickets_esp()
    for malo in ("X-1041", "T-", "T-12a", "T-٣"):
        regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 2)
        regs[0]["id"] = malo
        with pytest.raises(NoEquivalente):
            comprobar_equivalencia(esp, regs)


def test_valor_de_enumeracion_sin_codigo_se_descarta():
    esp = diseno.especializacion_de("tickets")
    regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 2)
    regs[0]["categoria"] = "facturacion"
    with pytest.raises(NoEquivalente):
        comprobar_equivalencia(esp, regs)


def test_eventos_que_no_sobreviven_a_la_abreviatura_se_descartan():
    esp = diseno.especializacion_de("eventos")
    base = datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 4)
    casos = [("valor", 0.15), ("valor", 1e-9), ("hora", "7:05"), ("hora", "24:61"), ("id_equipo", "EQ-417"), ("id_equipo", "EQ-00417")]
    for campo, malo in casos:
        regs = [dict(r) for r in base]
        regs[2][campo] = malo
        with pytest.raises(NoEquivalente):
            comprobar_equivalencia(esp, regs)


def test_constante_que_no_lo_es_se_descarta_y_un_lote_vacio_tambien():
    esp = diseno.especializacion_de("eventos")
    regs = [dict(r) for r in datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 4)]
    regs[3]["fecha"] = "2026-10-02"
    with pytest.raises(NoEquivalente):
        comprobar_equivalencia(esp, regs)
    with pytest.raises(NoEquivalente):
        esp.codificar([])


def test_un_entero_entero_como_float_conserva_el_tipo():
    """20.0 (float) debe volver como 20.0 y no como 20 (int): JSON los distingue al serializar."""
    esp = diseno.especializacion_de("eventos")
    regs = [dict(r) for r in datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 3)]
    regs[0]["valor"] = 20.0
    comprobar_equivalencia(esp, regs)
    regs[1]["valor"] = 20                                   # un int en un campo float no es el mismo objeto
    with pytest.raises(NoEquivalente):
        comprobar_equivalencia(esp, regs)


def test_una_reconstruccion_defectuosa_hace_fallar_la_comprobacion():
    esp = diseno.especializacion_de("tickets")
    regs = datos.generar_tickets(datos.SEMILLA_PRUEBA, 0, 5)
    comprobar_equivalencia(esp, regs)                        # sano
    real = especializacion.de_mini

    def roto(c, v):
        return "x" if c.tratamiento == "codigos" and v == "b" else real(c, v)

    with mock.patch.object(especializacion, "de_mini", roto):
        regs = [dict(r, prioridad="baja") for r in regs]
        with pytest.raises(NoEquivalente):
            comprobar_equivalencia(esp, regs)


def test_el_orden_de_claves_de_la_aplicacion_se_conserva():
    esp = diseno.especializacion_de("eventos")
    regs = datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 3)
    vuelta = esp.reconstruir(parse(perfiles.salida_especializada(esp, regs), esp.contrato()).to_canonical())
    assert [list(r) for r in vuelta] == [list(r) for r in regs]
    desordenado = [dict(reversed(list(r.items()))) for r in regs]
    with pytest.raises(NoEquivalente):                       # mismo contenido, otro orden de claves: no es idéntico
        comprobar_equivalencia(esp, desordenado)


def test_orden_contractual_distinto_no_cambia_el_objeto_reconstruido():
    dom = dominios()["eventos"]
    regs = datos.generar_eventos(datos.SEMILLA_PRUEBA, 0, 12)
    base = diseno.especializacion_de("eventos")
    nombres = [c.nombre() for c in base.campos_registro()]
    rng = random.Random(7)
    for _ in range(5):
        orden = nombres[:]
        rng.shuffle(orden)
        esp = replace(base, orden=orden)
        comprobar_equivalencia(esp, regs)
        assert [c.nombre() for c in esp.campos_registro()] == orden
    assert dom.id == "eventos"


# ----------------------------------------------------------------- fuzz con semilla fija
_ALFABETO = list("abcXYZ019 áéñü漢*,;|\\\"'{}[]") + ["\n"]


def _texto(rng: random.Random) -> str:
    while True:
        t = "".join(rng.choice(_ALFABETO) for _ in range(rng.randint(1, 40)))
        if t == t.strip():                                   # límite conocido: el espacio exterior no sobrevive
            return t


def test_fuzz_de_resumenes_con_caracteres_de_escape_en_el_general_y_en_el_especializado():
    rng = random.Random(20261001)
    dom = dominios()["tickets"]
    esp = diseno.especializacion_de("tickets")
    regs = []
    for i in range(300):
        regs.append({"id": f"T-{rng.randint(1, 99999)}", "prioridad": rng.choice(datos.TICKETS_ENUM_PRIORIDAD),
                     "categoria": rng.choice(datos.TICKETS_ENUM_CATEGORIA), "resumen": _texto(rng), "horas": rng.randint(0, 40)})
    ids = set()
    regs = [r for r in regs if not (r["id"] in ids or ids.add(r["id"]))]
    comprobar_equivalencia(esp, regs)
    perfiles.verificar_general(dom, regs)
    perfiles.verificar_dominio(dom, perfiles.contrato_dominio(dom, datos.generar_tickets(datos.SEMILLA_DESARROLLO, 0, 100)), regs)

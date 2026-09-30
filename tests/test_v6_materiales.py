"""Pruebas de los materiales documentales de V6 (evidencia/v6/): honestidad, privacidad y coherencia.

Comprueban que los materiales dicen lo que deben decir (estado pendiente, sin participantes, borrador sin
firmas, SUS con su atribución y su traducción provisional, plantilla de V6a vacía) y que no contienen
resultados, datos personales ni emojis. No juzgan la calidad de la redacción.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
V6 = RAIZ / "evidencia" / "v6"


def txt(p):
    return Path(p).read_text(encoding="utf-8")


def js(p):
    return json.loads(txt(p))


def archivos_de_texto():
    for p in sorted(V6.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".md", ".json", ".html", ".py", ".csv", ".mini"):
            yield p


# ------------------------------------------------------------------------------------------
# Estado y honestidad
# ------------------------------------------------------------------------------------------
def test_leeme_declara_que_no_hay_participantes():
    t = txt(V6 / "LEEME.md").lower()
    assert "sin participantes: estudio pendiente, materiales listos" in t
    for clave in ("naturalista", "controlado", "no contiene ningún resultado", "censurado", "restringida"):
        assert clave in t, clave


def test_estado_pendiente_y_sin_resultados():
    e = js(V6 / "estado.json")
    assert e["resumen"] == "sin participantes: estudio pendiente, materiales listos"
    for estudio, clase in (("V6a", "naturalista"), ("V6b", "controlado con tareas")):
        x = e[estudio]
        assert x["estado_ejecucion"] == "pendiente" and x["resultado"] == "no_evaluable"
        assert x["clasificacion"] == clase
        assert x["procedencia"] is None and x["que_falta"]
    # los datos que no existen son null, no ceros
    assert e["V6a"]["sistemas_acreditados"] is None
    assert e["V6b"]["resultados"] is None
    p = e["V6b"]["participantes"]
    assert p["pilotos_realizados"] is None and p["validos_realizados"] is None
    assert (p["pilotos_previstos"], p["validos_minimo_previsto"], p["validos_maximo_previsto"]) == (2, 8, 12)
    assert e["meta_documental"]["estado_de_la_meta"] == "no_evaluable"
    assert len(e["V6a"]["no_cuenta_como_segunda_adopcion_externa"]) == 2
    # los rótulos de materiales que nombran rutas existen
    for ruta in e["materiales"]:
        base = ruta.split(":")[0]
        destino = RAIZ / base if base.startswith("tools/") else V6 / base
        assert destino.exists(), ruta


def test_no_hay_corridas_de_v6_registradas():
    corridas = RAIZ / "evidencia" / "corridas"
    if corridas.exists():
        assert not [p for p in corridas.glob("*") if p.name.lower().startswith(("v6a", "v6b"))]


def test_estado_y_los_materiales_no_traen_cifras_de_resultados():
    """Busca frases típicas de un resultado ya obtenido; las cifras permitidas son parámetros del plan."""
    prohibidas = [r"SUS (obtenido|medio|promedio)\s*(fue|de|=)", r"la mediana (fue|resultó)", r"participantes completaron",
                  r"(resultados?|hallazgos?) de V6[ab]\s*:", r"n\s*=\s*\d+\s+participantes\s+válidos", r"se observó que"]
    for p in archivos_de_texto():
        if p.suffix in (".md", ".json") and p.name != "guia_mini.md":
            t = txt(p)
            for pat in prohibidas:
                assert not re.search(pat, t, re.I), (p.name, pat)


def test_sin_datos_personales_ni_emojis_ni_dingbats():
    correo = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
    telefono = re.compile(r"(?<![\d-])(\+?\d[\d ()]{7,}\d|\d{3}-\d{3}-\d{3,4})(?![\d-])")
    simbolos = re.compile("[←-⇿☀-➿⬀-⯿\U0001f000-\U0001faff]")
    for p in archivos_de_texto():
        if p.name == "guia_mini.md":
            continue
        t = txt(p)
        assert not correo.search(t), f"correo en {p}"
        if p.suffix in (".md", ".html"):
            assert not simbolos.search(t), f"emoji o dingbat en {p}: {simbolos.findall(t)}"
        if p.suffix == ".md":
            assert not telefono.search(t.replace("TP202610039", "")), f"posible teléfono en {p}"


def test_v6_no_versiona_nada_de_restringida_ni_binarios_grandes():
    for p in V6.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            assert p.stat().st_size < 400_000, f"{p} pesa demasiado"
            assert p.suffix.lower() not in (".png", ".pdf", ".mp4", ".zip", ".docx", ".xlsx"), p
    assert not (V6 / "sesiones").exists() and not (V6 / "restringida").exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git no está disponible")
def test_la_carpeta_de_datos_reales_esta_ignorada_por_git():
    r = subprocess.run(["git", "check-ignore", "-q", "evidencia/restringida/v6/sesiones/sesion_EST-01_2026-10-12.json"],
                       cwd=RAIZ, capture_output=True)
    if r.returncode == 128:
        pytest.skip("no es un repositorio git")
    assert r.returncode == 0, "evidencia/restringida/v6/... debe estar ignorada"


# ------------------------------------------------------------------------------------------
# Consentimiento
# ------------------------------------------------------------------------------------------
def test_consentimiento_es_borrador_sin_firmas_y_dice_donde_guardar_datos():
    t = txt(V6 / "consentimiento_borrador.md")
    assert "BORRADOR" in t and "PENDIENTE DE REVISIÓN" in t and "Sin firmas y sin aprobación" in t
    assert "evidencia/restringida/" in t and "ignora" in t
    for pedir in ("comité", "asesor", "eliminación", "grabación", "Contacto"):
        assert pedir in t, pedir
    # ninguna casilla marcada, ninguna firma o fecha puesta
    assert not re.search(r"\[[xX]\]", t)
    assert "- [ ] Autorizo la grabación de pantalla." in t
    assert t.count("*(sin firma") >= 2 and "*(sin fecha)*" in t
    # los datos que no existen quedan entre corchetes para completar, no inventados
    assert "[fecha por fijar]" in t and "[correo institucional del equipo]" in t


# ------------------------------------------------------------------------------------------
# SUS
# ------------------------------------------------------------------------------------------
# Enunciados originales de Brooke (1996), cotejados con el texto del capítulo (copia en digital.ahrq.gov)
BROOKE = [
    "I think that I would like to use this system frequently",
    "I found the system unnecessarily complex",
    "I thought the system was easy to use",
    "I think that I would need the support of a technical person to be able to use this system",
    "I found the various functions in this system were well integrated",
    "I thought there was too much inconsistency in this system",
    "I would imagine that most people would learn to use this system very quickly",
    "I found the system very cumbersome to use",
    "I felt very confident using the system",
    "I needed to learn a lot of things before I could get going with this system",
]


def test_sus_items_originales_y_atribucion():
    d = js(V6 / "sus" / "sus_items.json")
    assert [i["original_en"] for i in d["items"]] == BROOKE
    assert [i["n"] for i in d["items"]] == list(range(1, 11))
    assert [i["polaridad"] for i in d["items"]] == ["positivo", "negativo"] * 5
    assert d["original"]["autor"] == "John Brooke" and d["original"]["anio"] == 1996
    assert "Usability evaluation in industry" in d["original"]["obra"] and "189-194" in d["original"]["obra"]
    assert "Digital Equipment Corporation" in d["original"]["nota_de_derechos"]
    assert "impares" in d["puntuacion"]["regla"] and "2,5" in d["puntuacion"]["regla"]
    t = txt(V6 / "sus" / "sus.md")
    bajo = t.replace("*", "").lower()
    for clave in ("John Brooke", "1996", "PROVISIONAL", "2,5"):
        assert clave in t, clave
    for clave in ("no es un porcentaje", "antes de cualquier conversación"):
        assert clave in bajo, clave
    # cada ítem original aparece en el documento
    for it in BROOKE:
        assert it in t


def test_sus_version_espanola_es_provisional_y_no_inventa_citas():
    d = js(V6 / "sus" / "sus_items.json")
    es = d["version_es"]
    assert es["estado"].startswith("PROVISIONAL del equipo") and "versión lingüística por fijar" in es["estado"]
    assert all(i["es_provisional"] for i in d["items"])
    cand = es["adaptacion_candidata"]
    # solo se cita lo que se abrió: datos bibliográficos verificados; el apéndice con los ítems NO se abrió
    assert "10.2196/21161" in cand["cita"] and "JMIR Human Factors" in cand["cita"] and "2020" in cand["cita"]
    assert "NO se abrió" in cand["no_verificado"]
    assert "decision_pendiente" in cand
    # los enunciados de esa adaptación no se copiaron en ninguna parte
    assert "Apéndice multimedia 2" in cand["no_verificado"]


# ------------------------------------------------------------------------------------------
# V6a
# ------------------------------------------------------------------------------------------
def _hojas(o, ruta=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _hojas(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(o, list):
        yield ruta, o
    else:
        yield ruta, o


def test_v6a_plantilla_vacia_y_con_los_campos_de_evidencia():
    d = js(V6 / "v6a_plantilla.json")
    assert d["estado"] == "plantilla_vacia" and "SIN DATOS" in d["aviso"]
    requeridos = ["identificacion", "independencia_del_equipo", "mantenedor", "autorizacion", "cambio", "contrato",
                  "version_del_componente", "ejecucion", "incidencias", "impacto_tecnico", "conformidad_del_mantenedor", "limitaciones"]
    for k in requeridos:
        assert k in d, k
    # campos que exige el plan: mantenedor, permiso, cambio de código, contrato, ejecución, incidencias, versión
    assert "rol" in d["mantenedor"] and "uso_de_la_evidencia" in d["autorizacion"]
    assert {"commit_antes", "commit_despues", "archivos_tocados"} <= set(d["cambio"])
    assert {"sha256", "origen"} <= set(d["contrato"]) and {"hash_del_paquete", "version_mini_format"} <= set(d["version_del_componente"])
    assert {"escenario", "fallos_observados", "fecha_inicio_utc"} <= set(d["ejecucion"])
    assert d["incidencias"] == [] and d["limitaciones"] == []
    assert "es_ajeno_al_equipo" in d["independencia_del_equipo"]
    # ningún campo de datos trae un valor: todo es null, lista vacía o texto fijo de las claves de ayuda
    ayuda = {"aviso", "clasificacion", "nota", "esquema", "estado", "campos_de_incidencia", "enumeraciones", "contacto_guardado_en"}
    for ruta, v in _hojas({k: d[k] for k in requeridos}):
        hoja = ruta.split(".")[-1]
        if hoja in ayuda:
            continue
        assert v is None or v == [], f"{ruta} debería estar vacío: {v!r}"
    assert d["procedencia"] is None and d["ficha_numero"] is None


def test_v6a_md_no_da_por_acreditado_a_cima_ni_al_demostrador():
    t = txt(V6 / "v6a_plantilla.md")
    assert "plantilla vacía" in t.lower() and "No hay resultados" in t
    assert "CIMA" in t and "SIMA" in t and "demostrador" in t
    assert "no se da por hecho" in t and "reportada por el equipo" in t
    assert "No cuenta por sí solo" in t or "NO cuenta por sí solo" in t
    assert "dominios distintos" in t and "naturalista" in t
    assert "I4.4" in t and "sigue pendiente" in t


# ------------------------------------------------------------------------------------------
# Protocolo
# ------------------------------------------------------------------------------------------
def test_protocolo_fija_topes_duracion_y_censura():
    t = txt(V6 / "protocolo.md").replace("**", "")
    assert "10 + 100 + 10 = 120" in t and "30 + 30 + 15 + 10 + 15" in t and "La versión previa decía 80 minutos" in t
    for clave in ("tiempo agotado", "censurada", "no es éxito", "no se trunca a 30", "Wilcoxon", "Wilson", "pilotos",
                  "PIL-01", "evidencia/restringida/v6/", "personas reales"):
        assert clave in t, clave
    assert "aprobación institucional" in t.lower()
    assert "T1 JSON" in t and "T1 .mini" in t and "T2" in t and "T3" in t and "T4" in t
    assert "mediana de T1 .mini ≤ 30" in t and "SUS (media) ≥ 70" in t and "8 participantes" in t
    # la sesión no es naturalista
    assert "controlado con tareas" in t


def test_rutas_citadas_en_los_documentos_existen():
    """Toda ruta entre comillas invertidas que empiece por un directorio del flujo debe existir."""
    patron = re.compile(r"`((?:tareas|herramienta|sus|fixtures_de_prueba|evidencia/v6|evidencia/restringida|tools|tests|examples|sitio|forks)/[A-Za-z0-9_./<>*-]+)`")
    falta = []
    for md in V6.rglob("*.md"):
        if md.name == "guia_mini.md":
            continue
        for m in patron.findall(txt(md)):
            if any(c in m for c in "<>*"):
                continue
            ruta = m.rstrip("/.")
            if ruta.startswith("evidencia/restringida"):
                continue                                   # carpeta de datos reales: no existe en el repo
            candidatos = [RAIZ / ruta, V6 / ruta, md.parent / ruta]
            if not any(c.exists() for c in candidatos):
                falta.append((md.name, m))
    assert falta == [], falta

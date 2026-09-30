#!/usr/bin/env python3
"""Tarifas oficiales de los proveedores de modelos: consultar, verificar y mostrar.

Uso (desde la raíz del repositorio):
    python tools/tarifas.py consultar [--solo-comprobar] [--modelo ID ...] [--directorio DIR]
    python tools/tarifas.py verificar [--estricto] [--dias 14] [--ahora AAAA-MM-DDThh:mm:ssZ]
    python tools/tarifas.py mostrar [--proveedor P] [--estado verificada|no_verificada] [--json]
    python tools/tarifas.py sembrar --desde ARCHIVO.json      (solo la primera vez)

Solo biblioteca estándar. Principio: NUNCA se escribe un precio que este programa no haya
leído de la página oficial en ESTA ejecución. Si la consulta falla (red, bloqueo, redirección a
otra página, formato cambiado, JavaScript), la tarifa pasa a ``no_verificada`` con la causa
exacta y los precios activos quedan en ``null``; el último valor verificado se conserva aparte
en ``ultimo_valor_verificado`` solo como historia. Los consumidores (la calculadora de costos,
los informes) leen los precios activos y tratan ``no_verificada`` como "tarifa no verificada".

Archivos (en ``evidencia/tarifas/``):
    tarifas.json   una entrada por (proveedor, modelo_api_id) con precios USD por millón de tokens
    fuentes.json   cómo consultar cada entrada: URL a descargar, formato y expresión regular
    consultas/     una copia por consulta con URL final, estado HTTP, SHA-256 de la página y extracto

Tokenizadores (importante para quien convierta texto en costo): ``tiktoken`` es una
APROXIMACIÓN salvo para texto plano de los modelos OpenAI que tiktoken mapea (o200k_base).
Para Anthropic, Google, DeepSeek y otros modelos de Groq solo vale el ``usage`` de la respuesta
o el endpoint de conteo del proveedor; ver ``tokenizadores`` en tarifas.json.
"""
from __future__ import annotations

import argparse
import hashlib
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence, Tuple
from urllib.parse import urlparse

ESQUEMA = "mini-format/tarifas/1"
ESQUEMA_FUENTES = "mini-format/tarifas-fuentes/1"
ESQUEMA_CONSULTA = "mini-format/tarifas-consulta/1"
USER_AGENT = "Mozilla/5.0 (compatible; mini-format-tarifas/1.0; +https://mini-format.pmoluna.com; consulta de tarifas publicas, solo lectura)"
TIMEOUT_S = 30
REINTENTOS = 2
MAX_BYTES = 16 * 1024 * 1024
DIAS_MAXIMOS = 14
CAMPOS_PRECIO = ("entrada_sin_cache_por_millon", "entrada_cache_lectura_por_millon",
                 "entrada_cache_escritura_por_millon", "salida_por_millon")
GRUPO_A_CAMPO = {"entrada_sin_cache": "entrada_sin_cache_por_millon",
                 "entrada_cache_lectura": "entrada_cache_lectura_por_millon",
                 "entrada_cache_escritura": "entrada_cache_escritura_por_millon",
                 "salida": "salida_por_millon"}
ESTADOS = ("verificada", "no_verificada")
NOTA_TOKENIZADORES = (
    "tiktoken (o200k_base, cl100k_base, r50k_base) es una aproximación salvo para texto plano de los modelos de OpenAI "
    "que tiktoken mapea; para Anthropic, Google, DeepSeek y los modelos de Groq que no son gpt-oss solo valen el usage "
    "de la respuesta o el endpoint de conteo del proveedor. Los conteos locales de texto, los conteos de solicitud del "
    "proveedor y el usage de una llamada real son tres cosas distintas y no se suman ni se sustituyen."
)
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


# ------------------------------------------------------------------ utilidades
def raiz_repo() -> Path:
    return Path(__file__).resolve().parent.parent


def directorio_por_defecto() -> Path:
    return raiz_repo() / "evidencia" / "tarifas"


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parsear_fecha(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def sha256_texto(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def leer_json(p: Path) -> Any:
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def escribir_json(p: Path, obj: Any) -> None:
    """JSON determinista (claves en el orden dado, UTF-8, LF final) escrito de forma atómica."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, p)


def decimal_a_cadena(x: Any) -> Optional[str]:
    """Float/Decimal/cadena -> cadena decimal mínima ('15', '0.075'); None se queda en None."""
    if x is None:
        return None
    d = Decimal(repr(x)) if isinstance(x, float) else Decimal(str(x))
    return format(d.normalize(), "f")


def _normalizar_extracto(t: str) -> str:
    lineas = [re.sub(r"\s{2,}", " ", l.strip()) for l in t.strip().splitlines() if l.strip()]
    return " || ".join(lineas)[:600]


# ------------------------------------------------------------------ HTML a texto
class _Texto(HTMLParser):
    _OMITIR = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.trozos: List[str] = []
        self._prof = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._OMITIR:
            self._prof += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._OMITIR and self._prof:
            self._prof -= 1

    def handle_data(self, data: str) -> None:
        if not self._prof:
            self.trozos.append(data)


def html_a_texto(cuerpo: str) -> str:
    """Texto plano reconstruido de una página HTML: nodos de texto separados por un espacio,
    sin scripts ni estilos, sin espacios de ancho cero y con los blancos colapsados."""
    p = _Texto()
    p.feed(cuerpo)
    p.close()
    t = " ".join(p.trozos)
    t = t.replace("​", "").replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


# --------------------------------------------------------------------- descarga
class Respuesta(NamedTuple):
    status: Optional[int]
    url_final: Optional[str]
    cuerpo: bytes
    error: Optional[str]


def descargar_http(url: str, timeout: float = TIMEOUT_S, reintentos: int = REINTENTOS,
                   dormir: Callable[[float], None] = time.sleep) -> Respuesta:
    """GET con urllib, User-Agent identificable y espera creciente entre reintentos. Un estado
    HTTP de error NO se reintenta salvo 5xx; devuelve el estado tal cual (nunca lo maquilla)."""
    ultimo: Respuesta = Respuesta(None, None, b"", "sin intentos")
    for intento in range(reintentos + 1):
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT, "Accept-Language": "en",
            "Accept": "text/markdown, text/plain;q=0.9, text/html;q=0.8, */*;q=0.5"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                cuerpo = r.read(MAX_BYTES + 1)
                if len(cuerpo) > MAX_BYTES:
                    return Respuesta(r.status, r.geturl(), b"", "respuesta mayor que el límite")
                return Respuesta(r.status, r.geturl(), cuerpo, None)
        except urllib.error.HTTPError as e:
            try:
                cuerpo = e.read(MAX_BYTES)
            except Exception:
                cuerpo = b""
            ultimo = Respuesta(e.code, e.geturl() if hasattr(e, "geturl") else url, cuerpo, None)
            if e.code < 500:
                return ultimo
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            ultimo = Respuesta(None, None, b"", f"{type(e).__name__}: {e}")
        if intento < reintentos:
            dormir(2.0 * (intento + 1))
    return ultimo


# -------------------------------------------------------------------- consulta
def _misma_pagina(pedida: str, final: Optional[str]) -> bool:
    if not final:
        return False
    a, b = urlparse(pedida), urlparse(final)
    return a.netloc.lower() == b.netloc.lower() and a.path.rstrip("/") == b.path.rstrip("/")


def _evaluar_pagina(spec: Dict[str, Any], resp: Respuesta) -> Dict[str, Any]:
    """Resultado de aplicar el patrón de ``spec`` a la respuesta descargada."""
    url = spec["url"]
    out: Dict[str, Any] = {"url": url, "url_final": resp.url_final, "http_status": resp.status,
                           "bytes": len(resp.cuerpo), "sha256": hashlib.sha256(resp.cuerpo).hexdigest() if resp.cuerpo else None,
                           "encontrado": False, "extracto": None, "extracto_sha256": None, "grupos": {}, "motivo": None}
    if resp.error:
        out["motivo"] = "error_de_red: " + resp.error
        return out
    if resp.status in (401, 403, 429):
        out["motivo"] = f"bloqueada: HTTP {resp.status}"
        return out
    if resp.status != 200:
        out["motivo"] = f"http_{resp.status}"
        return out
    if not _misma_pagina(url, resp.url_final):
        out["motivo"] = f"redireccion_ajena: {url} -> {resp.url_final}"
        return out
    if len(resp.cuerpo) < 200:
        out["motivo"] = "contenido_insuficiente"
        return out
    texto = resp.cuerpo.decode("utf-8", errors="replace").replace("\r\n", "\n")
    if spec.get("formato", "markdown") == "html":
        texto = html_a_texto(texto)
    m = re.search(spec["patron"], texto)
    if not m:
        if re.search(r"(?i)enable javascript|requires? javascript", texto):
            out["motivo"] = "requiere_js: la página exige JavaScript y el extracto no está en el HTML"
        else:
            out["motivo"] = "extracto_ausente: el patrón ya no coincide con la página"
        return out
    g = m.groupdict()
    crudo = g.get("extracto") or m.group(0)
    ext = _normalizar_extracto(crudo)
    out.update({"encontrado": True, "extracto": ext, "extracto_sha256": sha256_texto(ext),
                "grupos": {k: v for k, v in g.items() if k != "extracto" and v is not None}})
    return out


def _precios_de_grupos(grupos: Dict[str, str]) -> Tuple[Dict[str, Optional[str]], Optional[str]]:
    """Convierte los grupos capturados en precios y comprueba su plausibilidad."""
    precios: Dict[str, Optional[str]] = {c: None for c in CAMPOS_PRECIO}
    for g, campo in GRUPO_A_CAMPO.items():
        v = grupos.get(g)
        if v is None:
            continue
        try:
            d = Decimal(v)
        except InvalidOperation:
            return precios, f"precio_no_plausible: {g}={v!r} no es un decimal"
        if d < 0:
            return precios, f"precio_no_plausible: {g} negativo"
        precios[campo] = decimal_a_cadena(d)
    ent, sal = precios["entrada_sin_cache_por_millon"], precios["salida_por_millon"]
    if ent is None or sal is None:
        return precios, "extracto_ausente: el patrón no devolvió entrada y salida"
    if Decimal(sal) <= 0:
        return precios, "precio_no_plausible: salida <= 0"
    cl = precios["entrada_cache_lectura_por_millon"]
    if cl is not None and Decimal(cl) > Decimal(ent):
        return precios, "precio_no_plausible: lectura de caché mayor que la entrada"
    return precios, None


def consultar(directorio: Path, descargar: Callable[[str], Respuesta] = descargar_http,
              ahora: Optional[str] = None, solo_comprobar: bool = False,
              modelos: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Consulta las páginas oficiales de cada entrada de ``fuentes.json``.

    Escribe ``consultas/<UTC>.json`` y, salvo ``solo_comprobar``, actualiza ``tarifas.json``:
    ``verificada`` solo si la página oficial lo muestra ahora; si no, ``no_verificada`` con la causa.
    Devuelve el documento de la consulta. ``descargar`` se inyecta en las pruebas (nunca red real).
    """
    directorio = Path(directorio)
    ahora = ahora or ahora_utc()
    tarifas_doc = leer_json(directorio / "tarifas.json")
    fuentes_doc = leer_json(directorio / "fuentes.json")
    por_clave = {(t["proveedor"], t["modelo_api_id"]): t for t in tarifas_doc["tarifas"]}
    cache: Dict[str, Respuesta] = {}

    def bajar(url: str) -> Respuesta:
        if url not in cache:
            cache[url] = descargar(url)
        return cache[url]

    entradas: List[Dict[str, Any]] = []
    n_cambios = 0
    for f in fuentes_doc["fuentes"]:
        clave = (f["proveedor"], f["modelo_api_id"])
        if modelos and f["modelo_api_id"] not in modelos:
            continue
        t = por_clave.get(clave)
        if t is None:
            entradas.append({"proveedor": clave[0], "modelo_api_id": clave[1], "estado": "no_verificada",
                             "motivo": "sin_entrada_en_tarifas", "paginas": []})
            continue
        paginas = [_evaluar_pagina(p, bajar(p["url"])) for p in f["paginas"]]
        entrada: Dict[str, Any] = {"proveedor": clave[0], "modelo_api_id": clave[1], "tipo": f.get("tipo", "precio"),
                                   "paginas": [{k: v for k, v in p.items() if k != "grupos"} for p in paginas],
                                   "precios": None, "cambio_respecto_ultimo": False, "diferencias": []}
        fallo = next((p["motivo"] for p in paginas if p["motivo"]), None)
        grupos: Dict[str, str] = {}
        for p in paginas:
            grupos.update(p["grupos"])
        extracto = " | ".join(p["extracto"] for p in paginas if p["extracto"])
        if fallo is None and f.get("tipo", "precio") == "retiro":
            fecha = grupos.get("retiro")
            entrada.update({"estado": "no_verificada", "motivo": "retirado_segun_pagina_oficial" + (f": cierre {fecha}" if fecha else "")})
        elif fallo is None:
            precios, fallo = _precios_de_grupos(grupos)
            if fallo is None:
                previos = {c: decimal_a_cadena(t.get(c)) for c in CAMPOS_PRECIO}
                dif = [{"campo": c, "anterior": previos[c], "actual": precios[c]} for c in CAMPOS_PRECIO
                       if (None if previos[c] is None else Decimal(previos[c])) != (None if precios[c] is None else Decimal(precios[c]))]
                if t.get("estado") != "verificada":
                    dif = []  # sin valor activo previo no hay "cambio": se informa como nueva verificación
                entrada.update({"estado": "verificada", "motivo": None, "precios": precios,
                                "cambio_respecto_ultimo": bool(dif), "diferencias": dif})
                n_cambios += 1 if dif else 0
        if fallo is not None:
            entrada.update({"estado": "no_verificada", "motivo": fallo})
        entrada["extracto"] = extracto or None
        entrada["extracto_sha256"] = sha256_texto(extracto) if extracto else None
        entradas.append(entrada)

    resumen = {"entradas": len(entradas),
               "verificadas": sum(1 for e in entradas if e["estado"] == "verificada"),
               "no_verificadas": sum(1 for e in entradas if e["estado"] != "verificada"),
               "con_cambio_de_precio": n_cambios}
    doc = {"esquema": ESQUEMA_CONSULTA, "consulta_utc": ahora, "agente": USER_AGENT, "solo_comprobar": bool(solo_comprobar),
           "resumen": resumen, "entradas": entradas}
    nombre = ahora.replace("-", "").replace(":", "") + ".json"
    escribir_json(directorio / "consultas" / nombre, doc)
    if not solo_comprobar:
        _aplicar(tarifas_doc, entradas, ahora, nombre)
        escribir_json(directorio / "tarifas.json", tarifas_doc)
    return doc


def _aplicar(tarifas_doc: Dict[str, Any], entradas: List[Dict[str, Any]], ahora: str, nombre_consulta: str) -> None:
    """Escribe el resultado de una consulta en las tarifas (precios activos solo si verificada)."""
    por_clave = {(t["proveedor"], t["modelo_api_id"]): t for t in tarifas_doc["tarifas"]}
    for e in entradas:
        t = por_clave.get((e["proveedor"], e["modelo_api_id"]))
        if t is None:
            continue
        if e["estado"] == "verificada":
            t.update(e["precios"])
            t["estado"] = "verificada"
            t["motivo_no_verificada"] = None
        else:
            if t.get("estado") == "verificada":   # historia: lo último que sí se leyó
                t["ultimo_valor_verificado"] = {**{c: t.get(c) for c in CAMPOS_PRECIO},
                                                "fecha_consulta_utc": t.get("fecha_consulta_utc"), "extracto": t.get("extracto")}
            for c in CAMPOS_PRECIO:
                t[c] = None
            t["estado"] = "no_verificada"
            t["motivo_no_verificada"] = e["motivo"]
        if e.get("extracto"):
            t["extracto"] = e["extracto"]
            t["extracto_sha256"] = e["extracto_sha256"]
        t["fecha_consulta_utc"] = ahora
        t["origen"] = "consultar"
        t["consulta"] = nombre_consulta
    tarifas_doc["consulta_utc"] = ahora


# ------------------------------------------------------------------ verificación
def verificar(directorio: Path, ahora: Optional[str] = None, dias: int = DIAS_MAXIMOS
              ) -> Tuple[List[str], List[str]]:
    """Validación SIN red: estructura, honestidad y antigüedad. Devuelve (errores, advertencias)."""
    directorio = Path(directorio)
    e: List[str] = []
    w: List[str] = []
    try:
        doc = leer_json(directorio / "tarifas.json")
    except (OSError, ValueError) as ex:
        return [f"no se puede leer tarifas.json: {ex}"], []
    if doc.get("esquema") != ESQUEMA:
        e.append(f"esquema debe ser {ESQUEMA!r}")
    if "aproximaci" not in (doc.get("nota_tokenizadores") or ""):
        e.append("falta nota_tokenizadores (tiktoken es una aproximación salvo OpenAI texto plano)")
    if not isinstance(doc.get("tokenizadores"), list) or not doc.get("tokenizadores"):
        e.append("faltan los métodos oficiales de conteo de tokens por proveedor (tokenizadores)")
    ref = parsear_fecha(ahora) if ahora else datetime.now(timezone.utc)
    vistos = set()
    tarifas = doc.get("tarifas")
    if not isinstance(tarifas, list) or not tarifas:
        return e + ["tarifas debe ser una lista no vacía"], w
    for i, t in enumerate(tarifas):
        etq = f"{t.get('proveedor')}/{t.get('modelo_api_id')}"
        for c in ("proveedor", "modelo_api_id", "moneda", "url_oficial", "estado", "fecha_consulta_utc", "extracto", "extracto_sha256"):
            if not t.get(c):
                e.append(f"{etq}: falta {c}")
        if (t.get("proveedor"), t.get("modelo_api_id")) in vistos:
            e.append(f"{etq}: entrada repetida")
        vistos.add((t.get("proveedor"), t.get("modelo_api_id")))
        if t.get("moneda") != "USD":
            e.append(f"{etq}: moneda debe ser USD")
        if t.get("consulta") and not (directorio / "consultas" / str(t["consulta"])).exists():
            e.append(f"{etq}: la consulta {t['consulta']} no existe en consultas/")
        if t.get("estado") not in ESTADOS:
            e.append(f"{etq}: estado debe ser uno de {ESTADOS}")
        if not str(t.get("url_oficial", "")).startswith("https://"):
            e.append(f"{etq}: url_oficial debe ser https")
        if t.get("fecha_consulta_utc") and not _FECHA.match(t["fecha_consulta_utc"]):
            e.append(f"{etq}: fecha_consulta_utc inválida")
        if t.get("extracto") and t.get("extracto_sha256") != sha256_texto(t["extracto"]):
            e.append(f"{etq}: extracto_sha256 no corresponde al extracto")
        for c in CAMPOS_PRECIO:
            v = t.get(c)
            if v is None:
                continue
            if isinstance(v, (int, float)) or not isinstance(v, str):
                e.append(f"{etq}: {c} debe ser una cadena decimal o null, no un número")
                continue
            try:
                if Decimal(v) < 0:
                    e.append(f"{etq}: {c} negativo")
            except InvalidOperation:
                e.append(f"{etq}: {c} no es decimal")
        if t.get("estado") == "verificada":
            if t.get("entrada_sin_cache_por_millon") is None or t.get("salida_por_millon") is None:
                e.append(f"{etq}: verificada exige precio de entrada y de salida")
            if t.get("fecha_consulta_utc") and _FECHA.match(t["fecha_consulta_utc"]):
                edad = (ref - parsear_fecha(t["fecha_consulta_utc"])).total_seconds() / 86400
                if edad > dias:
                    w.append(f"desactualizada: {etq} consultada hace {int(edad)} días (límite {dias}); ejecute 'consultar'")
                if edad < -0.01:
                    e.append(f"{etq}: fecha_consulta_utc en el futuro")
        elif t.get("estado") == "no_verificada":
            if any(t.get(c) is not None for c in CAMPOS_PRECIO):
                e.append(f"{etq}: una tarifa no_verificada no puede llevar precios activos")
            if not (t.get("motivo_no_verificada") or t.get("notas")):
                e.append(f"{etq}: no_verificada exige motivo")
    # fuentes
    try:
        fuentes = leer_json(directorio / "fuentes.json")
    except (OSError, ValueError) as ex:
        return e + [f"no se puede leer fuentes.json: {ex}"], w
    if fuentes.get("esquema") != ESQUEMA_FUENTES:
        e.append(f"fuentes.json: esquema debe ser {ESQUEMA_FUENTES!r}")
    claves_f = set()
    for f in fuentes.get("fuentes", []):
        clave = (f.get("proveedor"), f.get("modelo_api_id"))
        etq = f"{clave[0]}/{clave[1]}"
        claves_f.add(clave)
        if clave not in vistos:
            e.append(f"fuentes.json: {etq} no tiene entrada en tarifas.json")
        tipo = f.get("tipo", "precio")
        if tipo not in ("precio", "retiro"):
            e.append(f"fuentes.json: {etq} tipo inválido")
        if not f.get("paginas"):
            e.append(f"fuentes.json: {etq} sin páginas")
        grupos_vistos = set()
        for p in f.get("paginas", []):
            if not str(p.get("url", "")).startswith("https://"):
                e.append(f"fuentes.json: {etq} url no https")
            if p.get("formato", "markdown") not in ("markdown", "html"):
                e.append(f"fuentes.json: {etq} formato inválido")
            try:
                rx = re.compile(p.get("patron", ""))
                grupos_vistos |= set(rx.groupindex)
            except re.error as ex:
                e.append(f"fuentes.json: {etq} patrón inválido: {ex}")
        need = {"entrada_sin_cache", "salida"} if tipo == "precio" else {"retiro"}
        if not need <= grupos_vistos:
            e.append(f"fuentes.json: {etq} debe declarar los grupos {sorted(need)}")
    for clave in vistos - claves_f:
        e.append(f"fuentes.json: falta la fuente de {clave[0]}/{clave[1]}")
    return e, w


# ------------------------------------------------------------------- siembra
def sembrar(origen: Path, destino: Path, forzar: bool = False) -> Path:
    """Crea tarifas.json desde el JSON de la consulta manual del 2026-09-30 sin tocar un precio:
    solo cambia su representación (número -> cadena decimal mínima)."""
    destino = Path(destino)
    if (destino / "tarifas.json").exists() and not forzar:
        raise SystemExit("tarifas.json ya existe; use --forzar solo si quiere descartar las consultas posteriores")
    src = leer_json(origen)
    consulta = re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", src["consultado_utc"]).group(0)
    tarifas: List[Dict[str, Any]] = []
    for t in src["tarifas"]:
        api = t["modelo_api_id"]
        alias: List[str] = []
        m = re.match(r"^(\S+) \(alias: ([^)]+)\)$", api)
        if m:
            api, alias = m.group(1), [x.strip() for x in m.group(2).split(",")]
        if t["extracto_sha256"] != sha256_texto(t["extracto"]):
            raise SystemExit(f"{api}: el SHA-256 del extracto de origen no corresponde")
        nueva: Dict[str, Any] = {"proveedor": t["proveedor"], "modelo_comercial": t["modelo_comercial"], "modelo_api_id": api}
        if alias:
            nueva["alias"] = alias
        nueva.update({"moneda": t["moneda"]})
        for c in CAMPOS_PRECIO:
            nueva[c] = decimal_a_cadena(t[c])
        nueva.update({"otros_cargos": t["otros_cargos"], "url_oficial": t["url_oficial"], "extracto": t["extracto"],
                      "extracto_sha256": t["extracto_sha256"], "estado": t["estado"], "fecha_consulta_utc": consulta,
                      "origen": "consulta_manual_2026-09-30: descarga de la página oficial y lectura de la fila",
                      "consulta": None, "motivo_no_verificada": None, "ultimo_valor_verificado": None, "notas": t["notas"]})
        if t["estado"] != "verificada":
            nueva["motivo_no_verificada"] = t["notas"]
        tarifas.append(nueva)
    doc = {"esquema": ESQUEMA, "moneda": "USD", "unidad": "por millón de tokens, nivel estándar",
           "consulta_utc": consulta, "fuente_metodo": src["fuente_metodo"], "nota_tokenizadores": NOTA_TOKENIZADORES,
           "tokenizadores": src["tokenizadores"], "bloqueos": src["bloqueos"],
           "discrepancias_repo": src["discrepancias_repo"], "tarifas": tarifas}
    escribir_json(destino / "tarifas.json", doc)
    return destino / "tarifas.json"


# --------------------------------------------------------------------- mostrar
def _dias_desde(fecha: str, ahora: Optional[str]) -> Optional[int]:
    if not fecha or not _FECHA.match(fecha):
        return None
    ref = parsear_fecha(ahora) if ahora else datetime.now(timezone.utc)
    return int((ref - parsear_fecha(fecha)).total_seconds() // 86400)


def mostrar(directorio: Path, proveedor: Optional[str] = None, estado: Optional[str] = None,
            ahora: Optional[str] = None, dias: int = DIAS_MAXIMOS) -> str:
    doc = leer_json(Path(directorio) / "tarifas.json")
    filas = []
    for t in doc["tarifas"]:
        if proveedor and t["proveedor"].lower() != proveedor.lower():
            continue
        if estado and t["estado"] != estado:
            continue
        edad = _dias_desde(t.get("fecha_consulta_utc", ""), ahora)
        marca = t["estado"]
        if t["estado"] == "verificada" and edad is not None and edad > dias:
            marca = "desactualizada"
        filas.append([t["proveedor"], t["modelo_api_id"], marca,
                      *[("-" if t.get(c) is None else t[c]) for c in CAMPOS_PRECIO],
                      (t.get("fecha_consulta_utc") or "")[:10]])
    cab = ["proveedor", "modelo_api_id", "estado", "entrada", "cache_lect", "cache_escr", "salida", "consulta"]
    anchos = [max(len(str(x[i])) for x in [cab] + filas) for i in range(len(cab))]
    lineas = ["  ".join(str(c).ljust(anchos[i]) for i, c in enumerate(f)) for f in [cab] + filas]
    lineas.append("")
    lineas.append("USD por millón de tokens, nivel estándar. '-' = sin precio verificado o no aplica.")
    lineas.append(doc.get("nota_tokenizadores", ""))
    return "\n".join(lineas)


# -------------------------------------------------------------------------- CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="tarifas", description="Tarifas oficiales de proveedores de modelos")
    ap.add_argument("--directorio", type=Path, default=None, help="carpeta de tarifas (por defecto evidencia/tarifas)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("consultar", help="descarga las páginas oficiales y actualiza el estado")
    c.add_argument("--solo-comprobar", action="store_true", help="registra la consulta sin modificar tarifas.json")
    c.add_argument("--modelo", action="append", default=None, help="limita a estos modelo_api_id")
    v = sub.add_parser("verificar", help="valida estructura y antigüedad sin red")
    v.add_argument("--estricto", action="store_true", help="las advertencias (desactualizada) también fallan")
    v.add_argument("--dias", type=int, default=DIAS_MAXIMOS)
    v.add_argument("--ahora", default=None, help="instante de referencia AAAA-MM-DDThh:mm:ssZ (pruebas)")
    m = sub.add_parser("mostrar", help="tabla de tarifas")
    m.add_argument("--proveedor", default=None)
    m.add_argument("--estado", choices=ESTADOS, default=None)
    m.add_argument("--ahora", default=None)
    m.add_argument("--json", action="store_true")
    s = sub.add_parser("sembrar", help="crea tarifas.json desde la consulta manual (solo la primera vez)")
    s.add_argument("--desde", type=Path, required=True)
    s.add_argument("--forzar", action="store_true")
    a = ap.parse_args(argv)
    d = a.directorio or directorio_por_defecto()
    if a.cmd == "consultar":
        doc = consultar(d, ahora=None, solo_comprobar=a.solo_comprobar, modelos=a.modelo)
        r = doc["resumen"]
        for en in doc["entradas"]:
            marca = "OK " if en["estado"] == "verificada" else "NO "
            extra = "" if en["estado"] == "verificada" else f"  -> {en['motivo']}"
            cambio = "  (PRECIO CAMBIÓ: " + ", ".join(f"{x['campo']} {x['anterior']} -> {x['actual']}" for x in en["diferencias"]) + ")" if en.get("cambio_respecto_ultimo") else ""
            print(f"{marca}{en['proveedor']}/{en['modelo_api_id']}{extra}{cambio}")
        print(f"\n{r['verificadas']} verificadas, {r['no_verificadas']} no verificadas, {r['con_cambio_de_precio']} con cambio de precio.")
        if a.solo_comprobar:
            print("Modo --solo-comprobar: tarifas.json NO se modificó.")
        return 0
    if a.cmd == "verificar":
        errores, avisos = verificar(d, ahora=a.ahora, dias=a.dias)
        for x in errores:
            print("ERROR", x)
        for x in avisos:
            print("ADVERTENCIA", x)
        if not errores:
            doc = leer_json(d / "tarifas.json")
            n_ok = sum(1 for t in doc["tarifas"] if t["estado"] == "verificada")
            print(f"tarifas: {len(doc['tarifas'])} entradas ({n_ok} verificadas, {len(doc['tarifas']) - n_ok} no verificadas); {len(avisos)} advertencia(s)")
        return 1 if errores or (a.estricto and avisos) else 0
    if a.cmd == "mostrar":
        if a.json:
            doc = leer_json(d / "tarifas.json")
            json.dump([t for t in doc["tarifas"] if (not a.proveedor or t["proveedor"].lower() == a.proveedor.lower())
                       and (not a.estado or t["estado"] == a.estado)], sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            print(mostrar(d, a.proveedor, a.estado, a.ahora))
        return 0
    if a.cmd == "sembrar":
        print("escrito", sembrar(a.desde, d, a.forzar))
        return 0
    return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())

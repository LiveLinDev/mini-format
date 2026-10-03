"""Comprueba, por HTTP, qué hay publicado de verdad en el sitio.

    python tools/verificar_publicacion.py --esperado <sha>            # tras un despliegue
    python tools/verificar_publicacion.py --base http://127.0.0.1:8000 # contra un servidor local
    python tools/verificar_publicacion.py --json                       # salida para máquinas

Qué comprueba (solo lectura: únicamente peticiones GET):
  1. `/version.json`: si se da `--esperado`, el commit publicado debe coincidir. Si no coincide, el informe dice
     «SITIO NO ACTUALIZADO» y el código de salida es 1: nunca se presenta como actualizado algo que no lo está.
     Sin `--esperado` solo se informa del commit publicado y el estado de actualización queda «no verificado».
  2. Rutas clave: deben responder 200 (las rutas de `--rutas` o las de RUTAS_CLAVE).
  3. 404 real: una ruta inventada debe responder 404. Si responde 200 (típicamente con la portada) es un
     soft-404: se informa como ADVERTENCIA (falla la señal, no el despliegue); `--estricto` la convierte en error.
     El arreglo vive en nginx, no en el repositorio: sitio/servidor/NGINX_404.md.

Códigos de salida: 0 todo bien (puede haber advertencias); 1 algún error (versión distinta, ruta clave que no
responde 200, sitio inalcanzable, o advertencias con --estricto).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from urllib import error, request

BASE = "https://mini-format.pmoluna.com"
RUTAS_CLAVE = ("/", "/docs/", "/docs/spec/", "/docs/errors/E06/", "/playground/", "/mesa-de-ayuda/",
               "/taller/", "/ejemplo/", "/sima/", "/validacion/", "/economia/", "/flujo/", "/base.css", "/app.js",
               "/sitemap.xml", "/version.json")
# Rutas cuya ausencia no impide usar el sitio (p. ej. 404.html puede estar protegida como `internal` en nginx).
RUTAS_AVISO = ("/404.html",)


class _SinRedireccion(request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401
        return None


def consultar(url: str, timeout: float = 15.0) -> tuple[int | None, bytes, str]:
    """GET sin seguir redirecciones. Devuelve (estado, cuerpo, error); estado None si no hubo respuesta."""
    opener = request.build_opener(_SinRedireccion)
    peticion = request.Request(url, headers={"User-Agent": "mini-format-verificar-publicacion/1"})
    try:
        with opener.open(peticion, timeout=timeout) as respuesta:
            return respuesta.status, respuesta.read(4_000_000), ""
    except error.HTTPError as fallo:
        try:
            cuerpo = fallo.read(4_000_000)
        except Exception:  # noqa: BLE001
            cuerpo = b""
        return fallo.code, cuerpo, ""
    except (error.URLError, TimeoutError, OSError) as fallo:
        return None, b"", f"{type(fallo).__name__}: {fallo}"


def _coincide(publicado: str, esperado: str) -> bool:
    """Igualdad de commits admitiendo una abreviatura (mínimo 7 caracteres) de cualquiera de los dos."""
    publicado, esperado = publicado.strip().lower(), esperado.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{7,40}", publicado) or not re.fullmatch(r"[0-9a-f]{7,40}", esperado):
        return False
    return publicado.startswith(esperado) or esperado.startswith(publicado)


def verificar(base: str, esperado: str | None = None, rutas=RUTAS_CLAVE, timeout: float = 15.0, estricto: bool = False) -> dict:
    """Ejecuta todas las comprobaciones y devuelve el informe (dict serializable)."""
    base = base.rstrip("/")
    errores, advertencias, detalle = [], [], {}
    # ---- 1. versión publicada
    estado, cuerpo, fallo = consultar(base + "/version.json", timeout)
    version = None
    if estado != 200:
        errores.append(f"/version.json no responde 200 ({estado if estado else fallo})")
    else:
        try:
            version = json.loads(cuerpo.decode("utf-8"))
            if not isinstance(version, dict) or "commit" not in version:
                raise ValueError("falta la clave commit")
        except (ValueError, UnicodeDecodeError) as problema:
            version = None
            errores.append(f"/version.json no es un sello válido ({problema})")
    if version is None:
        actualizacion = "no verificable"
    elif esperado is None:
        actualizacion = "no verificado (falta --esperado)"
    elif _coincide(str(version["commit"]), esperado):
        actualizacion = "actualizado"
    else:
        actualizacion = "NO ACTUALIZADO"
        errores.append(f"SITIO NO ACTUALIZADO: version.json declara el commit {version['commit']} y se esperaba {esperado}")
    detalle["version"] = version
    # ---- 2. rutas clave
    estados = {}
    portada = None
    for ruta in rutas:
        estado, cuerpo, fallo = consultar(base + ruta, timeout)
        estados[ruta] = estado
        if ruta == "/":
            portada = cuerpo
        if estado != 200:
            errores.append(f"{ruta} responde {estado if estado else fallo}, se esperaba 200")
    for ruta in RUTAS_AVISO:
        estado, _, fallo = consultar(base + ruta, timeout)
        estados[ruta] = estado
        if estado != 200:
            advertencias.append(f"{ruta} responde {estado if estado else fallo} (se esperaba 200)")
    detalle["rutas"] = estados
    # ---- 3. 404 real
    inventada = f"/no-existe-{uuid.uuid4().hex[:10]}/"
    estado, cuerpo, fallo = consultar(base + inventada, timeout)
    detalle["ruta_inventada"] = {"ruta": inventada, "estado": estado}
    if estado == 404:
        respuesta_404 = "404 real"
    elif estado == 200:
        igual_portada = portada is not None and hashlib.sha256(cuerpo).digest() == hashlib.sha256(portada).digest()
        respuesta_404 = "soft-404 (200 con la portada)" if igual_portada else "soft-404 (200 con otra página)"
        advertencias.append(f"soft-404: {inventada} responde 200 {'con la portada ' if igual_portada else ''}en vez de 404; "
                            "hay que arreglar nginx (sitio/servidor/NGINX_404.md)")
    else:
        respuesta_404 = f"inesperada ({estado if estado else fallo})"
        advertencias.append(f"{inventada} responde {estado if estado else fallo}; se esperaba 404")
    detalle["respuesta_ruta_inventada"] = respuesta_404
    if estricto:
        errores.extend(f"(--estricto) {a}" for a in advertencias)
    return {"base": base, "esperado": esperado, "actualizacion": actualizacion, "ok": not errores,
            "errores": errores, "advertencias": advertencias, **detalle}


def imprimir(informe: dict, salida=None) -> None:
    salida = salida or sys.stdout

    def w(texto=""):
        print(texto, file=salida)
    v = informe.get("version") or {}
    w(f"Sitio: {informe['base']}")
    if v:
        w(f"  publicado: commit {v.get('commit')} · construido {v.get('construido')} · mini-format {v.get('mini_format')} · SPEC {v.get('spec')}")
    w(f"  actualización: {informe['actualizacion']}")
    w(f"  404 de una ruta inventada: {informe['respuesta_ruta_inventada']}")
    for ruta, estado in informe["rutas"].items():
        w(f"  {ruta} -> {estado}")
    for texto in informe["advertencias"]:
        w(f"ADVERTENCIA: {texto}")
    for texto in informe["errores"]:
        w(f"ERROR: {texto}")
    w("RESULTADO: " + ("correcto" if informe["ok"] else "FALLÓ")
      + (" (con advertencias)" if informe["ok"] and informe["advertencias"] else ""))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=BASE, help="URL base del sitio (por omisión producción)")
    ap.add_argument("--esperado", help="commit (completo o abreviado de 7+ caracteres) que debe estar publicado")
    ap.add_argument("--rutas", nargs="*", help="rutas que deben responder 200 (por omisión las rutas clave)")
    ap.add_argument("--timeout", type=float, default=15.0, help="segundos por petición")
    ap.add_argument("--estricto", action="store_true", help="las advertencias (soft-404...) cuentan como error")
    ap.add_argument("--json", action="store_true", help="imprime el informe como JSON")
    args = ap.parse_args(argv)
    informe = verificar(args.base, args.esperado, tuple(args.rutas) if args.rutas else RUTAS_CLAVE, args.timeout, args.estricto)
    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
    else:
        imprimir(informe)
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

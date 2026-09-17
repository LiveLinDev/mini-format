"""Demostración reproducible sin conexión del flujo de mini-format (HU25).

Recorre, con una salida de modelo grabada y sin acceso a la red, las etapas de integración del componente:

1. contrato de la familia ``a`` (ítems de evaluación);
2. instrucción para el modelo generada desde el contrato (``spec_block``);
3. lectura en streaming de una respuesta real archivada del experimento E1
   (``generative/raw/e1/haiku/mini/1.txt``, modelo ``claude-haiku-4-5-20251001``);
4. validación y diagnóstico con código, línea y campo;
5. reparación selectiva: se alteran deliberadamente dos líneas de la respuesta para mostrar el mecanismo y
   la respuesta de reparación se reproduce con las líneas originales de la misma salida grabada (no se
   invoca ningún modelo);
6. objetos tipados (JSON canónico).

La red se bloquea durante toda la ejecución: cualquier intento de conexión interrumpe la demostración.

Uso:  python demo/sin-conexion/demo.py [--rapido] [--pausa SEGUNDOS]
"""
import argparse
import json
import socket
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import Registry, parse  # noqa: E402
from minifmt.ai.repair import merge_repair, repair_request  # noqa: E402
from minifmt.prompt import spec_block  # noqa: E402
from minifmt.stream import Reader  # noqa: E402

SALIDA_GRABADA = RAIZ / "generative" / "raw" / "e1" / "haiku" / "mini" / "1.txt"
MODELO = "claude-haiku-4-5-20251001"
LIMITE_SEGUNDOS = 180


class RedBloqueada(RuntimeError):
    """Se lanza si algún componente intenta abrir una conexión durante la demostración."""


def bloquear_red():
    def _bloqueado(*_a, **_k):
        raise RedBloqueada("la demostración se ejecuta sin conexión: acceso a la red bloqueado")

    socket.socket.connect = _bloqueado          # type: ignore[assignment]
    socket.create_connection = _bloqueado       # type: ignore[assignment]
    socket.getaddrinfo = _bloqueado             # type: ignore[assignment]


def titulo(n, texto):
    print(f"\n[{n}/6] {texto}")
    print("-" * (len(texto) + 6))


def alterar(documento):
    """Introduce dos fallos típicos y devuelve (texto alterado, líneas alteradas, líneas originales)."""
    lineas = documento.split("\n")
    originales = {}
    # Registro en la línea 3: la opción correcta pierde su marcador (E08).
    originales[3] = lineas[2]
    lineas[2] = lineas[2].replace("*", "", 1)
    # Registro en la línea 6: nivel de Bloom fuera de la enumeración (E10).
    originales[6] = lineas[5]
    campos = lineas[5].split("|")
    campos[1] = "L9"
    lineas[5] = "|".join(campos)
    return "\n".join(lineas), sorted(originales), originales


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rapido", action="store_true", help="sin pausas entre fragmentos del streaming")
    ap.add_argument("--pausa", type=float, default=0.004, help="pausa entre fragmentos (segundos)")
    args = ap.parse_args(argv)
    inicio = time.monotonic()
    bloquear_red()

    titulo(1, "Contrato")
    contrato = Registry.load(RAIZ / "forks").get("a")
    print(f"Familia '{contrato.prefix}': {contrato.name}")
    print(f"Firma: {contrato.signature()}")

    titulo(2, "Instrucción para el modelo (generada desde el contrato)")
    bloque = spec_block(contrato, "es")
    for linea in bloque.splitlines()[:8]:
        print(f"  {linea}")
    print(f"  ... ({len(bloque.splitlines())} líneas; no se redacta a mano)")

    titulo(3, "Lectura en streaming de una respuesta grabada")
    respuesta = SALIDA_GRABADA.read_text(encoding="utf-8")
    print(f"Fuente: {SALIDA_GRABADA.relative_to(RAIZ).as_posix()} (modelo {MODELO}, experimento E1)")
    lector = Reader(contrato)
    for i in range(0, len(respuesta), 24):
        for item in lector.push(respuesta[i:i + 24]):
            print(f"  línea {item.line:>2}: registro {item.record['id']} recibido")
        if not args.rapido and args.pausa:
            time.sleep(args.pausa)
    final = lector.end()
    print(f"Registros válidos: {final.valid}/{final.expected} · errores: {len(final.errors)}")

    titulo(4, "Validación y diagnóstico")
    alterado, lineas_alteradas, originales = alterar(respuesta)
    print(f"Alteración deliberada de las líneas {lineas_alteradas} para mostrar la reparación.")
    diagnostico = Reader(contrato)
    diagnostico.push(alterado)
    resultado = diagnostico.end()
    for error in resultado.errors:
        campo = f", campo {error.field}" if getattr(error, "field", None) else ""
        print(f"  {error.code} en la línea {error.line}{campo}: {error.message}")
    print(f"Registros válidos conservados: {resultado.valid}/{resultado.expected}")

    titulo(5, "Reparación selectiva")
    solicitud = repair_request(alterado, contrato, "es", include_spec=False)
    print(f"Líneas reenviadas al modelo: {solicitud.lines} (de {resultado.expected} registros)")
    for item in solicitud.items:
        print(f"  línea {item.line}: {[e.code for e in item.errors]}")
    reparacion = "\n".join(originales[n] for n in solicitud.lines)
    print("Respuesta de reparación: líneas originales de la salida grabada (no se invoca un modelo).")
    fusion = merge_repair(alterado, reparacion, contrato, request=solicitud)
    print(f"Líneas reemplazadas: {fusion.replaced} · errores restantes: {len(fusion.errors)} · orden original conservado")

    titulo(6, "Objetos tipados")
    documento = parse(fusion.text, contrato)
    canonico = documento.to_canonical()
    primero = canonico[contrato.records_key][0]
    print(json.dumps(primero, ensure_ascii=False, indent=2))
    identico = canonico == parse(respuesta, contrato).to_canonical()
    print(f"Documento reparado idéntico a la respuesta original: {'sí' if identico else 'no'}")

    duracion = time.monotonic() - inicio
    print(f"\nDuración: {duracion:.1f} s (límite: {LIMITE_SEGUNDOS} s) · red bloqueada durante toda la ejecución")
    return 0 if (fusion.ok and identico and duracion < LIMITE_SEGUNDOS) else 1


if __name__ == "__main__":
    sys.exit(main())

"""V5 (b): streaming con cortes de bytes en CADA frontera (Reader de Python).

El documento se entrega partido en dos trozos de bytes UTF-8, b[:k] y b[k:], para todo k entre 0 y len(b):
incluye el corte en mitad de un carácter multibyte, en mitad de una secuencia de escape (``\\`` | ``n``),
entre CR y LF y dentro del BOM. El resultado (registros, errores con su línea, cabecera y diagnósticos)
debe ser idéntico al de parsear el texto entero en modo tolerante, y los registros emitidos por ``push()``
más ``final_records`` deben ser exactamente los registros válidos, en orden.

Base: los ficheros ``valid``, ``escaping`` y ``bad_*`` de las 14 familias y los casos strict/lenient de la
suite de conformidad (sin repetir el mismo texto con el mismo contrato), más documentos propios con
caracteres de 1, 2, 3 y 4 bytes y secuencias de escape en todas las posiciones. Las mismas comprobaciones en
TypeScript y en js/mini.js están en ts/test/cortes.test.ts.

Por omisión se cortan en cada byte los documentos de hasta 300 bytes y, en los mayores, cada byte de las
zonas críticas (principio, final, cerca de LF, CR o barra invertida y por dentro de los caracteres multibyte,
muestreados a partir del vigésimo). ``MINI_CORTES_COMPLETO=1`` corta en absolutamente todas las posiciones de todos los documentos.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from typing import Iterator, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from minifmt import Contract, MiniError, MiniValidationError, Registry, parse  # noqa: E402
from minifmt.stream import Reader  # noqa: E402

REG = Registry.load(ROOT / "forks")
COMPLETO = os.environ.get("MINI_CORTES_COMPLETO") == "1"
LIMITE_COMPLETO = 300
VECINDAD = 3

EXTRA = [  # documentos propios: 1, 2, 3 y 4 bytes por carácter, escapes y finales de línea
    ("fam:cls", "cls|n=2|k=6\r\nm1|ñandú € \U0001F600 e\u0301|question*,feedback,bug,request,praise,other|0.9|nota\\npartida\\\\fin\r\n"
                "m2|\\|barra y \\, coma|question,feedback,bug,request,praise*,other|0.5|"),
    ("fam:cls", "\ufeffcls|n=1|k=6\nm1|texto|question*,feedback,bug,request,praise,other|0.9|\\"),
    ("fam:cls", "cls|n=1|k=6\nm1|\U0001F600\U0001F600|question*,feedback,bug,request,praise,other|x|"),
    ("fam:cls", "cls|n=3\n\n   \nm1|a|question*,feedback,bug,request,praise,other|0.9|\n"),
]


def _base() -> Iterator[Tuple[str, str, Contract]]:
    vistos: Set[Tuple[str, str]] = set()
    contratos = {c.prefix: c for c in REG}
    for c in REG:
        for f in sorted((REG.paths[c.prefix] / "fixtures").glob("*.mini")):
            texto = f.read_text(encoding="utf-8")
            if (c.prefix, texto) not in vistos:
                vistos.add((c.prefix, texto))
                yield f"{c.prefix}/{f.name}", texto, c
    for archivo in sorted((ROOT / "conformance" / "cases").glob("*.json")):
        for caso in json.loads(archivo.read_text(encoding="utf-8"))["cases"]:
            if caso["mode"] not in ("strict", "lenient"):
                continue
            contrato = Contract.from_dict(caso["contract"]) if "contract" in caso else contratos[caso["family"]]
            clave = (caso["contract"]["prefix"] if "contract" in caso else caso["family"]) + json.dumps(caso.get("contract"), sort_keys=True)
            if (clave, caso["input"]) not in vistos:
                vistos.add((clave, caso["input"]))
                yield f"caso/{caso['id']}", caso["input"], contrato
    for i, (clave, texto) in enumerate(EXTRA):
        yield f"extra/{i}", texto, contratos[clave.split(":")[1]]


def cortes(datos: bytes) -> List[int]:
    n = len(datos)
    if COMPLETO or n <= LIMITE_COMPLETO:
        return list(range(n + 1))
    criticas: Set[int] = set(range(0, min(n, 64) + 1)) | {n - i for i in range(0, min(n, 16) + 1)}
    i = multibyte = 0
    while i < n:
        b = datos[i]
        if b >= 0xC0:  # principio de un carácter multibyte: todos los cortes que lo parten por dentro
            largo = 2 if b < 0xE0 else 3 if b < 0xF0 else 4
            multibyte += 1
            if multibyte <= 20 or multibyte % 7 == 0:  # el resto de los caracteres se muestrea (completo con MINI_CORTES_COMPLETO=1)
                criticas.update(range(i, min(n, i + largo) + 1))
            i += largo
            continue
        if b in (0x0A, 0x0D, 0x5C):  # salto de línea, CR, barra invertida: el corte justo antes, dentro y después
            criticas.update(range(max(0, i - VECINDAD), min(n, i + VECINDAD) + 1))
        i += 1
    return sorted(criticas)


def referencia(texto: str, contrato: Contract):
    try:
        doc = parse(texto, contrato, strict=False)
    except MiniValidationError as e:
        return ("raise", [x.to_dict() for x in e.errors])
    except MiniError as e:
        return ("raise", [e.to_dict()])
    return (doc.to_canonical(), [e.to_dict() for e in doc.errors], doc.diagnostics())


def por_trozos(trozos: List[bytes], contrato: Contract):
    lector = Reader(contrato, strict=False)
    emitidos = []
    for t in trozos:
        emitidos.extend(lector.push(t))
    res = lector.end()
    emitidos.extend(res.final_records)
    return (res.document.to_canonical(), [e.to_dict() for e in res.errors], res.document.diagnostics()), emitidos


class CortesEnCadaByte(unittest.TestCase):
    def test_todo_corte_equivale_a_parsear_entero(self):
        documentos = cortes_realizados = 0
        for etiqueta, texto, contrato in _base():
            datos = texto.encode("utf-8")
            esperado = referencia(texto, contrato)
            if esperado[0] == "raise":
                continue  # documento vacío: Python lanza en parse; el Reader devuelve E01 (ver test aparte)
            registros = esperado[0][contrato.records_key]
            documentos += 1
            for k in cortes(datos):
                obtenido, emitidos = por_trozos([datos[:k], datos[k:]], contrato)
                cortes_realizados += 1
                if obtenido != esperado:
                    self.fail(f"{etiqueta}: corte en el byte {k}/{len(datos)} difiere de parse\n"
                              f"  esperado: {str(esperado)[:300]}\n  obtenido: {str(obtenido)[:300]}")
                if [e.record for e in emitidos] != registros:
                    self.fail(f"{etiqueta}: corte en el byte {k}: los registros emitidos no son los válidos")
        self.assertGreater(documentos, 300)
        self.assertGreater(cortes_realizados, 10000)

    def test_tres_trozos_y_byte_a_byte_en_los_documentos_propios(self):
        for i, (clave, texto) in enumerate(EXTRA):
            contrato = REG.get(clave.split(":")[1])
            datos = texto.encode("utf-8")
            esperado = referencia(texto, contrato)
            solos, _ = por_trozos([datos[j:j + 1] for j in range(len(datos))], contrato)
            self.assertEqual(solos, esperado, f"extra/{i} byte a byte")
            for a in range(0, len(datos) + 1, 3):
                for b in range(a, len(datos) + 1, 5):
                    obtenido, _ = por_trozos([datos[:a], datos[a:b], datos[b:]], contrato)
                    self.assertEqual(obtenido, esperado, f"extra/{i} cortes {a},{b}")

    def test_flujo_sin_bytes_devuelve_e01(self):
        contrato = REG.get("cls")
        res = Reader(contrato, strict=False).end()
        self.assertEqual([(e.code, e.line) for e in res.errors], [("E01", 0)])

    def test_los_cortes_en_texto_str_tambien_son_equivalentes(self):
        """Mismo control con trozos str (no bytes): cada posición de carácter."""
        for i, (clave, texto) in enumerate(EXTRA):
            contrato = REG.get(clave.split(":")[1])
            esperado = referencia(texto, contrato)
            for k in range(len(texto) + 1):
                lector = Reader(contrato, strict=False)
                lector.push(texto[:k])
                res = lector.end(texto[k:])
                self.assertEqual((res.document.to_canonical(), [e.to_dict() for e in res.errors],
                                  res.document.diagnostics()), esperado, f"extra/{i} carácter {k}")


if __name__ == "__main__":
    unittest.main()

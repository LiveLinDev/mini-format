"""Genera los datos del banco de pruebas: contrato, respuestas por escenario y conteos de tokens reales."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
import tiktoken  # noqa: E402
from minifmt import Contract, dumps, parse, spec_block  # noqa: E402

CONTRATO = {
    "prefix": "rec", "version": 1, "name": "Reclamos de clientes", "records_key": "reclamos",
    "description": "Un reclamo por línea, extraído de mensajes de clientes.",
    "header": {"required": ["n"], "keys": {"l": {"type": "str", "desc": "idioma"}}},
    "core": [
        {"name": "id", "type": "str", "unique": True},
        {"name": "canal", "type": "enum", "values": ["web", "correo", "telefono", "tienda"]},
        {"name": "categoria", "type": "enum", "values": ["cobro", "entrega", "producto", "atencion", "otro"]},
        {"name": "prioridad", "type": "int", "min": 1, "max": 5},
        {"name": "monto", "type": "float", "min": 0, "optional": True},
        {"name": "resumen", "type": "str"},
    ],
    "extensions": [],
}
F = ["id", "canal", "categoria", "prioridad", "monto", "resumen"]
filas = [
    ("R-1001", "web", "cobro", 4, 129.9, "Cobro duplicado de la suscripción mensual"),
    ("R-1002", "correo", "entrega", 3, None, "El pedido figura entregado pero no llegó"),
    ("R-1003", "telefono", "producto", 2, 45.5, "Audífonos con falla en el lado izquierdo"),
    ("R-1004", "web", "cobro", 5, 980.0, "Cargo no reconocido en tarjeta, solicita anulación"),
    ("R-1005", "tienda", "entrega", 3, None, "Pedido 4471 | llegó incompleto, faltan 2 cajas"),
    ("R-1006", "correo", "atencion", 2, None, "No recibió respuesta del área de soporte en 5 días"),
    ("R-1007", "web", "producto", 4, 1299.0, "Laptop llegó con la pantalla rota"),
    ("R-1008", "telefono", "cobro", 3, 59.9, "Le cobraron envío en una compra con envío gratis"),
    ("R-1009", "web", "otro", 1, None, "Sugiere agregar pago con billetera digital"),
    ("R-1010", "correo", "cobro", 4, 129.9, "Reembolso aprobado hace 15 días sin abono"),
    ("R-1011", "tienda", "producto", 2, 35.0, "Talla distinta a la indicada en la etiqueta"),
    ("R-1012", "web", "entrega", 5, None, "Entrega programada a otra dirección, urgente"),
]
verdad = [dict(zip(F, r)) for r in filas]
c = Contract.from_dict(CONTRATO)
enc = {k: tiktoken.get_encoding(k) for k in ("o200k_base", "cl100k_base")}
tok = lambda s, k="o200k_base": len(enc[k].encode(s))

mini_ok = dumps({"header": {"l": "es"}, "reclamos": verdad}, c)
assert parse(mini_ok, c).to_canonical()["reclamos"] == verdad
json_ok = json.dumps({"reclamos": verdad}, ensure_ascii=False, separators=(",", ":"))
lineas = mini_ok.split("\n")
casero_ok = "\n".join(l.replace("\\|", "|") for l in lineas[1:])  # el prompt casero no define escapes

# Escenario 2: el texto trae el separador y el modelo no lo escapa
mini_delim = mini_ok.replace("Pedido 4471 \\| llegó", "Pedido 4471 | llegó")
# Escenario 3: la respuesta se corta dentro del registro 10 (límite de tokens de salida)
corte_mini = mini_ok.index("R-1010") + len("R-1010|correo|cobro|4|12")
mini_trunc = mini_ok[:corte_mini]
casero_trunc = casero_ok[:casero_ok.index("R-1010") + len("R-1010|correo|cobro|4|12")]
json_trunc = json_ok[:json_ok.index('"R-1010"') + len('"R-1010","canal":"correo","categoria":"cobro","prioridad":4,"monto":12')]
# Escenario 4: valores fuera del contrato
def fuera(t):
    return (t.replace("R-1004|web|cobro|5", "R-1004|web|reembolso|5")
             .replace("R-1008|telefono|cobro|3", "R-1008|telefono|cobro|7"))
mini_inval, casero_inval = fuera(mini_ok), fuera(casero_ok)
json_inval = (json_ok.replace('"R-1004","canal":"web","categoria":"cobro"', '"R-1004","canal":"web","categoria":"reembolso"')
                     .replace('"R-1008","canal":"telefono","categoria":"cobro","prioridad":3', '"R-1008","canal":"telefono","categoria":"cobro","prioridad":7'))
assert mini_inval != mini_ok and json_inval != json_ok

bloque = spec_block(c, "es")
datos = {
    "contrato": CONTRATO, "verdad": verdad,
    "tokens": {
        k: {"json": tok(json_ok, k), "json_indentado": tok(json.dumps({"reclamos": verdad}, ensure_ascii=False, indent=2), k),
            "mini": tok(mini_ok, k), "bloque": tok(bloque, k)} for k in enc
    },
    "tokens_registro_mini": {r["id"]: tok(l) for r, l in zip(verdad, lineas[1:])},
    "tokens_registro_json": {r["id"]: tok(json.dumps(r, ensure_ascii=False, separators=(",", ":"))) for r in verdad},
    "escenarios": [
        {"id": "ok", "titulo": "Respuesta correcta", "json": json_ok, "casero": casero_ok, "mini": mini_ok},
        {"id": "delim", "titulo": "Texto con el separador", "json": json_ok, "casero": casero_ok, "mini": mini_delim},
        {"id": "trunc", "titulo": "Respuesta cortada", "json": json_trunc, "casero": casero_trunc, "mini": mini_trunc},
        {"id": "inval", "titulo": "Valores fuera del contrato", "json": json_inval, "casero": casero_inval, "mini": mini_inval},
    ],
}
out = Path(__file__).parent / "datos_demo.json"
out.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(datos["tokens"], indent=1))
print(bloque)
print(mini_ok)

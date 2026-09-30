"""Configuración ESPECIALIZADA dentro de SPEC 1.1: contrato diseñado a mano + mapa explícito.

Una ``Especializacion`` describe, campo por campo, cómo el objeto de la aplicación se representa
en el documento .mini y cómo se reconstruye. Todo lo que no es el formato (códigos cortos de
enumeración, prefijo constante de un identificador, enteros escalados, hora como minutos) vive
en la APLICACIÓN como un mapa explícito: el mismo mapa se imprime en la instrucción (y por tanto
se cuenta en sus tokens) y lo usa ``reconstruir``. El núcleo de .mini no sabe nada de él: el objeto
canónico que entrega ``parse`` lleva los códigos cortos tal cual.

Regla de descarte: ``comprobar_equivalencia`` exige ``reconstruir(parse(dumps(codificar(x)))) == x``
para TODO registro (valores, tipos, orden de claves y metadatos). Si falla, la configuración no
sirve y no entra en ninguna comparación.

No amplía el formato: solo usa contrato, cabecera tipada, enum, int/float acotados y date de SPEC 1.1.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from minifmt import dumps, parse, spec_block  # noqa: E402
from minifmt.contract import Contract  # noqa: E402
from minifmt.errors import MiniError, MiniValidationError  # noqa: E402

TRATAMIENTOS = ("pasa", "codigos", "id_prefijo", "escalado", "hhmm", "constante")


class NoEquivalente(Exception):
    """La configuración no reconstruye el objeto original: se descarta."""


@dataclass
class Campo:
    """Tratamiento de UN campo del objeto original."""
    orig: str                          # nombre en el objeto de la aplicación (JSON)
    tratamiento: str = "pasa"          # uno de TRATAMIENTOS
    tipo: str = "str"                  # tipo del campo original: str, int, float, bool, enum, date
    minimo: Optional[float] = None     # rango (int/float); para 'escalado' es el rango ORIGINAL
    maximo: Optional[float] = None
    valores: Optional[List[str]] = None   # enum original (etiquetas)
    desc: str = ""                     # descripción que va a la instrucción
    # --- tratamiento 'codigos'
    mapa: Optional[Dict[str, str]] = None   # etiqueta -> código
    # --- tratamiento 'id_prefijo'
    prefijo: str = ""
    ancho: int = 0                     # 0 = sin ceros a la izquierda; >0 = relleno con ceros
    # --- tratamiento 'escalado'
    factor: int = 1
    # --- tratamiento 'constante'
    clave_cabecera: str = ""
    # --- nombre en el contrato .mini (por omisión, el original)
    mini: str = ""

    def nombre(self) -> str:
        return self.mini or self.orig

    # ------------------------------------------------------------ tipo en el contrato
    def tipo_mini(self) -> str:
        if self.tratamiento == "codigos":
            return "enum"
        if self.tratamiento in ("id_prefijo", "hhmm", "escalado"):
            return "int"
        return self.tipo

    def valores_mini(self) -> Optional[List[str]]:
        if self.tratamiento == "codigos":
            return [self.mapa[v] for v in (self.valores or [])]
        return self.valores if self.tipo == "enum" else None

    def rango_mini(self) -> Tuple[Optional[int], Optional[int]]:
        t = self.tratamiento
        if t == "id_prefijo":
            return (self.minimo if self.minimo is not None else 0), self.maximo
        if t == "hhmm":
            return 0, 1439
        if t == "escalado":
            lo = None if self.minimo is None else round(self.minimo * self.factor)
            hi = None if self.maximo is None else round(self.maximo * self.factor)
            return lo, hi
        return self.minimo, self.maximo


# ------------------------------------------------------------------ valores
def a_mini(c: Campo, v: Any) -> Any:
    t = c.tratamiento
    if t == "pasa":
        return v
    if t == "codigos":
        if v not in c.mapa:
            raise NoEquivalente(f"{c.orig}: valor {v!r} sin código")
        return c.mapa[v]
    if t == "id_prefijo":
        if not isinstance(v, str) or not v.startswith(c.prefijo):
            raise NoEquivalente(f"{c.orig}: {v!r} no empieza por {c.prefijo!r}")
        resto = v[len(c.prefijo):]
        if not resto.isascii() or not resto.isdigit():
            raise NoEquivalente(f"{c.orig}: {v!r} no es prefijo + dígitos")
        n = int(resto)
        if (f"{n:0{c.ancho}d}" if c.ancho else str(n)) != resto:
            raise NoEquivalente(f"{c.orig}: {v!r} no se reconstruye (ceros a la izquierda)")
        return n
    if t == "escalado":
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise NoEquivalente(f"{c.orig}: {v!r} no es numérico")
        n = round(v * c.factor)
        if de_mini(c, n) != v or type(de_mini(c, n)) is not type(v):
            raise NoEquivalente(f"{c.orig}: {v!r} no sobrevive al escalado x{c.factor}")
        return n
    if t == "hhmm":
        if not (isinstance(v, str) and len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit()):
            raise NoEquivalente(f"{c.orig}: {v!r} no es HH:MM")
        m = int(v[:2]) * 60 + int(v[3:])
        if de_mini(c, m) != v:
            raise NoEquivalente(f"{c.orig}: {v!r} no sobrevive a minutos")
        return m
    raise ValueError(t)


def de_mini(c: Campo, v: Any) -> Any:
    t = c.tratamiento
    if t == "pasa":
        return v
    if t == "codigos":
        inv = {cod: et for et, cod in c.mapa.items()}
        return inv[v]
    if t == "id_prefijo":
        return c.prefijo + (f"{v:0{c.ancho}d}" if c.ancho else str(v))
    if t == "escalado":
        return v / c.factor
    if t == "hhmm":
        return f"{v // 60:02d}:{v % 60:02d}"
    raise ValueError(t)


# ------------------------------------------------------------------ especialización
@dataclass
class Especializacion:
    prefijo: str                       # prefijo de la familia .mini (p. ej. «tke»)
    nombre: str
    descripcion: str = ""              # texto libre; aquí va la explicación de los mapas
    clave_json: str = "registros"      # envoltorio JSON de la aplicación ({clave: [...]})
    campos: List[Campo] = field(default_factory=list)   # en el ORDEN ORIGINAL de claves del objeto
    orden: Optional[List[str]] = None  # orden contractual (nombres de campo en el contrato); None = el original
    separador_lista: str = ","

    def campos_registro(self) -> List[Campo]:
        """Campos que viajan en la línea de cada registro, en el orden contractual."""
        viajan = {c.nombre(): c for c in self.campos if c.tratamiento != "constante"}
        orden = self.orden or [c.nombre() for c in self.campos if c.tratamiento != "constante"]
        if sorted(orden) != sorted(viajan):
            raise ValueError(f"orden inválido: {orden} frente a {list(viajan)}")
        return [viajan[n] for n in orden]

    def constantes(self) -> List[Campo]:
        return [c for c in self.campos if c.tratamiento == "constante"]

    # ---------------------------------------------------------------- contrato
    def descripcion_completa(self) -> str:
        """Descripción del contrato: la de la familia + los mapas (todo entra en el bloque de instrucción)."""
        partes = [self.descripcion] if self.descripcion else []
        for c in self.campos_registro():
            if c.tratamiento == "codigos":
                partes.append(f"{c.nombre()}: " + " ".join(f"{cod}={et}" for et, cod in c.mapa.items()) + ".")
            elif c.tratamiento == "id_prefijo":
                partes.append(f"{c.nombre()}: número del identificador sin el prefijo {c.prefijo}"
                              + (f" ({c.ancho} dígitos con ceros a la izquierda)" if c.ancho else "") + ".")
            elif c.tratamiento == "escalado":
                partes.append(f"{c.nombre()}: valor x{c.factor} como entero (p. ej. 21.5 se escribe {round(21.5 * c.factor)}).")
            elif c.tratamiento == "hhmm":
                partes.append(f"{c.nombre()}: minutos desde las 00:00 (HH:MM = 60*HH + MM).")
        return " ".join(partes)

    def contrato_dict(self) -> Dict[str, Any]:
        core = []
        for c in self.campos_registro():
            d: Dict[str, Any] = {"name": c.nombre(), "type": c.tipo_mini()}
            vals = c.valores_mini()
            if d["type"] == "enum":
                d["values"] = vals
            lo, hi = c.rango_mini()
            if d["type"] in ("int", "float"):
                if lo is not None:
                    d["min"] = lo
                if hi is not None:
                    d["max"] = hi
            if c.desc and c.tratamiento in ("pasa",) and d["type"] not in ("enum",):
                d["desc"] = c.desc
            core.append(d)
        claves = {"n": {"type": "int", "desc": "número de registros"}}
        req = ["n"]
        for c in self.constantes():
            claves[c.clave_cabecera] = {"type": c.tipo, "desc": c.desc or c.orig}
            req.append(c.clave_cabecera)
        return {"prefix": self.prefijo, "version": 1, "name": self.nombre,
                "description": self.descripcion_completa(), "list_separator": self.separador_lista,
                "header": {"required": req, "keys": claves}, "core": core, "extensions": []}

    def contrato(self) -> Contract:
        return Contract.from_dict(self.contrato_dict())

    # ---------------------------------------------------------------- codificar / reconstruir
    def codificar(self, registros: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Objeto canónico de .mini ({prefix, header, records}) a partir de los registros de la aplicación."""
        if not registros:
            raise NoEquivalente("lote vacío")
        cab: Dict[str, Any] = {}
        for c in self.constantes():
            vals = {json.dumps(r[c.orig]) for r in registros}
            if len(vals) != 1:
                raise NoEquivalente(f"{c.orig} no es constante en el lote: {sorted(vals)[:3]}")
            cab[c.clave_cabecera] = registros[0][c.orig]
        viajan = [c for c in self.campos if c.tratamiento != "constante"]
        recs = [{c.nombre(): a_mini(c, r[c.orig]) for c in viajan} for r in registros]
        return {"prefix": self.prefijo, "header": cab, "records": recs}

    def reconstruir(self, obj: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Inversa de ``codificar`` sobre el objeto que entrega ``parse(...).to_canonical()``."""
        cab = obj["header"]
        inv = {c.nombre(): c for c in self.campos if c.tratamiento != "constante"}
        out = []
        for r in obj["records"]:
            o: Dict[str, Any] = {}
            for c in self.campos:              # orden ORIGINAL de claves
                if c.tratamiento == "constante":
                    o[c.orig] = cab[c.clave_cabecera]
                else:
                    o[c.orig] = de_mini(c, r[c.nombre()])
            out.append(o)
        return out

    def mapa_explicito(self) -> Dict[str, Any]:
        """El mapa de la aplicación (lo que NO está en el núcleo de .mini): se guarda como ``mapa.json``."""
        m: Dict[str, Any] = {"esquema": "mini-format/mapa-opt/1", "prefijo": self.prefijo, "clave_json": self.clave_json,
                             "orden_contractual": [c.nombre() for c in self.campos_registro()], "campos": []}
        for c in self.campos:
            e: Dict[str, Any] = {"campo": c.orig, "tratamiento": c.tratamiento, "nombre_en_contrato": c.nombre()}
            if c.tratamiento == "codigos":
                e["codigos"] = dict(c.mapa)
            elif c.tratamiento == "id_prefijo":
                e.update(prefijo=c.prefijo, ancho=c.ancho)
            elif c.tratamiento == "escalado":
                e.update(factor=c.factor, tipo_original=c.tipo)
            elif c.tratamiento == "constante":
                e.update(clave_cabecera=c.clave_cabecera, tipo=c.tipo)
            m["campos"].append(e)
        return m


def serializar_objeto(obj: Any) -> str:
    """JSON determinista con tipos y orden de claves visibles (para comparar ida y vuelta)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def comprobar_equivalencia(esp: Especializacion, registros: Sequence[Dict[str, Any]]) -> None:
    """Lanza ``NoEquivalente`` si ``reconstruir(parse(dumps(codificar(x)))) != x`` (tipos y orden incluidos)."""
    c = esp.contrato()
    obj = esp.codificar(registros)
    try:
        texto = dumps(obj, c)
        doc = parse(texto, c, strict=True)
    except (MiniError, MiniValidationError) as e:
        raise NoEquivalente(f"el documento no es válido bajo el contrato: {e}") from None
    vuelta = esp.reconstruir(doc.to_canonical())
    if serializar_objeto(vuelta) != serializar_objeto(list(registros)):
        for i, (a, b) in enumerate(zip(vuelta, registros)):
            if serializar_objeto(a) != serializar_objeto(b):
                raise NoEquivalente(f"registro {i}: {serializar_objeto(b)} != {serializar_objeto(a)}")
        raise NoEquivalente("distinto número de registros")


# ------------------------------------------------------------------ esquemas de códigos
def _prefijo_unico(etiquetas: Sequence[str]) -> Dict[str, str]:
    """Prefijo más corto de cada etiqueta que no es prefijo de otra etiqueta (abreviatura mnemotécnica)."""
    out = {}
    for e in etiquetas:
        for k in range(1, len(e) + 1):
            p = e[:k]
            if not any(o != e and o.startswith(p) for o in etiquetas):
                out[e] = p
                break
        else:
            out[e] = e
    return out


def _iniciales(etiquetas: Sequence[str]) -> Optional[Dict[str, str]]:
    cods = {e: "".join(w[0] for w in e.split("_") if w) for e in etiquetas}
    return cods if len(set(cods.values())) == len(etiquetas) else None


def esquemas_de_codigos(etiquetas: Sequence[str]) -> Dict[str, Dict[str, str]]:
    """Esquemas candidatos de código para una enumeración, cada uno con mapa etiqueta -> código único."""
    etiquetas = list(etiquetas)
    n = len(etiquetas)
    out: Dict[str, Dict[str, str]] = {"etiqueta": {e: e for e in etiquetas}}
    out["abrev"] = _prefijo_unico(etiquetas)
    ini = _iniciales(etiquetas)
    if ini is not None and ini != out["abrev"]:
        out["iniciales"] = ini
    if n <= 26:
        out["seq_letra"] = {e: chr(ord("a") + i) for i, e in enumerate(etiquetas)}
        out["seq_LETRA"] = {e: chr(ord("A") + i) for i, e in enumerate(etiquetas)}
    if n <= 10:
        out["seq_digito"] = {e: str(i) for i, e in enumerate(etiquetas)}
    # sin duplicados dentro de un esquema
    return {k: v for k, v in out.items() if len(set(v.values())) == n}


def con_codigos(c: Campo, esquema: str) -> Campo:
    """Copia del campo con el esquema de códigos aplicado ('etiqueta' = dejar el campo como enum sin cambios)."""
    from dataclasses import replace
    if esquema == "etiqueta":
        return replace(c, tratamiento="pasa", mapa=None)
    return replace(c, tratamiento="codigos", mapa=esquemas_de_codigos(c.valores)[esquema])


# ------------------------------------------------------------------ instrucciones
def _tipo_legible(c: Campo) -> str:
    t = c.tipo_mini()
    if t == "enum":
        if c.tratamiento == "codigos":
            return " ".join(f"{cod}={et}" for et, cod in c.mapa.items())
        return "uno de " + "|".join(c.valores or [])
    lo, hi = c.rango_mini()
    base = {"str": "texto", "int": "entero", "float": "número", "bool": "true/false", "date": "fecha AAAA-MM-DD"}[t]
    if c.tratamiento == "id_prefijo":
        return base                                  # el rango (>= 0) lo dice la frase del prefijo
    fmt = lambda x: int(x) if float(x).is_integer() else x
    if t in ("int", "float"):
        if lo is not None and hi is not None:
            base += f" {fmt(lo)}..{fmt(hi)}"
        elif lo is not None:
            base += f" >= {fmt(lo)}"
        elif hi is not None:
            base += f" <= {fmt(hi)}"
    return base


def instruccion_compacta(esp: Especializacion, ejemplo: Optional[str] = None) -> str:
    """Instrucción escrita a mano (plantilla fija) con lo mínimo que necesita ESTE contrato: cabecera,
    orden de campos, tipos, rangos, mapas de códigos y las tres reglas de escape. Sin ejemplo por omisión.

    No es la salida de ``spec_block``: es una plantilla propia que debe validarse con un modelo real
    antes de adoptarla (este estudio no hace llamadas de API)."""
    ks = "".join(f"|{c.clave_cabecera}=<{c.desc or c.orig}>" for c in esp.constantes())
    L = ["Responde SOLO con un documento .mini: texto plano, sin Markdown ni comentarios.",
         f"Línea 1 (cabecera): {esp.prefijo}|n=<nº de registros>{ks}",
         "Luego UNA línea por registro, campos separados por |, en este orden:"]
    for i, c in enumerate(esp.campos_registro(), 1):
        extra = ""
        if c.tratamiento == "id_prefijo":
            extra = f" (número sin el prefijo {c.prefijo}" + (f"; {c.ancho} dígitos" if c.ancho else "") + ")"
        elif c.tratamiento == "escalado":
            extra = f" (valor x{c.factor}, p. ej. 21.5 -> {round(21.5 * c.factor)})"
        elif c.tratamiento == "hhmm":
            extra = " (minutos desde las 00:00)"
        elif c.desc and c.tipo_mini() != "enum":
            extra = f" ({c.desc})"
        L.append(f"{i}. {c.nombre()}: {_tipo_legible(c)}{extra}")
    L.append("Escapes: \\| = barra vertical, \\\\ = barra invertida, \\n = salto de línea. "
             "n = número exacto de líneas de registro.")
    if ejemplo:
        L.append("Ejemplo válido:")
        L.append(ejemplo)
    return "\n".join(L)


def instruccion_spec_block(esp: Especializacion, ejemplo: Optional[str] = None) -> str:
    """El bloque que produce la herramienta real (``spec_block``, idioma es) para el contrato especializado."""
    return spec_block(esp.contrato(), "es", ejemplo)

"""Auditoría independiente de una reparación: ¿se sobrescribió un registro válido? ¿se duplicó o inventó una identidad?

La comprueba el arnés SOBRE EL TEXTO (no confía en lo que diga la función de
fusión), de modo que sirve igual para ``minifmt.ai.merge_repair`` (que hoy
compara líneas enteras, no identidades) que para la fusión de JSON.

Definiciones, por documento:

* ``validos_sobrescritos``: registros válidos ANTES de reparar (líneas no
  marcadas como inválidas) que faltan o cambiaron DESPUÉS.
* ``identidades_duplicadas_finales``: valores repetidos del campo ``unique``
  (el primero del contrato) entre las líneas de registro del documento final,
  cuente o no el lector final esa línea.
* ``identidades_inventadas``: líneas nuevas del documento final (no estaban en
  el original) cuya identidad no coincide con la de ninguna línea rota que se
  pidió corregir.  Sin campo ``unique`` las dos últimas son ``None``
  (no aplicable), nunca 0.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from minifmt import Contract, codec
from minifmt.parser import _physical_lines

from .json_tolerante import ItemJSON, campos_identidad, identidad


def _ident_linea(linea: str, c: Contract) -> Optional[str]:
    try:
        campos = codec.split_fields(linea.replace("\n", " "), c.list_separator, 0, strict=False)
    except Exception:  # noqa: BLE001
        return None
    return codec.text_of(campos[0]) if campos else None


def identidades_mini(texto: str, c: Contract) -> Optional[List[str]]:
    if not c.fields or not c.fields[0].unique:
        return None
    fisicas = _physical_lines(texto)
    return [i for _, ln in fisicas[1:] if (i := _ident_linea(ln, c)) is not None]


def auditar_mini(documento_original: str, texto_final: str, lineas_rotas: List[int], textos_rotos: List[str],
                 c: Contract) -> Dict[str, Any]:
    fis0 = _physical_lines(documento_original)
    if not fis0:
        return {"validos_sobrescritos": 0, "identidades_duplicadas_finales": None, "identidades_inventadas": None,
                "correcciones_rechazadas_identidad": None}
    cab = fis0[0][0]
    rotas = set(lineas_rotas)
    validas_antes = Counter(t for ln, t in fis0 if ln not in rotas and ln != cab)
    todas_antes = Counter(t for ln, t in fis0 if ln != cab)
    despues = Counter(t for _, t in _physical_lines(texto_final)[1:])
    sobrescritos = sum((validas_antes - despues).values())
    ids = identidades_mini(texto_final, c)
    if ids is None:
        dup = inv = None
    else:
        dup = len(ids) - len(set(ids))
        rotos_ids = {i for t in textos_rotos if (i := _ident_linea(t.split("\n")[0], c)) is not None}
        nuevas = list((despues - todas_antes).elements())
        inv = sum(1 for t in nuevas if _ident_linea(t, c) not in rotos_ids)
    return {"validos_sobrescritos": sobrescritos, "identidades_duplicadas_finales": dup, "identidades_inventadas": inv,
            "correcciones_rechazadas_identidad": None}


def auditar_json(items_antes: List[ItemJSON], rechazados: List[int], registros_finales: List[Dict[str, Any]],
                 c: Contract, rechazos_identidad: int) -> Dict[str, Any]:
    """``rechazados``: posiciones 0-based que se pidió corregir."""
    campos = campos_identidad(c)
    validos = [it.objeto for it in items_antes if it.indice not in set(rechazados) and it.objeto is not None]
    finales = list(registros_finales)
    sobrescritos = sum(1 for v in validos if v not in finales)
    if not campos:
        return {"validos_sobrescritos": sobrescritos, "identidades_duplicadas_finales": None,
                "identidades_inventadas": None, "correcciones_rechazadas_identidad": rechazos_identidad}
    ids = [identidad(r, campos) for r in finales]
    dup = len(ids) - len(set(ids))
    return {"validos_sobrescritos": sobrescritos, "identidades_duplicadas_finales": dup, "identidades_inventadas": 0,
            "correcciones_rechazadas_identidad": rechazos_identidad}

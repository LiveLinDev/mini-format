"""Serie de tokens de V1 con reversibilidad verificada ANTES de contar (tres tokenizadores).

Para cada (variante, dominio, n) genera el documento con ``comun.generar`` (el mismo
generador que ``experiments/v1_tokens/run.py``), lo serializa en los 8 formatos
archivados más tres comparadores reversibles de ``benchmark/public/baselines.py``
(``xml_tipado``, ``csv_reversible``, ``toon_reversible``), verifica objeto -> texto -> objeto
de cada uno (``reversibilidad.py``) y solo entonces cuenta tokens. Un formato que no es
reversible para un documento se cuenta igualmente (para no ocultar su tamaño) pero con
``comparacion_valida = False`` y la causa: ninguna comparación de ahorro lo usa.

No llama a ningún modelo ni a la red. ``replicacion_de_base`` es verdadero para n > 12:
esos documentos repiten los 12 registros base de su dominio y no son muestras nuevas.
"""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import comun as C  # noqa: E402
import reversibilidad as R  # noqa: E402

FORMATOS_SERIE = ["json_pretty", "json_compact", "yaml", "xml", "csv", "toon", "toon_flat", "mini",
                  "xml_tipado", "csv_reversible", "toon_reversible"]
# Cómo se decodifica cada formato: el texto solo, con el contrato del dominio o con un mapa contado aparte.
DECODIFICACION = {
    "json_pretty": "autocontenida", "json_compact": "autocontenida", "yaml": "autocontenida",
    "xml": "con_contrato", "csv": "con_contrato", "toon": "autocontenida", "toon_flat": "con_contrato",
    "mini": "con_contrato", "xml_tipado": "autocontenida", "csv_reversible": "con_mapa", "toon_reversible": "con_mapa",
}
ORIGEN_FORMATO = {
    "json_pretty": "benchmark/formats.py", "json_compact": "benchmark/formats.py", "yaml": "benchmark/formats.py",
    "xml": "benchmark/formats.py (sin tipos)", "csv": "benchmark/formats.py (sin metadatos)",
    "toon": "TOON oficial vendored, tal cual", "toon_flat": "TOON oficial sobre aplanado por contrato", "mini": "minifmt.dumps",
    "xml_tipado": "benchmark/public/baselines.py", "csv_reversible": "benchmark/public/baselines.py (mapa aparte)",
    "toon_reversible": "benchmark/public/baselines.py (mapa aparte)",
}


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def medir_serie(toks: Dict[str, Any], variantes: Sequence[str], tamanos: Sequence[int],
                dominios: Optional[Sequence[str]] = None, log: Callable[[str], None] = print
                ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Devuelve (filas de tokens, filas de reversibilidad)."""
    reg = C.registro()
    dominios = list(dominios or reg.contracts)
    filas: List[Dict[str, Any]] = []
    filas_rev: List[Dict[str, Any]] = []
    t0 = time.time()
    for variante in variantes:
        for p in dominios:
            c = reg.get(p)
            docs = [C.generar(p, n, variante) for n in tamanos]
            ser = C.serializar_todos(docs, c)
            textos = [{f: t for f, (t, _) in s.items()} for s in ser]
            rev = R.verificar_lote(docs, textos, c)
            ext = R.comparadores_reversibles(docs, c)
            for i, n in enumerate(tamanos):
                replica = n > 12
                # Formatos finales: texto, resultado de reversibilidad, mapa.
                por_formato: Dict[str, Dict[str, Any]] = {}
                for f in R.FORMATOS_ARCHIVADOS:
                    por_formato[f] = {"texto": textos[i][f], "res": rev[i][f], "mapa": ""}
                por_formato["xml_tipado"] = {"texto": ext[i]["xml_tipado"]["texto"], "res": ext[i]["xml_tipado"]["resultado"], "mapa": ""}
                for f, pref in (("csv_reversible", "csv_rev"), ("toon_reversible", "toon_rev")):
                    por_formato[f] = {"variantes": {v: ext[i][f"{pref}:{v}"] for v in ("celdas", "columnas")}}
                for f, e in por_formato.items():
                    if "variantes" in e:
                        continue
                    filas_rev.append({"variante": variante, "dominio": p, "n": n, "formato": f, "estado": e["res"].estado,
                                      "causa": e["res"].causa, "normalizaciones": "; ".join(e["res"].normalizaciones),
                                      "decodificacion": DECODIFICACION[f], "texto_sha256": sha(e["texto"]),
                                      "replicacion_de_base": replica})
                for f, e in por_formato.items():
                    if "variantes" not in e:
                        continue
                    for v, x in e["variantes"].items():
                        filas_rev.append({"variante": variante, "dominio": p, "n": n, "formato": f"{f}:{v}", "estado": x["resultado"].estado,
                                          "causa": x["resultado"].causa, "normalizaciones": "; ".join(x["resultado"].normalizaciones),
                                          "decodificacion": DECODIFICACION[f], "texto_sha256": sha(x["texto"]),
                                          "replicacion_de_base": replica})
                for tname, tk in toks.items():
                    for f in FORMATOS_SERIE:
                        e = por_formato[f]
                        elegida = ""
                        mapa_tokens: Any = ""
                        if "variantes" in e:
                            cand = [(tk.count(x["texto"]), v, x) for v, x in e["variantes"].items()
                                    if x["resultado"].aceptado and x["texto"]]
                            if cand:
                                t, elegida, x = min(cand, key=lambda z: (z[0], z[1]))
                                texto, res, mapa_tokens = x["texto"], x["resultado"], tk.count(x["mapa"])
                            else:  # ninguna variante es reversible: se cuenta la menor, marcada no válida
                                cand2 = [(tk.count(x["texto"]), v, x) for v, x in e["variantes"].items() if x["texto"]]
                                if cand2:
                                    t, elegida, x = min(cand2, key=lambda z: (z[0], z[1]))
                                    texto, res, mapa_tokens = x["texto"], x["resultado"], tk.count(x["mapa"])
                                else:
                                    texto, res, t = "", next(iter(e["variantes"].values()))["resultado"], None
                        else:
                            texto, res = e["texto"], e["res"]
                            t = tk.count(texto)
                        filas.append({
                            "tokenizador": tname, "variante": variante, "dominio": p, "n": n, "formato": f,
                            "tokens": t, "bytes": len(texto.encode("utf-8")) if texto else None,
                            "tokens_por_registro": (t / n) if t is not None else None,
                            "reversibilidad": res.estado, "comparacion_valida": res.aceptado,
                            "decodificacion": DECODIFICACION[f], "variante_aplanado": elegida,
                            "mapa_tokens": mapa_tokens, "replicacion_de_base": replica,
                        })
            log(f"[serie] {variante:8s} {p:5s} ({time.time() - t0:6.1f}s)")
    return filas, filas_rev

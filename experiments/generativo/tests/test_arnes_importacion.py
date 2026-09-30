"""Importación de respuestas ya generadas (procedencia asistido_ia): mismo analizador, sin usage inventado, sin gasto."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import analyze
import run
from arnes import brazos as B
from arnes import ejecucion as X
from arnes import importacion as IM
from arnes import metricas as M
from arnes import tareas as T

MODELO = "ia-de-prueba"


def _preparadas(tareas=("ext-cls", "gen-card"), brazos=("A", "B", "D", "C"), reps=2):
    return IM.preparar_prompts(list(tareas), list(brazos), reps, MODELO)


def _respuestas(filas, ruido=None):
    """Convierte cada fila de prompt en una fila de respuesta con la referencia del brazo (con `ruido` opcional)."""
    out = []
    for f in filas:
        t = T.construir(f["dominio"])
        texto = B.salida_referencia(t, f["condicion"])
        if ruido:
            texto = ruido(f, texto)
        out.append({"celda_id": f["celda_id"], "dominio": f["dominio"], "condicion": f["condicion"], "repeticion": f["repeticion"],
                    "prompt_id": f["prompt_id"], "respuesta_bruta": texto, "modelo_declarado": MODELO,
                    "parametros": {"temperature": 0.7, "max_tokens": 4096}, "fecha_utc": "2026-09-30T12:00:00Z"})
    return out


def _escribir(ruta, filas):
    ruta.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas), encoding="utf-8")
    return ruta


def test_preparar_omite_C_con_motivo_y_da_prompts_exactos():
    filas, omitidas = _preparadas()
    assert {f["condicion"] for f in filas} == {"A", "B", "D"} and len(filas) == 2 * 3 * 2
    assert len(omitidas) == 4 and all("no_aplicable" in o["motivo"] for o in omitidas)
    ctx = X.Contexto({"tareas": ["ext-cls"], "idioma": "es"})
    f = next(x for x in filas if x["dominio"] == "ext-cls" and x["condicion"] == "D")
    p = ctx.prompt(ctx.tareas["ext-cls"], "D")
    assert f["system"] == p.system and f["user"] == p.user and f["prompt_id"].startswith("ext-cls/D/")


def test_importa_con_procedencia_asistida_sin_usage_ni_gasto(tmp_path):
    filas, _ = _preparadas()
    ruta = _escribir(tmp_path / "respuestas.jsonl", _respuestas(filas))
    salida = tmp_path / "res"
    inf = IM.importar(ruta, salida, reparacion=False)
    IM.escribir_resultados_importacion(salida, ruta, inf, idioma="es", raiz=Path(__file__).resolve().parents[3])
    assert inf.aceptadas == len(filas) and not inf.rechazadas
    ms = X.leer_muestras(salida / "muestras.jsonl")
    assert len(ms) == len(filas)
    for m in ms:
        assert m["procedencia"] == "asistido_ia" and m["adaptador"] == "importado" and m["asistido_ia"] is True and m["simulado"] is False
        assert m["solicitud"]["intentos"][0]["usage"] is None and m["solicitud"]["intentos"][0]["latencia_s"] is None
        assert m["metricas"]["tokens_entrada"] is None and m["metricas"]["tokens_salida"] is None       # nunca inventados
        assert m["costo_usd"] is None and m["costo_estado"] == "sin_usage"
        assert m["tokens_locales_aprox"]["tipo"] == "aproximacion_local_o200k_base" and m["tokens_locales_aprox"]["salida"] > 0
        assert m["latencia"]["flujo_s"] is None and m["proveedor"] == "asistido_ia" and m["modelo"] == MODELO
    man = json.loads((salida / "manifiesto.json").read_text(encoding="utf-8"))
    assert man["procedencia"] == "asistido_ia" and man["gasto_usd"] == 0 and "ASISTIDO POR IA" in man["advertencia"]
    assert len(man["hashes"]["prompts_sha256"]) == 64 and man["origen"]["sha256"]
    assert (salida / "importacion.json").exists() and (salida / "estado_estudio.json").exists()


def test_mismo_analizador_mismas_metricas(tmp_path):
    filas, _ = _preparadas(reps=1)
    def ruido(f, texto):
        if f["condicion"] == "B" and f["dominio"] == "ext-cls":
            return re.sub(r'"conf": [0-9.]+', '"conf": 9.9', texto, count=1)   # un registro inválido por contrato
        if f["condicion"] == "D":
            return texto.replace(texto.split("\n")[2], "m2|roto")           # una línea rota
        return texto
    ruta = _escribir(tmp_path / "r.jsonl", _respuestas(filas, ruido))
    salida = tmp_path / "res"
    IM.importar(ruta, salida, reparacion=False)
    for m in X.leer_muestras(salida / "muestras.jsonl"):
        t = T.construir(m["tarea"])
        directa = M.evaluar(B.leer(m["brazo"], m["respuesta"]["text"], t), t)
        for k in ("solicitados", "validos_contrato", "validos_finales", "exactos_contenido", "correctos", "incorrectos_sin_aviso",
                  "perdidos_detectados", "perdidos_sin_aviso", "sintaxis_ok", "detectado"):
            assert m["metricas"][k] == directa[k], (m["id"], k)
    assert any(m["metricas"]["validos_finales"] < m["metricas"]["solicitados"] for m in X.leer_muestras(salida / "muestras.jsonl"))


def test_filas_invalidas_no_se_descartan_en_silencio(tmp_path):
    filas, _ = _preparadas(tareas=("ext-cls",), brazos=("A", "B"), reps=1)
    resp = _respuestas(filas)
    resp.append(dict(resp[0], celda_id="dup"))                                              # celda duplicada
    resp.append({k: v for k, v in resp[1].items() if k != "respuesta_bruta"})               # falta un campo
    resp.append(dict(resp[0], repeticion=7, dominio="ext-inventado"))                        # dominio desconocido
    resp.append(dict(resp[0], repeticion=8, prompt_id="ext-cls/A/000000000000"))             # respuesta a otro prompt
    resp.append(dict(resp[0], repeticion=9, condicion="C", prompt_id=None))                  # C: no aplicable
    ruta = tmp_path / "r.jsonl"
    ruta.write_text("".join(json.dumps(f) + "\n" for f in resp) + "esto no es json\n", encoding="utf-8")
    inf = IM.importar(ruta, tmp_path / "res", reparacion=False)
    assert inf.aceptadas == 2 and len(inf.no_aplicables) == 1
    motivos = " | ".join(r["motivo"] for r in inf.rechazadas)
    for esperado in ("duplicada", "faltan campos: respuesta_bruta", "dominio desconocido", "no corresponde al prompt vigente", "ilegible"):
        assert esperado in motivos
    assert len(inf.rechazadas) == 5


def test_reimportar_es_idempotente(tmp_path):
    filas, _ = _preparadas(tareas=("ext-cls",), brazos=("B",), reps=3)
    ruta = _escribir(tmp_path / "r.jsonl", _respuestas(filas))
    IM.importar(ruta, tmp_path / "res", reparacion=False)
    tam = (tmp_path / "res" / "muestras.jsonl").stat().st_size
    inf = IM.importar(ruta, tmp_path / "res", reparacion=False)
    assert inf.aceptadas == 0 and (tmp_path / "res" / "muestras.jsonl").stat().st_size == tam


def test_flujo_de_reparacion_en_dos_pasadas(tmp_path):
    filas, _ = _preparadas(tareas=("ext-cls",), brazos=("B", "D"), reps=1)

    def ruido(f, texto):
        if f["condicion"] == "D":
            ls = texto.split("\n")
            ls[3] = "m4|roto"
            return "\n".join(ls)
        if f["condicion"] == "B":
            return re.sub(r'"conf": [0-9.]+', '"conf": 9.0', texto, count=1)
        return texto
    primera = _respuestas(filas, ruido)
    ruta1 = _escribir(tmp_path / "primarias.jsonl", primera)
    # 1.ª pasada: las primarias y las X+1 que no necesitan reparar
    res1 = tmp_path / "res1"
    inf = IM.importar(ruta1, res1)
    ms = {m["brazo"]: m for m in X.leer_muestras(res1 / "muestras.jsonl")}
    assert {"B", "D"} <= set(ms) and "D+1" not in ms                                        # D+1 necesita su respuesta de reparación
    assert any("D+1" in p["celda_id"] for p in inf.reparaciones_pendientes)
    # preparar las solicitudes de reparación y responderlas (aquí: con la referencia)
    sol = IM.preparar_reparaciones(primera)
    sd = next(s for s in sol if s["condicion"] == "D+1")
    t = T.construir("ext-cls")
    linea_buena = B.salida_referencia(t, "D").split("\n")[3]
    resp_rep = [{"celda_id": sd["celda_id"], "dominio": "ext-cls", "condicion": "D+1", "repeticion": 1, "prompt_id": sd["prompt_id"],
                 "respuesta_bruta": f"cls|n=1\n{linea_buena}", "modelo_declarado": MODELO, "parametros": {}, "fecha_utc": None}]
    ruta2 = _escribir(tmp_path / "todo.jsonl", primera + resp_rep)
    res2 = tmp_path / "res2"
    inf2 = IM.importar(ruta2, res2)
    m2 = {m["brazo"]: m for m in X.leer_muestras(res2 / "muestras.jsonl")}
    assert "D+1" in m2 and m2["D+1"]["generacion_de"] == m2["D"]["id"]
    assert m2["D+1"]["metricas"]["validos_finales"] == m2["D"]["metricas"]["validos_finales"] + 1
    assert m2["D+1"]["reparacion"]["auditoria"]["validos_sobrescritos"] == 0
    assert m2["D+1"]["solicitud"]["intentos"][-1]["fase"] == "reparacion" and m2["D+1"]["solicitud"]["intentos"][-1]["usage"] is None
    assert not [p for p in inf2.reparaciones_pendientes if "D+1" in p["celda_id"]]
    assert [p["celda_id"] for p in inf2.reparaciones_pendientes] == [x["celda_id"] for x in sol if x["condicion"] == "B+1"]   # B+1 sigue esperando


def test_prompt_id_de_reparacion_incorrecto_se_rechaza(tmp_path):
    filas, _ = _preparadas(tareas=("ext-cls",), brazos=("D",), reps=1)
    primera = _respuestas(filas, lambda f, t: t.replace(t.split("\n")[2], "m3|roto"))
    sd = IM.preparar_reparaciones(primera)[0]
    resp = {"celda_id": sd["celda_id"], "dominio": "ext-cls", "condicion": "D+1", "repeticion": 1, "prompt_id": "ext-cls/D+1/ffffffffffff",
            "respuesta_bruta": "cls|n=1\nx", "modelo_declarado": MODELO, "parametros": {}, "fecha_utc": None}
    inf = IM.importar(_escribir(tmp_path / "r.jsonl", primera + [resp]), tmp_path / "res")
    assert any("solicitud de reparación vigente" in r["motivo"] for r in inf.rechazadas)


def test_cli_importar_analiza_y_emite_evidencia_no_evaluable(tmp_path, monkeypatch):
    filas, _ = _preparadas(tareas=("ext-cls",), brazos=("A", "B", "D"), reps=2)
    ruta = _escribir(tmp_path / "asistido.jsonl", _respuestas(filas))
    salida = tmp_path / "res"
    corridas = tmp_path / "corridas"
    from arnes import evidencia as EV
    original = EV.emitir_corridas
    monkeypatch.setattr(EV, "emitir_corridas", lambda *a, **k: original(*a, **dict(k, directorio_corridas=corridas)))
    assert run.main(["importar", str(ruta), "--salida", str(salida), "--emitir-evidencia", "asistido-prueba"]) == 0
    md = (salida / "analisis" / "resumen.md").read_text(encoding="utf-8")
    assert "MATERIAL ASISTIDO POR IA" in md and "SIMULADOS" not in md
    meta = json.loads((salida / "analisis" / "meta_v2.json").read_text(encoding="utf-8"))
    assert meta["resultado"] == "no_evaluable"
    m = json.loads((corridas / "v2-asistido-prueba" / "manifiesto.json").read_text(encoding="utf-8"))
    assert m["procedencia"] == "asistido_ia" and m["resultado"] == "no_evaluable" and m["gasto_usd"] == 0.0
    # la tabla de costos queda vacía: sin usage ni factura no hay costo
    filas_v4 = (salida / "analisis" / "latencia_costo.csv").read_text(encoding="utf-8").splitlines()
    assert "asistido_ia" in filas_v4[1] or len(filas_v4) > 1
    assert all(f.get("costo_por_1000_validos_usd") in (None, "") for f in analyze.agrupar(
        X.leer_muestras(salida / "muestras.jsonl"), ("brazo",), ic=False))


def test_cli_preparar_y_sin_modelo_declarado(tmp_path, capsys):
    p = tmp_path / "prompts.jsonl"
    assert run.main(["preparar", "--tareas", "ext-cls", "--brazos", "A,D,C", "--repeticiones", "2", "--modelo-declarado", MODELO,
                     "--salida", str(p)]) == 0
    filas = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 4 and {f["condicion"] for f in filas} == {"A", "D"}
    with pytest.raises(SystemExit):
        run.main(["preparar", "--tareas", "ext-cls", "--salida", str(p)])

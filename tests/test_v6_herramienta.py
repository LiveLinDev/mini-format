"""Pruebas de la herramienta de sesión V6b (evidencia/v6/herramienta/sesion.html).

Dos niveles:
* núcleo en Node (vm): la lógica pura (contrabalanceo, SUS, cronómetro con topes, exportación) se carga
  desde el propio HTML y se compara con tools/analizar_v6.py. No necesita navegador.
* navegador real con Playwright (se omite si Playwright o Chromium no están instalados): abre el archivo
  por file://, arranca y detiene tareas con el reloj controlado, comprueba los topes, exporta, borra y
  vigila que no haya errores de consola ni peticiones de red.

Los datos que se usan son FIXTURES de prueba: no son datos de participantes.
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
HTML = RAIZ / "evidencia" / "v6" / "herramienta" / "sesion.html"


def _cargar_analizador():
    spec = importlib.util.spec_from_file_location("analizar_v6", RAIZ / "tools" / "analizar_v6.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["analizar_v6"] = mod
    spec.loader.exec_module(mod)
    return mod


A = _cargar_analizador()
NODE = shutil.which("node")
necesita_node = pytest.mark.skipif(NODE is None, reason="Node no está instalado")

HARNES = r"""
const vm = require('vm'), fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const m = html.match(/<script id="nucleo">([\s\S]*?)<\/script>/);
const ctx = {}; vm.createContext(ctx);
vm.runInContext(m[1] + "\nthis.V6 = V6;", ctx);
const V6 = ctx.V6;
const entrada = JSON.parse(fs.readFileSync(0, 'utf8'));
const f = eval('(' + entrada.codigo + ')');
process.stdout.write(JSON.stringify(f(V6)));
"""


def en_node(js_fn: str):
    """Ejecuta una función JS ``(V6) => ...`` contra el núcleo del HTML y devuelve su resultado JSON."""
    r = subprocess.run([NODE, "-e", HARNES, str(HTML)], input=json.dumps({"codigo": js_fn}),
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ------------------------------------------------------------------------------------------
# Núcleo en Node
# ------------------------------------------------------------------------------------------
@necesita_node
def test_contrabalanceo_js_igual_que_python():
    casos = [(n, s, p) for s in (0, 1, 42, 2024, 123456789, 4294967295) for n in (1, 2, 3, 4, 8, 10, 12, 13, 40) for p in (0, 2)]
    js = en_node("(V6) => %s.map(c => V6.contrabalanceo(c[0], c[1], c[2]))" % json.dumps(casos))
    for (n, s, p), filas in zip(casos, js):
        assert filas == A.contrabalanceo(n, s, p), (n, s, p)


@necesita_node
def test_mulberry32_js_igual_que_python():
    semillas = [0, 1, 7, 42, 65535, 2 ** 31, 4294967295]
    js = en_node("(V6) => %s.map(s => { const r = V6.mulberry32(s); return [r(), r(), r(), r(), r()]; })" % json.dumps(semillas))
    for s, out in zip(semillas, js):
        r = A.mulberry32(s)
        assert out == [r() for _ in range(5)]


@necesita_node
def test_sus_js_igual_que_python_y_a_mano():
    # referencias calculadas a mano (2,5 x [Σ impares (r-1) + Σ pares (5-r)])
    a_mano = {
        (3,) * 10: 50.0, (5, 1) * 5: 100.0, (1, 5) * 5: 0.0, (4, 2) * 5: 75.0,
        (5, 3, 3, 3, 3, 3, 3, 3, 3, 3): 55.0,        # solo el ítem 1 = 5: impares 4+4·2=12, pares 5·2=10 -> 22·2,5
    }
    vecs = [list(k) for k in a_mano]
    js = en_node("(V6) => %s.map(v => V6.puntuarSUS(v))" % json.dumps(vecs))
    assert js == list(a_mano.values())
    import random
    rnd = random.Random(7)
    aleatorios = [[rnd.randint(1, 5) for _ in range(10)] for _ in range(200)]
    js2 = en_node("(V6) => %s.map(v => V6.puntuarSUS(v))" % json.dumps(aleatorios))
    assert js2 == [A.puntuar_sus(v)[0] for v in aleatorios]
    # incompletos y fuera de rango: null
    malos = [[1] * 9, [1] * 10 + [1], [None] + [3] * 9, [6] + [3] * 9, [0] + [3] * 9, [3.5] + [3] * 9]
    assert en_node("(V6) => %s.map(v => V6.puntuarSUS(v))" % json.dumps(malos)) == [None] * len(malos)


@necesita_node
def test_topes_suman_100_y_coinciden_con_python():
    js = en_node("(V6) => V6.TOPES_MIN")
    assert js == A.TOPES_MIN
    assert sum(js.values()) == 100
    assert 10 + sum(js.values()) + 10 == 120


@necesita_node
def test_cronometro_respeta_el_tope_y_el_exito_no_pasa_del_tope():
    # t en milisegundos; reloj inyectado. Todo dentro de una sola ejecución de Node.
    res = en_node(r"""(V6) => {
      const out = {};
      const nueva = () => V6.crearSesion({codigo: 'EST-01', tipo: 'estudio', secuencia: 'S1', ensayo: true}, 0);
      const MIN = 60000;
      // 1) corre 10 min, pausa 50 min (no cuenta), reanuda y llega al tope a los 20 min más
      let s = nueva();
      out.no_inicia_segunda = V6.iniciar(s, 'T1_mini', 0);
      out.inicia = V6.iniciar(s, 'T1_json', 0);
      out.no_dos_a_la_vez = V6.puedeIniciar(s, 'T1_mini');
      V6.tick(s, 10 * MIN);
      V6.pausar(s, 'T1_json', 10 * MIN);
      V6.tick(s, 60 * MIN);
      out.en_pausa_ms = V6.transcurridoMs(s, 'T1_json', 60 * MIN);
      V6.reanudar(s, 'T1_json', 60 * MIN);
      out.cerradas_a_los_19 = V6.tick(s, 79 * MIN);
      out.cerradas_a_los_20 = V6.tick(s, 80 * MIN + 5000);   // el tick llega 5 s tarde
      const x = s.tareas.T1_json;
      out.estado = x.estado; out.resultado = x.resultado; out.acumulado_ms = x.acumulado_ms;
      out.fin_utc = x.fin_utc;                                  // debe ser el instante del tope, no el del tick tardío
      out.exito_tras_tope = V6.cerrar(s, 'T1_json', 'completa_sin_ayuda', 81 * MIN);
      out.reabrir_agotada = V6.reabrir(s, 'T1_json', 81 * MIN);
      out.puede_iniciar_siguiente = V6.puedeIniciar(s, 'T1_mini');
      // 2) éxito justo antes del tope y éxito con el tick atrasado
      s = nueva(); V6.iniciar(s, 'T2', 0) ;           // T2 no es la primera: no debe iniciar
      out.t2_primero = s.tareas.T2.estado;
      s = nueva(); V6.iniciar(s, 'T1_json', 0);
      out.ok_29_59 = V6.cerrar(s, 'T1_json', 'completa_sin_ayuda', 30 * MIN - 1000);
      s = nueva(); V6.iniciar(s, 'T1_json', 0);
      out.ok_30_01_sin_tick = V6.cerrar(s, 'T1_json', 'completa_sin_ayuda', 30 * MIN + 1000);
      out.resultado_30_01 = s.tareas.T1_json.resultado;
      // 3) ayuda convierte el éxito en 'con ayuda'
      s = nueva(); V6.iniciar(s, 'T1_json', 0); V6.ayuda(s, 'T1_json', 'pista', 2 * MIN);
      out.con_ayuda = V6.cerrar(s, 'T1_json', 'completa_sin_ayuda', 5 * MIN).resultado;
      // 4) el orden sigue la secuencia: S3 empieza por .mini
      s = V6.crearSesion({codigo: 'EST-03', tipo: 'estudio', secuencia: 'S3', ensayo: true}, 0);
      out.orden_s3 = s.orden;
      // 5) recarga con la tarea corriendo: queda pausada en el último latido
      s = nueva(); V6.iniciar(s, 'T1_json', 0); V6.tick(s, 7 * MIN);
      V6.recuperar(s, 500 * MIN);
      out.recuperada = [s.tareas.T1_json.estado, s.tareas.T1_json.acumulado_ms];
      // 6) cada tope por tarea
      const topes = {};
      for (const t of ['T1_json', 'T1_mini', 'T2', 'T3', 'T4']) {
        const q = V6.crearSesion({codigo: 'EST-01', tipo: 'estudio', secuencia: 'S1', ensayo: true}, 0);
        // cierra las anteriores como abandono para poder iniciar esta
        for (const prev of q.orden) { if (prev === t) break; V6.iniciar(q, prev, 0); V6.cerrar(q, prev, 'abandono', 0); }
        V6.iniciar(q, t, 0);
        V6.tick(q, V6.TOPES_MIN[t] * MIN - 1);
        const antes = q.tareas[t].estado;
        V6.tick(q, V6.TOPES_MIN[t] * MIN);
        topes[t] = [antes, q.tareas[t].estado, q.tareas[t].resultado, q.tareas[t].acumulado_ms / MIN];
      }
      out.topes = topes;
      return out;
    }""")
    assert res["no_inicia_segunda"] is False and res["inicia"] is True and res["no_dos_a_la_vez"] is False
    assert res["en_pausa_ms"] == 10 * 60000                         # la pausa no cuenta
    assert res["cerradas_a_los_19"] == []                            # 10 + 9 min = 19: sigue abierta
    assert res["cerradas_a_los_20"] == ["T1_json"]
    assert (res["estado"], res["resultado"], res["acumulado_ms"]) == ("cerrada", "tiempo_agotado", 30 * 60000)
    assert res["fin_utc"] == "1970-01-01T01:20:00.000Z"              # 80 min: el instante exacto del tope
    assert res["exito_tras_tope"]["ok"] is False
    assert res["reabrir_agotada"] is False
    assert res["puede_iniciar_siguiente"] is True
    assert res["t2_primero"] == "pendiente"
    assert res["ok_29_59"] == {"ok": True, "resultado": "completa_sin_ayuda"}
    assert res["ok_30_01_sin_tick"]["ok"] is False and res["resultado_30_01"] == "tiempo_agotado"
    assert res["con_ayuda"] == "completa_con_ayuda"
    assert res["orden_s3"] == ["T1_mini", "T1_json", "T2", "T3", "T4"]
    assert res["recuperada"] == ["pausada", 7 * 60000]
    esperado = {"T1_json": 30, "T1_mini": 30, "T2": 15, "T3": 10, "T4": 15}
    for t, m in esperado.items():
        assert res["topes"][t] == ["corriendo", "cerrada", "tiempo_agotado", m], t


@necesita_node
def test_exportacion_js_la_lee_el_analizador(tmp_path):
    res = en_node(r"""(V6) => {
      const MIN = 60000;
      const s = V6.crearSesion({codigo: 'EST-07', tipo: 'estudio', perfil: 'estudiante', lenguaje: 'python', secuencia: 'S2', semilla: 42, ensayo: true}, 0);
      let t = 0;
      const hacer = (tarea, dur, resultado, conAyuda) => {
        V6.iniciar(s, tarea, t);
        if (conAyuda) V6.ayuda(s, tarea, 'pista de prueba', t + 1000);
        t += dur; V6.tick(s, t);
        if (resultado) V6.cerrar(s, tarea, resultado, t);
        t += 1000;
      };
      hacer('T1_json', 12 * MIN + 500, 'completa_sin_ayuda');
      hacer('T1_mini', 30 * MIN + 10, null);                 // tiempo agotado por el cronómetro
      hacer('T2', 4 * MIN, 'completa_sin_ayuda', true);      // la ayuda lo vuelve 'con ayuda'
      hacer('T3', 2 * MIN, 'abandono');
      hacer('T4', 6 * MIN, 'no_completa');
      s.sus.respuestas = [4, 2, 4, 2, 4, 2, 4, 2, 4, 2]; s.sus.version_linguistica = 'es_provisional_equipo';
      return {json: V6.exportarJSON(s), csv: V6.exportarCSV(s), sus: V6.puntuarSUS(s.sus.respuestas)};
    }""")
    (tmp_path / "s.json").write_text(json.dumps(res["json"]), encoding="utf-8")
    (tmp_path / "s.csv").write_text(res["csv"], encoding="utf-8")
    por_json = A.cargar_sesiones([tmp_path / "s.json"])[0]
    por_csv = A.cargar_sesiones([tmp_path / "s.csv"])[0]
    for ses in (por_json, por_csv):
        assert ses["codigo"] == "EST-07" and ses["tipo_datos"] == "fixture_de_prueba"
        assert ses["orden_t1"] == "json_mini" and ses["variante_json"] == "B" and ses["variante_mini"] == "A"
        r = {t: ses["tareas"][t]["resultado"] for t in A.TAREAS}
        assert r == {"T1_json": "completa_sin_ayuda", "T1_mini": "tiempo_agotado", "T2": "completa_con_ayuda",
                     "T3": "abandono", "T4": "no_completa"}
        assert ses["tareas"]["T1_json"]["segundos"] == 12 * 60 + 0.5
        assert ses["tareas"]["T1_mini"]["segundos"] is None            # censurada: no se trunca a 30 min
        assert ses["tareas"]["T2"]["ayudas"] == 1
        assert A.puntuar_sus(ses["sus"]["respuestas"])[0] == res["sus"] == 75.0
        assert ses["sus"]["version"] == "es_provisional_equipo"
    # el JSON conserva además el registro completo de eventos
    assert any(e["tipo"] == "tiempo_agotado" and e["tarea"] == "T1_mini" for e in res["json"]["eventos"])
    assert res["json"]["aviso"] == "fixture de prueba, no son datos de participantes"


def test_html_sin_emojis_ni_red_ni_colores_propios():
    t = HTML.read_text(encoding="utf-8")
    # emojis y dingbats (incluye ✓ ✕ ✎ ★ ➜ y el bloque de emoticonos/símbolos)
    malos = re.findall("[←-⇿☀-➿⬀-⯿\U0001f000-\U0001faff✓✕]", t)
    assert malos == [], f"símbolos no permitidos: {malos}"
    assert not re.search(r"https?://", t), "la herramienta no debe referirse a URLs externas"
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=", t), "sin recursos externos"
    assert not re.search(r"\b(fetch|XMLHttpRequest|WebSocket|sendBeacon|import\()", t)
    # colores solo vía tokens: fuera del bloque :root no hay literales hex/rgb() con números
    css = re.search(r"<style>(.*?)</style>", t, re.S).group(1)
    resto = re.sub(r":root\{.*?\n\}|@media \(prefers-color-scheme: dark\)\{.*?\n\}\}|:root\[data-theme=\"dark\"\]\{.*?\n\}", "", css, flags=re.S)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", resto)
    assert not re.search(r"rgba?\(\s*\d", resto)
    assert 'lang="es"' in t and "<title>" in t


def test_textos_sus_del_html_coinciden_con_el_archivo_de_items():
    items = json.loads((RAIZ / "evidencia" / "v6" / "sus" / "sus_items.json").read_text(encoding="utf-8"))
    t = HTML.read_text(encoding="utf-8")
    for it in items["items"]:
        assert it["original_en"] in t, it["n"]
        assert it["es_provisional"] in t, it["n"]


# ------------------------------------------------------------------------------------------
# Navegador real
# ------------------------------------------------------------------------------------------
pw = pytest.importorskip("playwright.sync_api", reason="Playwright no está instalado")


@pytest.fixture(scope="module")
def navegador():
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:                      # Chromium no descargado
            pytest.skip(f"no se pudo lanzar Chromium: {e}")
        yield b
        b.close()


def _abrir(navegador, **ctx_opts):
    ctx = navegador.new_context(accept_downloads=True, viewport={"width": 1100, "height": 900}, **ctx_opts)
    page = ctx.new_page()
    eventos = {"consola": [], "errores": [], "peticiones": []}
    page.on("console", lambda m: eventos["consola"].append((m.type, m.text)))
    page.on("pageerror", lambda e: eventos["errores"].append(str(e)))
    page.on("request", lambda r: eventos["peticiones"].append(r.url))
    page.clock.install(time=1000)
    page.goto(HTML.as_uri())
    page.clock.pause_at(2000)                        # el tiempo solo avanza con run_for: pruebas deterministas
    return ctx, page, eventos


def _texto_reloj(page, t):
    return page.locator(f'[data-reloj="{t}"]').inner_text()


def _comenzar(page, codigo="EST-02", semilla="42", n="10"):
    page.fill("#codigo", codigo)
    page.check("#ensayo")
    page.fill("#semilla", semilla)
    page.fill("#nparts", n)
    page.click("#btn-plan")
    page.click("#btn-aplicar")
    page.click("#btn-comenzar")


def test_navegador_plan_de_contrabalanceo_igual_que_python(navegador):
    ctx, page, ev = _abrir(navegador)
    try:
        page.fill("#semilla", "2024")
        page.fill("#nparts", "13")
        page.click("#btn-plan")
        filas = page.eval_on_selector_all("#plan-tabla tbody tr", "rs => rs.map(r => Array.from(r.children).map(c => c.textContent))")
        esperado = A.contrabalanceo(13, 2024, 2)
        assert [(f[0], f[1], f[3], f[5], f[6]) for f in filas] == [(e["codigo"], e["tipo"], e["secuencia"], e["variante_json"], e["variante_mini"]) for e in esperado]
        # un código que no está en el plan no se asigna
        page.fill("#codigo", "EST-99")
        page.click("#btn-aplicar")
        assert "no está en el plan" in page.locator("#sec-ayuda").inner_text()
        assert ev["errores"] == []
    finally:
        ctx.close()


def test_navegador_sesion_completa(navegador, tmp_path):
    ctx, page, ev = _abrir(navegador)
    try:
        # EST-03 existe en el plan de 10 con semilla 42
        page.fill("#codigo", "EST-03")
        page.check("#ensayo")
        page.fill("#semilla", "42")
        page.fill("#nparts", "10")
        page.click("#btn-plan")
        page.click("#btn-aplicar")
        plan = {f["codigo"]: f for f in A.contrabalanceo(10, 42, 2)}
        assert page.input_value("#secuencia") == plan["EST-03"]["secuencia"]
        assert page.is_enabled("#btn-comenzar")
        page.click("#btn-comenzar")
        orden = ["T1_json", "T1_mini"] if plan["EST-03"]["orden_t1"] == "json_mini" else ["T1_mini", "T1_json"]
        orden += ["T2", "T3", "T4"]
        primera, segunda = orden[0], orden[1]
        # solo la primera se puede iniciar
        assert page.is_enabled(f'[data-fid="{primera}-iniciar"]')
        assert page.is_disabled(f'[data-fid="{segunda}-iniciar"]')
        page.click(f'[data-fid="{primera}-iniciar"]')
        assert page.is_disabled(f'[data-fid="{segunda}-iniciar"]')
        page.clock.fast_forward(5 * 60 * 1000)
        assert _texto_reloj(page, primera).startswith("05:00")
        page.click(f'[data-fid="{primera}-pausa"]')
        page.clock.fast_forward(10 * 60 * 1000)                       # en pausa no cuenta
        assert _texto_reloj(page, primera).startswith("05:00")
        page.click(f'[data-fid="{primera}-reanudar"]')
        page.clock.fast_forward(24 * 60 * 1000 + 59 * 1000)           # 29:59
        assert _texto_reloj(page, primera).startswith("29:59")
        assert page.is_enabled(f'[data-fid="{primera}-ok"]')
        page.clock.run_for(2000)                                 # pasa el tope: se cierra sola
        page.wait_for_selector(f'[data-tarea="{primera}"][data-estado="cerrada"]')
        assert _texto_reloj(page, primera).startswith("30:00")
        assert "Tiempo agotado" in page.locator(f'[data-tarea="{primera}"]').inner_text()
        assert page.is_disabled(f'[data-fid="{primera}-ok"]')    # ya no se puede marcar éxito
        assert page.locator(f'[data-fid="{primera}-deshacer"]').count() == 0
        page.clock.run_for(100)
        assert "Tiempo agotado" in page.locator("#vivo").inner_text()

        # segunda: con ayuda y éxito a los 3 minutos
        page.click(f'[data-fid="{segunda}-iniciar"]')
        page.fill(f'[data-tarea="{segunda}"] [data-nota-ayuda]', "pista de prueba")
        page.click(f'[data-fid="{segunda}-ayuda"]')
        page.clock.fast_forward(3 * 60 * 1000)
        page.click(f'[data-fid="{segunda}-ok"]')
        assert "Lograda con ayuda" in page.locator(f'[data-tarea="{segunda}"]').inner_text()

        # T2 llega a su tope de 15 min; T3 abandono; T4 entrega que no cumple
        page.click('[data-fid="T2-iniciar"]')
        page.clock.fast_forward(14 * 60 * 1000 + 59 * 1000)
        assert page.locator('[data-tarea="T2"]').get_attribute("data-estado") == "corriendo"
        page.clock.run_for(2000)
        page.wait_for_selector('[data-tarea="T2"][data-estado="cerrada"]')
        assert _texto_reloj(page, "T2").startswith("15:00")
        page.click('[data-fid="T3-iniciar"]')
        page.clock.run_for(60 * 1000)
        page.click('[data-fid="T3-abandono"]')
        page.click('[data-fid="T4-iniciar"]')
        page.clock.fast_forward(9 * 60 * 1000)
        page.click('[data-fid="T4-nocumple"]')
        assert page.locator("#tareas-resumen").inner_text().startswith("5 de 5")

        # SUS: [4,2,4,2,...] = 75
        for i in range(1, 11):
            page.check(f"#q{i}_{4 if i % 2 == 1 else 2}")
        assert "completo" in page.locator("#sus-estado").inner_text().lower()
        page.select_option("#sus-version", "es_provisional_equipo")
        assert page.locator("#sus-aviso").is_visible()
        for i in range(1, 11):
            page.check(f"#q{i}_{4 if i % 2 == 1 else 2}")

        # incidente
        page.fill("#inc-problema", "El ensayo de prueba muestra el registro de incidentes")
        page.click("#btn-inc")
        assert "ensayo de prueba" in page.locator("#inc-lista").inner_text()

        # exportar JSON y CSV y leerlos con el analizador
        with page.expect_download() as d:
            page.click("#btn-json")
        pj = tmp_path / d.value.suggested_filename
        d.value.save_as(pj)
        with page.expect_download() as d2:
            page.click("#btn-csv")
        pc = tmp_path / d2.value.suggested_filename
        d2.value.save_as(pc)
        assert pj.suffix == ".json" and pc.suffix == ".csv" and "EST-03" in pj.name
        s1 = A.cargar_sesiones([pj])[0]
        s2 = A.cargar_sesiones([pc])[0]
        for s in (s1, s2):
            r = {t: s["tareas"][t]["resultado"] for t in A.TAREAS}
            assert r[primera] == "tiempo_agotado" and r[segunda] == "completa_con_ayuda"
            assert r["T2"] == "tiempo_agotado" and r["T3"] == "abandono" and r["T4"] == "no_completa"
            assert s["tareas"][segunda]["segundos"] == 180.0 and s["tareas"][segunda]["ayudas"] == 1
            assert A.puntuar_sus(s["sus"]["respuestas"])[0] == 75.0
            assert s["tipo_datos"] == "fixture_de_prueba"
        doc = json.loads(pj.read_text(encoding="utf-8"))
        assert doc["tareas"][primera]["segundos_activos"] == 1800 and doc["tareas"]["T2"]["segundos_activos"] == 900
        assert doc["tareas"][primera]["pausas"] == 1
        assert doc["incidentes"][0]["problema"].startswith("El ensayo")

        # persistencia: recargar conserva la sesión
        page.reload()
        assert page.input_value("#codigo") == "EST-03"
        assert page.locator("#s-tareas").is_visible()
        assert page.locator(f'[data-tarea="{primera}"]').get_attribute("data-estado") == "cerrada"

        # borrar: pide confirmación y deja el navegador sin rastro
        page.click("#btn-borrar")
        page.click("#dlg-si")
        page.wait_for_load_state()
        page.wait_for_selector("#codigo")
        assert page.input_value("#codigo") == ""
        assert page.locator("#s-tareas").is_hidden()
        assert page.evaluate("localStorage.getItem('mini-format-v6b-sesion')") is None

        # nada de red, nada de errores
        assert ev["errores"] == []
        assert [m for m in ev["consola"] if m[0] in ("error", "warning")] == []
        externas = [u for u in ev["peticiones"] if not u.startswith(("file:", "blob:", "data:"))]
        assert externas == [], externas
    finally:
        ctx.close()


def test_navegador_cancelar_no_borra_y_reglas_de_arranque(navegador):
    ctx, page, ev = _abrir(navegador)
    try:
        assert page.is_disabled("#btn-comenzar")
        page.fill("#codigo", "Ana Perez")                           # un nombre no es un código
        assert "sin nombres" in page.locator("#codigo-err").inner_text()
        page.fill("#codigo", "EST-01")
        assert page.is_disabled("#btn-comenzar")                   # falta secuencia y consentimiento
        page.select_option("#secuencia", "S1")
        assert page.is_disabled("#btn-comenzar")                   # falta el consentimiento
        page.check("#consent")
        assert page.is_enabled("#btn-comenzar")
        page.click("#btn-comenzar")
        assert page.locator("#insignias").inner_text().find("estudio") >= 0
        page.click("#btn-borrar")
        page.click("#dlg-no")
        assert page.evaluate("localStorage.getItem('mini-format-v6b-sesion')") is not None
        assert page.locator("#s-tareas").is_visible()
        # recargar a mitad de una tarea en curso la deja en pausa, sin perder lo contado
        page.click('[data-fid="T1_json-iniciar"]')
        page.clock.fast_forward(3 * 60 * 1000 + 500)
        page.reload()
        assert page.locator('[data-tarea="T1_json"]').get_attribute("data-estado") == "pausada"
        assert page.locator("#s-tareas").is_visible()
        assert ev["errores"] == []
    finally:
        ctx.close()


def test_navegador_movil_y_accesibilidad_basica(navegador):
    ctx, page, ev = _abrir(navegador, color_scheme="dark")
    try:
        page.set_viewport_size({"width": 375, "height": 800})
        _comenzar(page, codigo="EST-02", n="10")
        desborde = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert desborde <= 1, f"desborde horizontal de {desborde}px en móvil"
        # todo control tiene nombre accesible
        sin_nombre = page.evaluate("""() => Array.from(document.querySelectorAll('button, input, select, textarea'))
            .filter(e => e.type !== 'hidden' && e.offsetParent !== null)
            .filter(e => !((e.labels && e.labels.length) || e.getAttribute('aria-label') || (e.textContent || '').trim() || e.closest('label')))
            .map(e => e.id || e.outerHTML.slice(0, 60))""")
        assert sin_nombre == []
        assert page.locator("html").get_attribute("lang") == "es"
        # el reloj tiene rol de temporizador y el aviso de tiempo usa una región viva
        assert page.locator('[role="timer"]').count() == 5
        assert page.locator("#vivo").get_attribute("aria-live") == "assertive"
        assert ev["errores"] == []
    finally:
        ctx.close()

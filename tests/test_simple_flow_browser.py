"""The entry page leads to a working story on desktop and mobile."""
from pathlib import Path
import json

import pytest

from minifmt.domain import decode_rows, infer_contract
from test_examples_flow import base_url, browser, page, pw

OUTPUT = Path(__file__).resolve().parents[1] / "output" / "playwright"


@pytest.mark.parametrize('language', ['es', 'en'])
@pytest.mark.parametrize('width', [390, 1440])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_hero_explains_the_format_change_without_overflow(page, base_url, language, width, theme):
    page.set_viewport_size({'width': width, 'height': 900})
    page.emulate_media(color_scheme=theme, reduced_motion='reduce')
    page.goto(base_url + '/')
    page.locator(f'[data-lang-btn="{language}"]').click()
    mini = page.locator(".example-mini pre")
    pw.expect(mini).to_be_visible()
    compact = mini.inner_text()
    page.locator("#view-mini").focus()
    page.keyboard.press("ArrowRight")
    original = page.locator(".example-json pre")
    pw.expect(original).to_be_visible()
    expected = json.loads(original.inner_text())
    last_field = "titulo" if language == "es" else "title"
    contract = infer_contract([expected], "ticket")
    assert decode_rows(compact, contract, last_text_field=last_field, expected_records=2) == expected
    assert len(compact) < len(original.inner_text())
    assert page.locator(".example-output").is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUTPUT / f'hero-{language}-{theme}-{width}.png'))


def test_landing_leads_to_the_real_recorded_workflow(page, base_url):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.goto(base_url + "/")
    pw.expect(page.locator("h1")).to_contain_text("costar menos")
    assert page.locator('#prueba-tokens').get_attribute('open') is None
    assert page.locator('#flujo-animado').get_attribute('open') is None
    page.screenshot(path=str(OUTPUT / "landing-overview.png"))
    page.locator('#flujo-animado > summary').click()
    page.locator('[data-dv-goto="5"]').click()
    pw.expect(page.locator('[data-dv-cap]')).to_contain_text('El parser entrega')
    pw.expect(page.locator('[data-dv-body]')).to_contain_text('JSON listo para guardar')
    page.locator('[data-dv-toggle]').click()
    page.locator('[data-lang-btn="en"]').click()
    page.locator('#flujo-animado > summary').click()
    page.locator('[data-dv-goto="5"]').click()
    pw.expect(page.locator('[data-dv-cap]')).to_contain_text('The parser returns')
    page.locator('[data-lang-btn="es"]').click()
    page.screenshot(path=str(OUTPUT / "landing-simple-desktop.png"), full_page=True)
    page.locator('.hero a[href="/flujo/"]').click()
    page.locator('#story-run').click()
    pw.expect(page.locator('#story-status')).to_have_text('20 tickets válidos. JSON listo para usar.')
    assert page.locator('#story-steps li').count() == 6
    page.locator('#story-output summary').click()
    data = json.loads(page.locator('#story-json').inner_text())
    assert len(data) == 20 and data[2]['id'] == 3
    page.screenshot(path=str(OUTPUT / "flow-simple-desktop.png"), full_page=True)
    page.reload()
    assert page.locator('#story-runs li').count() == 1
    page.locator('[data-lang-btn="en"]').click()
    page.locator('#story-run').click()
    pw.expect(page.locator('#story-status')).to_have_text('20 valid tickets. JSON ready to use.')


def test_story_on_mobile_with_reduced_motion_and_keyboard(page, base_url):
    page.set_viewport_size({'width':390,'height':844})
    page.emulate_media(reduced_motion='reduce')
    page.goto(base_url + '/flujo/')
    button=page.locator('#story-next')
    for _ in range(6):
        button.focus()
        button.press('Enter')
    pw.expect(page.locator('#story-output')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(OUTPUT / 'flow-simple-mobile.png'), full_page=True)


def test_landing_mobile_has_no_overflow_and_installation_is_copyable(page, base_url):
    page.set_viewport_size({'width':390,'height':844})
    page.goto(base_url + '/')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    pw.expect(page.locator('#instalar .cmd code').last).to_have_text('mini setup')
    page.emulate_media(reduced_motion='reduce')
    page.reload()
    page.locator('#flujo-animado > summary').click()
    page.locator('[data-dv-goto="5"]').click()
    pw.expect(page.locator('[data-dv-body]')).to_contain_text('JSON listo para guardar')
    assert page.locator('#demo-playground').get_attribute('data-playing') != '1'
    page.screenshot(path=str(OUTPUT / 'landing-simple-mobile.png'), full_page=True)


def test_benchmarks_show_one_comparison_and_open_the_linked_measurements(page, base_url):
    page.set_viewport_size({"width": 375, "height": 844})
    page.emulate_media(reduced_motion="reduce")
    page.goto(base_url + "/")
    assert page.locator(".cost-figure").count() == 1
    assert page.locator("table").count() == 0
    pw.expect(page.locator(".cost-figure")).to_contain_text("Costo estimado por 1.000 respuestas correctas")
    page.locator(".proof-actions > a").click()
    assert page.locator(".val-group[open]").count() == 0
    page.locator('a[href="#lotes-texto"]').click()
    pw.expect(page.locator("#lotes-texto table")).to_be_visible()
    assert page.locator(".val-group[open]").count() == 1
    page.goto(base_url + "/validacion/#reparacion-filas")
    pw.expect(page.locator("#reparacion-filas table")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

"""A beginner can read, compare and recover from errors on the actual workbench."""
from pathlib import Path
import json
import pytest
from test_examples_flow import base_url, browser, page, pw

OUTPUT = Path(__file__).resolve().parents[1] / 'output/playwright'


@pytest.mark.parametrize('locale', ['es', 'en'])
def test_editor_comparison_roundtrip_and_error_recovery(page, base_url, locale):
    page.goto(base_url + ('/playground/' if locale == 'es' else '/en/playground/'))
    pw.expect(page.locator('#status')).to_contain_text('10')
    expected = json.loads(page.locator('#jsonText').input_value())
    assert len(expected['records']) == 10
    assert page.locator('#jsonText').input_value().count('\n') < 20
    widths = page.locator('#tab-editor .grid').bounding_box()
    assert widths['width'] > 1250, 'desktop uses the available width'
    for selector in ('#miniText','#jsonText'):
        assert page.locator(selector).evaluate('(e)=>e.scrollWidth <= e.clientWidth + 1')
        assert page.locator(selector).evaluate('(e)=>e.scrollHeight <= e.clientHeight + 1')
    page.locator('#toMini').click()
    assert json.loads(page.locator('#jsonText').input_value()) == expected
    page.locator('[data-tab="compare"]').click()
    assert page.locator('.pg-bar-row').count() == 3
    pw.expect(page.locator('#compareSummary')).to_contain_text('JSON')
    assert page.locator('.compare-details').get_attribute('open') is None
    page.locator('#fmtSel').select_option('json')
    assert json.loads(page.locator('#fmtOut').inner_text()) == expected
    page.locator('.compare-details summary').click()
    assert page.locator('#tokTable tr').count() == 9
    page.locator('[data-tab="editor"]').click()
    page.locator('#jsonText').fill('{bad json')
    page.locator('[data-tab="compare"]').click()
    pw.expect(page.locator('#compareSummary')).to_contain_text('JSON')
    assert page.locator('.pg-bar-row').count() == 0
    page.locator('[data-tab="editor"]').click()
    page.locator('#loadExample').click()
    page.locator('#breakIt').click()
    pw.expect(page.locator('#status')).to_contain_text('incompleta' if locale == 'es' else 'incomplete')
    assert page.locator('#errList li').count() >= 3
    page.locator('#loadExample').click()
    assert json.loads(page.locator('#jsonText').input_value()) == expected
    page.locator('[data-tab="compare"]').click()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUTPUT / f'playground-compare-{locale}.png'))


def test_playground_mobile_and_keyboard_have_clear_states(page, base_url):
    page.set_viewport_size({'width':390,'height':844})
    page.emulate_media(reduced_motion='reduce')
    page.goto(base_url + '/playground/')
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('[data-tab="compare"]').focus()
    page.locator('[data-tab="compare"]').press('Enter')
    assert page.locator('.pg-bar-row').count() == 3
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('.compare-details summary').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('[data-tab="wizard"]').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(OUTPUT / 'playground-mobile.png'))

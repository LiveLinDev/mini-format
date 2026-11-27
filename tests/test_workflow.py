"""Application-level proofs: exact JSON, preserved lines and blocked bad data."""
import importlib.util
import asyncio
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from minifmt.domain import build_bundle, decode, encode
from minifmt.integration import prepare
from minifmt.workflow import Workflow, WorkflowError
from test_onboarding import _wizard


@pytest.fixture
def kit(tmp_path):
    sample = [{"id": 1, "titulo": "Acceso"}, {"id": 2, "titulo": "Factura"}]
    bundle = tmp_path / ".mini"
    contract = build_bundle([sample], "ticket", bundle)
    return bundle, contract, sample


def test_selective_repair_preserves_good_lines_and_returns_exact_json(kit):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    lines = valid.splitlines()
    raw = "```mini\r\n" + valid.replace("2|Factura", "dos|Factura").replace("\n", "\r\n") + "\r\n```"
    prompts = []
    def generate(prompt):
        prompts.append(prompt)
        return raw if len(prompts) == 1 else json.dumps({"3": lines[2]})
    flow = Workflow(bundle)
    assert flow.run(generate, "Classify support", expected_records=2) == sample
    assert flow.last_run["mini"] == valid
    assert len(prompts) == 2 and "prompt" not in flow.last_run
    assert "Classify support" in prompts[1] and contract["schema_id"] in prompts[1]
    assert flow.last_run["trace"][2]["changes"] == ["normalized CRLF to LF", "removed complete Markdown code fence"]


def test_missing_records_are_blocked_without_changing_count(kit):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    wire = encode(sample[:1], contract)
    calls = []
    def generate(prompt):
        calls.append(prompt)
        return wire
    with pytest.raises(WorkflowError):
        flow.run(generate, "Need two", expected_records=2)
    assert len(calls) == 2
    assert not flow.last_run["ok"] and "data" not in flow.last_run
    assert flow.last_run["diagnostics"]["errors"][0]["code"] == "D_EXPECTED_COUNT"


def test_surplus_separator_is_repaired_without_an_additional_model_call(kit):
    bundle, contract, sample = kit
    canonical = encode(sample, contract, shared=False, dictionaries=False)
    calls = []
    flow = Workflow(bundle)
    output = flow.run(lambda prompt: calls.append(prompt) or canonical + "|", "Clasifica", expected_records=2)
    assert output == sample and len(calls) == 1
    assert flow.last_run["mini"] == canonical
    assert "separadores finales sobrantes eliminados" in flow.summary()


@pytest.mark.parametrize("bundle_can_reuse_value", [True, False])
def test_workflow_reuses_the_validated_value_when_available(kit, monkeypatch, bundle_can_reuse_value):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    wire = encode(sample, contract, shared=False, dictionaries=False)
    decode_calls = []
    decode_document = flow.runtime._decode

    def counted_decode(text, contract, **options):
        decode_calls.append(text)
        return decode_document(text, contract, **options)

    monkeypatch.setattr(flow.runtime, "_decode", counted_decode)
    if not bundle_can_reuse_value:
        flow.runtime = SimpleNamespace(repair=flow.runtime.repair, decode=flow.runtime.decode)

    assert flow.process(wire, expected_records=len(sample)) == sample
    assert flow.last_run["mini"] == wire
    assert decode_calls == [wire] * (1 if bundle_can_reuse_value else 2)


def test_workflow_accepts_complete_json_under_the_contract(kit, tmp_path):
    bundle, contract, sample = kit
    raw = "\ufeff```json\r\n" + json.dumps(sample) + "\r\n```"
    calls = []
    flow = Workflow(bundle)

    assert flow.run(lambda prompt: calls.append(prompt) or raw, "Clasifica", expected_records=2) == sample
    assert len(calls) == 1
    assert decode(flow.last_run["mini"], contract) == sample
    assert "JSON validado convertido a .mini" in flow.summary()
    saved = flow.save_run(tmp_path / "historial")
    assert (saved / "respuesta_1.json").read_bytes() == raw.encode("utf-8")
    assert decode((saved / "resultado.mini").read_text(encoding="utf-8"), contract) == sample

    malformed = (
        '[{"id":1,"id":2,"titulo":"Acceso"},{"id":2,"titulo":"Factura"}]',
        json.dumps(sample[:1]),
        json.dumps([dict(sample[0], id=True), sample[1]]),
        raw + "\nFin.",
    )
    for response in malformed:
        with pytest.raises(WorkflowError):
            flow.process(response, expected_records=2, max_repairs=0)
    with pytest.raises(WorkflowError):
        flow.process(raw, expected_records=2, max_repairs=0, truncated=True)


def test_node_workflow_accepts_complete_json_under_the_contract(kit, tmp_path):
    bundle, _, sample = kit
    script = tmp_path / "fallback-json.mjs"
    script.write_text(f"""import {{ Workflow }} from {json.dumps((bundle / 'workflow.mjs').as_uri())};
const flow = new Workflow({{python: {json.dumps(sys.executable)}}});
const data = await flow.run(async () => JSON.stringify({json.dumps(sample)}), 'Clasifica',
  {{expectedRecords: 2, maxRepairs: 0}});
console.log(JSON.stringify({{data, source: flow.lastRun.trace[0].reply_format}}));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"data": sample, "source": "json"}


def test_compact_workflow_retries_and_saves_canonical_document(kit, tmp_path):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    calls = []
    replies = iter(["1 Acceso", "1 Acceso\n\n2 Factura"])
    result = flow.run(lambda prompt: calls.append(prompt) or next(replies), "Clasifica",
                      expected_records=2, last_text_field="titulo")
    assert result == sample
    assert len(calls) == 2 and contract["schema_id"] not in calls[0]
    assert "expected 2 records, received 1" in calls[1]
    assert decode(flow.last_run["mini"], contract) == sample
    saved = flow.save_run(tmp_path / "compact-run")
    assert (saved / "respuesta_2.txt").read_text(encoding="utf-8") == "1 Acceso\n\n2 Factura"
    assert decode((saved / "resultado.mini").read_text(encoding="utf-8"), contract) == sample
    with pytest.raises(WorkflowError):
        flow.run(lambda _: "uno Acceso\n2 Factura", "Clasifica",
                 expected_records=2, last_text_field="titulo", max_repairs=0)
    assert "data" not in flow.last_run


def test_node_compact_workflow_uses_the_same_schema_and_repairs(kit, tmp_path):
    bundle, _, sample = kit
    script = tmp_path / "compact.mjs"
    script.write_text(f"""import {{ Workflow }} from {json.dumps((bundle / 'workflow.mjs').as_uri())};
const flow = new Workflow({{lang: 'es', python: {json.dumps(sys.executable)}}});
const prompts = [];
const replies = ['1 Acceso', '1 Acceso\\n2 Factura'];
const data = await flow.run(async prompt => {{ prompts.push(prompt); return replies.shift(); }},
  'Clasifica', {{expectedRecords: 2, lastTextField: 'titulo'}});
console.log(JSON.stringify({{data, prompts, mini: flow.lastRun.mini}}));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["data"] == sample and len(output["prompts"]) == 2
    assert "2 fila(s)" in output["prompts"][0] and "received 1" in output["prompts"][1]
    assert output["mini"].startswith("ticket|v=1|")


def test_positional_workflow_repairs_types_with_the_provider_schema(kit, tmp_path):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    calls = []
    replies = iter(['[[true,"Acceso"],[2,"Factura"]]', '[[1,"Acceso"],[2,"Factura"]]'])

    def generate(prompt, schema):
        calls.append((prompt, schema))
        return next(replies)

    assert flow.run_positional(generate, "Clasifica", expected_records=2) == sample
    assert len(calls) == 2 and calls[0][1] == calls[1][1]
    assert "id, titulo" in calls[0][0] and "expected integer" in calls[1][0]
    schema = calls[0][1]
    assert schema["minItems"] == schema["maxItems"] == 2
    assert schema["items"]["prefixItems"] == [{"type": "integer"}, {"type": "string"}]
    assert decode(flow.last_run["mini"], contract) == sample
    assert (flow.save_run(tmp_path / "positional") / "respuesta_2.json").is_file()

    with pytest.raises(WorkflowError) as error:
        flow.run_positional(lambda *_: '[[1,"Acceso"]]', "Clasifica", expected_records=2, max_repairs=0)
    assert error.value.report["diagnostics"]["errors"][0]["code"] == "D_EXPECTED_COUNT"
    assert "data" not in flow.last_run


def test_positional_workflow_closes_the_outer_array_only_after_all_rows(kit):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    wire = '[[1,"Acceso"],[2,"Factura"]'
    assert flow.run_positional(lambda *_: wire, "Clasifica", expected_records=2, max_repairs=0) == sample
    assert "array JSON posicional cerrado" in flow.summary()
    assert flow.last_run["trace"][0]["text"] == wire
    assert decode(flow.last_run["mini"], contract) == sample

    for malformed in (wire[:-1], wire + ",", '[[1,"Acceso"]', '[[true,"Acceso"],[2,"Factura"]'):
        with pytest.raises(WorkflowError):
            flow.run_positional(lambda *_: malformed, "Clasifica", expected_records=2, max_repairs=0)


def test_positional_workflow_unwraps_one_complete_json_fence(kit):
    bundle, contract, sample = kit
    flow = Workflow(bundle)
    wire = '[[1,"Acceso"],[2,"Factura"]]'
    fenced = "```JSON\r\n" + wire + "\r\n```"
    assert flow.run_positional(lambda *_: fenced, "Clasifica", expected_records=2, max_repairs=0) == sample
    assert "bloque Markdown eliminado" in flow.summary()
    assert flow.last_run["trace"][0]["text"] == fenced
    assert decode(flow.last_run["mini"], contract) == sample

    for malformed in (fenced + "\nFin.", fenced + "\n" + fenced, fenced[:-3], fenced.replace("JSON", "toon")):
        with pytest.raises(WorkflowError):
            flow.run_positional(lambda *_: malformed, "Clasifica", expected_records=2, max_repairs=0)


def test_positional_workflow_removes_only_a_transport_bom(kit):
    bundle, _, sample = kit
    flow = Workflow(bundle)
    wire = '[[1,"\ufeffAcceso"],[2,"Factura"]]'
    expected = [dict(sample[0], titulo="\ufeffAcceso"), sample[1]]
    response = "\ufeff" + wire

    assert flow.run_positional(lambda *_: response, "Clasifica", expected_records=2, max_repairs=0) == expected
    assert "BOM eliminado" in flow.summary()
    assert flow.last_run["trace"][0]["text"] == response

    for malformed in ("\ufeff" + response, " " + response, "\ufeff[[true,\"Acceso\"],[2,\"Factura\"]]"):
        with pytest.raises(WorkflowError):
            flow.run_positional(lambda *_: malformed, "Clasifica", expected_records=2, max_repairs=0)


def test_node_positional_workflow_uses_the_same_schema_on_retry(kit, tmp_path):
    bundle, _, sample = kit
    script = tmp_path / "positional.mjs"
    script.write_text(f"""import {{ Workflow }} from {json.dumps((bundle / 'workflow.mjs').as_uri())};
const flow = new Workflow({{lang: 'es', python: {json.dumps(sys.executable)}}});
const calls = [];
const replies = ['[[1,"Acceso"]]', '\\uFEFF```json\\n[[1,"Acceso"],[2,"Factura"]\\n```'];
const data = await flow.runPositional(async (prompt, schema) => {{
  calls.push({{prompt, schema}}); return replies.shift();
}}, 'Clasifica', {{expectedRecords: 2}});
console.log(JSON.stringify({{data, calls, report: flow.lastRun}}));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["data"] == sample and output["report"]["positional_json"] is True
    assert any(step.get("changes") == ["removed UTF-8 BOM", "removed complete Markdown code fence", "closed positional JSON array"]
               for step in output["report"]["trace"])
    first, second = output["calls"]
    assert first["schema"] == second["schema"]
    assert "id, titulo" in first["prompt"] and "received 1" in second["prompt"]


def test_generated_compact_cli_uses_utf8_in_isolated_python(kit):
    bundle, _, _ = kit
    output = subprocess.run(
        [sys.executable, "-I", str(bundle / "workflow.py"), "-", "--last-text-field", "titulo", "--expected-records", "2"],
        input="1 Cambiar dirección\n2 Niño con acceso 🌊", capture_output=True, text=True, encoding="utf-8",
    )
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout) == [{"id": 1, "titulo": "Cambiar dirección"}, {"id": 2, "titulo": "Niño con acceso 🌊"}]


def test_repair_cannot_replace_valid_lines(kit):
    bundle, contract, sample = kit
    wire = encode(sample, contract, shared=False, dictionaries=False)
    replies = iter([wire.replace("2|Factura", "dos|Factura"), json.dumps({"2": "1|Alterado", "3": "2|Factura"})])
    flow = Workflow(bundle)
    with pytest.raises(WorkflowError):
        flow.run(lambda _: next(replies), "Classify")
    assert "data" not in flow.last_run
    assert flow.last_run["diagnostics"]["errors"][0]["code"] == "D_REPAIR"


def test_full_model_correction_preserves_validated_lines_and_history(kit, tmp_path):
    bundle, contract, data = kit
    wire = encode(data, contract, shared=False, dictionaries=False)
    wrong = wire.replace("\n1|", "\nuno|")
    flow = Workflow(bundle)
    assert flow.process(wrong, generate=lambda _: wire, expected_records=2) == data
    assert flow.last_run["mini"] == wire
    assert next(step for step in flow.last_run["trace"] if step["stage"] == "model_repair")["reply_format"] == "mini"
    saved = flow.save_run(tmp_path / "full-correction")
    assert (saved / "respuesta_2.mini").read_text(encoding="utf-8") == wire
    for modified in (wire.replace("Factura", "Modificado"), wire.replace("|v=1|n=2|", "|n=2|v=1|")):
        with pytest.raises(WorkflowError):
            flow.process(wrong, generate=lambda _: modified, expected_records=2)
        assert "validated row" in flow.last_run["diagnostics"]["errors"][0]["message"]


def test_full_model_correction_requires_terminator_for_last_invalid_row(kit):
    bundle, contract, data = kit
    wire = encode(data, contract, shared=False, dictionaries=False)
    wrong = wire.replace("\n2|", "\ndos|")
    flow = Workflow(bundle)
    with pytest.raises(WorkflowError):
        flow.process(wrong, generate=lambda _: wire, expected_records=2)
    assert "terminate" in flow.last_run["diagnostics"]["errors"][0]["message"]
    assert flow.process(wrong, generate=lambda _: wire + "\n", expected_records=2) == data
    assert flow.process(wrong, generate=lambda _: "```mini\n" + wire + "\n```", expected_records=2) == data


def test_generated_cli_runs_under_isolated_python_without_package(kit, tmp_path):
    bundle, contract, sample = kit
    wire = "```mini\n" + encode(sample, contract) + "\n```"
    result = subprocess.run([sys.executable, "-I", str(bundle / "workflow.py"), "-", "--expected-records", "2"],
                            input=wire, text=True, encoding="utf-8", capture_output=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == sample
    bad = subprocess.run([sys.executable, "-I", str(bundle / "workflow.py"), "-", "--out", str(tmp_path / "bad.json")],
                         input="ticket|n=20\n", text=True, encoding="utf-8", capture_output=True, cwd=tmp_path)
    assert bad.returncode == 1 and not (tmp_path / "bad.json").exists()


def test_auto_integration_executes_original_sdk_callback_and_removes_json_mode(kit, tmp_path):
    bundle, contract, sample = kit
    source = tmp_path / "app.py"
    source.write_text('import json\ndef get_tickets(client):\n    response = client.chat.completions.create(model="existing", messages=[{"role":"user","content":"Extract tickets"}], response_format={"type":"json_object"})\n    data = json.loads(response.choices[0].message.content)\n    return data\n', encoding="utf-8")
    original = source.read_bytes()
    prepared = prepare(source, bundle)
    assert prepared["supported"] and not prepared["applied"] and source.read_bytes() == original
    applied = prepare(source, bundle, apply=True)
    assert applied["applied"] and Path(applied["backup"]).read_bytes() == original
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        text = "```mini\n" + encode(sample, contract) + "\n```"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    sys.path.insert(0, str(tmp_path))
    try:
        spec = importlib.util.spec_from_file_location("patched_app", source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        assert module.get_tickets(client) == sample
    finally:
        sys.path.remove(str(tmp_path))
    assert len(calls) == 1 and calls[0]["model"] == "existing"
    assert "response_format" not in calls[0]
    assert calls[0]["messages"][0]["content"] == "Extract tickets"
    assert contract["schema_id"] in calls[0]["messages"][-1]["content"]


def test_unsupported_application_is_untouched_and_gets_a_real_plan(kit, tmp_path):
    bundle, _, _ = kit
    source = tmp_path / "app.ts"
    source.write_text('const data = JSON.parse(await provider.generateContent(task));', encoding="utf-8")
    original = source.read_bytes()
    report = prepare(source, bundle, lang="en")
    plan = Path(report["plan"]).read_text(encoding="utf-8")
    assert str(source) in plan and str(bundle / "prompt.en.md") in plan
    assert not report["supported"] and source.read_bytes() == original
    with pytest.raises(ValueError, match="automatic patch unavailable"):
        prepare(source, bundle, apply=True)
    assert source.read_bytes() == original


def test_english_setup_selects_english_prompt_and_prepares_integration(tmp_path):
    source = tmp_path / "app.ts"
    source.write_text("const data = JSON.parse(response);", encoding="utf-8")
    bundle = tmp_path / "toolkit"
    code, output = _wizard(["en", "4", "ticket", str(bundle), "2", str(source)])
    assert code == 0 and "Toolkit created" in output
    assert Workflow(bundle).lang == "en"
    prompt = (bundle / "try-prompt.md").read_text(encoding="utf-8")
    assert "Generate exactly 20" in prompt and Workflow(bundle).contract["schema_id"] in prompt
    assert "Integrate .mini" in (bundle / "integration/INTEGRATE.md").read_text(encoding="utf-8")
    # A later integration command keeps the language chosen at setup.
    assert "Integrate .mini" in Path(prepare(source, bundle)["plan"]).read_text(encoding="utf-8")


def test_recorded_20_ticket_run_is_reproducible():
    path = ROOT / "examples/flujo-soporte/run.py"
    spec = importlib.util.spec_from_file_location("support_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    live_replay = module.execute()
    saved = json.loads((path.parent / "history.json").read_text(encoding="utf-8"))
    assert live_replay == saved and len(saved["data"]) == 20


def test_async_python_callback_uses_the_same_repair_pipeline(kit):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    replies = iter([valid.replace("2|Factura", "dos|Factura"), json.dumps({"3": valid.splitlines()[2]})])
    async def generate(prompt):
        await asyncio.sleep(0)
        return next(replies)
    flow = Workflow(bundle)
    assert asyncio.run(flow.run_async(generate, "Classify", expected_records=2)) == sample
    assert flow.last_run["ok"]


def test_node_async_provider_repairs_and_returns_exact_json(kit, tmp_path):
    bundle, contract, sample = kit
    valid = encode(sample, contract, shared=False, dictionaries=False)
    script = tmp_path / "app.mjs"
    script.write_text(f"""import {{ Workflow }} from {json.dumps((bundle / 'workflow.mjs').as_uri())};
const replies = [{json.dumps(valid.replace('2|Factura', 'dos|Factura'))}, {json.dumps(json.dumps({'3':valid.splitlines()[2]}))}];
const flow = new Workflow({{python: {json.dumps(sys.executable)}}});
const data = await flow.run(async prompt => replies.shift(), 'Classify', {{expectedRecords:2}});
if (replies.length !== 0 || !flow.lastRun.ok) throw Error('repair did not run');
console.log(JSON.stringify(data));
""", encoding="utf-8")
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == sample


def test_auto_patch_rejects_shared_line_statements(kit, tmp_path):
    bundle, _, _ = kit
    source = tmp_path / "app.py"
    source.write_text('import json\ndef fetch(client):\n    response = client.chat.completions.create(model="x", messages=[])\n    data = json.loads(response.choices[0].message.content); use(data)\n', encoding="utf-8")
    original = source.read_bytes()
    assert not prepare(source, bundle)["supported"]
    assert source.read_bytes() == original


def test_live_example_uses_the_prompt_and_never_stores_the_key(monkeypatch):
    path = ROOT / "examples/flujo-soporte/run.py"
    spec = importlib.util.spec_from_file_location("support_live_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = path.parent
    from minifmt.domain import infer_contract
    data = json.loads((base / "expected.json").read_text(encoding="utf-8"))
    wire = encode(data, infer_contract([data], "ticket"))
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"choices":[{"message":{"content":wire}}]}).encode()
    requests = []
    def open_request(request, **kwargs):
        requests.append(request)
        return Response()
    monkeypatch.setattr(module.urllib.request, "urlopen", open_request)
    report = module.execute(key="fixture-key-keep-in-memory", model="fixture-model")
    assert report["mode"] == "live" and len(report["data"]) == 20
    assert "fixture-key" not in json.dumps(report)
    assert requests[0].full_url == "https://api.openai.com/v1/chat/completions"
    payload = json.loads(requests[0].data)
    assert payload["model"] == "fixture-model" and "20 mensajes" in payload["messages"][0]["content"]
    assert "mini-domain/1" in payload["messages"][0]["content"]


def _support_module(name):
    path = ROOT / "examples/flujo-soporte/run.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path.parent


class _ChatResponse:
    def __init__(self, content, finish="stop", usage=None):
        self.body = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": finish}],
                                "usage": usage or {"prompt_tokens": 100, "completion_tokens": 50}}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return self.body


def test_live_from_environment_switches_provider_without_code_changes(monkeypatch, tmp_path, capsys):
    module, base = _support_module("support_live_env")
    from minifmt.domain import infer_contract
    data = json.loads((base / "expected.json").read_text(encoding="utf-8"))
    wire = encode(data, infer_contract([data], "ticket"))
    requests = []

    def open_request(request, **kwargs):
        requests.append(request)
        return _ChatResponse(wire)
    monkeypatch.setattr(module.urllib.request, "urlopen", open_request)
    monkeypatch.setenv("MINI_IA_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("MINI_IA_MODEL", "modelo-abierto")
    monkeypatch.setenv("MINI_IA_KEY", "clave-de-prueba-en-memoria")
    monkeypatch.setenv("MINI_IA_CABECERA", "X-API-Key")
    monkeypatch.setenv("MINI_IA_EXTRA", '{"temperature": 0}')
    history = module.live_from_environment(str(tmp_path), "mini", 900)
    assert history["ok"] and len(history["data"]) == 20 and history["format"] == "mini"
    assert requests[0].full_url == "http://127.0.0.1:9/v1/chat/completions"
    assert requests[0].get_header("X-api-key") == "clave-de-prueba-en-memoria"
    payload = json.loads(requests[0].data)
    assert payload["model"] == "modelo-abierto" and payload["max_tokens"] == 900 and payload["temperature"] == 0
    assert history["calls"][0]["output_tokens"] == 50 and history["calls"][0]["finish_reason"] == "stop"
    saved = (tmp_path / "history.json").read_text(encoding="utf-8") + (tmp_path / "respuesta_1.mini").read_text(encoding="utf-8")
    assert "clave-de-prueba" not in saved and "clave-de-prueba" not in capsys.readouterr().out


def test_live_json_reader_loses_a_cut_answer_and_mini_keeps_complete_records(monkeypatch, tmp_path):
    module, base = _support_module("support_live_cut")
    from minifmt.domain import infer_contract
    data = json.loads((base / "expected.json").read_text(encoding="utf-8"))
    as_json = json.dumps(data, ensure_ascii=False)
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, **k: _ChatResponse(as_json[:300], "length"))
    history = module.execute(live=True, formato="json", max_tokens=80, out=tmp_path / "json")
    assert history["ok"] is False and history["data"] is None and "JSONDecodeError" in history["error"]
    wire = encode(data, infer_contract([data], "ticket"))
    lines = wire.splitlines()
    cut = "\n".join(lines[:9]) + "\n" + lines[9][:5]                 # header + 8 complete records + a cut line
    rest = encode(data[8:], infer_contract([data], "ticket"))
    answers = iter([_ChatResponse(cut, "length"), _ChatResponse(rest)])
    monkeypatch.setattr(module.urllib.request, "urlopen", lambda request, **k: next(answers))
    history = module.execute(live=True, formato="mini", max_tokens=80, out=tmp_path / "mini")
    assert history["ok"] and history["data"] == data
    assert [c["finish_reason"] for c in history["calls"]] == ["length", "stop"]
    assert any(step.get("stage") == "truncation" and step["complete_records"] == 8 for step in history["trace"])


# ---------------------------------------------------------------- HTTP chat calls (requests/httpx) and cut responses
HTTP_APP = '''"""Generator that already asks an OpenAI-compatible chat endpoint for JSON."""
import json
import requests

URL = "https://api.deepseek.com/chat/completions"


def call_model(prompt, max_tokens):
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": "Return only valid JSON."}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    response = requests.post(URL, headers={"Authorization": "Bearer key"}, json=payload, timeout=180)
    if response.status_code >= 400:
        raise RuntimeError("API error " + str(response.status_code))
    return response.json()


def other_call(prompt):
    return requests.post("https://api.example.com/v1/responses", json={"input": prompt}).json()


def tickets(prompt, max_tokens=900):
    raw = call_model(prompt, max_tokens)
    return json.loads(raw["choices"][0]["message"]["content"]), raw["usage"]
'''


class _HttpReply:
    def __init__(self, body, status_code=200):
        self.body, self.status_code = body, status_code

    def json(self):
        return self.body


def _fake_requests(monkeypatch, replies):
    """Install a fake ``requests`` module: each reply is (content, finish_reason) or an _HttpReply."""
    import types
    sent = []

    def post(url, json=None, **kwargs):
        sent.append({"url": url, "json": json, **kwargs})
        reply = replies.pop(0)
        if isinstance(reply, _HttpReply):
            return reply
        content, finish = reply
        return _HttpReply({"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                           "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}})
    module = types.ModuleType("requests")
    module.post = post
    monkeypatch.setitem(sys.modules, "requests", module)
    return sent


def _load(source, name):
    spec = importlib.util.spec_from_file_location(name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def kit4(tmp_path):
    sample = {"lote": "L1", "tickets": [{"id": i, "titulo": t} for i, t in enumerate(["Acceso", "Factura", "Clave", "Pago"], 1)]}
    bundle = tmp_path / ".mini"
    contract = build_bundle([sample], "ticket", bundle)
    return bundle, contract, sample


def test_complete_continuation_uses_only_the_suffix_after_a_matching_prefix(kit4):
    bundle, contract, sample = kit4
    wire = encode(sample, contract, shared=False, dictionaries=False)
    cut = "\n".join(wire.split("\n")[:3]) + "\n"
    flow = Workflow(bundle)
    calls = []
    assert flow.process(cut, generate=lambda prompt: calls.append(prompt) or wire,
                        expected_records=4, truncated=True) == sample
    assert len(calls) == 1 and "2 of 4 records" in calls[0]
    assert {"stage": "continuation_overlap", "records": 2} in flow.last_run["trace"]


@pytest.mark.parametrize("difference", ["retained_row", "metadata", "record_count"])
@pytest.mark.parametrize("correct_second_reply", [False, True])
def test_oversized_continuation_rejects_unanchored_rows(kit4, difference, correct_second_reply):
    bundle, contract, sample = kit4
    wire = encode(sample, contract, shared=False, dictionaries=False)
    cut = "\n".join(wire.split("\n")[:3]) + "\n"
    other = dict(sample, tickets=[dict(row) for row in sample["tickets"]])
    if difference == "retained_row":
        other["tickets"][0]["titulo"] = "Dato cambiado"
    elif difference == "metadata":
        other["lote"] = "Otro lote"
    else:
        other["tickets"].append({"id": 5, "titulo": "Sobra"})
    invalid = encode(other, contract, shared=False, dictionaries=False)
    missing = encode(dict(sample, tickets=sample["tickets"][2:]), contract, shared=False, dictionaries=False)
    calls = []
    replies = iter([invalid, missing if correct_second_reply else invalid])
    flow = Workflow(bundle)

    def model(prompt):
        calls.append(prompt)
        return next(replies)

    if correct_second_reply:
        assert flow.process(cut, generate=model, expected_records=4, truncated=True) == sample
    else:
        with pytest.raises(WorkflowError):
            flow.process(cut, generate=model, expected_records=4, truncated=True)
        assert "data" not in flow.last_run
    assert len(calls) == 2
    assert any(step["stage"] == "continuation_rejected" for step in flow.last_run["trace"])


def test_continuation_with_the_requested_count_preserves_legitimate_duplicates(kit4):
    bundle, contract, sample = kit4
    row = sample["tickets"][1]
    value = dict(sample, tickets=[*sample["tickets"][:2], row, sample["tickets"][3]])
    wire = encode(value, contract, shared=False, dictionaries=False)
    cut = "\n".join(wire.split("\n")[:3]) + "\n"
    rest = encode(dict(value, tickets=value["tickets"][2:]), contract, shared=False, dictionaries=False)
    flow = Workflow(bundle)
    assert flow.process(cut, generate=lambda _: rest, expected_records=4, truncated=True) == value


def test_restarted_continuation_preserves_json_number_types_in_metadata(kit4, tmp_path):
    _, _, sample = kit4
    data = dict(sample, ratio=1.0)
    bundle = tmp_path / ".numbers"
    contract = build_bundle([data], "ticket", bundle)
    wire = encode(data, contract, shared=False, dictionaries=False)
    cut = "\n".join(wire.split("\n")[:3]) + "\n"
    wrong = encode(dict(data, ratio=1), contract, shared=False, dictionaries=False)
    replies = iter([wrong, wire])
    flow = Workflow(bundle)
    result = flow.process(cut, generate=lambda _: next(replies), expected_records=4, truncated=True)
    assert type(result["ratio"]) is float and result == data
    assert any(step["stage"] == "continuation_rejected" for step in flow.last_run["trace"])


def test_http_chat_json_call_is_patched_with_one_changed_call(kit4, tmp_path, monkeypatch):
    bundle, contract, sample = kit4
    source = tmp_path / "generator.py"
    source.write_bytes(HTTP_APP.replace("\n", "\r\n").encode("utf-8"))
    original = source.read_bytes()
    prepared = prepare(source, bundle)
    assert prepared["supported"] and prepared["pattern"] == "requests-chat-json" and source.read_bytes() == original
    changed = [l for l in Path(prepared["diff"]).read_text(encoding="utf-8").splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert len(changed) == 3  # one import added, one call replaced
    applied = prepare(source, bundle, apply=True)
    assert applied["applied"] and Path(applied["backup"]).read_bytes() == original
    assert b"\n" not in source.read_bytes().replace(b"\r\n", b"")  # line endings preserved
    sent = _fake_requests(monkeypatch, [(encode(sample, contract, shared=False, dictionaries=False), "stop"), ("plain", "stop")])
    monkeypatch.syspath_prepend(str(tmp_path))
    app = _load(source, "patched_generator")
    data, usage = app.tickets("Create four tickets")
    assert data == sample and usage["completion_tokens"] == 10
    assert len(sent) == 1 and "response_format" not in sent[0]["json"]
    assert sent[0]["headers"] == {"Authorization": "Bearer key"} and sent[0]["timeout"] == 180
    assert sent[0]["json"]["messages"][:2] == [{"role": "system", "content": "Return only valid JSON."},
                                                {"role": "user", "content": "Create four tickets"}]
    assert contract["schema_id"] in sent[0]["json"]["messages"][-1]["content"]
    # The bridge keeps the model answer and the validated document for inspection with the mini CLI.
    run = bundle / "ultima_ejecucion"
    assert (run / "respuesta_1.mini").read_text(encoding="utf-8") == encode(sample, contract, shared=False, dictionaries=False)
    assert Workflow(bundle).runtime.diagnose((run / "resultado.mini").read_text(encoding="utf-8"), contract)["ok"]
    # Requests that are not JSON-mode chat calls go through unchanged.
    assert app.other_call("hi")["choices"][0]["message"]["content"] == "plain" and sent[1]["json"] == {"input": "hi"}


def test_cut_response_keeps_complete_records_and_requests_only_the_missing_ones(kit4, monkeypatch, tmp_path):
    bundle, contract, sample = kit4
    lines = encode(sample, contract, shared=False, dictionaries=False).split("\n")
    cut = "```mini\n" + "\n".join(lines[:3]) + "\n" + lines[3][:4]  # header + 2 records + a broken third; fence never closed
    rest = encode(dict(sample, tickets=sample["tickets"][2:]), contract, shared=False, dictionaries=False)
    sent = _fake_requests(monkeypatch, [(cut, "length"), (rest, "stop")])
    flow = Workflow(bundle)
    response = flow.post(sys.modules["requests"].post, "https://api.deepseek.com/chat/completions",
                         json={"model": "m", "messages": [{"role": "user", "content": "four tickets"}], "response_format": {"type": "json_object"}})
    body = response.json()
    assert json.loads(body["choices"][0]["message"]["content"]) == sample
    assert body["usage"] == {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220}
    assert len(sent) == 2 and "CONTINUATION REQUEST" in sent[1]["json"]["messages"][-1]["content"]
    assert "n=2" in sent[1]["json"]["messages"][-1]["content"]
    stages = [step["stage"] for step in flow.last_run["trace"]]
    assert "truncation" in stages and "continuation" in stages
    assert "removed unclosed Markdown code fence" in flow.last_run["trace"][2]["changes"]
    assert "2 conservados y 2 pedidos de nuevo" in response.mini_summary and "20 tokens de salida en 2 llamada(s)" in response.mini_summary
    saved = flow.save_run(tmp_path / "run")
    assert sorted(p.name for p in saved.iterdir()) == ["ejecucion.json", "respuesta_1.mini", "respuesta_2.mini", "resultado.mini"]
    assert (saved / "respuesta_1.mini").read_text(encoding="utf-8") == cut
    final = (saved / "resultado.mini").read_text(encoding="utf-8")
    assert final == encode(sample, contract, shared=False, dictionaries=False) + "\n"


@pytest.mark.parametrize("mapping_response", [False, True])
def test_sdk_length_signal_recovers_a_cut_field_that_still_parses(kit4, mapping_response):
    bundle, contract, sample = kit4
    flow = Workflow(bundle)
    wire = encode(sample, contract, shared=False, dictionaries=False)
    cut = wire[:-1]
    assert flow.runtime.decode(cut, contract)["tickets"][-1]["titulo"] == "Pag"
    rest = encode(dict(sample, tickets=sample["tickets"][-1:]), contract, shared=False, dictionaries=False)
    replies = iter([(cut, "length"), (rest, "stop")])
    prompts = []

    def create(**kwargs):
        prompts.append(kwargs["messages"][-1]["content"])
        text, finish_reason = next(replies)
        if mapping_response:
            return {"choices": [{"message": {"content": text}, "finish_reason": finish_reason}]}
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text),
                                                        finish_reason=finish_reason)])

    assert flow.complete(create, messages=[{"role": "user", "content": "four tickets"}]) == sample
    assert len(prompts) == 2 and "Return ONLY the 1 missing records" in prompts[1]


def test_text_callback_cut_is_inferred_from_a_short_last_line(kit4):
    bundle, contract, sample = kit4
    lines = encode(sample, contract, shared=False, dictionaries=False).split("\n")
    rest = encode(dict(sample, tickets=sample["tickets"][3:]), contract, shared=False, dictionaries=False)
    replies = ["\n".join(lines[:4]) + "\n" + lines[4][:1], rest]  # the last record lost its separator and fields
    prompts = []
    flow = Workflow(bundle)
    assert flow.run(lambda p: prompts.append(p) or replies.pop(0), "four tickets", expected_records=4) == sample
    assert len(prompts) == 2 and "Return ONLY the 1 missing records" in prompts[1]


def test_short_response_without_cut_is_still_blocked(kit4):
    bundle, contract, sample = kit4
    short = encode(dict(sample, tickets=sample["tickets"][:3]), contract, shared=False, dictionaries=False)
    calls = []
    with pytest.raises(WorkflowError):
        Workflow(bundle).run(lambda p: calls.append(p) or short, "four tickets", expected_records=4)
    assert len(calls) == 2  # one full regeneration, as before: a complete short document is not a cut


def test_http_errors_are_returned_unchanged(kit4, monkeypatch):
    bundle, _, _ = kit4
    error = _HttpReply({"error": "bad key"}, status_code=401)
    _fake_requests(monkeypatch, [error])
    response = Workflow(bundle).post(sys.modules["requests"].post, "u", json={"messages": [], "response_format": {"type": "json_object"}})
    assert response is error
